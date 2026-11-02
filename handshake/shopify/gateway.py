"""An agent-facing checkout for a real Shopify store, instrumented with Handshake.

Shopify has no public API an outside AI agent can buy through: checkout ends on
a page a human fills in. This gateway gives agents an ACP-shaped API in front
of the store, backed by the real store through the Admin API:

    GET  /shopify/acp/feed                   your live products and variants
    GET  /shopify/acp/products/{sku}         one variant, specs from metafields
    POST /shopify/acp/checkout_sessions      Shopify calculates the real total
    POST /shopify/acp/checkout_sessions/{id} re-quote, live: change a price in
                                             Shopify admin and the drift is real
    POST …/{id}/complete                     a real (test) order in your admin
    POST …/{id}/cancel
    GET  /shopify/acp/reoffers/{ref}         Handshake's re-offer, if any

It is wired to Handshake exactly as a merchant would wire it: the SDK
middleware reports the traffic, the catalogue and the learned schema are synced
through the client, and Handshake's directives arrive at a signed webhook. A
`patch_catalog` directive writes the missing spec back to the product in
Shopify.
"""

import logging
import os
import threading
import time
import uuid

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..live import store
from ..sdk import HandshakeClient, HandshakeMiddleware, WebhookSignatureError, verify_webhook
from . import catalog as cat
from .client import ShopifyAdmin, ShopifyError, configured

log = logging.getLogger("handshake.shopify")

# Replaceable in tests with a stand-in that answers like Shopify.
ADMIN_FACTORY = ShopifyAdmin
REFRESH_SECONDS = float(os.environ.get("SHOPIFY_REFRESH_SECONDS", "20"))


class _Slot:
    client = None

    def track(self, event):
        if self.client is not None:
            self.client.track(event)


CLIENT = _Slot()


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.admin = None
        self.shop = {}
        self.records = {}
        self.schema = {}
        self.synced_at = 0.0
        self.pushed = None
        self.error = ""
        self.base_url = None
        self.merchant_id = None
        self.api_key = None
        self.webhook_secret = ""
        self.sessions = {}
        self.log = {}

    def note(self, jid, line, kind="http"):
        self.log.setdefault(jid or "-", []).append({"t": time.time(), "kind": kind, "line": line})


S = State()

