"""The HTTP surface: health, guards, persistence, and the read paths a UI needs.

Skipped entirely when FastAPI is not installed, so the core suite stays
dependency-free.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

fastapi = pytest.importorskip("fastapi", reason="console extra not installed")
pytest.importorskip("httpx", reason="httpx is needed by fastapi's TestClient")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("HS_PAYMENTS", "sim")
    monkeypatch.setenv("HS_BUYERS", "heuristic")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")]:
        del sys.modules[mod]
    from handshake.server import app as server           # re-import with the temp DB
    server.STATE.__init__()
    return TestClient(server.app), server


def _wait(client, timeout=90):
    """Block until the current run finishes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get("/api/state?since=0").json()
        if not state["running"] and not state["scanning"]:
            return state
        time.sleep(0.2)
    raise AssertionError("run did not finish in time")


# ---------------- health and metadata ----------------

def test_healthz_reports_backends_and_store(client):
    c, _ = client
    body = c.get("/healthz").json()
    assert body["ok"] is True
    assert body["version"]
    assert body["backends"]["payments"] == "sim"
    assert "runs" in body["store"]


def test_index_serves_the_console(client):
    c, _ = client
    page = c.get("/").text
    assert "<title>" in page and "Handshake" in page
    # the page must not depend on a build step or an external script host
    assert "<script src=" not in page


# ---------------- a batch, end to end over HTTP ----------------

def test_batch_runs_persists_and_reads_back(client):
    c, server = client
    started = c.post("/api/run", json={"sessions": 120, "mode": "batch",
                                       "offline": True}).json()
    assert started["started"] is True
    state = _wait(c)

    assert state["summary"]["treatment"]["recovered_gmv"] > 0
    assert state["totals"]["failed"] > 0
    assert state["measured"] is True
    assert state["run_id"], "a finished run must be stored"

    runs = c.get("/api/runs").json()["runs"]
    assert runs and runs[0]["kind"] == "batch"
    assert runs[0]["headline"]["recovered"] > 0

    stored = c.get(f"/api/runs/{state['run_id']}").json()
    assert stored["chain_valid"] is True, "the stored chain must re-verify from SQLite"
    assert stored["sessions"]

    chain = c.get(f"/api/runs/{state['run_id']}/chain").json()
    assert chain["entries"] and chain["chain_valid"] is True


def test_trace_shows_only_merchant_observable_traffic(client):
    c, _ = client
    c.post("/api/run", json={"sessions": 120, "mode": "batch", "offline": True})
    _wait(c)

    sessions = c.get("/api/runs").json()["runs"]
    run_id = sessions[0]["run_id"]
    stored = c.get(f"/api/runs/{run_id}").json()
    failed = next(s for s in stored["sessions"]
                  if s["terminal_state"] == "FAILED" or s["recovered"])

    trace = c.get(f"/api/trace/{failed['session_id']}").json()
    assert trace["events"], "a trace must carry the API traffic"
    for event in trace["events"]:
        assert event["type"].startswith(("GET ", "POST ")), event["type"]
    # ground truth is exposed for scoring, never inside the diagnosis payload
    if trace["diagnosed"]:
        assert "injected_fault" not in trace["diagnosed"]


def test_walkthrough_is_flagged_as_not_measured(client):
    c, _ = client
    c.post("/api/run", json={"mode": "walkthrough"})
    state = _wait(c)
    assert state["measured"] is False
    runs = c.get("/api/runs").json()["runs"]
    assert runs[0]["measured"] is False


# ---------------- guards ----------------

def test_a_second_run_is_refused_while_one_is_in_flight(client):
    c, _ = client
    c.post("/api/run", json={"sessions": 400, "mode": "batch", "offline": True})
    second = c.post("/api/run", json={"sessions": 50, "mode": "batch"})
    assert second.status_code == 409
    c.post("/api/stop")
    _wait(c)


def test_token_is_enforced_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("HS_API_TOKEN", "s3cret")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")]:
        del sys.modules[mod]
    from handshake.server import app as server
    server.STATE.__init__()
    c = TestClient(server.app)

    assert c.post("/api/run", json={"sessions": 20}).status_code == 401
    assert c.post("/api/killswitch", json={"on": True}).status_code == 401
    ok = c.post("/api/killswitch", json={"on": True},
                headers={"X-Handshake-Token": "s3cret"})
    assert ok.status_code == 200 and ok.json()["kill_switch"] is True
    assert c.get("/healthz").json()["auth_required"] is True


def test_demo_mode_caps_the_batch_size(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DB", str(tmp_path / "demo.db"))
    monkeypatch.setenv("HS_DEMO_MODE", "1")
    monkeypatch.setenv("HS_MAX_SESSIONS", "60")
    monkeypatch.setenv("HS_MIN_RUN_GAP", "0")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")]:
        del sys.modules[mod]
    from handshake.server import app as server
    server.STATE.__init__()
    c = TestClient(server.app)

    started = c.post("/api/run", json={"sessions": 5000, "mode": "batch"}).json()
    assert started["sessions"] == 60
    c.post("/api/stop")


# ---------------- prevention over HTTP ----------------

def test_readiness_scan_over_http(client):
    c, _ = client
    assert c.post("/api/readiness", json={"sessions": 120}).json()["scanning"]
    state = _wait(c, timeout=180)
    report = state["readiness"]
    assert report and "error" not in report
    assert report["delta"]["revenue_gained"] > 0
    assert c.get("/api/runs?kind=scan").json()["runs"]


def test_overview_serves_stored_headlines(client):
    c, _ = client
    c.post("/api/run", json={"sessions": 120, "mode": "batch", "offline": True})
    _wait(c)
    body = c.get("/api/overview").json()
    assert body["batch"] and body["batch"]["headline"]["recovered"] > 0


# ---------------- cold-start seeding ----------------

def test_a_cold_store_is_seeded_from_the_committed_run(tmp_path, monkeypatch):
    """Free tiers lose the filesystem on every redeploy. A visitor arriving at a
    cold URL must still see the canonical figures, not an empty console."""
    monkeypatch.setenv("HS_DB", str(tmp_path / "cold.db"))
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")]:
        del sys.modules[mod]
    from handshake.server import app as server
    server.STATE.__init__()

    with TestClient(server.app) as c:               # triggers the startup hook
        health = c.get("/healthz").json()
        assert health["seed"]["seeded"], health["seed"]
        batch = next(s for s in health["seed"]["seeded"] if s["kind"] == "batch")
        assert batch["chain_valid"] is True, "the imported chain must verify"

        body = c.get("/api/overview").json()
        assert body["batch"]["headline"]["recovered"] > 0
        assert body["scan"]["headline"]["readiness"] > 0

        runs = c.get("/api/runs").json()["runs"]
        assert any(r["label"] == "canonical (committed)" for r in runs)


def test_seeding_never_overwrites_a_real_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DB", str(tmp_path / "warm.db"))
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")]:
        del sys.modules[mod]
    from handshake.store import seed as seeder
    first = seeder.seed(path=str(tmp_path / "warm.db"))
    assert first["seeded"]
    second = seeder.seed(path=str(tmp_path / "warm.db"))
    assert not second["seeded"] and "already stored" in second["skipped"]
