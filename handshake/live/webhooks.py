"""Signed outbound webhooks with retry.

Signature scheme (same shape as Stripe's, so existing verifiers port over):

    Handshake-Signature: t=<unix seconds>,v1=<hex hmac-sha256(secret, "<t>.<raw body>")>

A receiver recomputes the HMAC over the raw body and rejects anything older
than five minutes. `handshake.sdk.verify_webhook` does both.

Deliveries are queued in the store first and sent by the worker, so a slow or
failing merchant endpoint never blocks ingest. Failures back off exponentially
for up to eight attempts and are then marked failed — visible on the dashboard,
never silently dropped.
"""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from .. import __version__
from . import store

MAX_ATTEMPTS = 8
BACKOFF = (0, 5, 30, 120, 600, 1800, 3600, 7200)
TIMEOUT = 5.0


def sign(secret, body, ts=None):
    ts = int(ts or time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _http_send(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, f"HTTP {exc.code}"
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


# Replaceable for tests and for in-process demos: (url, body, headers) -> (status, error)
SEND = _http_send


def emit(merchant, journey_id, event, data):
    """Queue one webhook. A merchant with no URL still gets the row, marked
    skipped, so the dashboard shows what would have been sent."""
    payload = {"id": None, "type": event, "created": time.time(),
               "merchant_id": merchant["merchant_id"], "data": data}
    delivery_id = store.enqueue_delivery(merchant["merchant_id"], journey_id, event, payload)
    if not merchant.get("webhook_url"):
        store.mark_delivery(delivery_id, status="skipped",
                            last_error="no webhook_url configured")
    return delivery_id


def deliver(row):
    merchant = store.get_merchant(row["merchant_id"])
    if merchant is None or not merchant["webhook_url"]:
        store.mark_delivery(row["delivery_id"], status="skipped",
                            last_error="no webhook_url configured")
        return False
    payload = dict(row["payload"], id=row["delivery_id"])
    body = json.dumps(payload, default=str, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json",
               "User-Agent": f"Handshake-Webhooks/{__version__}",
               "Handshake-Event": row["event"],
               "Handshake-Delivery": row["delivery_id"],
               "Handshake-Signature": sign(merchant["webhook_secret"], body)}
    status, error = SEND(merchant["webhook_url"], body, headers)
    attempts = row["attempts"] + 1
    if 200 <= status < 300:
        store.mark_delivery(row["delivery_id"], status="delivered", attempts=attempts,
                            response_status=status, delivered_at=time.time(), last_error="")
        return True
    if attempts >= MAX_ATTEMPTS:
        store.mark_delivery(row["delivery_id"], status="failed", attempts=attempts,
                            response_status=status, last_error=error)
    else:
        store.mark_delivery(row["delivery_id"], attempts=attempts, response_status=status,
                            last_error=error,
                            next_attempt_at=time.time() + BACKOFF[min(attempts, len(BACKOFF) - 1)])
    return False


def deliver_due(now=None, limit=25):
    sent = 0
    for row in store.due_deliveries(now or time.time(), limit):
        if deliver(row):
            sent += 1
    return sent
