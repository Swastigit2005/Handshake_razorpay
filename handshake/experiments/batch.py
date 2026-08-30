"""Batch runner.

Randomised, stratified allocation into treatment and control; the control arm
is fully instrumented and receives no intervention, so natural self-recovery is
measured rather than credited to the system (spec 12).
"""

import random

from ..buyers.agent import BuyerAgent
from ..buyers.llm import LLMBudgetExhausted, LLMDecider
from ..buyers.personas import fleet
from ..config import RunConfig
from ..diagnosis.engine import diagnose
from ..executor.interventions import execute
from ..ledger.chain import Ledger
from ..merchant.api import MerchantAPI
from ..merchant.catalog import build_catalog
from ..merchant.faults import FaultInjector, choose_fault
from ..payments.adapter import build_backend
from ..policy.engine import PolicyEngine
from ..recorder.recorder import Trace
from ..taxonomy import Arm, Terminal

# Hours are drawn per session so that the quiet-hours rule (R-09) is actually
# exercised rather than asserted.
HOURS = list(range(24))
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 1, 2, 4, 6, 8, 9, 9, 8, 8, 9, 9, 8, 7, 6, 5, 4, 3, 2, 1]


class SessionResult:
    def __init__(self, trace, arm, fault, diagnosis):
        self.trace = trace
        self.arm = arm
        self.fault = fault or ""
        self.diagnosis = diagnosis
        self.recovered = False
        self.recovered_value = 0.0
        self.concession = 0.0
        self.interventions = []
        self.refusals = []
        self.exception = ""

    def as_dict(self):
        return {
            "session_id": self.trace.session_id,
            "buyer_id": self.trace.buyer_id,
            "persona": self.trace.persona,
            "arm": self.arm,
            "injected_fault": self.fault,
            "diagnosed_cause": self.diagnosis.cause if self.diagnosis else "",
            "confidence": round(self.diagnosis.confidence, 2) if self.diagnosis else 0.0,
            "terminal_state": self.trace.terminal_state,
            "basket_value": round(self.trace.basket_value, 2),
            "at_risk_value": round(self.trace.at_risk_value, 2),
            "converted_value": round(self.trace.converted_value, 2),
            "recovered": self.recovered,
            "recovered_value": round(self.recovered_value, 2),
            "concession": round(self.concession, 2),
            "interventions": self.interventions,
            "refusals": self.refusals,
            "exception": self.exception,
            "abandon_note": self.trace.abandon_note,
        }


class Sink:
    """Receives events as a batch runs. The batch works without one."""

    def emit(self, kind, **payload):
        pass

    def pause(self, seconds=0.0):
        pass


_NULL = Sink()


