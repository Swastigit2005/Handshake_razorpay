"""Wires the demo together and runs one agent at a time against the shop.

`bootstrap()` makes the demo shop a Handshake customer the same way a real one
becomes one: a merchant record, an API key, a webhook URL, then the catalogue
and schema pushed through the SDK over HTTP. The sandbox merchant has a
45-second idle window. Most abandonments are detected sooner: an agent that
cancels, or that asks the store for an offer, has stopped shopping by its own
action, and the journey closes at once.
"""

import random
import threading
import time
import uuid

from ..live import pipeline, store
from ..sdk import HandshakeClient
from . import app as shop_app
from .agent import ShoppingAgent, urllib_json
from .scenarios import CONDITION_TEXT, OFF_PLAYBOOK, SCENARIOS, judge, mandate_for, mystery

MERCHANT_ID = "m_demo_kaveri"
SANDBOX_SETTINGS = {"idle_seconds": 45, "reoffer_ttl_seconds": 180,
                    "retry_after_seconds": 3, "timezone": "Asia/Kolkata"}
# Quiet hours (R-09) are off for the sandbox so a 2 a.m. demo still shows a
# human-facing recovery. The dashboard's policy panel turns them back on.
SANDBOX_POLICY = {"quiet_hours": [24, 0]}

# How long a mystery shopper waits for a re-offer: long enough for a viewer to
# read the drafted fix and approve it.
MYSTERY_WAIT = 90.0

_lock = threading.Lock()
STATE = {"base_url": None, "api_key": None, "client": None, "http": None}
RUNS = {}
MAX_RUNS = 200


def bootstrap(base_url, http=None, transport=None):
    """Idempotent. Returns the sandbox merchant's API key."""
    with _lock:
        if STATE["base_url"] == base_url and STATE["client"] is not None:
            return STATE["api_key"]
        webhook = base_url.rstrip("/") + "/shop/webhooks/handshake"
        m = store.get_merchant(MERCHANT_ID)
        if m is None:
            m, key = store.create_merchant("Kaveri Home & Tech (sandbox)", webhook,
                                           SANDBOX_POLICY, SANDBOX_SETTINGS, sandbox=True,
                                           merchant_id=MERCHANT_ID)
        else:
            # Only the hash is stored, so a restarted process mints a fresh key.
            key = store.rotate_key(MERCHANT_ID)
            m = store.update_merchant(MERCHANT_ID, webhook_url=webhook,
                                      settings={**m["settings"], **SANDBOX_SETTINGS},
                                      policy={**SANDBOX_POLICY, **m["policy"]})
        if STATE["client"] is not None:
            STATE["client"].close(timeout=2)
        client = HandshakeClient(key, base_url, flush_interval=0.15, transport=transport)
        shop_app.configure(client, m["webhook_secret"])
        shop_app.sync(client)
        STATE.update(base_url=base_url, api_key=key, client=client, http=http or urllib_json)
        return key


def merchant():
    return store.get_merchant(MERCHANT_ID)


