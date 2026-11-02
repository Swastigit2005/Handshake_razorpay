"""Merchant-side client for the Handshake /v1 API.

Standard library only, so it drops into any Python shop without a dependency
review. The one rule it is built around: **instrumentation must never slow down
or break checkout.** `track()` puts the event on a bounded in-memory queue and
returns immediately; a daemon thread batches and sends. If Handshake is down,
events are retried with backoff, then dropped and counted — never raised into
the merchant's request path.
"""

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid

log = logging.getLogger("handshake.sdk")

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def urllib_transport(method, url, body, headers, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:
        log.debug("handshake transport error: %s", exc)
        return 0, b""


class HandshakeError(RuntimeError):
    def __init__(self, status, body):
        self.status, self.body = status, body
        msg = (body or {}).get("error", {}).get("message") if isinstance(body, dict) else body
        super().__init__(f"Handshake API {status}: {msg}")


class HandshakeClient:
    def __init__(self, api_key, base_url=DEFAULT_BASE_URL, *, flush_interval=0.5,
                 batch_size=200, max_queue=10000, timeout=5.0, max_retries=5,
                 transport=None, start=True):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.flush_interval = flush_interval
        self.batch_size = min(batch_size, 500)
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport or urllib_transport
        self._q = queue.Queue(maxsize=max_queue)
        self._inflight = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.stats = {"queued": 0, "sent": 0, "dropped": 0, "failed": 0, "retries": 0,
                      "duplicates": 0, "rejected": 0}
        if start:
            self.start()

    # --------------------------------------------------------- plumbing ---

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json", "User-Agent": "handshake-python/1"}

    def request(self, method, path, body=None):
        """Synchronous call. Raises HandshakeError on a non-2xx response."""
        data = json.dumps(body, default=str).encode() if body is not None else None
        status, raw = self.transport(method, self.base_url + path, data, self._headers(),
                                     self.timeout)
        try:
            parsed = json.loads(raw or b"{}")
        except ValueError:
            parsed = {"raw": (raw or b"")[:200].decode("utf-8", "replace")}
        if not 200 <= status < 300:
            raise HandshakeError(status, parsed)
        return parsed

    # ------------------------------------------------------------ events ---

    def track(self, event):
        """Queue one event. Never blocks, never raises."""
        event = dict(event)
        event.setdefault("event_id", f"ev_{uuid.uuid4().hex}")
        event.setdefault("ts", time.time())
        try:
            self._q.put_nowait(event)
            self.stats["queued"] += 1
        except queue.Full:
            self.stats["dropped"] += 1

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="handshake-sdk", daemon=True)
        self._thread.start()

    def _drain(self, first):
        batch = [first]
        while len(batch) < self.batch_size:
            try:
                batch.append(self._q.get_nowait())
            except queue.Empty:
                break
        return batch

    def _run(self):
        while not self._stop.is_set() or not self._q.empty():
            try:
                first = self._q.get(timeout=self.flush_interval)
            except queue.Empty:
                continue
            batch = self._drain(first)
            with self._lock:
                self._inflight += len(batch)
            try:
                self._send(batch)
            except Exception as exc:          # a bad transport must not kill the sender
                self.stats["failed"] += len(batch)
                log.warning("handshake sender error, dropped %d events: %s", len(batch), exc)
            finally:
                with self._lock:
                    self._inflight -= len(batch)
                for _ in batch:
                    self._q.task_done()

    def _send(self, batch):
        body = json.dumps({"events": batch}, default=str).encode()
        delay = 0.25
        for attempt in range(self.max_retries + 1):
            status, raw = self.transport("POST", self.base_url + "/v1/events", body,
                                         self._headers(), self.timeout)
            if 200 <= status < 300 or status == 422:
                try:
                    res = json.loads(raw or b"{}")
                except ValueError:
                    res = {}
                self.stats["sent"] += res.get("accepted", 0)
                self.stats["duplicates"] += res.get("duplicates", 0)
                self.stats["rejected"] += len(res.get("rejected", []))
                for r in res.get("rejected", [])[:3]:
                    log.warning("handshake rejected event %s: %s", r.get("index"), r.get("error"))
                return True
            if status in (400, 401, 403, 404, 413):
                log.error("handshake refused a batch (%s); dropping %d events", status, len(batch))
                self.stats["failed"] += len(batch)
                return False
            # 0 (network), 429 and 5xx are retried. Idempotency makes that safe.
            self.stats["retries"] += 1
            if self._stop.is_set() and attempt >= 1:
                break
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
        self.stats["failed"] += len(batch)
        return False

    def flush(self, timeout=10.0):
        """Block until everything queued so far has been attempted."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                busy = self._inflight
            if self._q.empty() and not busy:
                return True
            time.sleep(0.02)
        return False

    def close(self, timeout=10.0):
        self.flush(timeout)
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------ convenience ---

    def sync_catalog(self, products):
        """Upload the source-of-truth product records. Handshake builds repairs
        (a missing attribute, a structured policy) from these, never from the
        possibly-degraded feed."""
        stored = 0
        for i in range(0, len(products), 500):
            stored += self.request("PUT", "/v1/catalog", {"products": products[i:i + 500]})["stored"]
        return stored

    def put_schema(self, schema):
        """{category: [required attribute, …]} — what an agent needs before it buys."""
        return self.request("PUT", "/v1/schema", {"schema": schema})["schema"]

    def get_reoffer(self, ref):
        """The re-offer waiting for a journey or checkout, or None."""
        try:
            return self.request("GET", f"/v1/reoffers/{ref}")["offer"]
        except HandshakeError as exc:
            if exc.status == 404:
                return None
            raise

    def journey(self, ref):
        return self.request("GET", f"/v1/journeys/{ref}")

    def metrics(self):
        return self.request("GET", "/v1/metrics")
