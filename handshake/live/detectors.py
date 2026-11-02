"""Why did the agent stop? — the evidence engine for live traffic.

This answers a different question from the policy gate, and keeping the two
apart is the point of the design:

    detectors (this file)   WHY did the journey stop?     13 causes, evidence
    policy/engine.py        SHOULD we do anything about it? 11 rules, permit/refuse

A human who abandons a cart leaves no reason. An agent doesn't either — but it
leaves something a human never does: a complete, structured record of every
request it made and every response it was given. Agents are deterministic about
what they need. If one fetched a product and never opened a checkout, the
product record it was served either satisfied its requirements or it didn't,
and that record is in the trace.

So each cause has a detector that looks for its specific signature and returns
a hypothesis with a score and the exact evidence: which event, which field, what
was observed, what was expected. Every detector runs; nothing is first-match.
The hypotheses are ranked, and the margin between the top two is reported,
because a close second is information a merchant should see.

Three sources of evidence, in descending order of trust:

  1. rail codes      an explicit reason on the response (402 insufficient_funds)
  2. behaviour       where the agent stopped, measured against what it was served
                     and against the merchant's own catalogue and schema
  3. self-report     a reason the agent stated on cancel. Corroborating evidence
                     only: on its own it never clears R-10, because an agent that
                     learns "say price_changed" earns a price lock will say it.

When nothing in the trace explains the stop, the answer is UNKNOWN with
confidence 0, and R-10 routes the journey to a human instead of guessing.
"""

from ..taxonomy import CAUSES, UNKNOWN
from .events import STAGE, STAGE_ORDER, describe

RAIL_CODES = {
    "insufficient_funds": "B1", "insufficient_balance": "B1",
    "issuer_unavailable": "B2", "issuer_down": "B2", "bank_unavailable": "B2",
    "mandate_revoked": "B3", "mandate_expired": "B3", "mandate_invalid": "B3",
    "reserve_exhausted": "B4", "limit_exhausted": "B4",
    "instrument_declined": "B5", "card_expired": "B5", "invalid_vpa": "B5",
    "card_declined": "B5",
}
AUTH_ERRORS = {"authentication_required", "requires_action", "3ds_required",
               "otp_required", "approval_required"}
TRANSIENT_ERRORS = {"processing_error", "service_unavailable", "timeout",
                    "internal_error", "gateway_timeout"}
FULFILMENT_ERRORS = {"fulfilment_undetermined", "unserviceable", "no_route",
                     "tax_uncomputable", "address_unserviceable"}

# What agents say on cancel, mapped onto the closed taxonomy. Anything else is
# recorded verbatim and contributes nothing.
DECLARED = {
    "missing_information": "A1", "missing_attribute": "A1",
    "insufficient_product_data": "A1",
    "ambiguous_product": "A2", "variant_unclear": "A2",
    "price_changed": "A3", "quote_changed": "A3",
    "over_budget": "A4", "exceeds_cap": "A4", "spending_limit": "A4",
    "authentication_required": "A5", "needs_human": "A5",
    "merchant_error": "A6", "error": "A6",
    "policy_unclear": "A7", "return_policy_unclear": "A7",
    "cannot_deliver": "A8", "unserviceable": "A8",
}

UNCORROBORATED_SCORE = 0.45
CONTEST_MARGIN = 0.10
CONTEST_PENALTY = 0.15


class Hypothesis:
    def __init__(self, cause, score, summary, evidence, detail=None):
        self.cause = cause
        self.score = score
        self.summary = summary
        self.evidence = evidence
        self.detail = detail or {}
        self.corroborated_by_agent = False

    def as_dict(self):
        return {"cause": self.cause,
                "name": CAUSES[self.cause].name if self.cause in CAUSES else "unclassified",
                "score": round(self.score, 2), "summary": self.summary,
                "evidence": self.evidence, "detail": self.detail,
                "corroborated_by_agent": self.corroborated_by_agent}


def _ev(ev, what, observed=None, expected=None):
    out = {"event": ev["seq"], "type": ev["type"], "what": what}
    if observed is not None:
        out["observed"] = observed
    if expected is not None:
        out["expected"] = expected
    return out


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


