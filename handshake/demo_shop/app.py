"""Kaveri Home & Tech — an agent-facing store instrumented with the Handshake SDK.

This app stands in for a merchant's own checkout service. It knows nothing about
Handshake's internals: it is wired up the way any merchant would wire it up —

  1. `HandshakeMiddleware` on the app, so every ACP request is reported
  2. the catalogue and category schema synced through `HandshakeClient`
  3. a webhook endpoint that verifies the signature and applies directives
  4. a re-offer endpoint that asks Handshake what to tell a returning agent

Mounted at /shop in the demo process, but it talks to Handshake over HTTP,
exactly as it would from a different host.
"""

import copy
import logging
import random
import threading
import time
import uuid

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import RunConfig
from ..payments.adapter import PaymentError, build_backend
from ..sdk import HandshakeMiddleware, WebhookSignatureError, verify_webhook
from .catalog import PIM, SCHEMA, all_products, pim

log = logging.getLogger("handshake.demo_shop")


class _ClientSlot:
    """The middleware is installed at import; the client exists once the demo
    is bootstrapped and knows its own base URL. Until then, events are dropped."""

    def __init__(self):
        self.client = None

    def track(self, event):
        if self.client is not None:
            self.client.track(event)


class ShopState:
    def __init__(self):
        self.lock = threading.Lock()
        self.faults = {}          # journey_id -> set of hidden shop conditions
        self.resolved = {}        # journey_id -> set of conditions since fixed
        self.patches = {}         # journey_id -> {sku: {attr: value}}
        self.policies = {}        # journey_id -> {sku: policy}
        self.withdrawn = {}       # journey_id -> {sku}
        self.serviceable = {}     # journey_id -> {sku}
        self.sessions = {}        # checkout_id -> session
        self.approvals = {}       # token -> checkout_id
        self.log = {}             # journey_id -> [line]
        self.webhook_secret = ""
        # The store's own configuration, set by a person on /shop/admin. Unlike
        # `faults`, nobody injects these per run: every agent that shops meets
        # the store as it is, exactly like a real merchant's messy catalogue.
        self.store = {"global": set(), "products": {}}

    def reset(self):
        self.__init__()

    def note(self, journey_id, line, kind="http"):
        with self.lock:
            self.log.setdefault(journey_id or "-", []).append(
                {"t": time.time(), "kind": kind, "line": line})

    def has(self, journey_id, condition, sku=None):
        """Is this problem live for this agent, on this product?"""
        if condition in self.resolved.get(journey_id, set()):
            return False
        base = _base(sku) if sku else None
        if condition in self.faults.get(journey_id, set()):
            # Per-run (demo) faults target the 1.7 L kettle when product-scoped.
            if condition not in PRODUCT_SCOPED or base in (None, MYSTERY_TARGET):
                return True
        if condition in self.store["global"]:
            return True
        return bool(base and condition in self.store["products"].get(base, set()))

    def twins(self, journey_id):
        """SKUs listed twice (variant collision) for this agent."""
        out = {MYSTERY_TARGET} if self.has(journey_id, "variant_collision", MYSTERY_TARGET) else set()
        out |= {s for s, c in self.store["products"].items() if "variant_collision" in c
                and "variant_collision" not in self.resolved.get(journey_id, set())}
        return out - {s.removesuffix("-B") for s in self.withdrawn.get(journey_id, set())}

    def resolve(self, journey_id, *conditions):
        """Mark conditions fixed; with none named, every condition on the journey."""
        names = conditions or tuple(self.faults.get(journey_id, ()))
        self.resolved.setdefault(journey_id, set()).update(names)


# Problems that live on one product; the rest apply to the whole checkout.
PRODUCT_SCOPED = {"missing_attribute", "prose_policy", "variant_collision", "out_of_stock",
                  "slow_delivery", "price_drift"}
STORE_WIDE = {"shipping_fee", "unserviceable", "unsupported_payment", "otp_wall",
              "flaky_error", "insufficient_funds", "silent_decline"}
MYSTERY_TARGET = "KET-170"


def _base(sku):
    return sku[:-2] if sku.endswith("-B") else sku


SHOP = ShopState()
CLIENT = _ClientSlot()
try:
    _payments = build_backend(RunConfig(), random.Random(7))