app = FastAPI(title="Shopify agent gateway", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(HandshakeMiddleware, client=CLIENT)


# ------------------------------------------------------------- lifecycle ---

def merchant_id_for(domain):
    return "m_shopify_" + cat.slug(domain.split(".")[0])[:40]


def is_ready():
    return S.admin is not None and S.base_url is not None


def default_base():
    return (os.environ.get("HS_SELF_URL")
            or f"http://127.0.0.1:{os.environ.get('PORT', '8000')}").rstrip("/")


def ensure(base_url=None):
    """Connect on first use. Never raises: a failure is reported in status()."""
    if is_ready():
        return True
    if not configured() and ADMIN_FACTORY is ShopifyAdmin:
        return False
    try:
        bootstrap(base_url or default_base())
        return True
    except Exception as exc:
        S.error = f"{type(exc).__name__}: {exc}"
        log.warning("shopify gateway could not connect: %s", S.error)
        return False


def bootstrap(base_url, transport=None):
    """Connect to Shopify, register as a Handshake merchant, sync. Idempotent."""
    with S.lock:
        if S.base_url == base_url and S.admin is not None:
            return S.api_key
        if not configured() and ADMIN_FACTORY is ShopifyAdmin:
            raise ShopifyError("Shopify is not connected: set SHOPIFY_STORE_DOMAIN and "
                               "SHOPIFY_ADMIN_TOKEN")
        admin = ADMIN_FACTORY()
        shop = admin.shop()
        mid = merchant_id_for(shop.get("myshopifyDomain") or admin.domain)
        webhook = base_url.rstrip("/") + "/shopify/webhooks/handshake"
        settings = {"idle_seconds": 45, "reoffer_ttl_seconds": 1800,
                    "retry_after_seconds": 60, "timezone": os.environ.get("SHOPIFY_TIMEZONE",
                                                                            "Asia/Kolkata")}
        m = store.get_merchant(mid)
        if m is None:
            m, key = store.create_merchant(f"{shop['name']} (Shopify)", webhook, {}, settings,
                                           sandbox=True, merchant_id=mid)
        else:
            key = store.rotate_key(mid)            # only the hash is kept
            m = store.update_merchant(mid, webhook_url=webhook,
                                      settings={**m["settings"], **settings})
        if CLIENT.client is not None:
            CLIENT.client.close(timeout=2)
        CLIENT.client = HandshakeClient(key, base_url, flush_interval=0.15, transport=transport)
        S.admin, S.shop, S.base_url = admin, shop, base_url
        S.merchant_id, S.api_key, S.webhook_secret = mid, key, m["webhook_secret"]
        S.synced_at, S.pushed = 0.0, None
        refresh(force=True)
        return key


def refresh(force=False):
    """Re-read the catalogue from Shopify; push it to Handshake when it changed."""
    with S.lock:
        if not force and time.time() - S.synced_at < REFRESH_SECONDS:
            return
        try:
            records = cat.to_records(S.admin.products())
            currency = S.shop.get("currencyCode")
            for r in records:
                r["currency"] = currency
            S.records = {r["sku"]: r for r in records}
            S.schema = cat.derive_schema(records)
            S.synced_at, S.error = time.time(), ""
            fingerprint = (tuple(sorted((r["sku"], r["price"], str(r["attributes"]))
                                        for r in records)), str(S.schema))
            if fingerprint != S.pushed and CLIENT.client is not None:
                if S.schema:
                    CLIENT.client.put_schema(S.schema)
                CLIENT.client.sync_catalog([cat.public(r) for r in records])
                S.pushed = fingerprint
        except ShopifyError as exc:
            S.error = str(exc)
            log.warning("shopify sync failed: %s", exc)


def _address(pincode):
    addr = {"countryCode": (os.environ.get("SHOPIFY_SHIP_COUNTRY")
                            or (S.shop.get("billingAddress") or {}).get("countryCodeV2") or "IN"),
            "zip": str(pincode or ""), "address1": "AI agent delivery", "city": "—"}
    if os.environ.get("SHOPIFY_SHIP_PROVINCE"):
        addr["provinceCode"] = os.environ["SHOPIFY_SHIP_PROVINCE"]
    return addr


def _money(m):
    return round(float(((m or {}).get("shopMoney") or {}).get("amount") or 0), 2)


def _jid(h):
    return h or "-"


def _unavailable():
    return JSONResponse({"error": "shopify_not_connected",
                         "detail": S.error or "the gateway is not connected to a store"}, 503)


# ---------------------------------------------------------------- the API ---

@app.get("/acp/feed")
def feed(category: str = "", q: str = "", x_agent_journey: str = Header(default="")):
    if not ensure():
        return _unavailable()
    refresh()
    items = [cat.public(r) for r in S.records.values()
             if r["available"] and (not category or r["category"] == category)
             and (not q or q.lower() in (r["title"] + " " + r["category"]).lower())]
    S.note(_jid(x_agent_journey), f"GET /acp/feed?category={category}&q={q} → 200 ({len(items)} items)")
    return {"items": items, "count": len(items), "currency": S.shop.get("currencyCode")}


@app.get("/acp/products/{sku}")
def product(sku: str, x_agent_journey: str = Header(default="")):
    if not ensure():
        return _unavailable()
    refresh()
    r = S.records.get(sku)
    S.note(_jid(x_agent_journey), f"GET /acp/products/{sku} → {200 if r else 404}")
    if r is None:
        return JSONResponse({"error": "unknown_sku"}, 404)
    return cat.public(r)


def _quote(r, qty, pincode):
    calc = S.admin.quote(r["shopify"]["variant_id"], qty, _address(pincode))
    rates = sorted(calc.get("availableShippingRates") or [],
                   key=lambda x: float((x.get("price") or {}).get("amount") or 0))
    ships = any(li.get("requiresShipping", True) for li in calc.get("lineItems") or [{}])
    if ships and not rates:
        return None
    shipping = round(float(rates[0]["price"]["amount"]), 2) if rates else 0.0
    return {"subtotal": _money(calc["subtotalPriceSet"]), "tax": _money(calc["totalTaxSet"]),
            "shipping": shipping, "total": round(_money(calc["totalPriceSet"]) + shipping, 2),
            "currency": (calc["totalPriceSet"].get("shopMoney") or {}).get("currencyCode"),
            "shipping_method": rates[0]["title"] if rates else None,
            "shipping_handle": rates[0]["handle"] if rates else None}


@app.post("/acp/checkout_sessions")
async def create_session(request: Request, x_agent_journey: str = Header(default="")):
    if not ensure():
        return _unavailable()
    jid = _jid(x_agent_journey)
    body = await request.json()
    sku, qty, pincode = body.get("sku", ""), int(body.get("qty", 1) or 1), body.get("pincode", "")
    refresh()
    r = S.records.get(sku)
    if r is None:
        S.note(jid, "POST /acp/checkout_sessions → 404 unknown_sku")
        return JSONResponse({"error": "unknown_sku"}, 404)
    if not r["available"]:          # Shopify's own answer: tracking and oversell rules included
        S.note(jid, "POST /acp/checkout_sessions → 409 insufficient_stock")
        return JSONResponse({"error": "insufficient_stock",
                             "detail": f"{sku} is not available in the requested quantity"}, 409)
    try:
        q = _quote(r, qty, pincode)
    except ShopifyError as exc:
        S.note(jid, f"POST /acp/checkout_sessions → 502 {exc}")
        return JSONResponse({"error": "gateway_error", "detail": str(exc)[:200]}, 502)
    if q is None:
        S.note(jid, "POST /acp/checkout_sessions → 422 fulfilment_undetermined")
        return JSONResponse({"error": "fulfilment_undetermined",
                             "detail": f"no shipping rate to {pincode}"}, 422)
    cid = f"cs_{uuid.uuid4().hex[:12]}"
    S.sessions[cid] = {"journey": jid, "sku": sku, "qty": qty, "pincode": pincode,
                       "quote": q, "locked_total": None}
    out = {"session_id": cid, "sku": sku, "qty": qty,
           "fulfilment": {"ships_in_days": r["fulfilment"].get("ships_in_days"),
                          "method": q["shipping_method"]},
           **{k: q[k] for k in ("subtotal", "tax", "shipping", "total", "currency")}}
    S.note(jid, f"POST /acp/checkout_sessions → 200 {cid} total {q['total']:,.2f}")
    return out


@app.post("/acp/checkout_sessions/{cid}")
def update_session(cid: str):
    s = S.sessions.get(cid)
    if s is None:
        return JSONResponse({"error": "unknown_session"}, 404)
    r = S.records.get(s["sku"])
    try:
        q = _quote(r, s["qty"], s["pincode"]) or s["quote"]
    except ShopifyError as exc:
        return JSONResponse({"error": "gateway_error", "detail": str(exc)[:200]}, 502)
    s["quote"] = q
    total = s["locked_total"] if s["locked_total"] is not None else q["total"]
    S.note(s["journey"], f"POST /acp/checkout_sessions/{cid} → 200 re-quote {total:,.2f}")
    out = {"session_id": cid, **{k: q[k] for k in ("subtotal", "tax", "shipping", "currency")},
           "total": total}
    if s["locked_total"] is not None:
        out["price_locked"] = True
    return out


def accepted_methods():
    return {m.strip() for m in os.environ.get(
        "SHOPIFY_ACCEPTED_METHODS", "card_token,upi_intent,upi_reserve").split(",") if m.strip()}


@app.post("/acp/checkout_sessions/{cid}/complete")
async def complete_session(cid: str, request: Request):
    s = S.sessions.get(cid)
    if s is None:
        return JSONResponse({"error": "unknown_session"}, 404)
    body = await request.json()
    method = (body.get("instrument") or {}).get("type", "")
    jid = s["journey"]
    if method not in accepted_methods():
        S.note(jid, f"POST …/{cid}/complete → 400 payment_method_unsupported")
        return JSONResponse({"error": "payment_method_unsupported",
                             "detail": f"this store does not accept {method or 'that method'}; "
                                       f"accepted: {', '.join(sorted(accepted_methods()))}"}, 400)
    r = S.records.get(s["sku"])
    try:
        order = S.admin.place_order(r["shopify"]["variant_id"], s["qty"], _address(s["pincode"]),
                                    s["quote"].get("shipping_handle"),
                                    note=f"Placed by an AI agent via Handshake ({jid})")
    except ShopifyError as exc:
        S.note(jid, f"POST …/{cid}/complete → 502 {exc}")
        return JSONResponse({"error": "gateway_error", "detail": str(exc)[:200]}, 502)
    total = _money(order.get("totalPriceSet")) or s["quote"]["total"]
    S.note(jid, f"POST …/{cid}/complete → 200 order {order.get('name')} {total:,.2f}")
    S.sessions.pop(cid, None)
    return {"session_id": cid, "status": "captured", "ref": order.get("name"),
            "order_id": order.get("id"), "total": total}


@app.post("/acp/checkout_sessions/{cid}/cancel")
async def cancel_session(cid: str, request: Request):
    s = S.sessions.get(cid)
    if s is None:
        return JSONResponse({"error": "unknown_session"}, 404)
    # Kept, not deleted: a recovery (a price lock, say) may reopen it.
    s["cancelled"] = True
    body = await request.json()
    S.note(s["journey"], f"POST …/{cid}/cancel → 200" +
           (f" reason='{body.get('reason')}'" if body.get("reason") else ""))
    return {"session_id": cid, "status": "cancelled"}


@app.get("/acp/reoffers/{ref}")
def reoffer(ref: str):
    offer = CLIENT.client.get_reoffer(ref) if CLIENT.client else None
    if not offer:
        return JSONResponse({"pending": False}, 404)
    return {"pending": True, "offer": offer}


# ------------------------------------------------------------- directives ---

def _apply(directive):
    a = directive.get("merchant_action") or {}
    kind = a.get("type")
    if kind == "patch_catalog":
        r = S.records.get(a.get("sku"))
        if r is None:
            return "unknown sku; nothing written"
        for key, value in (a.get("set") or {}).items():
            S.admin.set_spec(r["shopify"]["product_id"], key, value)
        refresh(force=True)
        return f"wrote {', '.join(a.get('set') or {})} to {a['sku']} in Shopify"
    if kind == "price_lock":
        s = S.sessions.get(a.get("checkout_id"))
        if s:
            s["locked_total"] = a["locked_total"]
        return f"locked {a.get('checkout_id')} at {a['locked_total']:,.2f}"
    return f"noted {kind}: {a.get('merchant_change') or a.get('reason') or ''}".strip()


@app.post("/webhooks/handshake")
async def handshake_webhook(request: Request):
    raw = await request.body()
    try:
        event = verify_webhook(raw, request.headers.get("handshake-signature", ""), S.webhook_secret)
    except WebhookSignatureError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    data = event.get("data") or {}
    line = f"webhook {event['type']}"
    if event["type"] == "recovery.directive":
        try:
            line += f" {data.get('intervention')} → {_apply(data)}"
        except ShopifyError as exc:
            line += f" → could not apply: {exc}"
    S.note(data.get("journey_id"), line, "webhook")
    return {"ok": True}


# ------------------------------------------------------------- reading ---

def status():
    if not configured() and ADMIN_FACTORY is ShopifyAdmin:
        return {"connected": False, "configured": False}
    out = {"configured": True, "connected": is_ready(), "error": S.error}
    if is_ready():
        out.update(shop=S.shop.get("name"), domain=S.shop.get("myshopifyDomain"),
                   currency=S.shop.get("currencyCode"), merchant_id=S.merchant_id,
                   products=len({r["variant_group"] for r in S.records.values()}),
                   variants=len(S.records), categories=sorted({r["category"] for r in S.records.values()}),
                   schema=S.schema, synced_at=S.synced_at, api_calls=S.admin.calls,
                   auth_mode=S.admin.auth_mode,
                   accepted_methods=sorted(accepted_methods()),
                   gaps=cat.gaps(S.records.values(), S.schema))
    return out


@app.get("/", response_class=HTMLResponse)
def page():
    from pathlib import Path
    return HTMLResponse((Path(__file__).resolve().parents[1] / "web" / "shopify.html").read_text())
