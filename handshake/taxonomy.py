"""Failure taxonomy, intervention catalogue and rule identifiers.

Single source of truth for every identifier used in diagnosis, policy and the
audit ledger. Spec sections 6 and 10.
"""

from dataclasses import dataclass, field
from enum import Enum


class Family(str, Enum):
    A = "A"  # pre-payment agent abandonment
    B = "B"  # post-authorisation payment failure


@dataclass(frozen=True)
class Cause:
    id: str
    family: Family
    name: str
    signal: str
    interventions: tuple


CAUSES = {
    c.id: c
    for c in [
        Cause("A1", Family.A, "attribute_void",
              "agent required a field absent from the feed",
              ("I-01",)),
        Cause("A2", Family.A, "spec_ambiguity",
              "two or more variants indistinguishable on feed data",
              ("I-02",)),
        Cause("A3", Family.A, "quote_drift",
              "price or stock changed between session create and update",
              ("I-03",)),
        Cause("A4", Family.A, "reserve_ceiling",
              "basket total exceeded the agent's delegated spending cap",
              ("I-04", "I-05")),
        Cause("A5", Family.A, "human_auth_wall",
              "flow demanded OTP or manual approval with no human present",
              ("I-06",)),
        Cause("A6", Family.A, "ambiguous_error",
              "retryable error classified as terminal by the agent",
              ("I-08", "I-09")),
        Cause("A7", Family.A, "policy_unreadable",
              "return or warranty terms available only as prose",
              ("I-07",)),
        Cause("A8", Family.A, "fulfilment_mismatch",
              "pincode unserviceable or tax line uncomputable",
              ("I-01", "I-10")),
        Cause("B1", Family.B, "insufficient_balance",
              "mandate debit declined for funds",
              ("I-09",)),
        Cause("B2", Family.B, "issuer_downtime",
              "failures cluster by issuer inside a time window",
              ("I-09",)),
        Cause("B3", Family.B, "mandate_invalid",
              "authorisation object expired or revoked at debit time",
              ("I-06",)),
        Cause("B4", Family.B, "reserve_exhausted",
              "cumulative spend has consumed the delegated cap",
              ("I-05",)),
        Cause("B5", Family.B, "instrument_decline",
              "card expired, VPA invalid or method deregistered",
              ("I-08",)),
    ]
}

UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Intervention:
    id: str
    name: str
    mechanism: str
    concedes_margin: bool
    touches_human: bool
    rung: int


INTERVENTIONS = {
    i.id: i
    for i in [
        Intervention("I-01", "catalogue_delta_reoffer",
                     "patch the missing attribute and re-offer", False, False, 1),
        Intervention("I-02", "disambiguated_reoffer",
                     "return one resolved variant with differentiating fields", False, False, 1),
        Intervention("I-03", "price_lock_quote",
                     "honour the original quote for a bounded window", True, False, 1),
        Intervention("I-04", "bundle_resize",
                     "offer a compliant basket under the cap", False, False, 1),
        Intervention("I-05", "reserve_uplift_request",
                     "ask the human principal to raise the cap", False, True, 2),
        Intervention("I-06", "human_approval_link",
                     "issue a single-use expiring authorisation link", False, True, 2),
        Intervention("I-07", "structured_policy_document",
                     "serve returns and warranty terms as machine-readable fields", False, False, 1),
        Intervention("I-08", "alternate_instrument",
                     "re-attempt on a different payment method", False, False, 1),
        Intervention("I-09", "scheduled_retry",
                     "re-attempt inside permitted caps and cooldowns", False, False, 1),
        Intervention("I-10", "escalate_to_ops",
                     "route to a human queue as an unresolved exception", False, True, 3),
    ]
}

# Stopping and bounding rules (spec 10.2). Enforced in policy/engine.py.
RULES = {
    "R-01": "maximum re-offers per session",
    "R-02": "maximum interventions per buyer per rolling 24h",
    "R-03": "explicit decline terminates the session permanently",
    "R-04": "cumulative concession ceiling (margin floor)",
    "R-05": "halt when expected recovery value < intervention cost",
    "R-06": "abuse pattern: repeat abandonment to farm concessions",
    "R-07": "never raise a spending cap without recorded principal consent",
    "R-08": "mandate retries capped, then routed to a human",
    "R-09": "quiet hours on any human-facing escalation",
    "R-10": "diagnosis confidence below threshold routes to exceptions",
    "R-11": "global kill switch halts all money actions",
}


class Terminal(str, Enum):
    CONVERTED = "CONVERTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class Arm(str, Enum):
    TREATMENT = "treatment"
    CONTROL = "control"


@dataclass
class Verdict:
    """Result of the policy gate."""
    permitted: bool
    intervention_id: str = ""
    parameters: dict = field(default_factory=dict)
    binding_rule: str = ""
    reason: str = ""
    checks: list = field(default_factory=list)
