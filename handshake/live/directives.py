"""What a permitted intervention asks for, in a live deployment.

In the simulator the executor reaches into the merchant object and patches it.
A real Handshake cannot reach into a merchant's product database, and should
not be able to. So a permit becomes a directive with two halves:

  merchant_action   what the shop should change on its side, delivered by a
                    signed webhook. The shop applies it, or doesn't.
  reoffer           what the agent will be told when it polls for a re-offer.
                    Built from the merchant's own synced catalogue, so the agent
                    gets the repaired record even before the shop's feed is fixed.

A builder returns None when it cannot construct a truthful directive — the
missing value is not in the catalogue, no basket fits under the cap — and the
pipeline moves to the cause's next intervention, then to a human.
"""

import secrets
import uuid

from ..taxonomy import INTERVENTIONS


def _price_with_tax(p, qty=1):
    return round(p.get("price", 0) * qty * (1 + p.get("tax_rate", 0)), 2)


def _i01(dg, j, ctx):
    d = dg["detail"]
    if dg["cause"] == "A8":
        truth = ctx["product"](d.get("sku", "")) or {}
        ful = truth.get("fulfilment") or {}
        if not ful.get("serviceable_pincodes"):
            return None
        return ({"type": "repair_fulfilment", "sku": d["sku"], "pincode": d.get("pincode"),
                 "fulfilment": ful},
                {"type": "fulfilment_confirmed", "sku": d["sku"], "pincode": d.get("pincode"),
                 "ships_in_days": ful.get("ships_in_days"),
                 "message": f"Delivery to {d.get('pincode')} is confirmed for {d['sku']}."},
                0.0)
    values = d.get("source_values") or {}
    if not values:
        return None
    return ({"type": "patch_catalog", "sku": d["sku"], "set": values},
            {"type": "catalogue_delta", "sku": d["sku"], "attributes": values,
             "message": "The product record now includes " + ", ".join(
                 f"{k} = {v}" for k, v in values.items()) + "."},
            0.0)


def _i02(dg, j, ctx):
    d = dg["detail"]
    me, twin = ctx["product"](d.get("sku", "")), ctx["product"](d.get("collides_with", ""))
    if not me:
        return None
    return ({"type": "disambiguate", "sku": d["sku"], "collides_with": d.get("collides_with"),
             "keep": d["sku"]},
            {"type": "disambiguated", "sku": d["sku"], "title": me.get("title"),
             "attributes": me.get("attributes"),
             "withdrawn": d.get("collides_with") if twin else None,
             "message": f"{d['sku']} is the single listing for this product."},
            0.0)


def _i03(dg, j, ctx):
    d = dg["detail"]
    if d.get("quoted") is None or d.get("requoted") is None:
        return None
    ttl = ctx["policy"].price_lock_ttl_minutes
    concession = round(max(0.0, d["requoted"] - d["quoted"]), 2)
    return ({"type": "price_lock", "checkout_id": j["checkout_id"],
             "locked_total": d["quoted"], "ttl_minutes": ttl},
            {"type": "price_lock", "checkout_id": j["checkout_id"],
             "locked_total": d["quoted"], "ttl_minutes": ttl,
             "message": f"The original quote of ₹{d['quoted']:,.2f} is honoured for {ttl} minutes."},
            concession)


def _i04(dg, j, ctx):
    d = dg["detail"]
    cap = d.get("declared_cap")
    me = ctx["product"](d.get("sku", ""))
    if cap is None or not me:
        return None
    fits = [p for p in ctx["catalog"]()
            if p.get("category") == me.get("category") and p.get("stock", 1) > 0
            and _price_with_tax(p) <= cap]
    if not fits:
        return None
    # Closest to what the agent wanted: the most capable item that still fits.
    best = max(fits, key=lambda p: p.get("price", 0))
    total = _price_with_tax(best)
    return ({"type": "none"},
            {"type": "compliant_basket", "sku": best["sku"], "title": best.get("title"),
             "qty": 1, "total": total, "declared_cap": cap,
             "attributes": best.get("attributes"),
             "message": f"{best.get('title', best['sku'])} at ₹{total:,.2f} fits under your "
                        f"₹{cap:,.0f} cap."},
            0.0)


