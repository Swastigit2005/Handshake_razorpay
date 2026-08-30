"""Buyer personas (component C2).

Risk posture governs how readily an agent proceeds under uncertainty. Varying
it across the batch stops a failure class being confounded with one agent's
idiosyncrasies (spec 8.2, 12).
"""

import random

POSTURES = {
    "strict": {
        "needs_all_attributes": True,
        "needs_structured_policy": True,
        "drift_tolerance": 0.0,
        "retries_ambiguous_error": False,
        "consent_probability": 0.45,
    },
    "balanced": {
        "needs_all_attributes": True,
        "needs_structured_policy": False,
        "drift_tolerance": 0.05,
        "retries_ambiguous_error": False,
        "consent_probability": 0.60,
    },
    "permissive": {
        "needs_all_attributes": False,
        "needs_structured_policy": False,
        "drift_tolerance": 0.15,
        "retries_ambiguous_error": True,
        "consent_probability": 0.70,
    },
}

CATEGORIES = ["laptop_accessories", "audio", "home_kitchen", "everyday_small"]

PINCODES = ["560001", "560034", "400001", "110001", "600028"]


class Persona:
    def __init__(self, pid, posture, category, budget, cap, pincode, instrument):
        self.id = pid
        self.posture = posture
        self.rules = POSTURES[posture]
        self.category = category
        self.budget = budget
        self.cap = cap
        self.pincode = pincode
        self.instrument = instrument

    def __repr__(self):
        return f"<Persona {self.id} {self.posture} {self.category} cap={self.cap}>"


def make_persona(rng, index, catalog):
    """Build a persona against the real catalogue.

    A buyer shops for something that exists. Deriving the budget from an actual
    in-stock item guarantees every session has a candidate, so no model call is
    spent on a session with nothing to buy."""
    stocked = [p for p in catalog if p["stock"] > 0]
    reference = rng.choice(stocked)
    gross = reference["price"] * (1 + reference["tax_rate"])

    budget = round(gross * rng.uniform(1.15, 2.2) / 50) * 50
    cap = round(max(budget * rng.choice([0.7, 0.85, 1.0]), gross * 1.05), 2)

    instrument = {
        "type": rng.choice(["upi_reserve", "card_token", "upi_mandate"]),
        "state": "active",
    }
    if instrument["type"] == "upi_mandate":
        instrument["mandate"] = True

    return Persona(f"buyer_{index:04d}", rng.choice(list(POSTURES)),
                   reference["category"], budget, cap,
                   rng.choice(PINCODES), instrument)


def fleet(seed, n, catalog):
    rng = random.Random(seed)
    return [make_persona(rng, i, catalog) for i in range(n)]
