"""Handshake merchant SDK.

    from handshake.sdk import HandshakeClient, HandshakeMiddleware, verify_webhook

    hs = HandshakeClient(api_key=os.environ["HANDSHAKE_KEY"],
                         base_url="https://handshake.example.com")
    app.add_middleware(HandshakeMiddleware, client=hs)

    @app.post("/webhooks/handshake")
    async def handshake_webhook(request):
        event = verify_webhook(await request.body(),
                               request.headers["Handshake-Signature"], WEBHOOK_SECRET)
        ...
"""

import hashlib
import hmac
import json
import time

from .client import HandshakeClient, HandshakeError
from .middleware import DEFAULT_ROUTES, HandshakeMiddleware


class WebhookSignatureError(ValueError):
    pass


def verify_webhook(raw_body, signature_header, secret, tolerance=300, now=None):
    """Return the parsed event if the signature is valid and fresh; raise otherwise."""
    if isinstance(raw_body, str):
        raw_body = raw_body.encode()
    parts = dict(p.split("=", 1) for p in (signature_header or "").split(",") if "=" in p)
    try:
        ts = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        raise WebhookSignatureError("malformed Handshake-Signature header")
    if abs((now or time.time()) - ts) > tolerance:
        raise WebhookSignatureError("signature timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, given):
        raise WebhookSignatureError("signature mismatch")
    return json.loads(raw_body)


__all__ = ["HandshakeClient", "HandshakeError", "HandshakeMiddleware", "DEFAULT_ROUTES",
           "verify_webhook", "WebhookSignatureError"]
