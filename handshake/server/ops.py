"""Operational plumbing: structured logs, request ids, security headers.

    HS_LOG_FORMAT=json    one JSON object per line (default when not a TTY)
    HS_LOG_LEVEL=INFO
    HS_CORS_ORIGINS=https://dash.example.com,https://other.example.com
    HS_TRUST_PROXY=1      honour X-Forwarded-Proto for HSTS behind a load balancer

Every response carries `X-Request-Id` (the caller's, if it sent one, else a new
one), and every request is logged once with method, path, status, latency and
the merchant id when one authenticated. Bodies and API keys are never logged.
"""

import json
import logging
import os
import sys
import time
import uuid

log = logging.getLogger("handshake.http")


class JSONFormatter(logging.Formatter):
    def format(self, record):
        out = {"ts": round(record.created, 3), "level": record.levelname.lower(),
               "logger": record.name, "msg": record.getMessage()}
        for key, value in getattr(record, "fields", {}).items():
            out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging():
    fmt = os.environ.get("HS_LOG_FORMAT") or ("text" if sys.stderr.isatty() else "json")
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter() if fmt == "json" else
                         logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("handshake")
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("HS_LOG_LEVEL", "INFO").upper())
    root.propagate = False


SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"DENY"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]
QUIET_PATHS = ("/healthz", "/readyz", "/api/state", "/demo/api/runs/")


class RequestContext:
    """Pure ASGI, so it wraps streaming and mounted apps without buffering."""

    def __init__(self, app):
        self.app = app
        self.trust_proxy = os.environ.get("HS_TRUST_PROXY", "").lower() in ("1", "true", "yes")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        rid = headers.get(b"x-request-id", b"").decode("latin-1")[:64] or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        https = scope.get("scheme") == "https" or (
            self.trust_proxy and headers.get(b"x-forwarded-proto") == b"https")
        started = time.perf_counter()
        status = {"code": 500}

        async def wrapped(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                h = list(message.get("headers") or [])
                h.append((b"x-request-id", rid.encode()))
                h.extend(SECURITY_HEADERS)
                if https:
                    h.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = h
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            path = scope.get("path", "")
            if not (status["code"] < 400 and path.startswith(QUIET_PATHS)):
                log.info("request", extra={"fields": {
                    "request_id": rid, "method": scope.get("method"), "path": path,
                    "status": status["code"],
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "merchant_id": scope["state"].get("merchant_id")}})


def cors_origins():
    return [o.strip() for o in os.environ.get("HS_CORS_ORIGINS", "").split(",") if o.strip()]
