"""Live operator console.

    ./run_ui.sh          →  http://127.0.0.1:8000

Three things a static report cannot do, and all three are what a demo needs:
watch a batch as it happens, step through one recovery slowly enough to narrate,
and flip a governance control mid-run and see the refusals appear.
"""

import threading
import time

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ..config import RunConfig
from ..experiments.batch import Sink, run_batch
from ..experiments.report import compute
from ..taxonomy import CAUSES, RULES
from .ui import PAGE

app = FastAPI(title="Handshake console")


# --------------------------------------------------------------- state ------

class RunState:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = []
        self.results = []
        self.ledger = None
        self.decider = None
        self.cfg = RunConfig()
        self.running = False
        self.stopping = False
        self.mode = ""
        self.total = 0
        self.summary = None
        self.error = ""
        self.started_at = 0.0

    def reset(self, cfg, mode, total):
        self.events, self.results = [], []
        self.ledger = self.decider = self.summary = None
        self.cfg, self.mode, self.total = cfg, mode, total
        self.running, self.stopping, self.error = True, False, ""
        self.started_at = time.time()

    def add(self, event):
        with self.lock:
            event["seq"] = len(self.events)
            self.events.append(event)

    def since(self, index):
        with self.lock:
            return self.events[index:]


STATE = RunState()


class UISink(Sink):
    def __init__(self, state, pace=0.0):
        self.state = state
        self.pace = pace

    def emit(self, kind, **payload):
        payload["kind"] = kind
        payload["t"] = round(time.time() - self.state.started_at, 2)
        self.state.add(payload)
        if self.state.stopping:
            raise StopBatch()

    def pause(self, seconds=0.0):
        if self.pace:
            time.sleep(seconds or self.pace)


class StopBatch(RuntimeError):
    pass


# --------------------------------------------------------------- runner -----

def _runner(cfg, mode, pace):
    sink = UISink(STATE, pace)
    try:
        run = run_batch(cfg, sink=sink)
        STATE.results = run["results"]
        STATE.ledger = run["ledger"]
        STATE.decider = run.get("decider")
        summary, exceptions = compute(run)
        STATE.summary = summary
        sink.emit("done", sessions=len(run["results"]),
                  recovered=summary["arms"]["treatment"]["recovered_gmv"],
                  lift=summary["lift_over_control"])
    except StopBatch:
        STATE.add({"kind": "stopped", "seq": 0})
    except Exception as exc:  # surfaced in the UI rather than swallowed
        STATE.error = f"{type(exc).__name__}: {exc}"
        STATE.add({"kind": "error", "message": STATE.error, "seq": 0})
    finally:
        STATE.running = False


class RunRequest(BaseModel):
    sessions: int = 200
    mode: str = "batch"          # "batch" | "walkthrough"
    fault_incidence: float = 0.55
    seed: int = 20260830
    offline: bool = False        # force the reproducible offline backends


@app.post("/api/run")
def start_run(req: RunRequest):
    if STATE.running:
        return JSONResponse({"error": "a run is already in progress"}, 409)

    cfg = RunConfig()
    cfg.seed = req.seed
    if req.mode == "walkthrough":
        cfg.batch_size, cfg.fault_incidence, pace = 6, 1.0, 1.1
        cfg.force_treatment = True   # a walkthrough is a demo, not a measurement
    else:
        cfg.batch_size, cfg.fault_incidence, pace = req.sessions, req.fault_incidence, 0.0
    if req.offline:
        cfg.payments_backend, cfg.buyer_backend = "sim", "heuristic"
    cfg.policy.kill_switch = STATE.cfg.policy.kill_switch

    STATE.reset(cfg, req.mode, cfg.batch_size)
    threading.Thread(target=_runner, args=(cfg, req.mode, pace), daemon=True).start()
    return {"started": True, "mode": req.mode, "sessions": cfg.batch_size,
            "payments": cfg.payments_backend, "buyers": cfg.buyer_backend}


