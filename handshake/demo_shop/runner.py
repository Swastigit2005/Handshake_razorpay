"""Wires the demo together and runs one agent at a time against the shop.

`bootstrap()` makes the demo shop a Handshake customer the same way a real one
becomes one: a merchant record, an API key, a webhook URL, then the catalogue
and schema pushed through the SDK over HTTP. The sandbox merchant has a short
idle window (4 s) so an abandonment is detected while the viewer watches.
"""

import threading
import time
import uuid

from ..live import pipeline, store
from ..sdk import HandshakeClient
from . import app as shop_app
from .agent import ShoppingAgent, urllib_json
from .scenarios import SCENARIOS, mandate_for

MERCHANT_ID = "m_demo_kaveri"
SANDBOX_SETTINGS = {"idle_seconds": 4, "reoffer_ttl_seconds": 180,
                    "retry_after_seconds": 3, "timezone": "Asia/Kolkata"}
# Quiet hours (R-09) are off for the sandbox so a 2 a.m. demo still shows a
# human-facing recovery. The dashboard's policy panel turns them back on.
SANDBOX_POLICY = {"quiet_hours": [24, 0]}

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


def start(scenario, pace=0.35, reoffer_wait=30.0):
    if scenario not in SCENARIOS:
        raise KeyError(scenario)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    thoughts = []
    agent = ShoppingAgent(STATE["base_url"], mandate_for(scenario),
                          SCENARIOS[scenario]["fault"] or "", http=STATE["http"], log=thoughts,
                          reoffer_wait=reoffer_wait, pace=pace)
    run = {"run_id": run_id, "scenario": scenario, "agent_id": agent.agent_id,
           "journey_id": agent.journey_id, "thoughts": thoughts, "status": "running",
           "started": time.time(), "finished": 0.0, "outcome": None, "error": ""}
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


def view(run_id):
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
    sc = SCENARIOS[run["scenario"]]
    return {**{k: v for k, v in run.items() if k != "thoughts"},
            "thoughts": list(run["thoughts"]),
            "shop_log": list(shop_app.SHOP.log.get(jid, [])),
            "journey": journey,
            "scenario_meta": {"title": sc["title"], "story": sc["story"],
                              "expect": sc["expect"], "family": sc["family"]},
            "worker_alive": pipeline.WORKER.alive}