def _i05(dg, j, ctx):
    d = dg["detail"]
    if d.get("basket_total") is None:
        return None
    return ({"type": "none"},
            {"type": "cap_uplift_request", "requested_cap": d["basket_total"],
             "current_cap": d.get("declared_cap"), "requires_consent": True,
             "message": "Ask your owner to approve a higher limit. Handshake never raises "
                        "a cap itself."},
            0.0)


def _i06(dg, j, ctx):
    token = secrets.token_urlsafe(18)
    return ({"type": "issue_approval", "checkout_id": j["checkout_id"],
             "approval_token": token, "expires_in_minutes": 15, "single_use": True},
            {"type": "approval_link", "checkout_id": j["checkout_id"],
             "approval_token": token, "expires_in_minutes": 15, "single_use": True,
             "message": "Relay this single-use approval to your owner; complete with the "
                        "token once they approve."},
            0.0)


def _i07(dg, j, ctx):
    truth = ctx["product"](dg["detail"].get("sku", "")) or {}
    policy = truth.get("policy")
    if not isinstance(policy, dict) or policy.get("returns_days") is None:
        return None
    policy = {k: v for k, v in policy.items() if k != "text"}
    policy["structured"] = True
    return ({"type": "structure_policy", "sku": dg["detail"]["sku"], "policy": policy},
            {"type": "structured_policy", "sku": dg["detail"]["sku"], "policy": policy,
             "message": f"Returns: {policy.get('returns_days')} days. Warranty: "
                        f"{policy.get('warranty_months', '—')} months."},
            0.0)


def _i08(dg, j, ctx):
    return ({"type": "offer_alternate_instrument", "checkout_id": j["checkout_id"]},
            {"type": "alternate_instrument", "checkout_id": j["checkout_id"],
             "methods": ["upi_intent", "card_token"],
             "message": "Retry this checkout on a different payment method."},
            0.0)


def _i09(dg, j, ctx):
    wait = 0 if dg["cause"] == "A6" else ctx["settings"].get("retry_after_seconds", 900)
    return ({"type": "schedule_retry", "checkout_id": j["checkout_id"],
             "retry_after_seconds": wait},
            {"type": "retry", "checkout_id": j["checkout_id"], "retry_after_seconds": wait,
             "message": "That error was temporary. Retry the payment" +
                        (f" after {wait // 60} minutes." if wait else " now.")},
            0.0)


def _i10(dg, j, ctx):
    return ({"type": "escalate", "reason": dg.get("explanation", "")}, None, 0.0)


BUILDERS = {"I-01": _i01, "I-02": _i02, "I-03": _i03, "I-04": _i04, "I-05": _i05,
            "I-06": _i06, "I-07": _i07, "I-08": _i08, "I-09": _i09, "I-10": _i10}


def build(intervention_id, diagnosis, journey, ctx):
    built = BUILDERS[intervention_id](diagnosis, journey, ctx)
    if built is None:
        return None
    action, reoffer, concession = built
    spec = INTERVENTIONS[intervention_id]
    reversal = {}
    if intervention_id == "I-03":
        reversal = {"method": "quote_expiry", "window_minutes": action["ttl_minutes"]}
    elif intervention_id == "I-06":
        reversal = {"method": "token_expiry", "window_minutes": 15}
    elif intervention_id == "I-05":
        reversal = {"method": "consent_withdrawal"}
    return {"directive_id": f"dir_{uuid.uuid4().hex[:14]}",
            "intervention": intervention_id, "name": spec.name,
            "mechanism": spec.mechanism, "rung": spec.rung,
            "touches_human": spec.touches_human, "concedes_margin": spec.concedes_margin,
            "concession": concession, "merchant_action": action, "reoffer": reoffer,
            "reversal": reversal}
