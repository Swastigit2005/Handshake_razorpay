"""Demo scenarios: one per way an agent purchase can stop.

A scenario sets two things and nothing else:

  mandate   what the agent's owner told it — the goal, a budget, a spending cap
  fault     how the shop misbehaves for this one journey

The fault is the shop's private business. It reaches the shop in a header the
SDK never forwards, so Handshake sees only the HTTP traffic that results — the
same position a real merchant is in. `expect` is what a correct diagnosis looks
like, used by the tests and shown on the demo page *after* the run.
"""

BASE_MANDATE = {
    "goal": "Buy an electric kettle, at least 1.5 litres, at least 1,200 W, with a "
            "warranty and a returns window of 7 days or more.",
    "category": "home_kitchen",
    "query": "kettle",
    "prefer_sku": "KET-170",
    "budget": 3000.0,
    "cap": 3000.0,
    "pincode": "560034",
    "needs": ["capacity_l", "power_watts", "warranty_months"],
    "min": {"capacity_l": 1.5, "power_watts": 1200},
    "min_returns_days": 7,
    "drift_tolerance": 0.03,
    "retries_errors": False,
    "instrument": {"type": "upi_reserve", "mandate": True},
}

SCENARIOS = {
    "missing_attribute": {
        "title": "A spec is missing from the listing",
        "story": "The shop's feed drops the kettle's wattage. A person would buy anyway; "
                 "the agent was told to verify it, so it can't.",
        "fault": "missing_attribute", "expect": "A1", "family": "catalogue",
    },
    "variant_collision": {
        "title": "Two listings look identical",
        "story": "The same kettle is listed twice with the same price and specs. The agent "
                 "can't tell which one its owner meant, so it buys neither.",
        "fault": "variant_collision", "expect": "A2", "family": "catalogue",
    },
    "price_drift": {
        "title": "The price moved mid-checkout",
        "story": "The checkout re-quotes 9% higher than the first quote. The agent's owner "
                 "allowed 3% drift, so it walks.",
        "fault": "price_drift", "expect": "A3", "family": "checkout",
    },
    "over_cap": {
        "title": "Basket is over the spending cap",
        "story": "The owner capped the agent at ₹2,000. The 1.7 L kettle comes to ₹2,358.82 "
                 "with tax. The agent is not allowed to go over.",
        "fault": None, "mandate": {"cap": 2000.0}, "expect": "A4", "family": "checkout",
    },
    "otp_wall": {
        "title": "Payment needs an OTP",
        "story": "Payment demands a one-time password only the human owner can give. No "
                 "human is watching, so the agent stops.",
        "fault": "otp_wall", "expect": "A5", "family": "payment",
    },
    "flaky_error": {
        "title": "A temporary server error",
        "story": "Payment returns 503 once. A person presses Pay again; this agent treats "
                 "the error as final.",
        "fault": "flaky_error", "expect": "A6", "family": "payment",
    },
    "prose_policy": {
        "title": "Returns policy is a paragraph",
        "story": "Returns terms are a sentence of prose. The agent needs a number of days "
                 "it can check, so it won't buy.",
        "fault": "prose_policy", "expect": "A7", "family": "catalogue",
    },
    "unserviceable": {
        "title": "Can't confirm delivery",
        "story": "The shop's delivery table lost the agent's pincode, so checkout is "
                 "refused before it starts.",
        "fault": "unserviceable", "expect": "A8", "family": "checkout",
    },
    "insufficient_funds": {
        "title": "Not enough balance",
        "story": "The payment rail declines with insufficient_funds. The owner tops up a "
                 "moment later.",
        "fault": "insufficient_funds", "expect": "B1", "family": "payment",
    },
    "silent_decline": {
        "title": "Declined with no reason",
        "story": "The rail declines and gives no reason code. Handshake must not guess.",
        "fault": "silent_decline", "expect": "UNKNOWN", "family": "payment",
    },
    "false_claim": {
        "title": "The agent gives a false reason",
        "story": "Nothing is wrong. The agent cancels saying 'price_changed', the reason "
                 "that earns a discount. The traffic says otherwise.",
        "fault": "false_claim", "expect": "A3", "family": "trust",
    },
    "clean": {
        "title": "Nothing goes wrong",
        "story": "A healthy checkout, for contrast. The agent buys first time and Handshake "
                 "stays silent.",
        "fault": None, "expect": None, "family": "control",
    },
}