except PaymentError as exc:            # misconfigured keys must not take the shop down
    log.warning("demo shop falling back to simulated payments: %s", exc)
    _payments = build_backend(RunConfig(payments_backend="sim"), random.Random(7))

shop = FastAPI(title="Kaveri Home & Tech (demo merchant)", docs_url=None, redoc_url=None,
               openapi_url=None)
shop.add_middleware(HandshakeMiddleware, client=CLIENT)


def _journey(x_agent_journey):
    return x_agent_journey or "-"


def _served(product, jid):
    """A product record as the storefront serves it to an agent, after this
    journey's problems and any repairs the shop has applied since."""
    p = copy.deepcopy(product)
    patch = SHOP.patches.get(jid, {}).get(p["sku"], {})
    if SHOP.has(jid, "missing_attribute", p["sku"]):
        # The feed bug drops the second spec the category requires.
        required = SCHEMA.get(p["category"], [])
        if len(required) > 1:
            p["attributes"].pop(required[1], None)
    if SHOP.has(jid, "prose_policy", p["sku"]):
        p["policy"] = {"text": "Returns are accepted within a reasonable period, subject to "
                               "inspection and our standard terms.", "structured": False}
    p["attributes"].update(patch)
    if p["sku"] in SHOP.policies.get(jid, {}):
        p["policy"] = SHOP.policies[jid][p["sku"]]
    p.pop("fulfilment", None)
    p.pop("image", None)
    return p


def _feed(jid):
    items = []
    twins = SHOP.twins(jid)
    for p in PIM:
        if p["stock"] <= 0:
            continue
        items.append(_served(p, jid))
        if p["sku"] in twins:
            twin = _served(p, jid)
            twin["sku"] = p["sku"] + "-B"
            items.append(twin)
    return items


def _totals(unit, qty, tax_rate):
    sub = round(unit * qty, 2)
    tax = round(sub * tax_rate, 2)
    return {"unit_price": unit, "subtotal": sub, "tax": tax, "total": round(sub + tax, 2),
            "currency": "INR"}


# --------------------------------------------------------------- ACP surface ---

@shop.get("/acp/feed")
def feed(category: str = "", q: str = "", x_agent_journey: str = Header(default=""),
         x_demo_scenario: str = Header(default="")):
    jid = _journey(x_agent_journey)
    if x_demo_scenario and jid not in SHOP.faults:
        SHOP.faults[jid] = {c for c in x_demo_scenario.split(",") if c}
    items = [p for p in _feed(jid) if (not category or p["category"] == category)
             and (not q or q.lower() in p["title"].lower())]
    SHOP.note(jid, f"GET /acp/feed?category={category}&q={q} → 200 ({len(items)} items)")
    return {"items": items, "count": len(items)}


@shop.get("/acp/products/{sku}")
def product(sku: str, x_agent_journey: str = Header(default="")):
    jid = _journey(x_agent_journey)
    base = pim(_base(sku))
    if base is None:
        SHOP.note(jid, f"GET /acp/products/{sku} → 404")
        return JSONResponse({"error": "unknown_sku"}, 404)
    view = _served(base, jid)
    view["sku"] = sku
    SHOP.note(jid, f"GET /acp/products/{sku} → 200")
    return view


