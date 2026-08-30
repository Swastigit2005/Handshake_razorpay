"""Diagnosis engine (component C4).

Advisory only: it may propose a cause, it may never act. It reads the session
trace — merchant-observable API traffic — plus the merchant's own catalogue.
It never reads the injected fault label, which exists solely to score it.

Tier 1 is deterministic rules with confidence 1.0 on explicit reason codes.
Tier 2 (optional) hands residual traces to a model constrained to the closed
taxonomy. Anything below the confidence threshold routes to the exception
queue instead of an action (rule R-10).
"""

from dataclasses import dataclass, field

from ..merchant.catalog import required_attributes
from ..taxonomy import UNKNOWN

REASON_TO_CAUSE = {
    "insufficient_funds": "B1",
    "issuer_unavailable": "B2",
    "mandate_revoked": "B3",
    "reserve_exhausted": "B4",
    "instrument_declined": "B5",
}


@dataclass
class Diagnosis:
    session_id: str
    cause: str
    confidence: float
    method: str
    evidence: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def as_dict(self):
        return {"session_id": self.session_id, "cause": self.cause,
                "confidence": round(self.confidence, 2), "method": self.method,
                "evidence": self.evidence, "detail": self.detail}


def _created(trace):
    for ev in trace.events:
        if ev.type == "POST /checkout_sessions" and ev.http_status == 200:
            return ev
    return None


def diagnose(trace, merchant):
    ev_ids = lambda evs: [f"ev_{e.seq}" for e in evs]

    # ---- payment stage -------------------------------------------------
    for ev in reversed(trace.events):
        if ev.http_status == 402:
            code = REASON_TO_CAUSE.get(ev.response.get("reason_code"), UNKNOWN)
            return Diagnosis(trace.session_id, code, 1.0, "rule", ev_ids([ev]),
                             {"reason_code": ev.response.get("reason_code")})
        if ev.http_status == 401 and ev.response.get("error") == "authentication_required":
            return Diagnosis(trace.session_id, "A5", 1.0, "rule", ev_ids([ev]))
        if ev.http_status == 503 and ev.response.get("error") == "processing_error":
            return Diagnosis(trace.session_id, "A6", 1.0, "rule", ev_ids([ev]))
        if ev.http_status == 422 and ev.response.get("error") == "fulfilment_undetermined":
            return Diagnosis(trace.session_id, "A8", 1.0, "rule", ev_ids([ev]))

    # ---- session stage -------------------------------------------------
    created = _created(trace)
    if created:
        updates = [e for e in trace.events if e.type.startswith("POST /checkout_sessions/")
                   and not e.type.endswith("/complete") and e.http_status == 200]
        last_total = updates[-1].response.get("total") if updates else created.response.get("total")
        cap = created.request.get("declared_cap")

        if updates and created.response.get("total"):
            before = created.response["total"]
            if last_total and abs(last_total - before) > 0.01:
                return Diagnosis(trace.session_id, "A3", 1.0, "rule",
                                 ev_ids([created, updates[-1]]),
                                 {"quoted": before, "requoted": last_total})

        if cap is not None and last_total is not None and last_total > cap:
            return Diagnosis(trace.session_id, "A4", 1.0, "rule",
                             ev_ids([created] + updates[-1:]),
                             {"declared_cap": cap, "basket_total": last_total})

    # ---- discovery stage: merchant inspects its own catalogue ----------
    fetches = [e for e in trace.events if e.type.startswith("GET /products/")]
    if fetches and not created:
        sku = fetches[-1].request.get("sku", "")
        product = merchant.find(sku)
        view = merchant._view(product) if product else None
        if view:
            missing = [a for a in required_attributes(view["category"])
                       if a not in view.get("attributes", {})]
            if missing:
                return Diagnosis(trace.session_id, "A1", 0.92, "rule", ev_ids(fetches[-1:]),
                                 {"sku": sku, "missing_attribute": missing[0]})
            if not view["policy"].get("structured", True):
                return Diagnosis(trace.session_id, "A7", 0.90, "rule", ev_ids(fetches[-1:]),
                                 {"sku": sku})
            feed_ev = trace.last("GET /feed.json")
            twins = [p for p in merchant.peek_feed(category=view["category"])
                     if p["variant_group"] == view["variant_group"] and p["sku"] != view["sku"]
                     and p["attributes"] == view["attributes"] and p["price"] == view["price"]]
            if twins:
                return Diagnosis(trace.session_id, "A2", 0.82, "rule",
                                 ev_ids([e for e in (feed_ev, fetches[-1]) if e]),
                                 {"sku": sku, "collides_with": twins[0]["sku"]})

    return Diagnosis(trace.session_id, UNKNOWN, 0.0, "rule", [], {})
