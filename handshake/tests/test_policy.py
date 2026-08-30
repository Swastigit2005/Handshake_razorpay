"""Every stopping rule carries a test. The gate is the part that must not fail."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from handshake.config import RunConfig
from handshake.diagnosis.engine import Diagnosis
from handshake.policy.engine import PolicyEngine
from handshake.recorder.recorder import Trace
from handshake.taxonomy import UNKNOWN


def _trace(buyer="buyer_0001", value=5000.0):
    t = Trace(session_id="sess_test", buyer_id=buyer, persona="balanced",
              arm="treatment", spend_cap=4000.0)
    t.basket_value = value
    t.at_risk_value = value
    return t


def _diag(cause="A1", conf=0.92):
    return Diagnosis("sess_test", cause, conf, "rule", ["ev_1"],
                     {"missing_attribute": "material"})


def test_permits_a_clean_case():
    p = PolicyEngine(RunConfig())
    v = p.evaluate(_diag(), _trace(), hour=11)
    assert v.permitted and v.intervention_id == "I-01"
    assert any(c["rule"] == "R-07" for c in v.checks)


def test_r01_reoffer_limit():
    cfg = RunConfig()
    p = PolicyEngine(cfg)
    v = p.evaluate(_diag(), _trace(), hour=11,
                   attempt=cfg.policy.max_reoffers_per_session + 1)
    assert not v.permitted and v.binding_rule == "R-01"


def test_r02_buyer_cap():
    cfg = RunConfig()
    p = PolicyEngine(cfg)
    for _ in range(cfg.policy.max_interventions_per_buyer_24h):
        p.record_attempt("buyer_0001")
    v = p.evaluate(_diag(), _trace(), hour=11)
    assert not v.permitted and v.binding_rule == "R-02"


def test_r03_decline_is_permanent():
    p = PolicyEngine(RunConfig())
    p.record_decline("buyer_0001")
    v = p.evaluate(_diag(), _trace(), hour=11)
    assert not v.permitted and v.binding_rule == "R-03"


def test_r04_concession_ceiling_blocks_a_conceding_intervention():
    cfg = RunConfig()
    p = PolicyEngine(cfg)
    p.record_attempt("buyer_0001", concession=10_000.0)
    v = p.evaluate(_diag("A3", 1.0), _trace(), hour=11)
    assert not v.permitted and v.binding_rule in ("R-04", "R-09")
    assert any(c["rule"] == "R-04" and c["result"] == "fail" for c in v.checks)


def test_r05_expected_value_gate():
    p = PolicyEngine(RunConfig())
    v = p.evaluate(_diag("A5", 1.0), _trace(value=150.0), hour=11)
    assert not v.permitted and v.binding_rule == "R-05"


def test_r06_abuse_forces_no_concession_mode():
    cfg = RunConfig()
    p = PolicyEngine(cfg)
    for _ in range(cfg.policy.abuse_window_abandonments):
        p.record_abandonment("buyer_0001")
    v = p.evaluate(_diag("A3", 1.0), _trace(), hour=11)
    assert p.state("buyer_0001").no_concession_mode
    assert not v.permitted


def test_r08_mandate_retry_cap():
    cfg = RunConfig()
    p = PolicyEngine(cfg)
    for _ in range(cfg.policy.max_mandate_retries):
        p.record_attempt("buyer_0001", mandate_retry=True)
    v = p.evaluate(_diag("B1", 1.0), _trace(), hour=11)
    assert not v.permitted and v.binding_rule == "R-08"


def test_r09_quiet_hours_block_human_escalation():
    p = PolicyEngine(RunConfig())
    v = p.evaluate(_diag("A5", 1.0), _trace(), hour=23)
    assert not v.permitted
    assert any(c["rule"] == "R-09" and c["result"] == "fail" for c in v.checks)


def test_r10_low_confidence_never_acts():
    p = PolicyEngine(RunConfig())
    v = p.evaluate(_diag(UNKNOWN, 0.0), _trace(), hour=11)
    assert not v.permitted and v.binding_rule == "R-10"


def test_r11_kill_switch():
    cfg = RunConfig()
    cfg.policy.kill_switch = True
    p = PolicyEngine(cfg)
    v = p.evaluate(_diag(), _trace(), hour=11)
    assert not v.permitted and v.binding_rule == "R-11"


def test_r07_never_raises_a_cap_by_itself():
    """I-05 must always be a request, never a grant."""
    from handshake.taxonomy import INTERVENTIONS
    assert INTERVENTIONS["I-05"].touches_human
    p = PolicyEngine(RunConfig())
    v = p.evaluate(_diag("A4", 1.0), _trace(), hour=11)
    assert v.permitted
    assert v.intervention_id == "I-04"  # the non-human option is preferred first