@shop.post("/acp/checkout_sessions")
async def create_session(request: Request, x_agent_journey: str = Header(default="")):
    jid = _journey(x_agent_journey)
    body = await request.json()
    sku, qty, pincode = body.get("sku", ""), int(body.get("qty", 1)), body.get("pincode", "")
    base = pim(_base(sku))
    if base is None:
        SHOP.note(jid, f"POST /acp/checkout_sessions → 404 unknown_sku")
        return JSONResponse({"error": "unknown_sku"}, 404)
    if SHOP.has(jid, "unserviceable", sku) and sku not in SHOP.serviceable.get(jid, set()):
        SHOP.note(jid, f"POST /acp/checkout_sessions → 422 fulfilment_undetermined")
        return JSONResponse({"error": "fulfilment_undetermined",
                             "detail": "no serviceable route for this address"}, 422)
    if SHOP.has(jid, "out_of_stock", sku):
        SHOP.note(jid, f"POST /acp/checkout_sessions → 409 insufficient_stock")
        return JSONResponse({"error": "insufficient_stock",
                             "detail": f"{sku} is not available in the requested quantity"}, 409)
    ships = base["fulfilment"]["ships_in_days"]
    if SHOP.has(jid, "slow_delivery", sku):
        ships = 9                          # a warehouse transfer nobody put in the feed
    cid = f"cs_{uuid.uuid4().hex[:12]}"
    SHOP.sessions[cid] = {"journey": jid, "sku": sku, "qty": qty, "unit": base["price"],
                          "tax_rate": base["tax_rate"], "locked_total": None,
                          "pincode": pincode, "state": "open", "approval": None,
                          "attempts": 0}
    out = {"session_id": cid, "sku": sku, "qty": qty,
           "fulfilment": {"ships_in_days": ships},
           **_totals(base["price"], qty, base["tax_rate"])}
    SHOP.note(jid, f"POST /acp/checkout_sessions → 200 {cid} total ₹{out['total']:,.2f}")
    return out


@shop.post("/acp/checkout_sessions/{cid}")
def update_session(cid: str):
    s = SHOP.sessions.get(cid)
    if s is None:
        return JSONResponse({"error": "unknown_session"}, 404)
    unit = s["unit"]
    if SHOP.has(s["journey"], "price_drift", s["sku"]) and s["locked_total"] is None:
        unit = round(unit * 1.09, 2)
    totals = _totals(unit, s["qty"], s["tax_rate"])
    if SHOP.has(s["journey"], "shipping_fee", s["sku"]) and s["locked_total"] is None:
        totals["shipping"] = 149.0         # appears only at re-quote, never in the feed
        totals["total"] = round(totals["total"] + 149.0, 2)
    if s["locked_total"] is not None:
        totals["total"] = s["locked_total"]
        totals["price_locked"] = True
    s["quoted"] = totals["total"]
    SHOP.note(s["journey"], f"POST /acp/checkout_sessions/{cid} → 200 re-quote "
                            f"₹{totals['total']:,.2f}")
    return {"session_id": cid, **totals}


@shop.post("/acp/checkout_sessions/{cid}/complete")
async def complete_session(cid: str, request: Request):
    s = SHOP.sessions.get(cid)
    if s is None:
        return JSONResponse({"error": "unknown_session"}, 404)
    jid = s["journey"]
    body = await request.json()
    s["attempts"] += 1
    amount = s.get("quoted") or _totals(s["unit"], s["qty"], s["tax_rate"])["total"]

    def fail(status, payload, line):
        SHOP.note(jid, f"POST /acp/checkout_sessions/{cid}/complete → {status} {line}")
        return JSONResponse(payload, status)

    instrument = body.get("instrument") or {}
    if SHOP.has(jid, "unsupported_payment") and instrument.get("type") == "upi_reserve":
        return fail(400, {"error": "payment_method_unsupported",
                          "detail": "this store does not accept UPI Reserve mandates"},
                    "payment_method_unsupported")
    if SHOP.has(jid, "otp_wall"):
        token = body.get("approval_token")
        if not token or SHOP.approvals.get(token) != cid:
            return fail(401, {"error": "authentication_required",
                              "detail": "OTP must be completed by the account holder"},
                        "authentication_required")
        SHOP.approvals.pop(token, None)                    # single use
    if SHOP.has(jid, "flaky_error"):
        SHOP.resolve(jid, "flaky_error")                   # it was transient
        return fail(503, {"error": "processing_error",
                          "detail": "request could not be completed"}, "processing_error")
    forced = "insufficient_funds" if SHOP.has(jid, "insufficient_funds") else None
    try:
        result = _payments.charge(amount, instrument, forced_reason=forced)
        if SHOP.has(jid, "silent_decline"):
            # Roughly a quarter of real declines arrive like this: no reason at all.
            result.ok, result.reason_code = False, ""
    except PaymentError as exc:
        return fail(502, {"error": "gateway_unavailable", "detail": str(exc)}, "gateway")
    if not result.ok:
        payload = {"error": "payment_failed", "ref": result.ref}
        if result.reason_code:
            payload["reason_code"] = result.reason_code
        return fail(402, payload, result.reason_code or "(no reason code)")
    s["state"] = "completed"
    SHOP.note(jid, f"POST /acp/checkout_sessions/{cid}/complete → 200 captured "
                   f"₹{amount:,.2f} ({result.ref})")
    return {"session_id": cid, "status": "captured", "ref": result.ref, "total": amount,
            "payments": _payments.name}


