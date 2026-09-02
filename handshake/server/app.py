"""Live console and HTTP API.

    ./run_ui.sh                    →  http://127.0.0.1:8000
    docker compose up              →  http://127.0.0.1:8000

Three things a static report cannot do, and all three are what a demo needs:
watch a batch as it happens, step through one recovery slowly enough to narrate,
and flip a governance control mid-run and see the refusals appear.

Deployment notes
----------------
HS_DEMO_MODE=1   caps batch size and rate-limits runs, so a public URL is safe
                 to hand to a stranger.
HS_API_TOKEN     when set, every write endpoint requires X-Handshake-Token.
HS_DB            SQLite path. Runs, sessions and ledgers survive a restart.
"""

import os
import threading
import time

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__
from ..config import RunConfig
from ..experiments.batch import Sink, run_batch
from ..experiments.report import compute
from ..readiness.scan import scan as run_scan
from ..store import db, seed
from ..taxonomy import CAUSES, RULES
from .landing import LANDING
from .ui import PAGE

SEED_REPORT = {}


@asynccontextmanager
async def lifespan(_app):
    """Free tiers have an ephemeral filesystem: the database is lost on every
    redeploy and spin-down. Import the committed canonical run on startup so a
    cold URL is worth reading before anyone presses a button."""
    global SEED_REPORT
    if os.environ.get("HS_NO_SEED", "").lower() in ("1", "true", "yes"):
        SEED_REPORT = {"skipped": "HS_NO_SEED set"}
    else:
        try:
            SEED_REPORT = seed.seed()
        except Exception as exc:
            SEED_REPORT = {"skipped": f"{type(exc).__name__}: {exc}"}
    yield


app = FastAPI(title="Handshake", version=__version__,
              description="Revenue recovery for agent-driven checkout",
              lifespan=lifespan)

# Brand assets are checked into the repository and immutable at runtime. Resolve
# from this file rather than the process cwd so Docker, Render and local runs all
# serve the same URLs.
ASSET_DIR = Path(__file__).resolve().parents[2] / "assets"
if ASSET_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
else:
    # StaticFiles raises at import when the directory is absent, which would take
    # the whole console down over a missing social-preview image. Installed as a
    # wheel and run from elsewhere, this path does not exist. Serve without the
    # brand assets instead, and say so in /healthz.
    ASSET_DIR = None

DEMO_MODE = os.environ.get("HS_DEMO_MODE", "").lower() in ("1", "true", "yes")
API_TOKEN = os.environ.get("HS_API_TOKEN", "")
MAX_SESSIONS = int(os.environ.get("HS_MAX_SESSIONS", "400" if DEMO_MODE else "5000"))
MIN_GAP_SECONDS = float(os.environ.get("HS_MIN_RUN_GAP", "15" if DEMO_MODE else "0"))


def _guard(token):
    """Write endpoints: optional shared token, plus a demo-mode cooldown."""
    if API_TOKEN and token != API_TOKEN:
        return JSONResponse({"error": "invalid or missing X-Handshake-Token"}, 401)
    if STATE.running or STATE.scanning:
        return JSONResponse({"error": "a run is already in progress"}, 409)
    waited = time.time() - STATE.last_finished
    if MIN_GAP_SECONDS and waited < MIN_GAP_SECONDS:
        return JSONResponse(
            {"error": f"demo mode: wait {MIN_GAP_SECONDS - waited:.0f}s between runs"},
            429)
    return None


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
        self.scanning = False
        self.stopping = False
        self.mode = ""
        self.total = 0
        self.summary = None
        self.readiness = None
        self.error = ""
        self.started_at = 0.0
        self.last_finished = 0.0
        self.run_id = ""

    def reset(self, cfg, mode, total):
        self.events, self.results = [], []
        self.ledger = self.decider = self.summary = None
        self.cfg, self.mode, self.total = cfg, mode, total
        self.running, self.stopping, self.error = True, False, ""
        self.started_at = time.time()
        self.run_id = ""

    def add(self, event):
        with self.lock:
            event["seq"] = len(self.events)
            self.events.append(event)

    def since(self, index):
        with self.lock:
            return self.events[index:]

    def trace(self, session_id):
        for result in self.results:
            if result.trace.session_id == session_id:
                return result
        return None


STATE = RunState()


class StopBatch(RuntimeError):
    pass


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


# --------------------------------------------------------------- runners ----