@app.post("/api/stop")
def stop_run():
    STATE.stopping = True
    return {"stopping": True}


class KillSwitch(BaseModel):
    on: bool


@app.post("/api/killswitch")
def kill_switch(req: KillSwitch):
    """Rule R-11. Takes effect on the next policy evaluation, mid-run."""
    STATE.cfg.policy.kill_switch = req.on
    return {"kill_switch": req.on}


# --------------------------------------------------------------- state API --

def _live_totals():
    at_risk = recovered = concession = 0.0
    failed = recovered_n = 0
    causes = {}
    refusals = {}
    for e in STATE.events:
        if e["kind"] == "session_end" and e.get("arm") == "treatment":
            if e["terminal"] == "FAILED" or e.get("recovered"):
                at_risk += e["basket_value"]
                failed += 1
                cause = e.get("cause") or "UNKNOWN"
                row = causes.setdefault(cause, {"failed": 0, "at_risk": 0.0,
                                                "recovered": 0.0})
                row["failed"] += 1
                row["at_risk"] += e["basket_value"]
                if e.get("recovered"):
                    row["recovered"] += e["recovered_value"]
                    recovered += e["recovered_value"]
                    recovered_n += 1
        elif e["kind"] == "action":
            concession += e.get("concession", 0.0)
        elif e["kind"] == "verdict" and not e.get("permitted"):
            rule = e.get("binding_rule", "?")
            refusals[rule] = refusals.get(rule, 0) + 1
    return {
        "at_risk": round(at_risk, 2), "recovered": round(recovered, 2),
        "failed": failed, "recovered_n": recovered_n,
        "rate": round(recovered / at_risk, 4) if at_risk else 0.0,
        "concession": round(concession, 2),
        "concession_ratio": round(concession / recovered, 4) if recovered else 0.0,
        "causes": {k: {**v, "name": CAUSES[k].name if k in CAUSES else "unclassified",
                       "rate": round(v["recovered"] / v["at_risk"], 3) if v["at_risk"] else 0}
                   for k, v in sorted(causes.items(), key=lambda kv: -kv[1]["at_risk"])},
        "refusals": {k: {"count": v, "rule": RULES.get(k, "")}
                     for k, v in sorted(refusals.items())},
    }


@app.get("/api/state")
def state(since: int = 0):
    events = STATE.since(since)
    pool = STATE.decider.pool_state() if STATE.decider else []
    body = {
        "running": STATE.running,
        "mode": STATE.mode,
        "total": STATE.total,
        "next": since + len(events),
        "events": events,
        "totals": _live_totals(),
        "kill_switch": STATE.cfg.policy.kill_switch,
        "backends": {"payments": STATE.cfg.payments_backend,
                     "buyers": STATE.cfg.buyer_backend},
        "pool": pool,
        "error": STATE.error,
    }
    body["measured"] = not STATE.cfg.force_treatment
    if STATE.summary:
        s = STATE.summary
        body["summary"] = {
            "lift": s["lift_over_control"],
            "treatment": s["arms"]["treatment"],
            "control": s["arms"]["control"],
            "macro_f1": s["diagnosis"]["macro_f1"],
            "unclassified": s["diagnosis"]["unclassified"],
            "exceptions": s["exception_count"],
            "ledger": s["ledger"],
            "llm": s.get("llm"),
            "simulated": s["simulated_components"],
        }
    return body


@app.get("/api/session/{session_id}")
def session_chain(session_id: str):
    """The audit chain behind one session — every rupee is clickable to this."""
    if STATE.ledger is None:
        return JSONResponse({"error": "no completed run yet"}, 404)
    entries = STATE.ledger.for_session(session_id)
    ok, bad = STATE.ledger.verify()
    return {"session_id": session_id, "entries": entries,
            "chain_valid": ok, "first_bad": bad}


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE
