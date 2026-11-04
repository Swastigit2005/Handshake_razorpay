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
from . import money


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
             "message": f"The original quote of {money.fmt(d['quoted'], d.get('currency'))} is "
                        f"honoured for {ttl} minutes."},
            concession)


def passed_over(dg, j, ctx):
    """What the agent's choice reveals, when it picked an item listed above its
    cap while cheaper ones of the same kind were in front of it: it was not
    choosing on price. Returns (skipped skus, {facet: floor}) — the cheaper
    items it saw and skipped, and, for each facet on which its pick beat all
    of them, the value an alternative has to beat too. Empty when the pick
    looked affordable (tax or shipping pushed it over), so any cheaper item is
    a fair offer."""
    from .detectors import LOWER_IS_BETTER, current_attempt, facets
    d = dg["detail"]
    cap, me = d.get("declared_cap"), ctx["product"](d.get("sku", ""))
    if cap is None or not me or me.get("price", 0) <= cap or "events" not in ctx:
        return set(), {}
    seen = set()
    for e in current_attempt(ctx["events"]())[0]:
        if e["type"] == "feed.read":
            seen.update(i.get("sku") for i in (e.get("response") or {}).get("items") or [])
        elif e["type"] == "product.view" and e.get("http_status") == 200:
            seen.add(e.get("sku") or (e.get("request") or {}).get("sku"))
    skipped = []
    for sku in seen - {me["sku"], None}:
        p = ctx["product"](sku)
        if p and p.get("category") == me.get("category") and p.get("price", 0) < me["price"]:
            skipped.append(p)
    mine, floors = facets(me), {}
    for facet, value in mine.items():
        theirs = [facets(p).get(facet) for p in skipped]
        theirs = [v for v in theirs if v is not None]
        lower = facet in LOWER_IS_BETTER
        if theirs and all((value < v) if lower else (value > v) for v in theirs):
            floors[facet] = (min if lower else max)(theirs)
    return {p["sku"] for p in skipped}, floors


def _meets(p, floors):
    from .detectors import LOWER_IS_BETTER, facets
    have = facets(p)
    return all(have.get(f) is not None and
               ((have[f] < v) if f in LOWER_IS_BETTER else (have[f] > v))
               for f, v in floors.items())


