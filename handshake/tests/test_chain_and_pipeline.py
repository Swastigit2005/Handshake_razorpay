"""Ledger integrity, reproducibility, and the adversarial case."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from handshake.config import RunConfig
from handshake.experiments.batch import run_batch
from handshake.experiments.report import compute
from handshake.ledger.chain import Ledger
from handshake.policy.engine import PolicyEngine
from handshake.diagnosis.engine import Diagnosis
from handshake.recorder.recorder import Trace
from handshake.taxonomy import Terminal


# ---------- ledger ----------

def test_chain_verifies():
    led = Ledger()
    for i in range(5):
        led.append(f"sess_{i}", "policy_engine", "action_refused",
                   outcome={"binding_rule": "R-10"})
    ok, bad = led.verify()
    assert ok and bad == -1


def test_tampering_is_detected():
    led = Ledger()
    led.append("sess_1", "intervention_executor", "action_executed",
               outcome={"value": 100.0})
    led.append("sess_2", "intervention_executor", "action_executed",
               outcome={"value": 200.0})
    led.entries[0]["outcome"]["value"] = 999.0
    ok, bad = led.verify()
    assert not ok and bad == 0


def test_refusals_are_recorded_not_dropped():
    run = run_batch(_cfg(120))
    actions = [e for e in run["ledger"].entries if e["action"] == "action_refused"]
    assert actions, "a batch with no recorded refusal has no evidence of a gate"
    assert all(e["outcome"]["binding_rule"] for e in actions)


# ---------- reproducibility ----------

def _cfg(n):
    cfg = RunConfig()
    cfg.batch_size = n
    return cfg


def test_same_seed_reproduces_the_report():
    a, _ = compute(run_batch(_cfg(150)))
    b, _ = compute(run_batch(_cfg(150)))
    assert a["arms"]["treatment"]["recovered_gmv"] == b["arms"]["treatment"]["recovered_gmv"]
    assert a["diagnosis"]["macro_f1"] == b["diagnosis"]["macro_f1"]


# ---------- measurement integrity ----------

def test_control_arm_receives_no_intervention():
    run = run_batch(_cfg(200))
    for r in run["results"]:
        if r.arm == "control":
            assert [i for i in r.interventions if i != "none_buyer_self_recovery"] == []


def test_diagnosis_never_reads_the_injected_fault():
    """The ground-truth label must not appear anywhere in the evidence path."""
    run = run_batch(_cfg(120))
    for r in run["results"]:
        if not r.diagnosis:
            continue
        blob = str(r.diagnosis.as_dict())
        assert r.fault not in blob or r.fault == r.diagnosis.cause


def test_every_money_action_has_a_ledger_entry():
    run = run_batch(_cfg(200))
    for r in run["results"]:
        acted = [i for i in r.interventions if i != "none_buyer_self_recovery"]
        entries = run["ledger"].for_session(r.trace.session_id)
        executed = [e for e in entries if e["action"] == "action_executed"]
        assert len(executed) == len(acted)


# ---------- adversarial ----------

def test_concession_farming_is_blocked():
    """A buyer that abandons repeatedly to extract price is moved to
    no-concession recovery and the refusal names the binding rule."""
    cfg = RunConfig()
    policy = PolicyEngine(cfg)
    buyer = "buyer_farmer"
    verdicts = []
    for round_ in range(5):
        policy.record_abandonment(buyer)
        trace = Trace(session_id=f"sess_farm_{round_}", buyer_id=buyer,
                      persona="permissive", arm="treatment", spend_cap=9000.0)
        trace.basket_value = trace.at_risk_value = 6000.0
        diag = Diagnosis(trace.session_id, "A3", 1.0, "rule", ["ev_2"],
                         {"quoted": 6000.0, "requoted": 6600.0})
        verdicts.append(policy.evaluate(diag, trace, hour=12, attempt=1))

    assert verdicts[0].permitted, "a first-time quote drift should be recoverable"
    assert not verdicts[-1].permitted, "repeat abandonment must stop conceding"
    assert policy.state(buyer).no_concession_mode
    assert any(c["rule"] == "R-06" and c["result"] == "fail" for c in verdicts[-1].checks)


def test_kill_switch_halts_a_running_batch():
    cfg = _cfg(120)
    cfg.policy.kill_switch = True
    run = run_batch(cfg)
    acted = [i for r in run["results"] for i in r.interventions
             if i != "none_buyer_self_recovery"]
    assert acted == []
    refusals = [e for e in run["ledger"].entries
                if e["action"] == "action_refused"
                and e["outcome"]["binding_rule"] == "R-11"]
    assert refusals
