"""The live integration plane: detectors, the /v1 API, the SDK, and the demo
store end to end.

The end-to-end tests run the real chain — agent → shop → SDK middleware →
/v1/events → sweeper → detectors → policy gate → signed webhook → shop →
re-offer → agent — with every HTTP hop routed through FastAPI's TestClient
instead of a socket.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from handshake.live.detectors import diagnose  # noqa: E402
from handshake.live.events import InvalidEvent, normalise, redact  # noqa: E402

SCHEMA = {"home_kitchen": ["capacity_l", "power_watts", "warranty_months"]}
TRUTH = {"KET-170": {"sku": "KET-170", "category": "home_kitchen", "price": 1999.0,
                     "tax_rate": 0.18, "variant_group": "k17",
                     "attributes": {"capacity_l": 1.7, "power_watts": 1500,
                                    "warranty_months": 24},
                     "policy": {"returns_days": 10, "warranty_months": 24}}}


def ev(seq, type_, status=200, request=None, response=None, **kw):
    return {"seq": seq, "type": type_, "http_status": status, "request": request or {},
            "response": response or {}, "sku": kw.get("sku", ""),
            "checkout_id": kw.get("checkout_id", ""), "ts": float(seq)}


def view(seq=2, attrs=None, policy=None, **extra):
    rec = {"sku": "KET-170", "category": "home_kitchen", "price": 1999.0, "tax_rate": 0.18,
           "variant_group": "k17",
           "attributes": attrs if attrs is not None else dict(TRUTH["KET-170"]["attributes"]),
           "policy": policy if policy is not None else {"returns_days": 10}, **extra}
    return ev(seq, "product.view", response=rec, sku="KET-170")


def run(events):
    return diagnose(events, SCHEMA, TRUTH.get, lambda: list(TRUTH.values()))


def checkout(cap=3000, first=2358.82, second=2358.82):
    return [view(),
            ev(3, "checkout.create", request={"sku": "KET-170", "declared_cap": cap},
               response={"session_id": "cs_1", "total": first}),
            ev(4, "checkout.update", response={"total": second})]


# ------------------------------------------------------------- detectors ---

def test_missing_attribute_is_found_and_sourced_from_the_catalogue():
    d = run([ev(1, "feed.read"), view(attrs={"capacity_l": 1.7, "warranty_months": 24})])
    assert d["cause"] == "A1" and d["confidence"] >= 0.9
    assert d["detail"]["source_values"] == {"power_watts": 1500}
    assert d["evidence"][0]["event"] == 2


def test_an_empty_value_counts_as_missing():
    d = run([view(attrs={"capacity_l": 1.7, "power_watts": "", "warranty_months": 24})])
    assert d["cause"] == "A1"


def test_prose_policy():
    d = run([view(policy={"text": "reasonable period", "structured": False})])
    assert d["cause"] == "A7"


def test_variant_collision_uses_the_feed_the_agent_was_served():
    me = view()["response"]
    twin = dict(me, sku="KET-170-B")
    d = run([ev(1, "feed.read", response={"items": [me, twin]}), view()])
    assert d["cause"] == "A2" and d["detail"]["collides_with"] == "KET-170-B"


def test_quote_drift_and_cap():
    assert run(checkout(second=2571.11))["cause"] == "A3"
    d = run(checkout(cap=2000))
    assert d["cause"] == "A4" and d["detail"]["over_by"] == 358.82


def test_drift_the_agent_paid_through_is_not_the_reason():
    events = checkout(second=2400.0) + [
        ev(5, "checkout.complete", 402, response={"reason_code": "insufficient_funds"})]
    d = run(events)
    assert d["cause"] == "B1"
    assert [h["cause"] for h in d["hypotheses"]] == ["B1", "A3"]


@pytest.mark.parametrize("status,body,cause", [
    (401, {"error": "authentication_required"}, "A5"),
    (503, {"error": "processing_error"}, "A6"),
    (402, {"reason_code": "mandate_revoked"}, "B3"),
    (402, {"reason_code": "card_expired"}, "B5"),
])
def test_payment_stage_signals(status, body, cause):
    assert run(checkout() + [ev(5, "checkout.complete", status, response=body)])["cause"] == cause


def test_a_retried_error_is_not_an_abandonment_cause():
    events = checkout() + [ev(5, "checkout.complete", 503, response={"error": "processing_error"}),
                           ev(6, "checkout.complete", 402, response={"reason_code": "insufficient_funds"})]
    assert run(events)["cause"] == "B1"


def test_unserviceable():
    d = run([view(), ev(3, "checkout.create", 422, request={"sku": "KET-170", "pincode": "560034"},
                        response={"error": "fulfilment_undetermined"})])
    assert d["cause"] == "A8" and d["detail"]["pincode"] == "560034"


def test_decline_without_a_reason_is_unknown_not_a_guess():
    d = run(checkout() + [ev(5, "checkout.complete", 402, response={"error": "payment_failed"})])
    assert d["cause"] == "UNKNOWN" and d["confidence"] == 0.0
    assert any("no reason code" in o for o in d["observations"])


def test_a_viewed_and_left_journey_with_a_complete_record_is_unknown():
    d = run([ev(1, "feed.read"), view()])
    assert d["cause"] == "UNKNOWN"


def test_self_report_alone_never_clears_the_threshold():
    events = checkout() + [ev(5, "checkout.cancel", request={"reason": "price_changed"})]
    d = run(events)
    assert d["cause"] == "A3" and d["confidence"] < 0.7
    assert d["declared"]["corroborated"] is False


def test_self_report_that_agrees_raises_confidence():
    events = checkout(second=2571.11) + [ev(5, "checkout.cancel", request={"reason": "price_changed"})]
    d = run(events)
    assert d["cause"] == "A3" and d["confidence"] == 0.96
    assert d["hypotheses"][0]["corroborated_by_agent"]


def test_close_competitors_lower_confidence():
    # Over the cap from the first quote *and* drifted: two independent strong
    # explanations, reported as contested.
    d = run(checkout(cap=2300, second=2571.11))
    assert d["contested"] and d["confidence"] < 0.8
    assert {h["cause"] for h in d["hypotheses"]} == {"A3", "A4"}


def test_a_cap_breach_caused_by_a_price_move_names_the_price_move():
    # The first quote fitted the cap; only the re-quote broke it. Root cause: A3.
    d = run(checkout(cap=2400, second=2571.11))
    assert d["cause"] == "A3" and not d["contested"] and d["confidence"] >= 0.9
    a4 = next(h for h in d["hypotheses"] if h["cause"] == "A4")
    assert a4["detail"]["consequence_of"] == "A3"


def test_a_second_attempt_is_diagnosed_on_its_own_events():
    # Attempt 1: missing attribute. Re-offer collected. Attempt 2: price drift.
    first = [ev(1, "feed.read"), view(2, attrs={"capacity_l": 1.7, "warranty_months": 24}),
             ev(3, "reoffer.fetch", 200, response={"offer": {"type": "catalogue_delta"}})]
    second = [ev(4, "checkout.create", request={"sku": "KET-170", "declared_cap": 3000},
                 response={"session_id": "cs_2", "total": 2358.82}),
              ev(5, "checkout.update", response={"total": 2571.11})]
    d = run(first + second)
    assert d["cause"] == "A3"
    assert any("second attempt" in o for o in d["observations"])


def test_reoffer_polls_are_not_the_last_thing_the_agent_did():
    d = run([view(attrs={}), ev(3, "reoffer.fetch", 404)])
    assert "opened product" in d["observations"][0]


# ---------------------------------------------------------------- events ---

def test_normalise_rejects_what_the_pipeline_cannot_stitch():
    with pytest.raises(InvalidEvent):
        normalise({"type": "product.view"})
    with pytest.raises(InvalidEvent):
        normalise({"type": "bogus", "agent_id": "a"})


def test_redaction_is_by_key_at_any_depth():
    out = redact({"instrument": {"card_number": "4111", "cvv": "1"}, "otp": "9",
                  "approval_token": "t", "sku": "KET", "items": [{"email": "x@y"}]})
    assert out["instrument"] == {"card_number": "[redacted]", "cvv": "[redacted]"}
    assert out["otp"] == out["approval_token"] == out["items"][0]["email"] == "[redacted]"
    assert out["sku"] == "KET"


# ------------------------------------------------------------------ API ---

fastapi = pytest.importorskip("fastapi", reason="console extra not installed")
pytest.importorskip("httpx", reason="httpx is needed by fastapi's TestClient")
from fastapi.testclient import TestClient  # noqa: E402

# The connection pools live here; re-importing it would orphan open pools.
KEEP_MODULES = {"handshake", "handshake.database"}


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv("HS_LIVE_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv("HS_NO_SEED", "1")
    monkeypatch.setenv("HS_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HS_PAYMENTS", "sim")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")
                and m not in KEEP_MODULES and not m.startswith("handshake.tests")]:
        del sys.modules[mod]
    from handshake.server import app as server
    from handshake.live import pipeline, store, webhooks
    with TestClient(server.app) as tc:
        sent = []

        def send(url, body, headers):
            sent.append((url, json.loads(body), headers))
            path = url.split("://", 1)[1].split("/", 1)[1]
            r = tc.post("/" + path, content=body, headers=headers)
            return r.status_code, "" if r.status_code < 300 else r.text

        webhooks.SEND = send
        yield {"tc": tc, "server": server, "pipeline": pipeline, "store": store,
               "webhooks": webhooks, "sent": sent}


def merchant(live, name="Acme", **body):
    r = live["tc"].post("/v1/merchants", json={"name": name, **body},
                        headers={"Authorization": "Bearer admin-secret"})
    assert r.status_code == 201, r.text
    key = r.json()["api_key"]
    return key, {"Authorization": f"Bearer {key}"}


def test_merchant_creation_needs_the_admin_token(live):
    tc = live["tc"]
    assert tc.post("/v1/merchants", json={"name": "x"}).status_code == 401
    key, h = merchant(live)
    assert key.startswith("hsk_live_")
    me = tc.get("/v1/me", headers=h).json()
    assert me["name"] == "Acme" and "key_hash" not in me


def test_every_v1_read_needs_a_key(live):
    tc = live["tc"]
    for path in ("/v1/me", "/v1/journeys", "/v1/metrics", "/v1/ledger/verify"):
        r = tc.get(path)
        assert r.status_code == 401 and r.json()["error"]["type"] == "authentication_error"
    assert tc.get("/v1/me", headers={"Authorization": "Bearer hsk_live_nope"}).status_code == 401


def _discovery_events(journey="jr_1", agent="ag_1", attrs=None):
    return [{"event_id": f"{journey}-1", "type": "feed.read", "agent_id": agent,
             "journey_id": journey, "response": {"count": 1}},
            {"event_id": f"{journey}-2", "type": "product.view", "agent_id": agent,
             "journey_id": journey, "sku": "KET-170",
             "response": {**TRUTH["KET-170"], "attributes": attrs if attrs is not None
                          else {"capacity_l": 1.7, "warranty_months": 24}}}]


def _setup_catalogue(tc, h):
    assert tc.put("/v1/schema", json={"schema": SCHEMA}, headers=h).status_code == 200
    assert tc.put("/v1/catalog", json={"products": list(TRUTH.values())},
                  headers=h).json() == {"stored": 1}


def test_ingest_is_idempotent_and_reports_bad_events(live):
    tc = live["tc"]
    _, h = merchant(live)
    batch = _discovery_events() + [{"type": "nope", "agent_id": "a"}]
    first = tc.post("/v1/events", json={"events": batch}, headers=h).json()
    assert first["accepted"] == 2 and first["rejected"][0]["index"] == 2
    again = tc.post("/v1/events", json={"events": batch[:2]}, headers=h).json()
    assert again["accepted"] == 0 and again["duplicates"] == 2
    assert tc.post("/v1/events", json={"events": [{"type": "x"}]}, headers=h).status_code == 422


def test_journeys_stitch_by_checkout_id_without_a_journey_header(live):
    tc = live["tc"]
    _, h = merchant(live)
    tc.post("/v1/events", headers=h, json={"events": [
        {"type": "checkout.create", "agent_id": "ag", "sku": "KET-170",
         "response": {"session_id": "cs_9", "total": 100.0}},
        {"type": "checkout.update", "agent_id": "other-hash", "checkout_id": "cs_9",
         "response": {"total": 100.0}}]})
    js = tc.get("/v1/journeys", headers=h).json()["journeys"]
    assert len(js) == 1 and js[0]["checkout_id"] == "cs_9"
    assert len(tc.get("/v1/journeys/cs_9", headers=h).json()["events"]) == 2


def test_tenants_cannot_see_each_other(live):
    tc = live["tc"]
    _, ha = merchant(live, "A")
    _, hb = merchant(live, "B")
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=ha)
    assert tc.get("/v1/journeys/jr_1", headers=ha).status_code == 200
    assert tc.get("/v1/journeys/jr_1", headers=hb).status_code == 404
    assert tc.get("/v1/journeys", headers=hb).json()["journeys"] == []


def test_abandon_diagnose_permit_and_signed_webhook(live):
    tc, pipeline = live["tc"], live["pipeline"]
    _, h = merchant(live, webhook_url="http://testserver/hook-sink")
    _setup_catalogue(tc, h)
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=h)
    m = live["store"].merchant_by_key(h["Authorization"][7:])
    j = pipeline.close(m, "jr_1", "idle_timeout")
    assert j["status"] == "recovering"
    assert j["diagnosis"]["cause"] == "A1"
    assert j["directive"]["merchant_action"] == {"type": "patch_catalog", "sku": "KET-170",
                                                  "set": {"power_watts": 1500}}
    offer = tc.get("/v1/reoffers/jr_1", headers=h).json()
    assert offer["offer"]["attributes"] == {"power_watts": 1500}

    live["webhooks"].deliver_due()
    url, payload, headers = live["sent"][-1]
    from handshake.sdk import verify_webhook
    assert verify_webhook(json.dumps(payload, separators=(",", ":")),
                          headers["Handshake-Signature"], m["webhook_secret"])["type"] \
        in ("journey.abandoned", "recovery.directive")

    # The agent comes back and pays: attributed to the intervention.
    tc.post("/v1/events", headers=h, json={"events": [
        {"type": "checkout.complete", "agent_id": "ag_1", "journey_id": "jr_1",
         "response": {"total": 2358.82, "status": "captured"}}]})
    done = tc.get("/v1/journeys/jr_1", headers=h).json()
    assert done["status"] == "recovered" and done["recovered_value"] == 2358.82
    assert [e["action"] for e in done["ledger"]] == ["diagnosed", "intervention_permitted",
                                                       "recovered"]
    assert tc.get("/v1/ledger/verify", headers=h).json()["valid"] is True


def test_a_value_missing_from_the_catalogue_too_is_not_fabricated(live):
    tc = live["tc"]
    _, h = merchant(live)
    tc.put("/v1/schema", json={"schema": SCHEMA}, headers=h)   # schema, but no catalogue
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=h)
    m = live["store"].merchant_by_key(h["Authorization"][7:])
    j = live["pipeline"].close(m, "jr_1", "idle_timeout")
    assert j["status"] == "exception"
    assert "could not be built" in j["verdict"]["reason"]


def test_kill_switch_refuses_with_r11(live):
    tc = live["tc"]
    _, h = merchant(live)
    _setup_catalogue(tc, h)
    assert tc.patch("/v1/policy", json={"kill_switch": True}, headers=h).json()["policy"]["kill_switch"]
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=h)
    m = live["store"].merchant_by_key(h["Authorization"][7:])
    j = live["pipeline"].close(m, "jr_1", "idle_timeout")
    assert j["status"] == "exception" and j["verdict"]["binding_rule"] == "R-11"
    assert j["verdict"]["checklist"][-1] == {"rule": "R-11", "text": j["verdict"]["checklist"][-1]["text"],
                                             "result": "fail", "state": "ON"}


def test_r02_caps_interventions_per_agent_across_journeys(live):
    tc = live["tc"]
    _, h = merchant(live)
    _setup_catalogue(tc, h)
    m = live["store"].merchant_by_key(h["Authorization"][7:])
    outcomes = []
    for i in range(4):
        tc.post("/v1/events", json={"events": _discovery_events(f"jr_{i}", "same-agent")},
                headers=h)
        outcomes.append(live["pipeline"].close(m, f"jr_{i}", "idle_timeout")["verdict"])
    assert [o["permitted"] for o in outcomes] == [True, True, True, False]
    # The fourth journey is also the agent's fourth abandonment in 24h (R-06),
    # which only removes concessions; R-02 is what refuses.
    assert outcomes[3]["binding_rule"] == "R-02"


def test_idle_sweeper_closes_and_reopens(live):
    tc, store, pipeline = live["tc"], live["store"], live["pipeline"]
    _, h = merchant(live, settings={"idle_seconds": 0})
    _setup_catalogue(tc, h)
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=h)
    pipeline.sweep(now=time.time() + 1)
    mid = store.merchant_by_key(h["Authorization"][7:])["merchant_id"]
    assert store.get_journey(mid, "jr_1")["status"] == "recovering"
    pipeline.sweep(now=time.time() + 10_000)                 # re-offer TTL passed
    assert store.get_journey(mid, "jr_1")["status"] == "lost"


def test_policy_changes_are_validated_and_ledgered(live):
    tc = live["tc"]
    _, h = merchant(live)
    assert tc.patch("/v1/policy", json={"confidence_threshold": 2}, headers=h).status_code == 422
    r = tc.patch("/v1/policy", json={"confidence_threshold": 0.8, "quiet_hours": [22, 8]},
                 headers=h).json()
    assert r["policy"]["confidence_threshold"] == 0.8
    assert list(r["policy"]["quiet_hours"]) == [22, 8]
    assert tc.get("/v1/ledger", headers=h).json()["entries"][-1]["action"] == "policy_changed"


# ------------------------------------------------------------------ SDK ---

def test_sdk_client_batches_and_survives_an_outage():
    from handshake.sdk import HandshakeClient
    calls = []

    def flaky(method, url, body, headers, timeout):
        calls.append(json.loads(body)["events"] if body else None)
        return (0, b"") if len(calls) == 1 else (200, json.dumps(
            {"accepted": len(calls[-1]), "duplicates": 0, "rejected": []}).encode())

    c = HandshakeClient("hsk_test_x", "http://x", flush_interval=0.02, transport=flaky)
    for i in range(5):
        c.track({"type": "feed.read", "agent_id": "a"})
    assert c.flush(5)
    c.close()
    assert c.stats["sent"] == 5 and c.stats["retries"] == 1
    assert calls[0] == calls[1]                       # same ids on retry: idempotent


def test_sdk_track_never_raises_when_the_queue_is_full():
    from handshake.sdk import HandshakeClient
    c = HandshakeClient("hsk_test_x", "http://x", max_queue=2, start=False)
    for _ in range(5):
        c.track({"type": "feed.read", "agent_id": "a"})
    assert c.stats == {**c.stats, "queued": 2, "dropped": 3}


def test_webhook_verification_rejects_tampering_and_replay():
    from handshake.live.webhooks import sign
    from handshake.sdk import WebhookSignatureError, verify_webhook
    body = b'{"type":"ping"}'
    header = sign("whsec_1", body)
    assert verify_webhook(body, header, "whsec_1") == {"type": "ping"}
    with pytest.raises(WebhookSignatureError):
        verify_webhook(b'{"type":"pong"}', header, "whsec_1")
    with pytest.raises(WebhookSignatureError):
        verify_webhook(body, sign("whsec_1", body, ts=time.time() - 3600), "whsec_1")


# ------------------------------------------------- demo store, end to end ---

@pytest.fixture()
def demo(tmp_path, monkeypatch):
    """A real uvicorn server on a free port. The agent, the shop's SDK and the
    webhooks all go over real HTTP, exactly as in a deployment."""
    import socket
    import threading

    import uvicorn

    monkeypatch.setenv("HS_DB", str(tmp_path / "e2e.db"))
    monkeypatch.setenv("HS_NO_SEED", "1")
    monkeypatch.setenv("HS_PAYMENTS", "sim")
    monkeypatch.setenv("HS_LOG_LEVEL", "WARNING")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")
                and m not in KEEP_MODULES and not m.startswith("handshake.tests")]:
        del sys.modules[mod]
    from handshake.server import app as server
    from handshake.demo_shop import runner

    monkeypatch.setitem(runner.SANDBOX_SETTINGS, "idle_seconds", 1)
    monkeypatch.setitem(runner.SANDBOX_SETTINGS, "retry_after_seconds", 0)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port,
                                        log_level="warning", lifespan="on"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    assert srv.started, "uvicorn did not start"
    from handshake.live import pipeline
    pipeline.WORKER.interval = 0.1
    runner.bootstrap(f"http://127.0.0.1:{port}")
    yield runner
    srv.should_exit = True
    thread.join(timeout=20)


def _finish(runner, run, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = runner.view(run["run_id"])
        j = v["journey"]
        if v["status"] == "done" and j and j["status"] not in ("open", "abandoned", "recovering"):
            return v
        time.sleep(0.2)
    v = runner.view(run["run_id"])
    raise AssertionError(f"run did not settle: status={v['status']} error={v['error']!r} "
                         f"journey={(v['journey'] or {}).get('status')} "
                         f"sdk={runner.STATE['client'].stats} "
                         f"thoughts={[t['text'][:60] for t in v['thoughts'][-4:]]}")


EXPECTED = {
    "missing_attribute": ("A1", "recovered", "I-01"),
    "price_drift": ("A3", "recovered", "I-03"),
    "over_cap": ("A4", "recovered", "I-04"),
    "otp_wall": ("A5", "recovered", "I-06"),
    "insufficient_funds": ("B1", "recovered", "I-09"),
    "silent_decline": ("UNKNOWN", "exception", "R-10"),
    "false_claim": ("A3", "exception", "R-10"),
}


def test_demo_scenarios_end_to_end_through_the_sdk(demo):
    runs = {name: demo.start(name, pace=0, reoffer_wait=15) for name in EXPECTED}
    clean = demo.start("clean", pace=0, reoffer_wait=0)
    for name, run in runs.items():
        v = _finish(demo, run)
        j = v["journey"]
        cause, status, action = EXPECTED[name]
        got = j["verdict"].get("intervention_id") or j["verdict"].get("binding_rule")
        assert (j["diagnosis"]["cause"], j["status"], got) == (cause, status, action), name
        assert v["outcome"]["bought"] is (status == "recovered"), name
        # Handshake was never told the scenario: the header never reaches it.
        stored = json.dumps(j["events"]).lower()
        assert "demo-scenario" not in stored and "demo_scenario" not in stored, name
        if name not in ("insufficient_funds",):     # that one is also a real rail code
            assert name not in stored, name
    assert _finish(demo, clean)["journey"]["status"] == "converted"
    from handshake.live import store
    assert store.verify_ledger(demo.MERCHANT_ID)["valid"]


# ------------------------------------------------- database and concurrency ---

def test_readyz_reports_the_configured_backend(live):
    import os
    body = live["tc"].get("/readyz").json()
    from handshake.database import MIGRATIONS
    assert body["ready"] is True and body["schema_version"] == MIGRATIONS[-1][0]
    want = "postgres" if os.environ.get("HS_TEST_DATABASE_URL") else "sqlite"
    assert body["dialect"] == want
    assert "@" not in body["database"].split("//")[-1].split("/")[0] or ":" not in \
        body["database"].split("@")[0].split("//")[-1]          # no password printed


def test_concurrent_ledger_appends_keep_one_valid_chain(live):
    import threading
    store = live["store"]
    m, _ = store.create_merchant("Chain")
    errors = []

    def write(n):
        try:
            for i in range(10):
                store.ledger_append(m["merchant_id"], f"j{n}", "test", "tick", outcome={"i": i})
        except Exception as exc:                      # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    v = store.verify_ledger(m["merchant_id"])
    assert v == {**v, "valid": True, "entries": 60}


def test_two_workers_closing_one_journey_diagnose_it_once(live):
    import threading
    tc, store, pipeline = live["tc"], live["store"], live["pipeline"]
    _, h = merchant(live)
    _setup_catalogue(tc, h)
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=h)
    m = store.merchant_by_key(h["Authorization"][7:])
    barrier = threading.Barrier(4)

    def race():
        barrier.wait()
        pipeline.close(m, "jr_1", "idle_timeout")

    threads = [threading.Thread(target=race) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    actions = [e["action"] for e in store.ledger(m["merchant_id"], "jr_1")]
    assert actions == ["diagnosed", "intervention_permitted"]
    assert store.buyer_history(m["merchant_id"], "ag_1", "jr_1")["interventions_24h"] == 1


def test_webhook_claims_are_exclusive(live):
    store = live["store"]
    m, _ = store.create_merchant("Hooks", webhook_url="http://testserver/x")
    for i in range(5):
        store.enqueue_delivery(m["merchant_id"], "", "ping", {"i": i})
    first = store.claim_deliveries(time.time(), limit=10)
    second = store.claim_deliveries(time.time(), limit=10)
    assert len(first) == 5 and second == []          # leased, not re-sent
    assert len(store.claim_deliveries(time.time() + 120, limit=10)) == 5   # lease lapsed


def test_event_retention_keeps_open_journeys(live):
    tc, store = live["tc"], live["store"]
    _, h = merchant(live)
    tc.post("/v1/events", json={"events": _discovery_events("jr_old")}, headers=h)
    mid = store.merchant_by_key(h["Authorization"][7:])["merchant_id"]
    assert store.purge_events(time.time() + 10) == 0          # still open: kept
    store.update_journey(mid, "jr_old", status="lost")
    assert store.purge_events(time.time() + 10) == 2


# ------------------------------------------------- outside the playbook ---

def test_an_unrecognised_refusal_is_explained_without_a_rule_for_it():
    events = checkout() + [ev(5, "checkout.complete", 400,
                              response={"error": "payment_method_unsupported",
                                        "detail": "this store does not accept UPI Reserve"}),
                           ev(6, "checkout.cancel")]
    d = run(events)
    assert d["cause"] == "N1" and d["confidence"] < 0.70          # never acts alone
    assert d["detail"]["error"] == "payment_method_unsupported"
    assert d["evidence"][0]["event"] == 5                          # the refusal, not the cancel


def test_the_weakest_option_on_a_dimension_is_found_without_a_rule_for_it():
    peers = {**TRUTH, "KET-150": {"sku": "KET-150", "category": "home_kitchen", "price": 1590.0,
                                  "attributes": {"capacity_l": 1.5, "power_watts": 1500},
                                  "policy": {"returns_days": 10, "warranty_months": 12},
                                  "fulfilment": {"ships_in_days": 2}}}
    feed = ev(1, "feed.read", response={"items": [view()["response"], peers["KET-150"]]})
    created = ev(3, "checkout.create", request={"sku": "KET-170", "declared_cap": 3000},
                 response={"session_id": "cs_1", "total": 2358.82,
                           "fulfilment": {"ships_in_days": 9}})
    d = diagnose([feed, view(), created, ev(4, "checkout.update", response={"total": 2358.82}),
                  ev(5, "checkout.cancel")], SCHEMA, peers.get, lambda: list(peers.values()))
    assert d["cause"] == "N2" and d["detail"]["facet"] == "ships_in_days"
    assert d["detail"]["best_alternative"] == "KET-150" and d["confidence"] < 0.70


def test_analyst_output_is_validated_not_trusted():
    from handshake.live.analyst import parse
    events = [{**view(), "seq": 1}, {**ev(2, "checkout.cancel"), "seq": 2}]
    catalogue = list(TRUTH.values())
    good = parse('{"cause": "NOVEL", "label": "Colour Wrong!", "explanation": "It wanted red.",'
                 ' "evidence": [1, 99], "confidence": 0.9, "proposal": {"action":'
                 ' "alternative_product", "sku": "NOPE-1", "message": "Try this."}}',
                 events, catalogue)
    assert good.cause == "N3" and good.score <= 0.66              # capped below R-10
    assert [e["event"] for e in good.evidence] == [1]              # invented event dropped
    assert good.detail["label"] == "colour_wrong_"
    assert good.detail["proposal"]["action"] == "information"      # invented SKU refused
    assert parse('{"cause": "A1", "explanation": "x", "evidence": [42]}', events, catalogue) is None
    assert parse("not json", events, catalogue) is None


def test_the_analyst_is_consulted_only_when_detectors_are_unsure():
    calls = []

    def fake(evs):
        calls.append(len(evs))
        return None
    diagnose([view(attrs={"capacity_l": 1.7, "warranty_months": 24})], SCHEMA, TRUTH.get,
             analyst=fake)
    assert calls == []                              # A1 at 0.92: deterministic, no model
    diagnose([ev(1, "feed.read"), view()], SCHEMA, TRUTH.get, analyst=fake)
    assert calls == [2]                             # nothing explains it: ask


def _novel_journey(live, h):
    tc = live["tc"]
    tc.put("/v1/schema", json={"schema": SCHEMA}, headers=h)
    alt = {"sku": "KET-150", "category": "home_kitchen", "price": 1590.0, "tax_rate": 0.18,
           "stock": 10, "attributes": {"capacity_l": 1.5, "power_watts": 1500},
           "policy": {"returns_days": 10}, "fulfilment": {"ships_in_days": 2}}
    tc.put("/v1/catalog", json={"products": [{**TRUTH["KET-170"], "stock": 5}, alt]}, headers=h)
    base = {"agent_id": "ag_n", "journey_id": "jr_n"}
    tc.post("/v1/events", headers=h, json={"events": [
        {**base, "type": "product.view", "sku": "KET-170", "response": TRUTH["KET-170"]},
        {**base, "type": "checkout.create", "sku": "KET-170", "http_status": 409,
         "request": {"sku": "KET-170"},
         "response": {"error": "insufficient_stock", "detail": "KET-170 is not available"}}]})
    m = live["store"].merchant_by_key(h["Authorization"][7:])
    return m, live["pipeline"].close(m, "jr_n", "idle_timeout")


def test_novel_cause_drafts_a_fix_and_waits_for_a_person(live):
    _, h = merchant(live)
    m, j = _novel_journey(live, h)
    assert j["status"] == "exception" and j["diagnosis"]["cause"] == "N1"
    prop = j["verdict"]["proposal"]
    assert prop["action"] == "alternative_product" and prop["sku"] == "KET-150"
    assert live["tc"].get("/v1/reoffers/jr_n", headers=h).status_code == 404   # nothing sent yet

    r = live["tc"].post("/v1/journeys/jr_n/approve", headers=h,
                        json={"approved_by": "Asha", "message": "KET-150 is in stock now."})
    assert r.status_code == 200 and r.json()["status"] == "recovering"
    offer = live["tc"].get("/v1/reoffers/jr_n", headers=h).json()["offer"]
    assert offer["type"] == "merchant_offer" and offer["message"] == "KET-150 is in stock now."
    entry = live["store"].ledger(m["merchant_id"], "jr_n")[-1]
    assert entry["action"] == "proposal_approved" and entry["trigger"]["approved_by"] == "Asha"
    # A second approval of the same journey is refused: it is no longer an exception.
    assert live["tc"].post("/v1/journeys/jr_n/approve", headers=h, json={}).status_code == 409
    patterns = live["tc"].get("/v1/patterns", headers=h).json()["patterns"]
    assert patterns[0]["cause"] == "N1" and patterns[0]["approved"] == 1


def test_approval_still_obeys_the_kill_switch(live):
    _, h = merchant(live)
    _novel_journey(live, h)
    live["tc"].patch("/v1/policy", json={"kill_switch": True}, headers=h)
    r = live["tc"].post("/v1/journeys/jr_n/approve", headers=h, json={"message": "x"})
    assert r.status_code == 409 and "R-11" in r.json()["error"]["message"]


def test_judge_scores_against_the_agents_own_reason():
    from handshake.demo_shop.scenarios import judge
    dg = {"cause": "N2", "confidence": 0.62, "detail": {"facet": "ships_in_days"}}
    assert judge("slow:ships_in_days", dg, "exception")[0] == "correct"
    assert judge("A1", dg, "exception")[0] == "honest_unknown"      # below the bar: not a claim
    assert judge("A1", {"cause": "A3", "confidence": 0.9}, "recovering")[0] == "wrong"
    assert judge("decline:no_reason", {"cause": "UNKNOWN", "confidence": 0}, "exception")[0] == "correct"
    assert judge(None, None, None)[0] == "n/a"


def test_mystery_runs_are_reproducible_from_their_seed():
    import random
    from handshake.demo_shop.scenarios import mystery
    assert mystery(random.Random(7)) == mystery(random.Random(7))
    seen = {c for s in range(200) for c in mystery(random.Random(s))[1]}
    assert {"slow_delivery", "unsupported_payment", "out_of_stock", "shipping_fee"} <= seen


def test_mystery_shoppers_end_to_end_with_approval(demo, monkeypatch):
    """Blind runs over real HTTP: sealed until judged; approved fixes recover."""
    monkeypatch.setattr(demo, "MYSTERY_WAIT", 12.0)
    seeds = [54, 43, 24, 76]   # refused payment (kettle), stock-out (kettle), drift (stand), funds (headphones)
    runs = [demo.start("mystery", pace=0, seed=s) for s in seeds]
    first = demo.view(runs[0]["run_id"])
    assert first["sealed"] and first["thoughts"] == [] and first["truth"] == []
    assert "Sealed" in first["scenario_meta"]["story"]
    approved = set()
    deadline = time.time() + 90
    pending = {r["run_id"] for r in runs}
    results = {}
    while pending and time.time() < deadline:
        for rid in list(pending):
            v = demo.view(rid)
            j = v["journey"] or {}
            if j.get("status") == "exception" and (j.get("verdict") or {}).get("proposal") \
                    and rid not in approved:
                demo.approve(rid)
                approved.add(rid)
            if v["status"] == "done" and v["judgement"]:
                results[rid] = v
                pending.discard(rid)
        time.sleep(0.3)
    assert not pending, f"runs did not finish: {pending}"
    for rid, v in results.items():
        assert v["judgement"]["verdict"] in ("correct", "n/a"), (v["truth"], v["journey"]["diagnosis"])
        assert v["outcome"]["bought"], v["truth"]
    assert len(approved) == 2                     # the two outside the playbook needed a person


# --------------------------------------------- found by a real agent (Claude) ---

def test_a_repeat_offer_pickup_does_not_hide_the_second_stop():
    # Claude: stop 1 (missing battery) → took the offer → payment refused →
    # picked the old offer up again → cancelled. The refusal must still be read.
    events = [ev(1, "feed.read"), view(2, attrs={"capacity_l": 1.7, "warranty_months": 24}),
              ev(3, "reoffer.fetch", 200, response={"offer": {"type": "catalogue_delta"}}),
              view(4),
              ev(5, "checkout.create", request={"sku": "KET-170"},
                 response={"session_id": "cs_9", "total": 2358.82}),
              ev(6, "checkout.update", response={"total": 2358.82}),
              ev(7, "checkout.complete", 400, response={"error": "payment_method_unsupported"}),
              ev(8, "reoffer.fetch", 200, response={"offer": {"type": "catalogue_delta"}}),
              ev(9, "checkout.cancel", request={"reason": "store refuses my payment method"})]
    d = run(events)
    assert d["cause"] == "N1" and d["detail"]["error"] == "payment_method_unsupported"


def test_a_used_offer_is_not_served_again_and_a_repeat_ask_rediagnoses(live):
    tc, store = live["tc"], live["store"]
    _, h = merchant(live)
    _setup_catalogue(tc, h)
    tc.post("/v1/events", json={"events": _discovery_events()}, headers=h)
    base = {"agent_id": "ag_1", "journey_id": "jr_1"}
    # Asking for an offer is itself the abandonment signal: no idle timer needed.
    tc.post("/v1/events", headers=h, json={"events": [{**base, "type": "reoffer.fetch",
                                                      "http_status": 404}]})
    assert tc.get("/v1/journeys/jr_1", headers=h).json()["status"] == "recovering"
    assert tc.get("/v1/reoffers/jr_1", headers=h).status_code == 200      # picked up
    tc.post("/v1/events", headers=h, json={"events": [
        {**base, "type": "reoffer.fetch", "http_status": 200},
        {**base, "type": "checkout.create", "sku": "KET-170",
         "response": {"session_id": "cs_2", "total": 2358.82}},
        {**base, "type": "checkout.complete", "http_status": 400,
         "response": {"error": "payment_method_unsupported"}}]})
    assert tc.get("/v1/reoffers/jr_1", headers=h).status_code == 404      # used: not re-served
    tc.post("/v1/events", headers=h, json={"events": [{**base, "type": "reoffer.fetch",
                                                      "http_status": 404}]})
    j = tc.get("/v1/journeys/jr_1", headers=h).json()
    assert j["status"] == "exception" and j["diagnosis"]["cause"] == "N1"
    assert j["verdict"]["proposal"]["action"] == "alternate_instrument"


# ------------------------------------------------------- MCP and store admin ---

def test_mcp_endpoint_speaks_the_protocol_and_shops_over_http(demo):
    import json as _json
    import urllib.request
    base = demo.STATE["base_url"]

    def rpc(body, sid=""):
        req = urllib.request.Request(base + "/mcp", data=_json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Accept": "application/json, text/event-stream",
                                              **({"Mcp-Session-Id": sid} if sid else {})})
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, r.headers.get("Mcp-Session-Id", ""), (_json.loads(raw) if raw else None)

    st, sid, init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "pytest-agent", "version": "1"}}})
    assert st == 200 and sid and init["result"]["serverInfo"]["name"] == "kaveri-home-tech"
    assert rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)[0] == 202
    tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)[2]["result"]["tools"]
    assert {t["name"] for t in tools} >= {"search_products", "pay", "check_for_offer"}
    out = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
               "params": {"name": "get_product", "arguments": {"sku": "IEM-010"}}}, sid)[2]
    product = _json.loads(out["result"]["content"][0]["text"])
    assert product["sku"] == "IEM-010" and out["result"]["isError"] is False
    bad = rpc({"jsonrpc": "2.0", "id": 4, "method": "nope"}, sid)[2]
    assert bad["error"]["code"] == -32601
    # The agent's request reached Handshake through the store's SDK, under its own identity.
    from handshake.demo_shop import mcp_server
    agent = mcp_server.SESSIONS[sid]["store"].agent_id
    assert agent.startswith("pytestagent_")
    demo.STATE["client"].flush(5)
    from handshake.live import store
    assert any(j["agent_id"] == agent for j in store.list_journeys(demo.MERCHANT_ID, None, 50, 0))


def test_store_admin_settings_are_the_stores_real_state(demo):
    import json as _json
    import urllib.request
    base = demo.STATE["base_url"] + "/shop"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method,
                                     data=_json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return _json.loads(r.read())

    cfg = call("PUT", "/admin/api/config", {"global": ["unsupported_payment", "bogus"],
                                            "products": {"HPH-045": ["missing_attribute"]}})
    assert cfg["global"] == ["unsupported_payment"]                 # unknown problems ignored
    served = call("GET", "/acp/products/HPH-045")                  # any agent, no header needed
    assert "battery_hours" not in served["attributes"]
    assert "battery_hours" in call("GET", "/acp/products/IEM-010")["attributes"]
    call("PUT", "/admin/api/config", {"global": [], "products": {}})
    assert "battery_hours" in call("GET", "/acp/products/HPH-045")["attributes"]


def test_claudes_live_trace_slow_delivery_from_search_results():
    # Replayed from the live run: search → checkout (ships in 9) → cancel with a
    # free-text reason. No product page was ever opened.
    al1 = {"sku": "LST-AL1", "category": "laptop_accessories", "price": 1790.0, "tax_rate": 0.18,
           "attributes": {"compatibility": '11"-16" laptops', "weight_g": 690},
           "policy": {"returns_days": 10, "warranty_months": 12}, "fulfilment": {"ships_in_days": 2}}
    fd2 = {**al1, "sku": "LST-FD2", "price": 2290.0}
    cat = {"LST-AL1": al1, "LST-FD2": fd2}
    listed = [{k: v for k, v in p.items() if k != "fulfilment"} for p in (al1, fd2)]
    events = [ev(1, "feed.read", response={"items": listed[:1]}),
              ev(2, "feed.read", response={"items": listed}),
              ev(3, "checkout.create", request={"sku": "LST-AL1", "declared_cap": 3000},
                 response={"session_id": "cs_1", "total": 2112.2, "fulfilment": {"ships_in_days": 9}},
                 sku="LST-AL1"),
              ev(4, "checkout.cancel", request={"reason": "Ships in 9 days; buyer needs delivery "
                                                          "within 4 days (travelling)."})]
    d = diagnose(events, {"laptop_accessories": ["compatibility", "material", "weight_g"]},
                 cat.get, lambda: list(cat.values()))
    assert d["cause"] == "N2" and d["detail"]["facet"] == "ships_in_days"
    assert d["detail"]["best_alternative"] == "LST-FD2"
    assert d["declared"]["corroborated"] is True and d["confidence"] <= 0.66   # still a person's call


def test_free_text_never_creates_a_hypothesis_on_its_own():
    events = checkout() + [ev(5, "checkout.cancel", request={"reason": "the price went up"})]
    d = run(events)                     # nothing in the traffic shows a price change
    assert d["cause"] == "UNKNOWN" and not (d["declared"] or {}).get("corroborated")


def test_offer_polls_alone_never_open_a_journey(live):
    _, h = merchant(live)
    resp = live["tc"].post("/v1/events", headers=h, json={"events": [
        {"type": "reoffer.fetch", "agent_id": "ag_x", "journey_id": "jr_after_purchase",
         "http_status": 404}]})
    r = resp.json()
    assert resp.status_code == 200 and r["ignored"] == 1 and r["accepted"] == 0
    assert live["tc"].get("/v1/journeys", headers=h).json()["journeys"] == []