def _i04(dg, j, ctx):
    d = dg["detail"]
    cap = d.get("declared_cap")
    me = ctx["product"](d.get("sku", ""))
    if cap is None or not me:
        return None
    skipped, floors = passed_over(dg, j, ctx)
    fits = [p for p in ctx["catalog"]()
            if p.get("category") == me.get("category") and p.get("stock", 1) > 0
            and _price_with_tax(p) <= cap and p["sku"] not in skipped and _meets(p, floors)]
    if not fits:
        return None
    # Closest to what the agent wanted: the most capable item that still fits.
    best = max(fits, key=lambda p: p.get("price", 0))
    total = _price_with_tax(best)
    return ({"type": "none"},
            {"type": "compliant_basket", "sku": best["sku"], "title": best.get("title"),
             "qty": 1, "total": total, "declared_cap": cap,
             "attributes": best.get("attributes"),
             "message": f"{best.get('title', best['sku'])} at "
                        f"{money.fmt(total, best.get('currency') or d.get('currency'))} fits under "
                        f"your {money.fmt(cap, best.get('currency') or d.get('currency'), 0)} cap."},
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


def _i11(dg, j, ctx):
    # Never built automatically. An outside-the-playbook cause reaches the agent
    # only through approve(), after a person has read the draft.
    return None


BUILDERS = {"I-01": _i01, "I-02": _i02, "I-03": _i03, "I-04": _i04, "I-05": _i05,
            "I-06": _i06, "I-07": _i07, "I-08": _i08, "I-09": _i09, "I-10": _i10,
            "I-11": _i11}


# --------------------------------------------------------------- proposals ---
#
# For a journey the gate would not act on by itself — an open-ended cause, or a
# hypothesis below the confidence bar — Handshake still drafts the recovery it
# would try, so the person reviewing it approves or edits instead of starting
# from a blank page. Drafts are built from the merchant's own catalogue; the
# analyst's suggestion is used only after it has been validated against it.

def _alternative(ctx, sku, better=None):
    me = ctx["product"](sku) or {}
    pool = [p for p in ctx["catalog"]()
            if p.get("category") == me.get("category") and p.get("sku") != sku
            and p.get("stock", 1) > 0]
    if better:
        pool = [p for p in pool if better(p)]
    if not pool:
        return None
    price = me.get("price", 0)
    return min(pool, key=lambda p: abs(p.get("price", 0) - price))


def propose(dg, journey, ctx):
    d = dg.get("detail") or {}
    if d.get("self_report_only") or dg.get("cause") in (None, "UNKNOWN"):
        return None
    if d.get("proposal"):                                   # the analyst's, validated
        return dict(d["proposal"])
    sku = d.get("sku") or journey.get("sku") or ""

    if dg["cause"] == "N2":
        from .detectors import LOWER_IS_BETTER, facets
        facet, served = d["facet"], d["served"]

        def better(p):
            v = facets(p).get(facet)
            return v is not None and (v < served if facet in LOWER_IS_BETTER else v > served)

        alt = _alternative(ctx, sku, better)
        if alt is None:
            return {"action": "information", "source": "rules",
                    "message": "", "merchant_change":
                    f"No listing beats {sku} on {facet.replace('_', ' ')}. Improve it on "
                    f"{sku} itself (currently {served})."}
        val = facets(alt).get(facet)
        nice = facet.replace("_", " ")
        return {"action": "alternative_product", "sku": alt["sku"], "source": "rules",
                "message": f"{alt.get('title', alt['sku'])} ({alt['sku']}) has {nice} {val}, "
                           f"against {served} on {sku}.",
                "merchant_change": f"{sku}'s {nice} ({served}) is the weakest in its "
                                   "category; agents that check it walk away."}

    if dg["cause"] == "A4" and d.get("declared_cap") is not None:
        me = ctx["product"](sku) or {}
        _, floors = passed_over(dg, journey, ctx)
        cur = d.get("currency") or me.get("currency")
        cap, total = d["declared_cap"], d.get("basket_total")
        need = ", ".join(f"{f.replace('_', ' ')} beyond {v}" for f, v in floors.items())
        gap = f" ({money.fmt(total - cap, cur)} off)" if total is not None else ""
        return {"action": "information", "source": "rules", "message": "",
                "merchant_change":
                    f"Nothing in stock fits this agent's {money.fmt(cap, cur, 0)} cap"
                    + (f" and what it chose {me.get('title', sku)} for ({need})" if need else "")
                    + f". {me.get('title', sku)} at {money.fmt(cap, cur)}{gap} would have sold."}

    if dg["cause"] == "N1":
        text = f"{d.get('error', '')} {d.get('detail', '')}".lower()
        if any(w in text for w in ("payment", "instrument", "method", "upi", "card")):
            return {"action": "alternate_instrument", "methods": ["card_token", "upi_intent"],
                    "source": "rules",
                    "message": "That payment method isn't accepted here. Card and UPI intent "
                               "both work; please retry with one of them.",
                    "merchant_change": f"Agents arrive with methods your checkout rejects "
                                       f"('{d.get('error')}'). Accept them, or list accepted "
                                       "methods in the feed."}
        if "stock" in text or "available" in text:
            alt = _alternative(ctx, sku)
            if alt:
                return {"action": "alternative_product", "sku": alt["sku"], "source": "rules",
                        "message": f"{sku} sold out at checkout. {alt.get('title', alt['sku'])} "
                                   f"({alt['sku']}) is in stock at "
                                   f"{money.fmt(alt.get('price', 0), alt.get('currency'), 0)}.",
                        "merchant_change": f"{sku} was listed as available but refused at "
                                           "checkout. Sync stock to the feed."}
        return {"action": "retry", "source": "rules",
                "message": "That error has been fixed on our side. Please try again.",
                "merchant_change": f"Investigate {d.get('status')} '{d.get('error')}' on "
                                   f"{d.get('step', 'this step')} before approving."}
    return None


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
