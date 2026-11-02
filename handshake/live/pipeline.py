"""The live pipeline: ingest → abandon → diagnose → gate → direct → attribute.

A journey is one agent's attempt to buy at one merchant. It opens on the
agent's first request and closes one of four ways:

    converted    a completion returned 200
    abandoned    the agent cancelled, or went silent for the merchant's idle window
    → recovering a directive was permitted and a re-offer is waiting
    → recovered  the agent came back and paid; the value is attributed
    → lost       the re-offer expired, or R-05 judged it not worth trying
    → exception  the gate refused; a human should look

Diagnosis and the gate never share code. `detectors.diagnose` produces a cause
and a confidence; `policy.engine.PolicyEngine` — the same class, the same eleven
rules, the same unit tests as the simulator — decides whether anything happens.
"""

import threading
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from ..config import PolicyConfig
from ..policy.engine import PolicyEngine
from ..taxonomy import CAUSES, RULES
from . import directives, store, webhooks
from .detectors import diagnose
from .events import STAGE, STAGE_ORDER, InvalidEvent, normalise

try:
    from zoneinfo import ZoneInfo
except ImportError:                                     # pragma: no cover
    ZoneInfo = None

DEFAULT_SETTINGS = {
    "idle_seconds": 900,            # silence after which an open journey is abandoned
    "reoffer_ttl_seconds": 1800,    # how long a re-offer stays claimable
    "retry_after_seconds": 900,     # I-09 cooldown for payment-family retries
    "timezone": "Asia/Kolkata",     # for R-09 quiet hours
}
TERMINAL_OPEN = ("abandoned", "exception", "lost")
REFUSAL_TO_STATUS = {"R-05": "lost"}        # everything else needs a human
MAX_BATCH = 500

_close_lock = threading.Lock()


def settings_for(merchant):
    return {**DEFAULT_SETTINGS, **(merchant.get("settings") or {})}


def policy_for(merchant):
    cfg = PolicyConfig()
    for key, value in (merchant.get("policy") or {}).items():
        if hasattr(cfg, key):
            setattr(cfg, key, tuple(value) if key == "quiet_hours" else value)
    if global_kill_switch():
        cfg.kill_switch = True
    return cfg


_GLOBAL = {"kill": False}


def global_kill_switch(value=None):
    if value is not None:
        _GLOBAL["kill"] = bool(value)
    return _GLOBAL["kill"]


def _local_hour(tz):
    if ZoneInfo is None:
        return datetime.now(timezone.utc).hour
    try:
        return datetime.now(ZoneInfo(tz)).hour
    except Exception:
        return datetime.now(timezone.utc).hour


# ------------------------------------------------------------------ ingest ---

def _resolve_journey(merchant, ev, settings):
    mid = merchant["merchant_id"]
    if ev["journey_id"]:
        return ev["journey_id"]
    if ev["checkout_id"]:
        found = store.journey_by_checkout(mid, ev["checkout_id"])
        if found:
            return found
    found = store.open_journey_for_agent(mid, ev["agent_id"], settings["idle_seconds"])
    if found:
        return found
    if ev["sku"] and ev["type"] in ("checkout.create", "checkout.complete", "reoffer.fetch"):
        found = store.recovering_journey_for(mid, ev["agent_id"], ev["sku"])
        if found:
            return found
    return f"j_{uuid.uuid4().hex[:16]}"


def _basket_from(ev):
    res, req = ev["response"], ev["request"]
    if ev["type"] in ("checkout.create", "checkout.update", "checkout.complete"):
        total = res.get("total") if isinstance(res.get("total"), (int, float)) \
            else req.get("amount")
        return total if isinstance(total, (int, float)) else None
    if ev["type"] == "product.view" and isinstance(res.get("price"), (int, float)):
        return round(res["price"] * (1 + (res.get("tax_rate") or 0)), 2)
    return None


