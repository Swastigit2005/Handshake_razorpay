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
    # Over the cap *and* drifted: two strong explanations, reported as contested.
    d = run(checkout(cap=2400, second=2571.11))
    assert d["contested"] and d["confidence"] < 0.8
    assert {h["cause"] for h in d["hypotheses"]} == {"A3", "A4"}


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


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv("HS_LIVE_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv("HS_NO_SEED", "1")
    monkeypatch.setenv("HS_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HS_PAYMENTS", "sim")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")
                and not m.startswith("handshake.tests")]:
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
def demo(live, monkeypatch):
    tc = live["tc"]
    from handshake.demo_shop import runner

    monkeypatch.setitem(runner.SANDBOX_SETTINGS, "idle_seconds", 1)
    monkeypatch.setitem(runner.SANDBOX_SETTINGS, "retry_after_seconds", 0)

    def sdk_transport(method, url, body, headers, timeout):
        r = tc.request(method, "/" + url.split("://", 1)[1].split("/", 1)[1],
                       content=body, headers=headers)
        return r.status_code, r.content

    def agent_http(method, url, body=None, headers=None):
        r = tc.request(method, "/" + url.split("://", 1)[1].split("/", 1)[1],
                       json=body, headers=headers)
        return r.status_code, (r.json() if r.content else {})

    runner.bootstrap("http://testserver", http=agent_http, transport=sdk_transport)
    live["pipeline"].WORKER.interval = 0.1
    return runner


def _finish(runner, run, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = runner.view(run["run_id"])
        j = v["journey"]
        if v["status"] == "done" and j and j["status"] not in ("open", "abandoned", "recovering"):
            return v
        time.sleep(0.2)
    raise AssertionError(f"run did not settle: {runner.view(run['run_id'])['journey']}")


EXPECTED = {
    "missing_attribute": ("A1", "recovered", "I-01"),
    "price_drift": ("A3", "recovered", "I-03"),
    "over_cap": ("A4", "recovered", "I-04"),
    "otp_wall": ("A5", "recovered", "I-06"),
    "insufficient_funds": ("B1", "recovered", "I-09"),
    "silent_decline": ("UNKNOWN", "exception", "R-10"),
    "false_claim": ("A3", "exception", "R-10"),
}


def test_demo_scenarios_end_to_end_through_the_sdk(demo, live):
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
    key = demo.STATE["api_key"]
    assert live["tc"].get("/v1/ledger/verify",
                          headers={"Authorization": f"Bearer {key}"}).json()["valid"]
