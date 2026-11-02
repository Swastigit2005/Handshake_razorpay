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
