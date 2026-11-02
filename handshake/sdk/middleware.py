"""ASGI middleware: instrument an agent-facing checkout with one line.

    app.add_middleware(HandshakeMiddleware, client=HandshakeClient(KEY, URL))

Works with FastAPI, Starlette, Quart, Django-ASGI — anything ASGI. It reads the
request body, lets the app handle the request untouched, captures the response,
and hands one event to the client's queue. The app sees the same bytes it would
have seen without it; if anything in here fails, the request still completes.

Routes are matched by regular expression on the path *suffix*, so a store that
mounts its agent API under /api/acp/v2 needs no configuration. The defaults
follow the Agentic Commerce Protocol's checkout-session shape; pass `routes=`
to map a different API.

Only the request and response bodies of matched routes are captured. Headers
are not forwarded, except the three that identify the agent. Sensitive fields
are redacted again on the server.
"""

import json
import logging
import re
import time
from hashlib import sha1

log = logging.getLogger("handshake.sdk")

DEFAULT_ROUTES = (
    ("GET", r"/feed(?:\.json)?$", "feed.read"),
    ("GET", r"/products/(?P<sku>[^/]+)$", "product.view"),
    ("POST", r"/checkout_sessions$", "checkout.create"),
    ("POST", r"/checkout_sessions/(?P<checkout_id>[^/]+)/complete$", "checkout.complete"),
    ("POST", r"/checkout_sessions/(?P<checkout_id>[^/]+)/cancel$", "checkout.cancel"),
    ("POST", r"/checkout_sessions/(?P<checkout_id>[^/]+)$", "checkout.update"),
    ("GET", r"/reoffers/(?P<checkout_id>[^/]+)$", "reoffer.fetch"),
)
MAX_CAPTURE = 256 * 1024


def default_agent_id(headers, scope):
    """X-Agent-Id when the agent platform sends one; otherwise a stable hash of
    user agent and client address, which is weaker and says so in its prefix."""
    if headers.get("x-agent-id"):
        return headers["x-agent-id"]
    client = (scope.get("client") or ("", 0))[0]
    return "anon_" + sha1(f"{headers.get('user-agent', '')}|{client}".encode()).hexdigest()[:16]


def _json(raw):
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {"_unparsed": True}
    return value if isinstance(value, dict) else {"items": value} if isinstance(value, list) \
        else {"value": value}


class HandshakeMiddleware:
    def __init__(self, app, client, routes=DEFAULT_ROUTES, agent_id=default_agent_id,
                 journey_header="x-agent-journey", principal_header="x-agent-principal"):
        self.app = app
        self.client = client
        self.routes = [(m.upper(), re.compile(p), t) for m, p, t in routes]
        self.agent_id = agent_id
        self.journey_header = journey_header
        self.principal_header = principal_header

    def _match(self, method, path):
        for m, pattern, etype in self.routes:
            if m == method:
                found = pattern.search(path)
                if found:
                    return etype, found.groupdict()
        return None, {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        etype, params = self._match(scope["method"], scope["path"])
        if etype is None:
            return await self.app(scope, receive, send)

        started = time.perf_counter()
        chunks, more = [], True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        req_body = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": req_body, "more_body": False}
            return await receive()

        captured = {"status": 500, "body": bytearray()}

        async def capture(message):
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
            elif message["type"] == "http.response.body":
                if len(captured["body"]) < MAX_CAPTURE:
                    captured["body"].extend(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, replay, capture)
        finally:
            try:
                self._record(scope, etype, params, req_body, captured, started)
            except Exception as exc:                      # never break checkout
                log.warning("handshake middleware could not record: %s", exc)

    def _record(self, scope, etype, params, req_body, captured, started):
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        request = _json(req_body)
        if scope.get("query_string"):
            from urllib.parse import parse_qsl
            request = {**dict(parse_qsl(scope["query_string"].decode("latin-1"))), **request}
        response = _json(bytes(captured["body"]))
        checkout_id = params.get("checkout_id") or response.get("session_id") \
            or response.get("checkout_session_id") or ""
        sku = params.get("sku") or request.get("sku") or response.get("sku") or ""
        self.client.track({
            "type": etype,
            "agent_id": self.agent_id(headers, scope),
            "journey_id": headers.get(self.journey_header, ""),
            "principal_id": headers.get(self.principal_header, ""),
            "checkout_id": checkout_id, "sku": sku,
            "method": scope["method"], "path": scope["path"],
            "http_status": captured["status"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "request": request, "response": response,
        })