def ingest(merchant, raw_events):
    """Validate, redact, stitch and store a batch. Idempotent per event_id."""
    if not isinstance(raw_events, list):
        raise InvalidEvent("events must be a list")
    if len(raw_events) > MAX_BATCH:
        raise InvalidEvent(f"at most {MAX_BATCH} events per request")
    mid = merchant["merchant_id"]
    settings = settings_for(merchant)
    accepted, duplicates, rejected, touched = 0, 0, [], []
    for i, raw in enumerate(raw_events):
        try:
            ev = normalise(raw)
        except InvalidEvent as exc:
            rejected.append({"index": i, "error": str(exc)})
            continue
        if store.event_exists(mid, ev["event_id"]):
            duplicates += 1
            continue
        jid = _resolve_journey(merchant, ev, settings)
        j = store.get_journey(mid, jid) or store.create_journey(
            mid, jid, ev["agent_id"], ev["principal_id"], ev["ts"])
        ev["journey_id"] = jid
        if not store.insert_event(mid, jid, ev):
            duplicates += 1
            continue
        accepted += 1
        touched.append(jid)
        _apply(merchant, j, ev)
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected,
            "journeys": sorted(set(touched))}


def _apply(merchant, j, ev):
    """Fold one event into its journey's state."""
    mid, jid = merchant["merchant_id"], j["journey_id"]
    fields = {}
    if ev["type"] != "reoffer.fetch":
        # Polling for a re-offer is waiting, not shopping: it must not keep an
        # abandoned journey looking alive past its idle window.
        fields["last_event_at"] = max(j["last_event_at"], ev["ts"])
    stage = STAGE.get(ev["type"], "discovery")
    if stage != "recovery" and STAGE_ORDER[stage] > STAGE_ORDER.get(j["stage"], 0):
        fields["stage"] = stage
    checkout_id = (ev["checkout_id"] or ev["response"].get("session_id") or "") \
        if ev["type"].startswith("checkout.") else ""
    # A fresh session opened after a re-offer becomes the journey's current one.
    new_session = ev["type"] == "checkout.create" and ev["http_status"] == 200
    if checkout_id and (new_session or not j["checkout_id"]):
        fields["checkout_id"] = checkout_id
    sku = ev["sku"] or ev["request"].get("sku") or ev["response"].get("sku") or ""
    if sku and ev["type"] in ("product.view", "checkout.create"):
        fields["sku"] = sku
    value = _basket_from(ev)
    if value is not None and ev["http_status"] < 500:
        fields["basket_value"] = value

    status = j["status"]
    paid = ev["type"] == "checkout.complete" and ev["http_status"] == 200

    if status in TERMINAL_OPEN and ev["type"] != "reoffer.fetch" and not paid:
        # The agent kept going after we called it abandoned (the idle window was
        # too short for it). Reopen; the earlier diagnosis stays in the ledger.
        fields.update(status="open", closed_at=0, close_reason="")
        store.ledger_append(mid, jid, "pipeline", "journey_reopened",
                            trigger={"event": ev["event_id"], "type": ev["type"]})
        status = "open"

    store.update_journey(mid, jid, **fields)

    if paid:
        total = ev["response"].get("total") or fields.get("basket_value") or j["basket_value"]
        if status == "recovering":
            store.update_journey(mid, jid, status="recovered", recovered_value=total,
                                 closed_at=ev["ts"])
            reoffer = store.get_reoffer(mid, jid, mark_fetched=False) or {}
            entry = store.ledger_append(
                mid, jid, "pipeline", "recovered",
                trigger={"event": ev["event_id"]},
                outcome={"recovered_value": total, "offer_id": reoffer.get("offer_id"),
                         "intervention": (j.get("verdict") or {}).get("intervention_id")})
            webhooks.emit(merchant, jid, "journey.recovered",
                          {"journey_id": jid, "recovered_value": total,
                           "intervention": (j.get("verdict") or {}).get("intervention_id"),
                           "ledger_entry": entry["entry_id"]})
        elif status in ("open",) + TERMINAL_OPEN:
            store.update_journey(mid, jid, status="converted", basket_value=total,
                                 closed_at=ev["ts"])
        return

    if ev["type"] == "checkout.cancel" and status in ("open", "recovering"):
        # From "recovering": the agent took the re-offer, tried again and gave up
        # again. That is a second attempt, and R-01 counts it.
        close(merchant, jid, "agent_cancelled")


