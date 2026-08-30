"""Seeded fault injection.

The injected fault is the ground-truth label for evaluating the diagnosis
engine (spec 8.1, 12). It is recorded on the session and NEVER exposed to the
diagnosis engine, which must recover it from the trace alone.
"""

import copy
import random

FAMILY_A = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]
FAMILY_B = ["B1", "B2", "B3", "B4", "B5"]

# Weights chosen so no class is too rare to measure in a 500-session batch.
WEIGHTS = {
    "A1": 16, "A2": 8, "A3": 12, "A4": 14, "A5": 8, "A6": 10, "A7": 6, "A8": 8,
    "B1": 7, "B2": 4, "B3": 3, "B4": 2, "B5": 2,
}


def choose_fault(rng, incidence):
    """Return a fault code, or None for a clean session."""
    if rng.random() > incidence:
        return None
    codes = list(WEIGHTS)
    return rng.choices(codes, weights=[WEIGHTS[c] for c in codes], k=1)[0]


class FaultInjector:
    """Applies one fault to the merchant's behaviour for a single session."""

    def __init__(self, code, rng):
        self.code = code
        self.rng = rng
        self.applied = []
        self.resolved = False
        # A quarter of payment declines arrive without a usable reason code,
        # as they do on real rails. The diagnosis engine must then refuse to
        # guess (rule R-10) rather than invent a cause.
        self.obscure_reason = bool(code and code.startswith("B") and rng.random() < 0.25)

    def resolve(self):
        """Called by the executor once an intervention has removed the blocker."""
        self.resolved = True

    @property
    def active(self):
        return bool(self.code) and not self.resolved

    # ----- feed / product view -----

    def degrade_product(self, product, required):
        """Mutate a copy of the product record as the agent would see it."""
        p = copy.deepcopy(product)
        if self.resolved:
            return p
        if self.code == "A1":
            missing = self.rng.choice(required)
            p["attributes"].pop(missing, None)
            p["_missing_attribute"] = missing
            self.applied.append(f"removed attribute {missing}")
        elif self.code == "A7":
            p["policy"] = {
                "structured": False,
                "prose": ("Returns are accepted at the discretion of the seller within a "
                          "reasonable period subject to condition of goods and applicable "
                          "terms; warranty claims are handled by the manufacturer."),
            }
            self.applied.append("policy replaced with prose")
        elif self.code == "A8":
            p["fulfilment"] = dict(p["fulfilment"])
            p["fulfilment"]["serviceable_pincodes"] = []
            self.applied.append("pincode made unserviceable")
        return p

    def sibling_variant(self, product):
        """For A2: an indistinguishable second variant in the same group."""
        if self.code != "A2" or self.resolved:
            return None
        twin = copy.deepcopy(product)
        twin["sku"] = product["sku"] + "-V2"
        twin["price"] = product["price"]
        self.applied.append("indistinguishable variant introduced")
        return twin

    # ----- session lifecycle -----

    def drift(self, product):
        """For A3: price mutation between session create and update."""
        if self.code != "A3" or self.resolved:
            return None
        delta = self.rng.choice([0.06, 0.09, 0.13, 0.18])
        new_price = round(product["price"] * (1 + delta), 2)
        self.applied.append(f"price drifted +{int(delta * 100)}%")
        return new_price

    def requires_human_auth(self):
        return self.code == "A5" and not self.resolved

    def ambiguous_error(self):
        return self.code == "A6" and not self.resolved

    def force_over_cap(self):
        return self.code == "A4" and not self.resolved

    # ----- family B -----

    def mandate_outcome(self):
        """Reason code returned by the payment rail on a mandate debit."""
        if self.resolved:
            return None
        if self.obscure_reason:
            return "unspecified"
        return {
            "B1": "insufficient_funds",
            "B2": "issuer_unavailable",
            "B3": "mandate_revoked",
            "B4": "reserve_exhausted",
            "B5": "instrument_declined",
        }.get(self.code)

    @property
    def family(self):
        if not self.code:
            return None
        return self.code[0]
