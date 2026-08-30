"""Intervention executor (component C6).

Executes exactly one intervention per permit, records the concession it cost
and the path by which it could be reversed. It acts only on a permit issued by
the policy engine; it contains no decision logic of its own.
"""

import time
import uuid


class Outcome:
    def __init__(self, ok, offer=None, concession=0.0, note="", reversal=None,
                 mandate_retry=False):
        self.ok = ok
        self.offer = offer
        self.concession = concession
        self.note = note
        self.reversal = reversal or {}
        self.mandate_retry = mandate_retry

    def as_dict(self):
        return {"ok": self.ok, "note": self.note,
                "concession": round(self.concession, 2),
                "offer": {k: v for k, v in (self.offer or {}).items() if k != "token"}}


def _true_record(merchant, sku):
    return merchant.find(sku)


def execute(verdict, diagnosis, trace, merchant, agent, cfg):
    iid = verdict.intervention_id
    sku = agent.sku
    session = merchant.sessions.get(agent.session_id)
    truth = _true_record(merchant, sku or "")

    # ---- I-01 catalogue delta ------------------------------------------
    if iid == "I-01":
        if diagnosis.cause == "A8":
            if not truth:
                return Outcome(False, note="no catalogue record to repair")
            merchant.fulfilment_patches[truth["sku"]] = dict(truth["fulfilment"])
            return Outcome(True, {"intervention": "I-01", "sku": sku},
                           note="fulfilment data repaired from source record")
        attr = diagnosis.detail.get("missing_attribute")
        if not truth or not attr:
            return Outcome(False, note="missing attribute could not be sourced")
        merchant.catalog_patches.setdefault(truth["sku"], {})[attr] = truth["attributes"][attr]
        return Outcome(True, {"intervention": "I-01", "sku": sku, "attribute": attr},
                       note=f"catalogue patched with {attr}")

    # ---- I-02 disambiguated re-offer -----------------------------------
    if iid == "I-02":
        if not truth:
            return Outcome(False, note="variant group not found")
        merchant.forced_variant[truth["variant_group"]] = truth["sku"]
        return Outcome(True, {"intervention": "I-02", "sku": truth["sku"]},
                       note="variant collision resolved to a single SKU")

    # ---- I-03 price lock -----------------------------------------------
    if iid == "I-03":
        if session is None:
            return Outcome(False, note="session not found")
        original = diagnosis.detail.get("quoted")
        current = diagnosis.detail.get("requoted")
        if original is None or current is None:
            return Outcome(False, note="no quote pair on record")
        concession = max(0.0, current - original)
        session.quoted_price = round(original / (session.qty * (1 + session.product["tax_rate"])), 2)
        session.price_locked_until = time.time() + cfg.policy.price_lock_ttl_minutes * 60
        return Outcome(True, {"intervention": "I-03", "locked_total": original},
                       concession=concession,
                       note=f"original quote honoured for {cfg.policy.price_lock_ttl_minutes} min",
                       reversal={"method": "quote_expiry",
                                 "window_minutes": cfg.policy.price_lock_ttl_minutes})

    # ---- I-04 bundle resize --------------------------------------------
    if iid == "I-04":
        cap = agent.effective_cap
        candidates = [p for p in merchant.peek_feed(category=truth["category"])] if truth else []
        fits = [p for p in candidates
                if p["price"] * (1 + p["tax_rate"]) <= cap and p["sku"] == sku]
        if fits:
            return Outcome(True, {"intervention": "I-04", "sku": sku, "qty": 1},
                           note="quantity reduced to fit the declared cap")
        alt = sorted([p for p in candidates if p["price"] * (1 + p["tax_rate"]) <= cap],
                     key=lambda p: -p["price"])
        if not alt:
            return Outcome(False, note="no compliant basket exists under the cap")
        return Outcome(True, {"intervention": "I-04", "sku": alt[0]["sku"], "qty": 1},
                       note=f"compliant basket offered at or below cap ({alt[0]['sku']})")

    # ---- I-05 reserve uplift request -----------------------------------
    if iid == "I-05":
        total = diagnosis.detail.get("basket_total") or trace.at_risk_value
        return Outcome(True, {"intervention": "I-05", "new_cap": round(total, 2),
                              "requires_consent": True},
                       note="uplift requested from the principal; never self-granted",
                       reversal={"method": "consent_withdrawal"})

    # ---- I-06 human approval link --------------------------------------
    if iid == "I-06":
        if diagnosis.cause == "B3":
            merchant.injector.resolve()
        return Outcome(True, {"intervention": "I-06", "token": uuid.uuid4().hex,
                              "expires_in_minutes": 15, "single_use": True},
                       note="single-use approval link issued to the principal",
                       reversal={"method": "token_expiry", "window_minutes": 15})

    # ---- I-07 structured policy ----------------------------------------
    if iid == "I-07":
        if not truth:
            return Outcome(False, note="policy source record not found")
        merchant.policy_patches[truth["sku"]] = dict(truth["policy"])
        return Outcome(True, {"intervention": "I-07", "sku": truth["sku"]},
                       note="returns and warranty served as machine-readable fields")

    # ---- I-08 alternate instrument -------------------------------------
    if iid == "I-08":
        merchant.injector.resolve() if diagnosis.cause == "B5" else None
        return Outcome(True, {"intervention": "I-08", "instrument": "card_token"},
                       note="re-attempted on an alternate instrument")

    # ---- I-09 scheduled retry ------------------------------------------
    if iid == "I-09":
        cause = diagnosis.cause
        if cause in ("B1", "B2"):
            # Funds arriving or an issuer recovering is probabilistic, not certain.
            if merchant.injector.rng.random() < (0.55 if cause == "B1" else 0.8):
                merchant.injector.resolve()
            return Outcome(True, {"intervention": "I-09", "drop_mandate": False},
                           note="retry scheduled inside the permitted cap and cooldown",
                           mandate_retry=True)
        return Outcome(True, {"intervention": "I-09", "drop_mandate": False},
                       note="request re-attempted after a transient error")

    # ---- I-10 escalate to operations -----------------------------------
    if iid == "I-10":
        return Outcome(True, None, note="routed to the operations queue as an exception")

    return Outcome(False, note=f"unimplemented intervention {iid}")