def mandate_for(name):
    sc = SCENARIOS[name]
    return {**BASE_MANDATE, **(sc.get("mandate") or {})}


# ---------------------------------------------------------------- mystery ---
#
# Nobody chooses what goes wrong. A random brief meets a shop with zero to two
# random hidden conditions, four of which no playbook entry covers. What the
# agent actually does — buy, or stop for whichever problem it hits first, or
# stop because nothing fits its brief — emerges from the two. The agent's own
# record of why it stopped is the ground truth Handshake is scored against.

CONDITIONS = ["missing_attribute", "variant_collision", "price_drift", "otp_wall",
              "flaky_error", "prose_policy", "unserviceable", "insufficient_funds",
              "silent_decline"]
OFF_PLAYBOOK = ["slow_delivery", "unsupported_payment", "out_of_stock", "shipping_fee"]

CONDITION_TEXT = {
    "missing_attribute": "the feed dropped a required spec from the {product}",
    "variant_collision": "the {product} was listed twice, identically",
    "price_drift": "the checkout re-quoted 9% higher",
    "otp_wall": "payment demanded an OTP",
    "flaky_error": "payment returned one 503",
    "prose_policy": "the {product}'s returns policy was prose",
    "unserviceable": "the delivery table lost the agent's pincode",
    "insufficient_funds": "the rail declined for funds",
    "silent_decline": "the rail declined with no reason code",
    "slow_delivery": "a warehouse transfer made the {product} ship in 9 days (not in the feed)",
    "unsupported_payment": "the shop refuses UPI Reserve mandates at payment",
    "out_of_stock": "the {product} sold out between listing and checkout",
    "shipping_fee": "a ₹149 shipping fee appeared only at re-quote",
}

# What a mystery shopper can be sent to buy. Each brief targets one product (the
# owner's favourite); product-scoped problems land on it. Caps straddle the
# target's price with 18% GST, so some briefs cannot afford it at all.
BRIEFS = [
    {"label": "an electric kettle", "product": "1.7 L kettle",
     "goal": "Buy an electric kettle, at least 1.5 litres and 1,200 W.",
     "category": "home_kitchen", "query": "kettle", "prefer_sku": "KET-170",
     "needs": ["capacity_l", "power_watts", "warranty_months"],
     "min": {"capacity_l": 1.5, "power_watts": 1200}, "rank": "capacity_l",
     "caps": [1900.0, 2400.0, 3000.0, 5000.0]},
    {"label": "wireless headphones", "product": "over-ear headphones",
     "goal": "Buy wireless headphones with at least 30 hours of battery.",
     "category": "audio", "query": "headphones", "prefer_sku": "HPH-045",
     "needs": ["driver_mm", "battery_hours", "codec_support"],
     "min": {"battery_hours": 30}, "rank": "battery_hours",
     "caps": [4500.0, 5000.0, 6000.0, 6000.0]},
    {"label": "a laptop stand", "product": "aluminium laptop stand",
     "goal": "Buy a laptop stand for a 15.6-inch laptop.",
     "category": "laptop_accessories", "query": "stand", "prefer_sku": "LST-AL1",
     "needs": ["compatibility", "material", "weight_g"], "min": {}, "rank": "weight_g",
     "caps": [2000.0, 2500.0, 3000.0, 3000.0]},
]
_LAST = {"target": None, "conditions": None}


def condition_text(condition, product="1.7 L kettle"):
    return CONDITION_TEXT[condition].format(product=product)


