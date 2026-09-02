"""Buyer agent (component C2).

The agent is an external actor: it sees only what the merchant exposes and
decides for itself whether to proceed. Nothing it "thinks" is written to the
trace — the trace holds merchant-observable API traffic only, which is all a
real merchant would ever have to diagnose from.

Two backends:
  heuristic  deterministic decision policy driven by the persona's risk posture
  llm        a real model makes the proceed/abandon judgement (needs an API key)
"""


from ..merchant.catalog import required_attributes
from .llm import (  # re-exported: the buyer fleet's model backend
    LLMBudgetExhausted, LLMDecider, _parse_decision)
from ..taxonomy import Terminal


class BuyerAgent:
    def __init__(self, persona, trace, rng, decider=None):
        self.p = persona
        self.trace = trace
        self.rng = rng
        self.decider = decider
        self.effective_cap = persona.cap
        self.session_id = None
        self.sku = None
        self.qty = 1
        self.instrument = dict(persona.instrument)

    # ---------- helpers ----------

    def _gross(self, view, qty=1):
        return round(view["price"] * qty * (1 + view["tax_rate"]), 2)

    def _ambiguous(self, feed, view):
        peers = [i for i in feed
                 if i["variant_group"] == view["variant_group"] and i["sku"] != view["sku"]]
        for peer in peers:
            if peer["attributes"] == view["attributes"] and peer["price"] == view["price"]:
                return True
        return False

    def _abandon(self, note, value):
        self.trace.close(Terminal.FAILED, value=value, note=note)
        return self.trace

    # ---------- journey ----------

    def run(self, merchant):
        ceiling = min(self.p.budget, self.p.cap)
        feed = merchant.get_feed(category=self.p.category, max_price=ceiling)
        affordable = [i for i in feed if self._gross(i) <= ceiling]
        if not affordable:
            return self.trace.close(Terminal.FAILED, 0.0, "no affordable candidate in feed")

        if merchant.injector.force_over_cap():
            view = max(affordable, key=lambda i: i["price"])
            self.effective_cap = round(self._gross(view) * 0.55, 2)
        else:
            view = self.rng.choice(affordable)

        self.sku = view["sku"]
        detail = merchant.get_product(self.sku) or view
        value = self._gross(detail, self.qty)
        self.trace.basket = [{"sku": self.sku, "title": detail.get("title", ""),
                              "category": detail.get("category", ""),
                              "qty": self.qty, "price": detail["price"]}]
        self.trace.basket_value = value

        required = required_attributes(detail["category"])
        missing = [a for a in required if a not in detail.get("attributes", {})]

        proceed = None
        if self.decider and self.decider.available():
            proceed = self.decider.decide(self.p, detail, required)

        if proceed is False:
            return self._abandon("no checkout session opened after product fetch", value)

        if proceed is None:
            if missing and self.p.rules["needs_all_attributes"]:
                return self._abandon("no checkout session opened after product fetch", value)
            if self._ambiguous(feed, detail) and self.p.posture != "permissive":
                return self._abandon("no checkout session opened after product fetch", value)
            if (not detail["policy"].get("structured", True)
                    and self.p.rules["needs_structured_policy"]):
                return self._abandon("no checkout session opened after product fetch", value)

        return self._checkout(merchant, value)

    def _checkout(self, merchant, value):
        status, body = merchant.create_checkout_session(
            self.sku, self.qty, self.p.pincode, declared_cap=self.effective_cap)
        if status != 200:
            return self._abandon("checkout session refused by merchant", value)

        self.session_id = body["session_id"]
        created_total = body["total"]

        status, body = merchant.update_checkout_session(self.session_id)
        total = body["total"]
        self.trace.basket_value = total

        if created_total > 0:
            drift = (total - created_total) / created_total
            if drift > self.p.rules["drift_tolerance"]:
                return self._abandon("session updated then left open", total)

        if total > self.effective_cap:
            return self._abandon("session left open above declared cap", total)

        return self._complete(merchant, total)

    def _complete(self, merchant, total, allow_retry=True):
        status, body = merchant.complete_checkout_session(self.session_id, self.instrument)
        if status == 200:
            return self.trace.close(Terminal.CONVERTED, value=body["total"])
        if status == 401:
            return self._abandon("completion refused, authentication required", total)
        if status == 503:
            if allow_retry and self.p.rules["retries_ambiguous_error"]:
                self.instrument["retry"] = True
                return self._complete(merchant, total, allow_retry=False)
            return self._abandon("completion abandoned after processing error", total)
        return self._abandon("payment attempt failed", total)

    # ---------- recovery ----------

    def respond_to_reoffer(self, merchant, offer):
        """Re-evaluate after the recovery layer has acted. Returns the trace."""
        merchant.get_reoffer(self.session_id or "none")
        kind = offer.get("intervention")

        if kind in ("I-01", "I-02", "I-07"):
            detail = merchant.get_product(offer.get("sku", self.sku)) or {}
            if not detail:
                return None
            self.sku = offer.get("sku", self.sku)
            return self._checkout(merchant, self._gross(detail, self.qty))

        if kind == "I-03":
            status, body = merchant.update_checkout_session(self.session_id)
            total = body["total"]
            if total > self.effective_cap:
                return None
            return self._complete(merchant, total)

        if kind == "I-04":
            self.qty = offer["qty"]
            self.sku = offer["sku"]
            detail = merchant.get_product(self.sku)
            status, body = merchant.create_checkout_session(
                self.sku, self.qty, self.p.pincode, declared_cap=self.effective_cap)
            if status != 200:
                return None
            self.session_id = body["session_id"]
            status, body = merchant.update_checkout_session(self.session_id)
            if body["total"] > self.effective_cap:
                return None
            return self._complete(merchant, body["total"])

        if kind == "I-05":
            if self.rng.random() > self.p.rules["consent_probability"]:
                return None                      # principal declined
            self.effective_cap = offer["new_cap"]
            status, body = merchant.update_checkout_session(self.session_id)
            return self._complete(merchant, body["total"])

        if kind == "I-06":
            if self.rng.random() > self.p.rules["consent_probability"]:
                return None
            self.instrument["human_approval_token"] = offer["token"]
            status, body = merchant.update_checkout_session(self.session_id)
            return self._complete(merchant, body["total"])

        if kind == "I-08":
            self.instrument = {"type": offer["instrument"], "state": "active", "retry": True}
            status, body = merchant.update_checkout_session(self.session_id)
            return self._complete(merchant, body["total"])

        if kind == "I-09":
            self.instrument["retry"] = True
            self.instrument.pop("mandate", None) if offer.get("drop_mandate") else None
            status, body = merchant.update_checkout_session(self.session_id)
            return self._complete(merchant, body["total"])

        return None