def _runner(cfg, mode, pace):
    sink = UISink(STATE, pace)
    try:
        run = run_batch(cfg, sink=sink)
        STATE.results = run["results"]
        STATE.ledger = run["ledger"]
        STATE.decider = run.get("decider")
        summary, _ = compute(run)
        STATE.summary = summary
        try:
            STATE.run_id = db.save_batch(
                summary, [r.as_dict() for r in run["results"]], run["ledger"],
                kind=mode, measured=not cfg.force_treatment)
        except Exception as exc:                       # storage must not lose a run
            STATE.error = f"stored nothing: {type(exc).__name__}: {exc}"
        sink.emit("done", sessions=len(run["results"]), run_id=STATE.run_id,
                  recovered=summary["arms"]["treatment"]["recovered_gmv"],
                  lift=summary["lift_over_control"])
    except StopBatch:
        STATE.add({"kind": "stopped", "seq": 0})
    except Exception as exc:
        STATE.error = f"{type(exc).__name__}: {exc}"
        STATE.add({"kind": "error", "message": STATE.error, "seq": 0})
    finally:
        STATE.running = False
        STATE.last_finished = time.time()


def _scan_runner(sessions, defect_rate, top):
    try:
        cfg = RunConfig()
        cfg.payments_backend = "sim"        # a scan never needs to move money
        report = run_scan(sessions=sessions, defect_rate=defect_rate,
                          cfg=cfg, top_k=top)
        try:
            report["run_id"] = db.save_scan(report)
        except Exception:
            pass
        STATE.readiness = report
    except Exception as exc:
        STATE.readiness = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        STATE.scanning = False
        STATE.last_finished = time.time()


# --------------------------------------------------------------- schemas ----

class RunRequest(BaseModel):
    sessions: int = 200
    mode: str = "batch"          # "batch" | "walkthrough"
    fault_incidence: float = 0.55
    seed: int = 20260830
    offline: bool = False


class ScanRequest(BaseModel):
    sessions: int = 300
    defect_rate: float = 0.22
    top: int = 5


class KillSwitch(BaseModel):
    on: bool


# --------------------------------------------------------------- writes -----

@app.post("/api/run")
def start_run(req: RunRequest, x_handshake_token: str = Header(default="")):
    blocked = _guard(x_handshake_token)
    if blocked:
        return blocked

    cfg = RunConfig()
    cfg.seed = req.seed
    if req.mode == "walkthrough":
        cfg.batch_size, cfg.fault_incidence, pace = 6, 1.0, 1.1
        cfg.force_treatment = True   # a walkthrough is a demo, not a measurement
    else:
        cfg.batch_size = max(10, min(req.sessions, MAX_SESSIONS))
        cfg.fault_incidence = req.fault_incidence
        pace = 0.0
    if req.offline or DEMO_MODE and not os.environ.get("HS_LLM_API_KEYS"):
        cfg.payments_backend, cfg.buyer_backend = "sim", "heuristic"
    cfg.policy.kill_switch = STATE.cfg.policy.kill_switch

    STATE.reset(cfg, req.mode, cfg.batch_size)
    threading.Thread(target=_runner, args=(cfg, req.mode, pace), daemon=True).start()
    return {"started": True, "mode": req.mode, "sessions": cfg.batch_size,
            "payments": cfg.payments_backend, "buyers": cfg.buyer_backend,
            "capped_at": MAX_SESSIONS if DEMO_MODE else None}


@app.post("/api/readiness")
def readiness(req: ScanRequest, x_handshake_token: str = Header(default="")):
    """Prevention, not recovery: find and price the catalogue's own defects."""
    blocked = _guard(x_handshake_token)
    if blocked:
        return blocked
    STATE.scanning = True
    STATE.readiness = None
    sessions = max(50, min(req.sessions, MAX_SESSIONS))
    threading.Thread(target=_scan_runner,
                     args=(sessions, req.defect_rate, req.top), daemon=True).start()
    return {"scanning": True, "sessions": sessions}


@app.post("/api/stop")
def stop_run():
    STATE.stopping = True
    return {"stopping": True}


@app.post("/api/killswitch")
def kill_switch(req: KillSwitch, x_handshake_token: str = Header(default="")):
    """Rule R-11. Takes effect on the next policy evaluation, mid-run."""
    if API_TOKEN and x_handshake_token != API_TOKEN:
        return JSONResponse({"error": "invalid or missing X-Handshake-Token"}, 401)
    STATE.cfg.policy.kill_switch = req.on
    return {"kill_switch": req.on}


# --------------------------------------------------------------- reads ------

def _live_totals():
    at_risk = recovered = concession = 0.0
    failed = recovered_n = 0
    causes, refusals, interventions = {}, {}, {}
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
            iid = e.get("intervention", "?")
            interventions[iid] = interventions.get(iid, 0) + 1
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
        "interventions": dict(sorted(interventions.items())),
    }


@app.get("/healthz")
def healthz():
    try:
        store = db.stats()
        healthy = True
    except Exception as exc:
        store, healthy = {"error": str(exc)}, False
    return JSONResponse({
        "ok": healthy,
        "version": __version__,
        "demo_mode": DEMO_MODE,
        "auth_required": bool(API_TOKEN),
        "max_sessions": MAX_SESSIONS,
        "backends": {"payments": RunConfig().payments_backend,
                     "buyers": RunConfig().buyer_backend},
        "busy": STATE.running or STATE.scanning,
        "store": store,
        "assets": bool(ASSET_DIR),
        "seed": SEED_REPORT,
    }, status_code=200 if healthy else 503)


