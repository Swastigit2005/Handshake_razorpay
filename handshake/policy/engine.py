"""Policy engine (component C5).

The authoritative gate. Deterministic by design — no model is consulted here.
An LLM may propose a cause; only this table decides whether anything happens,
which action it is, and under what bounds. Every rule evaluated is recorded,
including the ones that passed.
"""

from dataclasses import dataclass, field

from ..taxonomy import CAUSES, INTERVENTIONS, UNKNOWN, Verdict

# Prior probability that an intervention converts, by cause. Published as
# priors; replaced by measured rates once a batch has run.
P_SUCCESS = {
    "A1": 0.85, "A2": 0.80, "A3": 0.70, "A4": 0.55, "A5": 0.45,
    "A6": 0.75, "A7": 0.70, "A8": 0.60,
    "B1": 0.40, "B2": 0.65, "B3": 0.35, "B4": 0.40, "B5": 0.50,
}


@dataclass
class BuyerState:
    buyer_id: str
    interventions_24h: int = 0
    abandonments_24h: int = 0
    declined: bool = False
    concession_total: float = 0.0
    mandate_retries: int = 0
    no_concession_mode: bool = False
    history: list = field(default_factory=list)


class PolicyEngine:
    def __init__(self, cfg):
        self.cfg = cfg.policy
        self.states = {}

    def state(self, buyer_id):
        return self.states.setdefault(buyer_id, BuyerState(buyer_id))

    # ---------- helpers ----------

    def _check(self, checks, rule, state_str, ok):
        checks.append({"rule": rule, "state": state_str, "result": "pass" if ok else "fail"})
        return ok

    def _quiet_hours(self, hour):
        start, end = self.cfg.quiet_hours
        return hour >= start or hour < end

    # ---------- the gate ----------

    def evaluate(self, diagnosis, trace, hour, attempt=1, excluded=()):
        """Return a Verdict. `excluded` holds intervention ids already tried."""
        checks = []
        st = self.state(trace.buyer_id)
        basket = trace.at_risk_value or trace.basket_value

        if not self._check(checks, "R-11", "off" if not self.cfg.kill_switch else "ON",
                           not self.cfg.kill_switch):
            return Verdict(False, binding_rule="R-11", reason="kill switch engaged", checks=checks)

        conf = f"{diagnosis.confidence:.2f} vs {self.cfg.confidence_threshold:.2f}"
        if not self._check(checks, "R-10", conf,
                           diagnosis.cause != UNKNOWN
                           and diagnosis.confidence >= self.cfg.confidence_threshold):
            return Verdict(False, binding_rule="R-10",
                           reason="diagnosis below confidence threshold", checks=checks)

        if not self._check(checks, "R-03", "declined" if st.declined else "none", not st.declined):
            return Verdict(False, binding_rule="R-03",
                           reason="principal declined earlier", checks=checks)

        if not self._check(checks, "R-01", f"{attempt - 1}/{self.cfg.max_reoffers_per_session}",
                           attempt - 1 < self.cfg.max_reoffers_per_session):
            return Verdict(False, binding_rule="R-01",
                           reason="re-offer limit for this session", checks=checks)

        if not self._check(checks, "R-02",
                           f"{st.interventions_24h}/{self.cfg.max_interventions_per_buyer_24h}",
                           st.interventions_24h < self.cfg.max_interventions_per_buyer_24h):
            return Verdict(False, binding_rule="R-02",
                           reason="buyer intervention cap for 24h", checks=checks)

        abuse = st.abandonments_24h >= self.cfg.abuse_window_abandonments
        self._check(checks, "R-06", f"{st.abandonments_24h} abandonments", not abuse)
        if abuse:
            st.no_concession_mode = True

        cause = CAUSES.get(diagnosis.cause)
        if cause is None:
            return Verdict(False, binding_rule="R-10", reason="cause not in taxonomy",
                           checks=checks)

        if cause.family.value == "B":
            ok = st.mandate_retries < self.cfg.max_mandate_retries
            self._check(checks, "R-08",
                        f"{st.mandate_retries}/{self.cfg.max_mandate_retries}", ok)
            if not ok:
                return Verdict(False, binding_rule="R-08",
                               reason="mandate retry cap reached, routed to a human",
                               checks=checks)

        # ---- choose the intervention ----
        chosen = None
        for iid in cause.interventions:
            if iid in excluded:
                continue
            spec = INTERVENTIONS[iid]
            if spec.concedes_margin:
                headroom = basket * self.cfg.concession_ceiling_pct - st.concession_total
                if st.no_concession_mode or headroom <= 0:
                    self._check(checks, "R-04",
                                f"headroom {max(headroom, 0):.2f}"
                                + (" / no-concession mode" if st.no_concession_mode else ""),
                                False)
                    continue
                self._check(checks, "R-04", f"headroom {headroom:.2f}", True)
            if spec.touches_human:
                if not self._check(checks, "R-09", f"hour {hour:02d}",
                                   not self._quiet_hours(hour)):
                    continue
            chosen = spec
            break

        if chosen is None:
            binding = "R-04" if st.no_concession_mode else "R-09"
            return Verdict(False, binding_rule=binding,
                           reason="no permitted intervention remains for this cause",
                           checks=checks)

        # ---- expected value gate (R-05) ----
        cost = self.cfg.cost_human_inr if chosen.touches_human else self.cfg.cost_machine_inr
        ev = basket * self.cfg.gross_margin_pct * P_SUCCESS.get(diagnosis.cause, 0.4)
        if not self._check(checks, "R-05", f"EV {ev:.2f} vs cost {cost:.2f}", ev > cost):
            return Verdict(False, binding_rule="R-05",
                           reason="expected recovery below intervention cost", checks=checks)

        self._check(checks, "R-07", "no cap raised without consent", True)

        return Verdict(True, intervention_id=chosen.id,
                       parameters={"cause": diagnosis.cause,
                                   "no_concession": st.no_concession_mode},
                       checks=checks)

    # ---------- bookkeeping ----------

    def record_attempt(self, buyer_id, concession=0.0, mandate_retry=False):
        st = self.state(buyer_id)
        st.interventions_24h += 1
        st.concession_total += concession
        if mandate_retry:
            st.mandate_retries += 1

    def record_abandonment(self, buyer_id):
        self.state(buyer_id).abandonments_24h += 1

    def record_decline(self, buyer_id):
        self.state(buyer_id).declined = True