class Trace:
    """Indexes a journey's events once so each detector reads it cheaply."""

    def __init__(self, events):
        self.events = events
        self.by_type = {}
        for ev in events:
            self.by_type.setdefault(ev["type"], []).append(ev)

    def of(self, t):
        return self.by_type.get(t, [])

    def after(self, ev, t=None):
        return [e for e in self.events if e["seq"] > ev["seq"] and (t is None or e["type"] == t)]

    @property
    def created(self):
        return next((e for e in self.of("checkout.create") if e["http_status"] == 200), None)

    @property
    def last(self):
        """The last shopping event. Re-offer polls are the agent waiting, not
        shopping, and say nothing about why it stopped."""
        shopping = [e for e in self.events if e["type"] != "reoffer.fetch"]
        return shopping[-1] if shopping else None

    def stage(self):
        best = "discovery"
        for ev in self.events:
            s = STAGE.get(ev["type"], "discovery")
            if s != "recovery" and STAGE_ORDER[s] > STAGE_ORDER[best]:
                best = s
        return best


# ---------------------------------------------------------------- detectors ---

def detect_rail_code(tr, ctx):
    out = []
    for ev in tr.of("checkout.complete"):
        if ev["http_status"] != 402 or tr.after(ev, "checkout.complete"):
            continue
        code = (ev["response"].get("reason_code") or "").lower()
        cause = RAIL_CODES.get(code)
        if cause:
            out.append(Hypothesis(
                cause, 0.99,
                f"The payment rail declined with reason code '{code}'.",
                [_ev(ev, "payment declined with an explicit reason code",
                     observed=code)],
                {"reason_code": code}))
        else:
            ctx["observations"].append(
                f"Payment declined (402) with {'reason ' + repr(code) if code else 'no reason code'}"
                " — the rail did not say why, and the engine will not guess.")
    return out


def detect_auth_wall(tr, ctx):
    for ev in tr.of("checkout.complete"):
        err = (ev["response"].get("error") or "").lower()
        if (ev["http_status"] == 401 or err in AUTH_ERRORS) and not tr.after(ev, "checkout.complete"):
            return [Hypothesis(
                "A5", 0.97,
                "Payment needed a one-time password or approval that only the human owner can "
                "give, and no human was present.",
                [_ev(ev, "completion demanded human authentication",
                     observed=f"{ev['http_status']} {err}".strip())],
                {"error": err})]
    return []


def detect_transient_error(tr, ctx):
    for ev in tr.of("checkout.complete"):
        err = (ev["response"].get("error") or "").lower()
        if (500 <= ev["http_status"] <= 504 or err in TRANSIENT_ERRORS) \
                and not tr.after(ev, "checkout.complete"):
            return [Hypothesis(
                "A6", 0.95,
                "The shop returned a retryable server error and the agent treated it as final. "
                "A person would have pressed Pay again.",
                [_ev(ev, "retryable error, never retried",
                     observed=f"{ev['http_status']} {err}".strip(),
                     expected="a second completion attempt")],
                {"error": err})]
    return []


def detect_fulfilment(tr, ctx):
    for ev in tr.of("checkout.create"):
        err = (ev["response"].get("error") or "").lower()
        if ev["http_status"] == 422 and (err in FULFILMENT_ERRORS or "servic" in err):
            pincode = ev["request"].get("pincode") or ev["request"].get("postal_code")
            sku = ev.get("sku") or ev["request"].get("sku", "")
            return [Hypothesis(
                "A8", 0.95,
                f"The shop could not confirm delivery to pincode {pincode} for {sku}, so the "
                "agent could not open a checkout.",
                [_ev(ev, "checkout refused: no serviceable route",
                     observed=f"422 {err}", expected="a quote with a delivery estimate")],
                {"sku": sku, "pincode": pincode})]
    return []


def detect_quote_drift(tr, ctx):
    created = tr.created
    if not created:
        return []
    updates = [e for e in tr.after(created, "checkout.update") if e["http_status"] == 200]
    before = created["response"].get("total")
    if not updates or not isinstance(before, (int, float)):
        return []
    last = updates[-1]
    after = last["response"].get("total")
    if not isinstance(after, (int, float)) or abs(after - before) <= 0.01:
        return []
    pct = (after - before) / before if before else 0.0
    paid_after = bool(tr.after(last, "checkout.complete"))
    score = 0.9 if after > before and not paid_after else (0.2 if paid_after else 0.3)
    return [Hypothesis(
        "A3", score,
        f"The price moved from ₹{before:,.2f} to ₹{after:,.2f} ({pct:+.1%}) between the quote "
        "and the re-quote, and the agent stopped right after.",
        [_ev(created, "first quote", observed=before),
         _ev(last, "re-quote", observed=after, expected=before)],
        {"quoted": before, "requoted": after, "drift_pct": round(pct, 4),
         "sku": created.get("sku") or created["request"].get("sku", "")})]