@app.get("/api/state")
def state(since: int = 0):
    events = STATE.since(since)
    body = {
        "running": STATE.running,
        "scanning": STATE.scanning,
        "mode": STATE.mode,
        "total": STATE.total,
        "next": since + len(events),
        "events": events,
        "totals": _live_totals(),
        "kill_switch": STATE.cfg.policy.kill_switch,
        "backends": {"payments": STATE.cfg.payments_backend,
                     "buyers": STATE.cfg.buyer_backend},
        "pool": STATE.decider.pool_state() if STATE.decider else [],
        "error": STATE.error,
        "measured": not STATE.cfg.force_treatment,
        "readiness": STATE.readiness,
        "run_id": STATE.run_id,
        "demo_mode": DEMO_MODE,
        "version": __version__,
    }
    if STATE.summary:
        s = STATE.summary
        body["summary"] = {
            "lift": s["lift_over_control"],
            "treatment": s["arms"]["treatment"],
            "control": s["arms"]["control"],
            "macro_f1": s["diagnosis"]["macro_f1"],
            "per_class": s["diagnosis"]["per_class"],
            "unclassified": s["diagnosis"]["unclassified"],
            "exceptions": s["exception_count"],
            "ledger": s["ledger"],
            "llm": s.get("llm"),
            "simulated": s["simulated_components"],
        }
    return body


@app.get("/api/session/{session_id}")
def session_chain(session_id: str):
    """The audit chain behind one session — every rupee clicks through to this."""
    if STATE.ledger is None:
        return JSONResponse({"error": "no completed run yet"}, 404)
    ok, bad = STATE.ledger.verify()
    return {"session_id": session_id,
            "entries": STATE.ledger.for_session(session_id),
            "chain_valid": ok, "first_bad": bad}


@app.get("/api/trace/{session_id}")
def session_trace(session_id: str):
    """What the merchant actually saw: the API traffic, nothing more."""
    result = STATE.trace(session_id)
    if result is None:
        return JSONResponse({"error": "unknown session in the current run"}, 404)
    trace = result.trace
    return {
        "session_id": session_id,
        "buyer": trace.buyer_id, "persona": trace.persona, "arm": trace.arm,
        "terminal": str(trace.terminal_state).split(".")[-1],
        "basket": trace.basket, "basket_value": round(trace.basket_value, 2),
        "spend_cap": trace.spend_cap,
        "abandon_note": trace.abandon_note,
        "injected_fault": trace.injected_fault,
        "diagnosed": result.diagnosis.as_dict() if result.diagnosis else None,
        "interventions": result.interventions,
        "recovered": result.recovered,
        "recovered_value": round(result.recovered_value, 2),
        "events": [e.as_dict() for e in trace.events],
    }


@app.get("/api/overview")
def overview():
    """Headline figures for a cold visitor, from the last stored run of each kind.

    A deployed URL should be worth reading before anyone presses a button."""
    out = {"batch": None, "scan": None}
    try:
        for row in db.recent(limit=40):
            if row["kind"] == "scan" and out["scan"] is None:
                out["scan"] = row
            elif row["kind"] in ("batch", "walkthrough") and out["batch"] is None:
                if row["measured"]:
                    out["batch"] = row
            if out["batch"] and out["scan"]:
                break
    except Exception as exc:
        out["error"] = str(exc)
    return out


@app.get("/api/runs")
def runs(limit: int = 20, kind: str = ""):
    try:
        return {"runs": db.recent(limit=limit, kind=kind or None)}
    except Exception as exc:
        return JSONResponse({"error": str(exc), "runs": []}, 200)


@app.get("/api/runs/{run_id}")
def stored_run(run_id: str):
    row = db.get_run(run_id)
    if row is None:
        return JSONResponse({"error": "unknown run"}, 404)
    ok, bad = db.verify_chain(run_id)
    row["chain_valid"], row["first_bad"] = ok, bad
    return row


@app.get("/api/runs/{run_id}/chain")
def stored_chain(run_id: str, session_id: str = ""):
    ok, bad = db.verify_chain(run_id)
    return {"run_id": run_id, "session_id": session_id,
            "entries": db.chain(run_id, session_id or None),
            "chain_valid": ok, "first_bad": bad}


@app.get("/", response_class=HTMLResponse)
def index():
    """The landing page. A stranger should understand the problem, see the
    mechanism and read the honest limitations before they touch a control."""
    return LANDING


@app.get("/console", response_class=HTMLResponse)
def console():
    """The live operator console — the thing the landing page sends you to."""
    return PAGE