def mystery(rng, avoid_repeat=False):
    """(mandate, conditions) — a random brief and a random set of shop problems.
    With `avoid_repeat`, the product and the problems differ from the last run,
    so consecutive runs never look the same."""
    briefs = BRIEFS
    if avoid_repeat and _LAST["target"]:
        briefs = [b for b in BRIEFS if b["prefer_sku"] != _LAST["target"]] or BRIEFS
    brief = rng.choice(briefs)
    m = dict(BASE_MANDATE)
    m.update({k: brief[k] for k in ("category", "query", "prefer_sku", "needs", "min", "rank")})
    m["product"] = brief["product"]
    m["cap"] = rng.choice(brief["caps"])
    m["budget"] = max(m["cap"], 3000.0)
    m["drift_tolerance"] = rng.choice([0.02, 0.03, 0.05, 0.08])
    m["max_ship_days"] = rng.choice([None, None, 3, 5])
    m["min_warranty_months"] = rng.choice([None, None, None, 12, 24])
    m["min_returns_days"] = rng.choice([7, 7, 7, 10])
    rules = [f"cap ₹{m['cap']:,.0f}", f"price may move {m['drift_tolerance']:.0%}"]
    if m["max_ship_days"]:
        rules.append(f"must ship within {m['max_ship_days']} days")
    if m["min_warranty_months"]:
        rules.append(f"warranty ≥ {m['min_warranty_months']} months")
    rules.append(f"returns ≥ {m['min_returns_days']} days")
    m["goal"] = brief["goal"] + " Rules from my owner: " + ", ".join(rules) + "."
    pool = CONDITIONS + OFF_PLAYBOOK * 2           # off-playbook problems are common
    for _ in range(20):
        count = rng.choice([0, 1, 1, 1, 1, 2, 2])
        conditions = []
        while len(conditions) < count:
            c = rng.choice(pool)
            if c not in conditions:
                conditions.append(c)
        if not avoid_repeat or set(conditions) != set(_LAST["conditions"] or ()) or not conditions:
            break
    if avoid_repeat:
        _LAST.update(target=m["prefer_sku"], conditions=conditions)
    return m, conditions


def judge(truth, diagnosis, status):
    """Score Handshake's answer against the agent's real reason.
    Returns (verdict, sentence): correct | honest_unknown | wrong | n/a."""
    if truth is None:
        return ("n/a", "The agent bought first time; there was nothing to explain.")
    dg = diagnosis or {}
    cause, detail = dg.get("cause"), dg.get("detail") or {}
    if truth == "false_claim":
        ok = (dg.get("declared") or {}).get("corroborated") is False and status == "exception"
        return ("correct" if ok else "wrong",
                "The agent lied about its reason; Handshake refused to reward it."
                if ok else "The agent lied about its reason and Handshake acted on it.")
    if truth == "decline:no_reason":
        return ("correct" if cause == "UNKNOWN" else "wrong",
                "The rail gave no reason, and Handshake declined to invent one.")
    if truth.startswith(("slow:", "brief:")):
        field = truth.split(":", 1)[1]
        if cause == "N2" and detail.get("facet") == field:
            return ("correct", f"Handshake found the {field.replace('_', ' ')} problem without "
                               "a rule for it.")
    elif truth.startswith("refused:"):
        if cause == "N1" and detail.get("error") == truth.split(":", 1)[1]:
            return ("correct", "Handshake read the refusal no playbook entry covers.")
    elif truth == cause:
        return ("correct", "Handshake named the real reason.")
    elif any(h["cause"] == truth and (h.get("detail") or {}).get("consequence_of") == cause
             for h in dg.get("hypotheses") or []):
        return ("correct", f"The agent's reason ({truth}) was a consequence of {cause}; "
                           "Handshake named the root cause and listed both.")
    if cause == "N3":
        return ("honest_unknown", "The analyst offered a hypothesis; a person decides.")
    if cause in (None, "UNKNOWN") or (dg.get("confidence") or 0) < 0.7:
        return ("honest_unknown", "Handshake didn't have enough evidence and said so, "
                                  "instead of guessing.")
    return ("wrong", f"Handshake said {cause}; the real reason was {truth}.")