def detect_cap(tr, ctx):
    created = tr.created
    if not created:
        return []
    cap = created["request"].get("declared_cap")
    if not isinstance(cap, (int, float)):
        return []
    quotes = [created] + [e for e in tr.after(created, "checkout.update") if e["http_status"] == 200]
    last = quotes[-1]
    total = last["response"].get("total")
    if not isinstance(total, (int, float)) or total <= cap:
        return []
    paid_after = bool(tr.after(last, "checkout.complete"))
    return [Hypothesis(
        "A4", 0.2 if paid_after else 0.93,
        f"The basket came to ₹{total:,.2f} against a spending cap of ₹{cap:,.2f} that the "
        "agent's owner set. The agent is not allowed to go over it.",
        [_ev(created, "spending cap declared on checkout", observed=cap),
         _ev(last, "basket total above the cap", observed=total, expected=f"≤ {cap}")],
        {"declared_cap": cap, "basket_total": total, "over_by": round(total - cap, 2),
         "sku": created.get("sku") or created["request"].get("sku", "")})]


def _last_view_without_checkout(tr):
    """The product the agent looked at last, if it never tried to buy it."""
    views = [e for e in tr.of("product.view") if e["http_status"] == 200]
    if not views:
        return None
    last = views[-1]
    if tr.after(last, "checkout.create"):
        return None
    return last


def _category(view, ctx):
    sku = view.get("sku") or view["request"].get("sku", "")
    cat = view["response"].get("category")
    if not cat:
        rec = ctx["catalog"](sku)
        cat = rec.get("category") if rec else None
    return cat


def detect_attribute_void(tr, ctx):
    view = _last_view_without_checkout(tr)
    if not view:
        return []
    sku = view.get("sku") or view["request"].get("sku", "")
    required = ctx["schema"].get(_category(view, ctx) or "", [])
    served = view["response"].get("attributes") or {}
    missing = [a for a in required if _empty(served.get(a))]
    if not missing:
        return []
    truth = ctx["catalog"](sku) or {}
    known = {a: (truth.get("attributes") or {}).get(a) for a in missing}
    sourceable = {a: v for a, v in known.items() if not _empty(v)}
    score = 0.92 if sourceable else 0.86
    names = ", ".join(missing)
    tail = (" Your own catalogue has the value, so the feed is dropping it."
            if sourceable else " Your catalogue does not have the value either.")
    return [Hypothesis(
        "A1", score,
        f"The product record served for {sku} had no {names}, which the "
        f"'{_category(view, ctx)}' category requires. An agent will not buy what it cannot "
        f"verify against its instructions, so it never opened a checkout.{tail}",
        [_ev(view, f"served record missing required field{'s' if len(missing) > 1 else ''}",
             observed={a: served.get(a) for a in missing}, expected=f"values for {names}")],
        {"sku": sku, "missing_attribute": missing[0], "missing": missing,
         "source_values": sourceable})]


def detect_policy(tr, ctx):
    view = _last_view_without_checkout(tr)
    if not view:
        return []
    policy = view["response"].get("policy")
    structured = isinstance(policy, dict) and policy.get("structured", True) is not False \
        and not _empty(policy.get("returns_days"))
    if structured:
        return []
    sku = view.get("sku") or view["request"].get("sku", "")
    shown = policy if isinstance(policy, str) else (policy or {}).get("text", policy)
    return [Hypothesis(
        "A7", 0.80,
        f"Returns and warranty terms for {sku} were served as prose, not as fields. An agent "
        "told to buy only with a returns window it can check had nothing to check.",
        [_ev(view, "policy not machine-readable",
             observed=(shown[:120] + "…") if isinstance(shown, str) and len(shown) > 120 else shown,
             expected="{returns_days, warranty_months}")],
        {"sku": sku})]