# ------------------------------------------------------------------- close ---

def _context(mid, merchant):
    return {"product": lambda sku: store.get_product(mid, sku) if sku else None,
            "catalog": lambda: store.catalog(mid),
            "policy": policy_for(merchant), "settings": settings_for(merchant)}


def checklist(checks):
    """All eleven rules, each marked pass, fail, or not reached — so a merchant
    can see what the gate considered, not just where it stopped."""
    seen = {c["rule"]: c for c in checks}
    out = []
    for rule, text in RULES.items():
        c = seen.get(rule)
        out.append({"rule": rule, "text": text,
                    "result": c["result"] if c else "not_reached",
                    "state": c["state"] if c else ""})
    return out


def close(merchant, journey_id, reason):
    """Close an open journey as abandoned and run it through diagnosis and the gate.
    Safe to call twice: the second call finds it no longer open."""
    mid = merchant["merchant_id"]
    with _close_lock:
        j = store.get_journey(mid, journey_id)
        if j is None or j["status"] not in ("open", "recovering"):
            return j
        store.update_journey(mid, journey_id, status="abandoned", closed_at=time.time(),
                             close_reason=reason)

    events = store.journey_events(mid, journey_id)
    schema = store.get_schema(mid)
    dg = diagnose(events, schema, lambda sku: store.get_product(mid, sku) if sku else None,
                  lambda: store.catalog(mid))
    store.update_journey(mid, journey_id, diagnosis=dg)
    store.ledger_append(mid, journey_id, "diagnosis", "diagnosed",
                        trigger={"close_reason": reason, "events": len(events)},
                        diagnosis={k: dg[k] for k in ("cause", "confidence", "method",
                                                      "contested", "evidence", "detail")})
    webhooks.emit(merchant, journey_id, "journey.abandoned",
                  {"journey_id": journey_id, "agent_id": j["agent_id"],
                   "checkout_id": j["checkout_id"], "basket_value": j["basket_value"],
                   "stage": dg["stage"], "close_reason": reason,
                   "diagnosis": {k: dg[k] for k in ("cause", "name", "confidence",
                                                    "explanation", "contested")}})
    return gate(merchant, journey_id, dg)