@shop.post("/acp/checkout_sessions/{cid}/cancel")
async def cancel_session(cid: str, request: Request):
    s = SHOP.sessions.get(cid)
    if s is None:
        return JSONResponse({"error": "unknown_session"}, 404)
    body = await request.json()
    s["state"] = "cancelled"
    SHOP.note(s["journey"], f"POST /acp/checkout_sessions/{cid}/cancel → 200"
                            + (f" reason='{body.get('reason')}'" if body.get("reason") else ""))
    return {"session_id": cid, "status": "cancelled"}


@shop.get("/acp/reoffers/{ref}")
def reoffer(ref: str, x_agent_journey: str = Header(default="")):
    """Agents poll here. The shop asks Handshake what to say."""
    jid = _journey(x_agent_journey)
    client = CLIENT.client
    offer = client.get_reoffer(ref) if client else None
    SHOP.note(jid, f"GET /acp/reoffers/{ref} → {'200 offer ' + offer['type'] if offer else '404'}")
    if not offer:
        return JSONResponse({"pending": False}, 404)
    return {"pending": True, "offer": offer}


# ------------------------------------------------------------------ webhook ---

def _apply(directive):
    a = directive.get("merchant_action") or {}
    jid = directive.get("journey_id", "-")
    kind = a.get("type")
    if kind == "patch_catalog":
        SHOP.patches.setdefault(jid, {}).setdefault(a["sku"], {}).update(a.get("set") or {})
        return f"patched {a['sku']} with {', '.join(a.get('set') or {})}"
    if kind == "disambiguate":
        SHOP.withdrawn.setdefault(jid, set()).add(a.get("collides_with"))
        return f"withdrew duplicate listing {a.get('collides_with')}"
    if kind == "structure_policy":
        SHOP.policies.setdefault(jid, {})[a["sku"]] = a["policy"]
        return f"published structured returns policy for {a['sku']}"
    if kind == "repair_fulfilment":
        SHOP.serviceable.setdefault(jid, set()).add(a["sku"])
        return f"restored delivery to {a.get('pincode')} for {a['sku']}"
    if kind == "price_lock":
        s = SHOP.sessions.get(a.get("checkout_id"))
        if s:
            s["locked_total"] = a["locked_total"]
        return f"locked {a.get('checkout_id')} at ₹{a['locked_total']:,.2f}"
    if kind == "issue_approval":
        SHOP.approvals[a["approval_token"]] = a["checkout_id"]
        return f"armed a single-use approval for {a['checkout_id']}"
    if kind in ("schedule_retry", "offer_alternate_instrument"):
        SHOP.resolve(jid, "insufficient_funds", "silent_decline")
        return "payment retry armed"
    if kind == "approved_offer":
        if a.get("action") == "retry":
            SHOP.resolve(jid)                  # the merchant fixed what broke
        change = a.get("merchant_change") or ""
        return f"approved {a.get('action')}" + (f" · noted: {change[:80]}" if change else "")
    if kind == "none":
        return "nothing to change on the shop side"
    return f"logged {kind or 'event'}"


@shop.post("/webhooks/handshake")
async def handshake_webhook(request: Request):
    raw = await request.body()
    try:
        event = verify_webhook(raw, request.headers.get("handshake-signature", ""),
                               SHOP.webhook_secret)
    except WebhookSignatureError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    data = event.get("data") or {}
    jid = data.get("journey_id") or "-"
    if event["type"] == "recovery.directive":
        did = _apply(data)
        SHOP.note(jid, f"webhook recovery.directive {data.get('intervention')} → applied: {did}",
                  "webhook")
    else:
        SHOP.note(jid, f"webhook {event['type']} → acknowledged", "webhook")
    return {"ok": True}


