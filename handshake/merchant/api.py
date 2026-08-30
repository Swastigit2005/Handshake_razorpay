"""Merchant simulator (component C1).

An ACP-shaped surface: a machine-readable feed, checkout session create/update/
complete, and a re-offer channel the recovery layer writes into. Called
in-process by the batch runner and wrapped over HTTP by merchant/http.py.
"""

import time
import uuid

from .catalog import required_attributes


class CheckoutSession:
    def __init__(self, sid, product, qty, pincode):
        self.id = sid
        self.product = product
        self.qty = qty
        self.pincode = pincode
        self.created_at = time.time()
        self.state = "open"
        self.quoted_price = product["price"]
        self.price_locked_until = 0.0
        self.reoffer = None
        self.completed_ref = ""

    def totals(self, price=None):
        unit = price if price is not None else self.quoted_price
        sub = round(unit * self.qty, 2)
        tax = round(sub * self.product["tax_rate"], 2)
        return {"unit_price": unit, "subtotal": sub, "tax": tax,
                "total": round(sub + tax, 2), "currency": "INR"}


class MerchantAPI:
    def __init__(self, catalog, injector, payments, trace):
        self.catalog = catalog
        self.injector = injector
        self.payments = payments
        self.trace = trace
        self.sessions = {}
        self.catalog_patches = {}   # sku -> {attribute: value}, written by I-01
        self.policy_patches = {}    # sku -> structured policy, written by I-07
        self.forced_variant = {}    # variant_group -> sku, written by I-02
        self.fulfilment_patches = {}  # sku -> fulfilment record, written by I-01

    # ---------- discovery ----------

    def _view(self, product):
        """The product record as an agent sees it, after faults and patches."""
        req = required_attributes(product["category"])
        p = self.injector.degrade_product(product, req)
        patch = self.catalog_patches.get(product["sku"])
        if patch:
            p["attributes"].update(patch)
            p.pop("_missing_attribute", None)
        pol = self.policy_patches.get(product["sku"])
        if pol:
            p["policy"] = pol
        ful = self.fulfilment_patches.get(product["sku"])
        if ful:
            p["fulfilment"] = ful
        return p

    def get_feed(self, category=None, max_price=None):
        t0 = time.perf_counter()
        items = []
        for product in self.catalog:
            if category and product["category"] != category:
                continue
            if max_price is not None and product["price"] > max_price:
                continue
            if product["stock"] <= 0:
                continue
            view = self._view(product)
            items.append(view)
            twin = self.injector.sibling_variant(product)
            if twin and self.forced_variant.get(product["variant_group"]) is None:
                items.append(self._view(twin))
        self.trace.event("GET /feed.json",
                         {"category": category, "max_price": max_price},
                         {"count": len(items)},
                         latency_ms=(time.perf_counter() - t0) * 1000)
        return items

    def peek_feed(self, category=None):
        """Non-recording read of the current feed view (used by diagnosis)."""
        items = []
        for product in self.catalog:
            if category and product["category"] != category:
                continue
            if product["stock"] <= 0:
                continue
            items.append(self._view(product))
            twin = self.injector.sibling_variant(product)
            if twin and self.forced_variant.get(product["variant_group"]) is None:
                items.append(self._view(twin))
        return items

    def find(self, sku):
        base = sku.replace("-V2", "")
        return next((p for p in self.catalog if p["sku"] == base), None)

    def get_product(self, sku):
        for product in self.catalog:
            if product["sku"] == sku:
                view = self._view(product)
                self.trace.event(f"GET /products/{sku}", {"sku": sku},
                                 {"found": True, "price": view["price"]})
                return view
        self.trace.event(f"GET /products/{sku}", {"sku": sku}, {"found": False}, 404)
        return None

    # ---------- checkout ----------

    def create_checkout_session(self, sku, qty, pincode, declared_cap=None):
        t0 = time.perf_counter()
        product = next((p for p in self.catalog if p["sku"] == sku.replace("-V2", "")), None)
        if product is None:
            self.trace.event("POST /checkout_sessions", {"sku": sku}, {"error": "unknown_sku"}, 404)
            return 404, {"error": "unknown_sku"}

        view = self._view(product)
        serviceable = view["fulfilment"]["serviceable_pincodes"]
        if serviceable and pincode not in serviceable:
            serviceable = serviceable  # deliverable elsewhere, not here
        if not serviceable:
            body = {"error": "fulfilment_undetermined",
                    "detail": "no serviceable route for this address"}
            self.trace.event("POST /checkout_sessions",
                             {"sku": sku, "pincode": pincode}, body, 422,
                             (time.perf_counter() - t0) * 1000)
            return 422, body

        sid = f"cs_{uuid.uuid4().hex[:12]}"
        session = CheckoutSession(sid, view, qty, pincode)
        self.sessions[sid] = session
        body = {"session_id": sid, "sku": sku, "qty": qty,
                "fulfilment": {"ships_in_days": view["fulfilment"]["ships_in_days"]},
                **session.totals()}
        self.trace.event("POST /checkout_sessions",
                         {"sku": sku, "qty": qty, "pincode": pincode,
                          "declared_cap": declared_cap}, body, 200,
                         (time.perf_counter() - t0) * 1000)
        return 200, body

    def update_checkout_session(self, sid):
        session = self.sessions.get(sid)
        if session is None:
            return 404, {"error": "unknown_session"}
        drifted = self.injector.drift(session.product)
        if drifted is not None and time.time() > session.price_locked_until:
            session.quoted_price = drifted
        body = {"session_id": sid, **session.totals()}
        self.trace.event(f"POST /checkout_sessions/{sid}", {"session_id": sid}, body)
        return 200, body

    def complete_checkout_session(self, sid, instrument):
        session = self.sessions.get(sid)
        if session is None:
            return 404, {"error": "unknown_session"}
        totals = session.totals()

        if self.injector.requires_human_auth() and not instrument.get("human_approval_token"):
            body = {"error": "authentication_required",
                    "detail": "OTP or 3DS challenge must be completed by the account holder"}
            self.trace.event(f"POST /checkout_sessions/{sid}/complete",
                             {"amount": totals["total"]}, body, 401)
            return 401, body

        if self.injector.ambiguous_error() and not instrument.get("retry"):
            body = {"error": "processing_error", "detail": "request could not be completed"}
            self.trace.event(f"POST /checkout_sessions/{sid}/complete",
                             {"amount": totals["total"]}, body, 503)
            return 503, body

        forced = self.injector.mandate_outcome() if instrument.get("mandate") else None
        result = self.payments.charge(totals["total"], instrument, forced_reason=forced)
        if not result.ok:
            body = {"error": "payment_failed", "reason_code": result.reason_code,
                    "ref": result.ref}
            self.trace.event(f"POST /checkout_sessions/{sid}/complete",
                             {"amount": totals["total"], "instrument": instrument.get("type")},
                             body, 402)
            return 402, body

        session.state = "completed"
        session.completed_ref = result.ref
        body = {"session_id": sid, "status": "captured", "ref": result.ref, **totals}
        self.trace.event(f"POST /checkout_sessions/{sid}/complete",
                         {"amount": totals["total"], "instrument": instrument.get("type")}, body)
        return 200, body

    # ---------- recovery channel ----------

    def put_reoffer(self, sid, offer):
        session = self.sessions.get(sid)
        if session is not None:
            session.reoffer = offer
        return offer

    def get_reoffer(self, sid):
        session = self.sessions.get(sid)
        offer = session.reoffer if session else None
        self.trace.event(f"GET /reoffers/{sid}", {"session_id": sid},
                         offer or {"pending": False})
        return offer