def start(scenario, pace=0.35, reoffer_wait=30.0, seed=None):
    """`scenario` is a teaching scenario name, or "mystery": a random brief and
    random hidden shop conditions that nobody picks."""
    if scenario != "mystery" and scenario not in SCENARIOS:
        raise KeyError(scenario)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    thoughts = []
    if scenario == "mystery":
        seed = seed if seed is not None else random.randrange(1, 10**9)
        mandate, conditions = mystery(random.Random(seed))
        reoffer_wait = max(reoffer_wait, MYSTERY_WAIT)   # time for a person to approve
    else:
        mandate = mandate_for(scenario)
        conditions = [SCENARIOS[scenario]["fault"]] if SCENARIOS[scenario]["fault"] else []
    agent = ShoppingAgent(STATE["base_url"], mandate, ",".join(conditions),
                          http=STATE["http"], log=thoughts, reoffer_wait=reoffer_wait,
                          pace=pace)
    run = {"run_id": run_id, "scenario": scenario, "agent_id": agent.agent_id,
           "journey_id": agent.journey_id, "thoughts": thoughts, "status": "running",
           "started": time.time(), "finished": 0.0, "outcome": agent.outcome, "error": "",
           "seed": seed, "mandate": mandate, "conditions": conditions}
    if len(RUNS) >= MAX_RUNS:
        for old in sorted(RUNS, key=lambda k: RUNS[k]["started"])[:MAX_RUNS // 2]:
            RUNS.pop(old, None)
    RUNS[run_id] = run

    def go():
        try:
            run["outcome"] = agent.run()
        except Exception as exc:
            run["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            STATE["client"].flush(timeout=5)
            run["status"] = "done"
            run["finished"] = time.time()

    threading.Thread(target=go, name=f"demo-{run_id}", daemon=True).start()
    return run


def view(run_id, peek=False):
    """Everything the demo page shows for one run, from three vantage points."""
    run = RUNS.get(run_id)
    if run is None:
        return None
    jid = run["journey_id"]
    m = merchant()
    journey = None
    if m is not None and store.get_journey(MERCHANT_ID, jid):
        from ..live import api
        journey = api.journey(jid, merchant=m)
    if run["scenario"] == "mystery":
        meta = {"title": "Mystery shopper", "family": "mystery", "expect": None,
                "story": "Hidden shop conditions: " + ("; ".join(
                    CONDITION_TEXT[c] + (" (outside the playbook)" if c in OFF_PLAYBOOK else "")
                    for c in run["conditions"]) or "none — any stop came from the brief alone")
                + ". The agent's brief: " + run["mandate"]["goal"]}
    else:
        sc = SCENARIOS[run["scenario"]]
        meta = {"title": sc["title"], "story": sc["story"], "expect": sc["expect"],
                "family": sc["family"]}
    outcome = run["outcome"] or {}
    verdict = None
    settled = journey and journey["status"] not in ("open", "abandoned", "recovering")
    # Judge as soon as Handshake has settled the journey, even while the agent is
    # still waiting for a re-offer: the diagnosis is what is being scored.
    if (settled and outcome.get("truths") is not None) or run["status"] == "done":
        diagnosis = (journey or {}).get("diagnosis")
        truth = (outcome.get("truths") or [None])[-1]
        verdict = judge(truth, diagnosis, (journey or {}).get("status") if truth else None)
    # A mystery stays a mystery on the wire, not just on the screen: until
    # Handshake has answered, nothing that reveals the truth leaves the server.
    sealed = run["scenario"] == "mystery" and verdict is None and not peek
    hidden = {k: v for k, v in run.items()
              if k not in ("thoughts", "mandate", "conditions", "outcome")}
    if sealed:
        meta = {**meta, "story": "Sealed until Handshake answers."}
    return {**hidden,
            "outcome": None if sealed else {k: outcome.get(k) for k in ("bought", "recovered", "total")},
            "thoughts": [] if sealed else list(run["thoughts"]),
            "sealed": sealed,
            "shop_log": list(shop_app.SHOP.log.get(jid, [])),
            "journey": journey,
            "scenario_meta": meta,
            "truth": [] if sealed else (outcome.get("truths") or []),
            "judgement": {"verdict": verdict[0], "sentence": verdict[1]} if verdict else None,
            "worker_alive": pipeline.WORKER.alive}


def judge_run(run):
    """Score a run's latest stop against Handshake's latest diagnosis."""
    outcome = run.get("outcome") or {}
    m = merchant()
    j = store.get_journey(MERCHANT_ID, run["journey_id"]) if m else None
    if j is None or run["status"] != "done":
        return None
    if j["status"] in ("open", "abandoned"):
        return None
    truth = (outcome.get("truths") or [None])[-1]     # the diagnosis is of the last stop
    return judge(truth, j["diagnosis"], j["status"] if truth else None)[0]


def scorecard():
    """How often Handshake explained a mystery shopper correctly, honestly said it
    couldn't, or got it wrong. Computed from the runs on this process."""
    tally = {"correct": 0, "honest_unknown": 0, "wrong": 0, "n/a": 0}
    recovered = 0
    for run in list(RUNS.values()):
        if run["scenario"] != "mystery":
            continue
        v = judge_run(run)
        if v is None:
            continue
        tally[v] += 1
        if (run.get("outcome") or {}).get("recovered"):
            recovered += 1
    explained = tally["correct"] + tally["honest_unknown"] + tally["wrong"]
    return {**tally, "stopped": explained, "recovered": recovered,
            "accuracy": round(tally["correct"] / explained, 3) if explained else None}


def approve(run_id, message=None, action=None, sku=None):
    run = RUNS.get(run_id)
    if run is None:
        raise KeyError(run_id)
    return pipeline.approve(merchant(), run["journey_id"], "demo viewer",
                            {"message": message, "action": action, "sku": sku})