# ----------------------------------------------------------------- admin ---
#
# The merchant's back office. What is set here is the store's real state: it is
# not passed to agents, not passed to Handshake, and not recorded per run. An
# agent that shops afterwards simply meets it, as it would meet a real store.

STORE_PROBLEMS = {
    "missing_attribute": "drop a required spec from the listing",
    "prose_policy": "returns policy as a paragraph of prose",
    "variant_collision": "list it twice, identically",
    "slow_delivery": "ships in 9 days (the feed doesn't say)",
    "out_of_stock": "sells out at checkout",
    "price_drift": "price rises 9% at re-quote",
    "shipping_fee": "add a ₹149 shipping fee at re-quote",
    "unserviceable": "can't confirm delivery to any pincode",
    "unsupported_payment": "refuse UPI Reserve mandates",
    "otp_wall": "demand an OTP at payment",
    "flaky_error": "fail payment once with a 503",
    "insufficient_funds": "decline payment for funds",
    "silent_decline": "decline payment with no reason code",
}


def store_config():
    return {"global": sorted(SHOP.store["global"]),
            "products": {k: sorted(v) for k, v in SHOP.store["products"].items() if v},
            "problems": STORE_PROBLEMS, "product_scoped": sorted(PRODUCT_SCOPED),
            "store_wide": sorted(STORE_WIDE),
            "catalogue": [{"sku": p["sku"], "title": p["title"], "category": p["category"],
                           "price": p["price"]} for p in PIM]}


@shop.get("/admin/api/config")
def get_store_config():
    return store_config()


@shop.put("/admin/api/config")
async def put_store_config(request: Request):
    body = await request.json()
    glob = {c for c in body.get("global") or [] if c in STORE_WIDE}
    products = {}
    for sku, conds in (body.get("products") or {}).items():
        if pim(sku) is None:
            return JSONResponse({"error": f"unknown sku {sku!r}"}, 422)
        products[sku] = {c for c in conds if c in PRODUCT_SCOPED}
    SHOP.store = {"global": glob, "products": products}
    return store_config()


@shop.get("/admin", response_class=HTMLResponse)
def admin_page():
    from pathlib import Path
    return HTMLResponse((Path(__file__).resolve().parents[1] / "web" / "store_admin.html").read_text())


# --------------------------------------------------------------- storefront ---

@shop.get("/", response_class=HTMLResponse)
def storefront():
    cards = "".join(
        f"<div class='c'><div class='sku'>{p['sku']}</div><h3>{p['title']}</h3>"
        f"<div class='p'>₹{p['price']:,.0f}</div><ul>"
        + "".join(f"<li><span>{k.replace('_', ' ')}</span>{v}</li>"
                  for k, v in p["attributes"].items())
        + "</ul></div>" for p in PIM)
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Kaveri Home &amp; Tech</title><style>
body{{margin:0;font:15px/1.5 Inter,system-ui,sans-serif;background:#faf7f2;color:#2a2118}}
header{{padding:22px 28px;background:#3b2a1a;color:#fbe9d0}} header b{{font-size:20px}}
header p{{margin:4px 0 0;opacity:.75;font-size:13px}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;padding:24px 28px}}
.c{{background:#fff;border:1px solid #eadfcf;border-radius:12px;padding:16px}}
.sku{{font:12px ui-monospace,monospace;color:#a08a6e}} h3{{margin:4px 0 6px;font-size:16px}}
.p{{font-weight:700;font-size:18px}} ul{{list-style:none;padding:0;margin:10px 0 0;font-size:13px}}
li{{display:flex;justify-content:space-between;border-top:1px dashed #eee;padding:3px 0}} li span{{color:#8a7a66}}
footer{{padding:0 28px 28px;font-size:13px;color:#8a7a66}}</style>
<header><b>Kaveri Home &amp; Tech</b><p>A fictional demo merchant. Agents shop at <code>/shop/acp/*</code>; this page is for people.</p></header>
<main>{cards}</main>
<footer>Instrumented with the Handshake SDK · <a href="/demo">watch an agent shop here</a></footer>"""


def configure(client, webhook_secret):
    CLIENT.client = client
    SHOP.webhook_secret = webhook_secret


def sync(client):
    client.put_schema(SCHEMA)
    return client.sync_catalog(all_products())