def run_batch(cfg=None, progress=None, sink=None):
    cfg = cfg or RunConfig()
    sink = sink or _NULL
    master = random.Random(cfg.seed)
    catalog = build_catalog(cfg.seed)
    personas = fleet(cfg.seed + 1, max(40, cfg.batch_size // 4), catalog)
    policy = PolicyEngine(cfg)
    ledger = Ledger()
    decider = LLMDecider(cfg) if cfg.buyer_backend == "llm" else None
    results = []

    # Stratified allocation: alternate arms within each fault stratum so the
    # arms inherit the same fault mix.
    strata = {}

    for i in range(cfg.batch_size):
        rng = random.Random(cfg.seed * 1000 + i)
        persona = personas[i % len(personas)]
        fault = choose_fault(rng, cfg.fault_incidence)
        key = fault or "clean"
        strata[key] = strata.get(key, 0) + 1
        arm = (Arm.TREATMENT if (cfg.force_treatment or strata[key] % 2 == 0)
               else Arm.CONTROL)
        hour = rng.choices(HOURS, weights=HOUR_WEIGHTS, k=1)[0]

        trace = Trace(session_id=f"sess_{i:05d}", buyer_id=persona.id,
                      persona=persona.posture, arm=arm.value, spend_cap=persona.cap,
                      injected_fault=fault or "")
        injector = FaultInjector(fault, rng)
        payments = build_backend(cfg, rng)
        merchant = MerchantAPI(catalog, injector, payments, trace)
        agent = BuyerAgent(persona, trace, rng, decider)
        if fault and fault.startswith("B"):
            # A payment-rail fault only has meaning on a mandate instrument.
            agent.instrument = {"type": "upi_mandate", "state": "active", "mandate": True}

        sink.emit("session_start", session_id=trace.session_id, index=i,
                  buyer=persona.id, persona=persona.posture, arm=arm.value,
                  category=persona.category, cap=agent.effective_cap, hour=hour)
        try:
            agent.run(merchant)
        except LLMBudgetExhausted as exc:
            raise LLMBudgetExhausted(
                f"the model quota ran out after {i} of {cfg.batch_size} sessions "
                f"({decider.calls} calls). Continuing would mix model and heuristic "
                f"decisions in one batch, which is attributable to neither. "
                f"Original error: {exc}") from exc

        if trace.abandon_note == "no affordable candidate in feed":
            continue  # no purchase intent was satisfiable; not a recoverable failure

        diagnosis = None
        if trace.terminal_state == Terminal.FAILED:
            policy.record_abandonment(persona.id)
            ledger.append(trace.session_id, "recorder", "terminal_failure_detected",
                          trigger={"type": "terminal_failure",
                                   "at_risk_value": round(trace.at_risk_value, 2),
                                   "currency": "INR"})
            sink.emit("failure_detected", session_id=trace.session_id,
                      at_risk=round(trace.at_risk_value, 2),
                      note=trace.abandon_note)
            sink.pause()
            diagnosis = diagnose(trace, merchant)
            ledger.append(trace.session_id, "diagnosis_engine", "cause_assigned",
                          diagnosis=diagnosis.as_dict())
            sink.emit("diagnosis", session_id=trace.session_id,
                      cause=diagnosis.cause, confidence=diagnosis.confidence,
                      method=diagnosis.method, detail=diagnosis.detail)
            sink.pause()

        result = SessionResult(trace, arm.value, fault, diagnosis)

        if trace.terminal_state == Terminal.FAILED and arm is Arm.TREATMENT:
            _recover(result, trace, merchant, agent, policy, ledger, cfg, hour,
                     persona, sink)

        # Buyer-side behaviour, identical in both arms: some agents re-plan and
        # come back on their own when the blocker was transient. In treatment it
        # only matters where our intervention did not already succeed, so the
        # arms remain comparable and the lift is not inflated.
        if trace.terminal_state == Terminal.FAILED and not result.recovered:
            _natural_retry(result, trace, merchant, agent, rng, ledger)

        results.append(result)
        sink.emit("session_end", session_id=trace.session_id,
                  terminal=str(trace.terminal_state).split(".")[-1],
                  basket_value=round(trace.basket_value, 2),
                  at_risk=round(trace.at_risk_value, 2),
                  recovered=result.recovered,
                  recovered_value=round(result.recovered_value, 2),
                  cause=result.diagnosis.cause if result.diagnosis else "",
                  interventions=list(result.interventions),
                  exception=result.exception, arm=arm.value)
        sink.emit("progress", done=len(results), total=cfg.batch_size)
        if progress and (i + 1) % max(1, cfg.batch_size // 10) == 0:
            progress(i + 1, cfg.batch_size)

    return {"config": cfg, "results": results, "ledger": ledger,
            "policy": policy, "catalog": catalog, "decider": decider}


# Causes a buyer can plausibly clear without help, and how often.
NATURAL_RECOVERY = {"A6": 0.35, "B1": 0.30, "B2": 0.35, "A3": 0.10}


def _natural_retry(result, trace, merchant, agent, rng, ledger):
    cause = result.diagnosis.cause if result.diagnosis else ""
    p = NATURAL_RECOVERY.get(cause, 0.0)
    if p <= 0 or rng.random() > p:
        return
    merchant.injector.resolve()
    agent.instrument["retry"] = True
    if not agent.session_id:
        return
    status, body = merchant.update_checkout_session(agent.session_id)
    before = trace.terminal_state
    agent._complete(merchant, body.get("total", 0.0))
    if trace.terminal_state == Terminal.CONVERTED:
        result.recovered = True
        result.recovered_value = trace.converted_value
        result.interventions.append("none_buyer_self_recovery")
        ledger.append(trace.session_id, "recorder", "buyer_self_recovery",
                      outcome={"state": "converted",
                               "value": round(trace.converted_value, 2),
                               "attributed_to": "buyer, not the recovery layer"})
    else:
        trace.terminal_state = before


def _recover(result, trace, merchant, agent, policy, ledger, cfg, hour, persona,
             sink=None):
    sink = sink or _NULL
    excluded = set()
    for attempt in range(1, cfg.policy.max_reoffers_per_session + 2):
        diagnosis = result.diagnosis
        verdict = policy.evaluate(diagnosis, trace, hour, attempt=attempt, excluded=excluded)

        if not verdict.permitted:
            ledger.append(trace.session_id, "policy_engine", "action_refused",
                          diagnosis=diagnosis.as_dict(),
                          policy_checks=verdict.checks,
                          outcome={"state": "refused", "binding_rule": verdict.binding_rule,
                                   "reason": verdict.reason})
            result.refusals.append({"rule": verdict.binding_rule, "reason": verdict.reason})
            result.exception = f"{verdict.binding_rule}: {verdict.reason}"
            sink.emit("verdict", session_id=trace.session_id, permitted=False,
                      binding_rule=verdict.binding_rule, reason=verdict.reason,
                      checks=verdict.checks)
            return

        sink.emit("verdict", session_id=trace.session_id, permitted=True,
                  intervention=verdict.intervention_id, checks=verdict.checks)
        sink.pause()
        outcome = execute(verdict, diagnosis, trace, merchant, agent, cfg)
        policy.record_attempt(persona.id, concession=outcome.concession,
                              mandate_retry=outcome.mandate_retry)
        result.interventions.append(verdict.intervention_id)
        result.concession += outcome.concession

        ledger.append(trace.session_id, "intervention_executor", "action_executed",
                      diagnosis=diagnosis.as_dict(),
                      policy_checks=verdict.checks,
                      outcome={"intervention": verdict.intervention_id,
                               **outcome.as_dict()},
                      reversal=outcome.reversal)

        sink.emit("action", session_id=trace.session_id,
                  intervention=verdict.intervention_id, ok=outcome.ok,
                  note=outcome.note, concession=round(outcome.concession, 2),
                  reversal=outcome.reversal)
        sink.pause()

        if not outcome.ok or outcome.offer is None:
            excluded.add(verdict.intervention_id)
            if outcome.offer is None and outcome.ok:
                result.exception = "routed to operations queue"
                return
            continue

        merchant.put_reoffer(agent.session_id or "none", outcome.offer)
        before = trace.terminal_state
        agent.respond_to_reoffer(merchant, outcome.offer)

        if trace.terminal_state == Terminal.CONVERTED:
            result.recovered = True
            result.recovered_value = trace.converted_value
            sink.emit("recovered", session_id=trace.session_id,
                      value=round(trace.converted_value, 2),
                      intervention=verdict.intervention_id)
            ledger.append(trace.session_id, "recorder", "recovery_confirmed",
                          outcome={"state": "converted",
                                   "value": round(trace.converted_value, 2),
                                   "ref": _last_ref(trace)},
                          reversal={"method": "refund", "window_hours": 24})
            return

        trace.terminal_state = before
        if verdict.intervention_id in ("I-05", "I-06"):
            policy.record_decline(persona.id)
            ledger.append(trace.session_id, "escalation", "principal_declined",
                          outcome={"state": "declined",
                                   "intervention": verdict.intervention_id})
            result.exception = "principal declined the request"
            return
        excluded.add(verdict.intervention_id)

    result.exception = result.exception or "re-offer limit reached"


def _last_ref(trace):
    for ev in reversed(trace.events):
        if isinstance(ev.response, dict) and ev.response.get("ref"):
            return ev.response["ref"]
    return ""