def gate(merchant, journey_id, dg):
    mid = merchant["merchant_id"]
    j = store.get_journey(mid, journey_id)
    cfg = policy_for(merchant)
    engine = PolicyEngine(SimpleNamespace(policy=cfg))
    hist = store.buyer_history(mid, j["agent_id"], journey_id)
    st = engine.state(j["agent_id"])
    st.interventions_24h = hist["interventions_24h"]
    st.abandonments_24h = hist["abandonments_24h"]
    st.declined = hist["declined"]
    st.concession_total = hist["concession_24h"]
    st.mandate_retries = hist["mandate_retries"]

    diag = SimpleNamespace(cause=dg["cause"], confidence=dg["confidence"])
    view = SimpleNamespace(buyer_id=j["agent_id"], at_risk_value=j["basket_value"],
                           basket_value=j["basket_value"])
    hour = _local_hour(settings_for(merchant)["timezone"])
    ctx = _context(mid, merchant)

    excluded, unbuildable, all_checks = [], [], []
    while True:
        v = engine.evaluate(diag, view, hour, attempt=j["attempts"] + 1,
                            excluded=tuple(excluded))
        all_checks = v.checks
        if not v.permitted:
            break
        directive = directives.build(v.intervention_id, dg, j, ctx)
        if directive is not None:
            break
        unbuildable.append(v.intervention_id)
        excluded.append(v.intervention_id)

    verdict = {"permitted": v.permitted, "intervention_id": v.intervention_id,
               "binding_rule": v.binding_rule, "reason": v.reason,
               "checks": all_checks, "checklist": checklist(all_checks),
               "unbuildable": unbuildable, "local_hour": hour}

    if not v.permitted and unbuildable:
        # The gate would have allowed an action we could not construct truthfully
        # (the catalogue lacks the value). That is a merchant data problem, not a
        # refusal — say so instead of blaming a rule.
        verdict["reason"] = (f"{', '.join(unbuildable)} permitted, but the directive could not "
                             "be built from the merchant's catalogue")

    if not v.permitted or v.intervention_id == "I-10":
        status = REFUSAL_TO_STATUS.get(v.binding_rule, "exception")
        store.update_journey(mid, journey_id, status=status, verdict=verdict)
        store.ledger_append(mid, journey_id, "policy", "intervention_refused"
                            if not v.permitted else "escalated",
                            diagnosis={"cause": dg["cause"], "confidence": dg["confidence"]},
                            policy_checks=all_checks,
                            outcome={"binding_rule": v.binding_rule, "reason": verdict["reason"],
                                     "status": status})
        webhooks.emit(merchant, journey_id, "journey.exception" if status == "exception"
                      else "journey.lost",
                      {"journey_id": journey_id, "binding_rule": v.binding_rule,
                       "rule": RULES.get(v.binding_rule, ""), "reason": verdict["reason"],
                       "diagnosis": {"cause": dg["cause"], "explanation": dg["explanation"]}})
        return store.get_journey(mid, journey_id)

    directive["journey_id"] = journey_id
    directive["checkout_id"] = j["checkout_id"]
    directive["agent_id"] = j["agent_id"]
    store.record_intervention(mid, j["agent_id"], journey_id, v.intervention_id,
                              concession=directive["concession"],
                              mandate_retry=v.intervention_id == "I-09"
                              and CAUSES[dg["cause"]].family.value == "B")
    offer = None
    if directive["reoffer"]:
        offer = store.put_reoffer(mid, journey_id,
                                  dict(directive["reoffer"], journey_id=journey_id,
                                       intervention=v.intervention_id),
                                  settings_for(merchant)["reoffer_ttl_seconds"])
        directive["reoffer"] = offer
    store.update_journey(mid, journey_id, status="recovering", verdict=verdict,
                         directive=directive, attempts=j["attempts"] + 1,
                         concession=j["concession"] + directive["concession"])
    entry = store.ledger_append(
        mid, journey_id, "policy", "intervention_permitted",
        diagnosis={"cause": dg["cause"], "confidence": dg["confidence"]},
        policy_checks=all_checks,
        outcome={"intervention": v.intervention_id, "directive_id": directive["directive_id"],
                 "concession": directive["concession"],
                 "offer_id": offer["offer_id"] if offer else None},
        reversal=directive["reversal"])
    webhooks.emit(merchant, journey_id, "recovery.directive",
                  dict(directive, ledger_entry=entry["entry_id"]))
    return store.get_journey(mid, journey_id)


# ------------------------------------------------------------------ sweeper ---

def sweep(now=None):
    """Close idle journeys and expire stale re-offers. Returns what it did."""
    now = now or time.time()
    closed = expired = 0
    for mid, jid in store.idle_journeys(now, DEFAULT_SETTINGS["idle_seconds"]):
        merchant = store.get_merchant(mid)
        if merchant:
            close(merchant, jid, "idle_timeout")
            closed += 1
    for mid, jid in store.expired_recoveries(now):
        store.update_journey(mid, jid, status="lost")
        store.ledger_append(mid, jid, "pipeline", "reoffer_expired",
                            outcome={"status": "lost"})
        merchant = store.get_merchant(mid)
        if merchant:
            webhooks.emit(merchant, jid, "journey.lost",
                          {"journey_id": jid, "reason": "re-offer expired unclaimed"})
        expired += 1
    return {"closed": closed, "expired": expired}


class Worker:
    """One background thread: sweeps idle journeys and delivers webhooks."""

    def __init__(self, interval=0.5):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.ticks = 0
        self.last_error = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="handshake-live",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def tick(self):
        sweep()
        webhooks.deliver_due()
        self.ticks += 1

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception as exc:                     # the worker must never die
                self.last_error = f"{type(exc).__name__}: {exc}"

    @property
    def alive(self):
        return bool(self._thread and self._thread.is_alive())


WORKER = Worker()
