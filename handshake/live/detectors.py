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
from . import money
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
# Family N (outside the playbook) never clears R-10's default 0.70 by itself:
# an open-ended guess can reach a person, never move money on its own.
NOVEL_CAP = 0.66

# Facets an agent compares between offers, and which way is better. Price is
# left out on purpose: within budget, "it was dearer" is a reason a person
# gives, and the cap breach (A4) already covers the case where it binds.
LOWER_IS_BETTER = {"ships_in_days", "delivery_days", "lead_time_days"}
SKIP_FACETS = {"price", "weight_g", "tax_rate", "stock"}
STEP_LABEL = {"feed.read": "catalogue request", "product.view": "product request",
              "checkout.create": "attempt to open a checkout",
              "checkout.update": "re-quote", "checkout.complete": "payment attempt",
              "checkout.cancel": "cancellation"}


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
        """The checkout session the agent was last working in."""
        return next((e for e in reversed(self.of("checkout.create")) if e["http_status"] == 200),
                    None)

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
    cur = money.of(last["response"], created["response"])
    paid_after = bool(tr.after(last, "checkout.complete"))
    score = 0.9 if after > before and not paid_after else (0.2 if paid_after else 0.3)
    return [Hypothesis(
        "A3", score,
        f"The price moved from {money.fmt(before, cur)} to {money.fmt(after, cur)} ({pct:+.1%}) between the quote "
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
    first = created["response"].get("total")
    cur = money.of(last["response"], created["response"])
    if isinstance(first, (int, float)) and first <= cap and not paid_after:
        # The first quote fitted. The cap was breached only because the price
        # moved, so the price move is the root cause and a price lock fixes both.
        return [Hypothesis(
            "A4", 0.55,
            f"The basket went over the {money.fmt(cap, cur)} cap, but only after the re-quote: the "
            f"first quote ({money.fmt(first, cur)}) fitted. This is a consequence of the price move, "
            "not a separate cause.",
            [_ev(created, "first quote within the cap", observed=first, expected=f"≤ {cap}"),
             _ev(last, "re-quote above the cap", observed=total)],
            {"declared_cap": cap, "basket_total": total, "consequence_of": "A3",
             "sku": created.get("sku") or created["request"].get("sku", "")})]
    return [Hypothesis(
        "A4", 0.2 if paid_after else 0.93,
        f"The basket came to {money.fmt(total, cur)} against a spending cap of {money.fmt(cap, cur)} that the "
        "agent's owner set. The agent is not allowed to go over it.",
        [_ev(created, "spending cap declared on checkout", observed=cap),
         _ev(last, "basket total above the cap", observed=total, expected=f"≤ {cap}")],
        {"declared_cap": cap, "basket_total": total, "over_by": round(total - cap, 2),
         "currency": cur,
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


# ------------------------------------------------- open-ended (family N) ---
#
# The detectors above each recognise one known signature. The two below don't
# know what they are looking for in advance. They ask general questions any
# abandonment can answer: did the shop refuse the last thing the agent asked
# for, and was what the agent was shown worse than its alternatives?

def _shopping(tr):
    return [e for e in tr.events if e["type"] != "reoffer.fetch"]


def current_sku(tr):
    for e in reversed(tr.events):
        sku = e.get("sku") or e["request"].get("sku") or ""
        if sku and e["type"] in ("product.view", "checkout.create"):
            return sku
    return ""


HANDLED_ERRORS = AUTH_ERRORS | TRANSIENT_ERRORS | FULFILMENT_ERRORS


def detect_rejection(tr, ctx):
    # A polite cancel after a refusal is the agent leaving, not the reason it left.
    shopping = [e for e in _shopping(tr) if e["type"] != "checkout.cancel"]
    if not shopping:
        return []
    last = shopping[-1]
    if any(e["type"] != "checkout.cancel" and e["seq"] > last["seq"] for e in _shopping(tr)):
        return []
    st, res = last["http_status"], last["response"]
    err = str(res.get("error") or "").lower()
    if not 400 <= st < 500 or st in (401, 402) or err in HANDLED_ERRORS \
            or (st == 422 and "servic" in err):
        return []
    detail = str(res.get("detail") or res.get("message") or "")
    step = STEP_LABEL.get(last["type"], last["type"])
    return [Hypothesis(
        "N1", NOVEL_CAP,
        f"The shop answered the agent's {step} with {st} "
        f"'{err or 'no error code'}'{(': ' + detail) if detail else ''}, and the agent "
        "stopped there. No playbook entry covers this error, so Handshake drafts a fix "
        "for a person to approve.",
        [_ev(last, "request refused, nothing after it", observed=f"{st} {err}".strip())],
        {"status": st, "error": err, "detail": detail, "step": last["type"],
         "sku": current_sku(tr)})]


def facets(record, served_fulfilment=None):
    """Numeric facets of an offer that an agent can compare."""
    out = {}
    for key, value in (record.get("attributes") or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
    policy = record.get("policy")
    if isinstance(policy, dict):
        for key in ("returns_days", "warranty_months"):
            if isinstance(policy.get(key), (int, float)):
                out[key] = policy[key]
    ful = served_fulfilment or record.get("fulfilment") or {}
    if isinstance(ful.get("ships_in_days"), (int, float)):
        out["ships_in_days"] = ful["ships_in_days"]
    return {k: v for k, v in out.items() if k not in SKIP_FACETS}


def _worse(facet, mine, theirs):
    return mine > theirs if facet in LOWER_IS_BETTER else mine < theirs


def detect_offer_mismatch(tr, ctx):
    shopping = _shopping(tr)
    if not shopping or tr.of("checkout.complete"):
        return []
    last = shopping[-1]
    if last["http_status"] != 200 or last["type"] not in (
            "product.view", "checkout.create", "checkout.update", "checkout.cancel"):
        return []
    sku = current_sku(tr)
    views = [e for e in tr.of("product.view") if (e.get("sku") or e["request"].get("sku")) == sku
             and e["http_status"] == 200]
    feeds = tr.of("feed.read")
    listed = [(e, p) for e in feeds for p in (e["response"].get("items") or [])
              if p.get("sku") == sku]
    if not sku or not (views or listed):
        return []
    # An agent may compare offers straight from search results without opening
    # the product page; what the listing served is then the record it judged.
    if views:
        view_ev, served = views[-1], views[-1]["response"]
    else:
        view_ev, served = listed[-1]
    created = tr.created
    served_ful = (created["response"].get("fulfilment") if created else None) or None
    mine = facets(served, served_ful)
    if not mine:
        return []

    shown = {p.get("sku"): p for e in feeds for p in (e["response"].get("items") or [])
             if p.get("sku") != sku}
    shown = list(shown.values())
    pool = shown or [p for p in ctx["all_products"]()
                     if p.get("category") == served.get("category") and p.get("sku") != sku]
    peers = []
    for p in pool:
        truth = ctx["catalog"](p.get("sku", "")) or {}
        merged = {**truth, **p}
        merged["fulfilment"] = truth.get("fulfilment") or p.get("fulfilment")
        peers.append((p.get("sku"), facets(merged)))
    peers = [(s, f) for s, f in peers if f]
    if not peers:
        return []

    best = None
    for facet, value in mine.items():
        values = [(s, f[facet]) for s, f in peers if facet in f]
        if not values or not all(_worse(facet, value, v) for _, v in values):
            continue
        top_sku, top = (min if facet in LOWER_IS_BETTER else max)(values, key=lambda x: x[1])
        gap = abs(value - top) / max(abs(value), abs(top), 1e-9)
        if best is None or gap > best[3]:
            best = (facet, value, (top_sku, top), gap)
    if best is None:
        return []
    facet, value, (top_sku, top), gap = best
    score = min(NOVEL_CAP, 0.5 + 0.16 * gap)
    where = view_ev if facet != "ships_in_days" or not created else created
    nice = facet.replace("_", " ")
    return [Hypothesis(
        "N2", score,
        f"{sku} was the weakest of the agent's options on {nice}: {value} against "
        f"{top} for {top_sku}. The agent looked, then stopped. Agents compare offers on "
        "exactly this kind of field, so this is the likeliest reason, but it is a "
        "hypothesis: a person approves any re-offer.",
        [_ev(where, f"served {nice} worse than every alternative", observed=value,
             expected=f"{'≤' if facet in LOWER_IS_BETTER else '≥'} {top} ({top_sku})")],
        {"sku": sku, "facet": facet, "served": value, "best_alternative": top_sku,
         "alternative_value": top, "gap": round(gap, 3)})]


DETECTORS = (detect_rail_code, detect_auth_wall, detect_transient_error,
             detect_fulfilment, detect_quote_drift, detect_cap,
             detect_attribute_void, detect_policy, detect_variant_collision,
             detect_rejection, detect_offer_mismatch)


# ------------------------------------------------------------------ verdict ---

def _declared(tr):
    for ev in reversed(tr.of("checkout.cancel")):
        reason = (ev["request"].get("reason") or ev["response"].get("reason") or "").strip()
        if reason:
            return ev, reason.lower()
    return None, ""


# Words that, in an agent's free-text reason, point at a hypothesis's subject.
# Used only to corroborate a hypothesis the traffic already supports.
_TEXT_HINTS = {
    "A1": ("missing", "not listed", "doesn't list", "does not list", "no spec", "unverif",
           "can't verify", "cannot verify"),
    "A2": ("identical", "duplicate", "two listings", "ambiguous"),
    "A3": ("price changed", "price went up", "price increased", "re-quote", "requote",
           "more expensive", "price rose"),
    "A4": ("cap", "budget", "limit", "over my", "too expensive"),
    "A5": ("otp", "authenticat", "approval", "verification code"),
    "A6": ("error", "failed", "503", "server"),
    "A7": ("return", "warranty terms", "policy"),
    "A8": ("deliver to", "pincode", "serviceable", "can't deliver", "cannot deliver"),
    "N1": ("not accept", "doesn't accept", "does not accept", "unsupported", "refused",
           "out of stock", "sold out", "unavailable"),
}
_FACET_HINTS = {"ships_in_days": ("ship", "deliver", "arriv", "days"),
                "warranty_months": ("warranty",), "returns_days": ("return",),
                "battery_hours": ("battery",), "capacity_l": ("capacity", "litre", "liter"),
                "power_watts": ("watt", "power")}


def _text_supports(text, h):
    text = text.lower()
    if h.cause == "N2":
        words = _FACET_HINTS.get(h.detail.get("facet"), (h.detail.get("facet", "").split("_")[0],))
    else:
        words = _TEXT_HINTS.get(h.cause, ())
    return any(w in text for w in words)


ANALYST_BELOW = 0.70


def current_attempt(events):
    """The events of the agent's latest attempt. After it collects a re-offer and
    tries again, the earlier attempt was already diagnosed; reading it again
    would explain the old stop instead of the new one. Catalogue reads from the
    earlier attempt are kept, since they are still what the agent was shown."""
    # An attempt begins where the agent acts on an offer. Picking an offer up
    # again afterwards (a repeat poll) starts nothing, so only pickups followed
    # by real shopping count.
    acting = {"product.view", "checkout.create", "checkout.update", "checkout.complete"}
    starts = [e["seq"] for i, e in enumerate(events)
              if e["type"] == "reoffer.fetch" and e["http_status"] == 200
              and any(x["type"] in acting for x in events[i + 1:])]
    if not starts:
        return events, False
    last_offer = starts[-1]
    later = [e for e in events if e["seq"] > last_offer]
    feeds = [e for e in events if e["type"] == "feed.read" and e["seq"] < last_offer][-1:]
    return feeds + later, True


def diagnose(events, schema, catalog_lookup, all_products=lambda: [], analyst=None):
    """Diagnose one closed journey. Pure without `analyst`: same events, same
    answer. With it, a model is consulted only when no detector reaches
    ANALYST_BELOW — known causes stay fully deterministic."""
    events, retried = current_attempt(events)
    tr = Trace(events)
    ctx = {"schema": schema or {}, "catalog": catalog_lookup,
           "all_products": all_products, "observations": []}
    if retried:
        ctx["observations"].append("This is the agent's second attempt, after a re-offer. "
                                   "Only events since then are read.")

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
            # Free text. It may corroborate what the traffic already shows — never
            # create a hypothesis by itself.
            agrees = next((h for h in hyps if _text_supports(said, h)), None)
            if agrees:
                agrees.score = min(NOVEL_CAP if agrees.cause.startswith("N") else 0.99,
                                   agrees.score + 0.06)
                agrees.corroborated_by_agent = True
                agrees.evidence.append(_ev(cancel_ev, "agent's stated reason agrees",
                                           observed=said))
                declared.update(maps_to=agrees.cause, corroborated=True)
            else:
                ctx["observations"].append(f"Agent stated '{said}', which nothing in the "
                                           "traffic confirms.")

    method = "evidence-v2"
    if analyst is not None and (not hyps or max(h.score for h in hyps) < ANALYST_BELOW):
        extra = analyst(events)
        if extra is not None:
            hyps.append(extra)
            method = "evidence-v2+analyst"

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
                "method": method, "stage": stage, "contested": False,
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
            "method": method, "stage": stage, "contested": contested,
            "explanation": top.summary, "hypotheses": [h.as_dict() for h in hyps],
            "evidence": top.evidence, "detail": top.detail, "observations": observations,
            "declared": declared}
