"""The normalised event schema.

A merchant's checkout speaks its own dialect of HTTP. The SDK middleware maps
each request to one of the semantic types below, and everything downstream —
the detectors, the dashboard, the ledger — reads only these. The mapping lives
in the SDK so a merchant can change it without a Handshake deploy.

An event is what crossed the merchant's boundary and nothing else: no agent
reasoning, no scenario label, no fault injection metadata. The detectors have to
work from exactly what a real merchant's server would have logged.
"""

import re
import time
import uuid

TYPES = (
    "feed.read",            # agent listed products
    "product.view",         # agent fetched one product record
    "checkout.create",      # checkout session opened (ACP: POST /checkout_sessions)
    "checkout.update",      # session re-quoted
    "checkout.complete",    # payment attempted
    "checkout.cancel",      # agent closed the session, optionally saying why
    "reoffer.fetch",        # agent polled for a recovery offer
)

STAGE = {"feed.read": "discovery", "product.view": "discovery",
         "checkout.create": "checkout", "checkout.update": "checkout",
         "checkout.cancel": "checkout", "checkout.complete": "payment",
         "reoffer.fetch": "recovery"}
STAGE_ORDER = {"discovery": 0, "checkout": 1, "payment": 2, "recovery": 3}

# Field names whose values never leave the merchant's process. Matched on the
# key, case-insensitively, at any depth. Server-side redaction repeats the SDK's
# so a misconfigured client cannot store a card number.
SENSITIVE = re.compile(
    r"(card_?number|^pan$|cvv|cvc|otp|password|passcode|secret|authorization|"
    r"approval_token|access_token|refresh_token|^token$|account_number|aadhaar|"
    r"email|phone|mobile|address_line|street)", re.I)

MAX_DEPTH = 6
MAX_LIST = 200
MAX_STR = 2000


def redact(value, depth=0):
    if depth > MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        return {k: ("[redacted]" if SENSITIVE.search(str(k)) else redact(v, depth + 1))
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, depth + 1) for v in value[:MAX_LIST]]
    if isinstance(value, str) and len(value) > MAX_STR:
        return value[:MAX_STR] + "…"
    return value


class InvalidEvent(ValueError):
    pass


def normalise(raw):
    """Validate one inbound event and return the canonical dict.

    Accepts the shape the SDK emits; tolerant of absent optional fields, strict
    on the ones the pipeline keys on."""
    if not isinstance(raw, dict):
        raise InvalidEvent("event must be an object")
    etype = raw.get("type")
    if etype not in TYPES:
        raise InvalidEvent(f"unknown event type {etype!r}; expected one of {', '.join(TYPES)}")
    agent_id = str(raw.get("agent_id") or "").strip()
    if not agent_id:
        raise InvalidEvent("agent_id is required: it is how a journey is stitched together")
    try:
        status = int(raw.get("http_status", 200))
    except (TypeError, ValueError):
        raise InvalidEvent("http_status must be an integer")
    ts = raw.get("ts")
    try:
        ts = float(ts) if ts is not None else time.time()
    except (TypeError, ValueError):
        raise InvalidEvent("ts must be epoch seconds")
    request = raw.get("request") or {}
    response = raw.get("response") or {}
    if not isinstance(request, dict) or not isinstance(response, dict):
        raise InvalidEvent("request and response must be objects")
    return {
        "event_id": str(raw.get("event_id") or f"ev_{uuid.uuid4().hex}")[:80],
        "type": etype,
        "ts": ts,
        "agent_id": agent_id[:120],
        "principal_id": str(raw.get("principal_id") or "")[:120],
        "journey_id": str(raw.get("journey_id") or "")[:80],
        "checkout_id": str(raw.get("checkout_id") or "")[:80],
        "sku": str(raw.get("sku") or "")[:80],
        "http_status": status,
        "method": str(raw.get("method") or "")[:8],
        "path": str(raw.get("path") or "")[:300],
        "latency_ms": float(raw.get("latency_ms") or 0.0),
        "request": redact(request),
        "response": redact(response),
    }


def describe(ev):
    """One line a merchant can read: what crossed the wire."""
    t, st = ev["type"], ev.get("http_status", 200)
    req, res = ev.get("request", {}), ev.get("response", {})
    sku = ev.get("sku") or req.get("sku") or res.get("sku") or ""
    if t == "feed.read":
        n = res.get("count", len(res.get("items", []) or []))
        return f"listed the catalogue ({n} items)"
    if t == "product.view":
        return f"opened product {sku}" + ("" if st == 200 else f" → {st}")
    if t == "checkout.create":
        if st != 200:
            return f"tried to open checkout for {sku} → {st} {res.get('error', '')}".strip()
        total = res.get("total")
        cap = req.get("declared_cap")
        return (f"opened checkout {ev.get('checkout_id') or res.get('session_id', '')}"
                f" at ₹{total:,.2f}" if isinstance(total, (int, float)) else "opened checkout") + \
            (f" (cap ₹{cap:,.0f})" if isinstance(cap, (int, float)) else "")
    if t == "checkout.update":
        total = res.get("total")
        return f"re-quoted checkout at ₹{total:,.2f}" if isinstance(total, (int, float)) \
            else "re-quoted checkout"
    if t == "checkout.complete":
        if st == 200:
            return f"paid ₹{res.get('total', 0):,.2f}"
        code = res.get("reason_code") or res.get("error") or ""
        return f"payment attempt → {st} {code}".strip()
    if t == "checkout.cancel":
        why = req.get("reason")
        return "cancelled checkout" + (f", stating '{why}'" if why else ", no reason given")
    if t == "reoffer.fetch":
        offer = res.get("offer") or {}
        return (f"collected a recovery offer ({offer.get('type', 'offer')})" if st == 200
                else "polled for a recovery offer, none yet")
    return t