def detect_variant_collision(tr, ctx):
    view = _last_view_without_checkout(tr)
    if not view:
        return []
    sku = view.get("sku") or view["request"].get("sku", "")
    me = view["response"]
    group = me.get("variant_group")
    if not group:
        return []
    feeds = [e for e in tr.of("feed.read") if e["seq"] < view["seq"]]
    pool = (feeds[-1]["response"].get("items") if feeds else None) or ctx["all_products"]()
    twins = [p for p in pool if p.get("variant_group") == group and p.get("sku") != sku
             and (p.get("attributes") or {}) == (me.get("attributes") or {})
             and p.get("price") == me.get("price")]
    if not twins:
        return []
    evidence = [_ev(view, "product viewed", observed=sku)]
    if feeds:
        evidence.insert(0, _ev(feeds[-1], "listing served two indistinguishable variants",
                               observed=[sku, twins[0].get("sku")]))
    return [Hypothesis(
        "A2", 0.78,
        f"{sku} and {twins[0].get('sku')} were listed with the same price and identical "
        "fields. The agent could not tell which one its owner meant, so it bought neither.",
        evidence, {"sku": sku, "collides_with": twins[0].get("sku")})]


DETECTORS = (detect_rail_code, detect_auth_wall, detect_transient_error,
             detect_fulfilment, detect_quote_drift, detect_cap,
             detect_attribute_void, detect_policy, detect_variant_collision)


# ------------------------------------------------------------------ verdict ---

def _declared(tr):
    for ev in reversed(tr.of("checkout.cancel")):
        reason = (ev["request"].get("reason") or ev["response"].get("reason") or "").strip()
        if reason:
            return ev, reason.lower()
    return None, ""


def diagnose(events, schema, catalog_lookup, all_products=lambda: []):
    """Diagnose one closed journey. Pure: same events, same answer."""
    tr = Trace(events)
    ctx = {"schema": schema or {}, "catalog": catalog_lookup,
           "all_products": all_products, "observations": []}

    hyps = []
    for detector in DETECTORS:
        hyps.extend(detector(tr, ctx))

    cancel_ev, said = _declared(tr)
    declared = None
    if said:
        claimed = DECLARED.get(said)
        declared = {"reason": said, "maps_to": claimed or UNKNOWN, "event": cancel_ev["seq"]}
        match = next((h for h in hyps if h.cause == claimed), None)
        if match:
            match.score = min(0.99, match.score + 0.06)
            match.corroborated_by_agent = True
            match.evidence.append(_ev(cancel_ev, "agent's stated reason agrees", observed=said))
            declared["corroborated"] = True
        elif claimed:
            h = Hypothesis(
                claimed, UNCORROBORATED_SCORE,
                f"The agent said '{said}', but nothing in the traffic supports it. A stated "
                "reason alone never moves money: an agent that learns which words earn a "
                "concession will repeat them.",
                [_ev(cancel_ev, "uncorroborated self-report", observed=said)],
                {"self_report_only": True})
            hyps.append(h)
            declared["corroborated"] = False
        else:
            ctx["observations"].append(f"Agent stated '{said}', which maps to no known cause.")

    hyps.sort(key=lambda h: -h.score)
    stage = tr.stage()
    last = tr.last
    observations = ctx["observations"]
    if last is not None:
        observations.insert(0, f"Last thing the shop saw: the agent {describe(last)}.")

    if not hyps:
        if stage == "discovery" and tr.of("product.view"):
            observations.append("The agent viewed a product and left. Nothing in the record it "
                                "was served explains it — the product may simply not have "
                                "matched what it was sent to buy.")
        return {"cause": UNKNOWN, "name": "unclassified", "confidence": 0.0,
                "method": "evidence-v2", "stage": stage, "contested": False,
                "explanation": "Nothing in the traffic explains why this journey stopped. "
                               "Handshake will not guess: it goes to the exceptions queue.",
                "hypotheses": [], "evidence": [], "detail": {},
                "observations": observations, "declared": declared}

    top = hyps[0]
    confidence = top.score
    contested = len(hyps) > 1 and hyps[1].cause != top.cause \
        and top.score - hyps[1].score < CONTEST_MARGIN
    if contested:
        confidence = max(0.0, confidence - CONTEST_PENALTY)
        observations.append(
            f"Two explanations are nearly as strong ({top.cause} {top.score:.2f}, "
            f"{hyps[1].cause} {hyps[1].score:.2f}); confidence lowered to "
            f"{confidence:.2f}.")
    return {"cause": top.cause, "name": CAUSES[top.cause].name, "confidence": round(confidence, 2),
            "method": "evidence-v2", "stage": stage, "contested": contested,
            "explanation": top.summary, "hypotheses": [h.as_dict() for h in hyps],
            "evidence": top.evidence, "detail": top.detail, "observations": observations,
            "declared": declared}
