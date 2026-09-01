"""Seed the database from the canonical run committed to the repository.

Free hosting tiers have an ephemeral filesystem: the SQLite file is lost on every
redeploy and every spin-down. Without this, a visitor arriving at a cold URL sees
an empty console and has to run a batch before anything means something.

So on startup, if the store is empty, the canonical run in `runs/` is imported.
It is the same artefact set the README quotes and the tests reproduce, so the
deployed console tells the truth the moment it wakes up.
"""

import json
import os
import time
import uuid

from . import db

RUNS_DIR = os.environ.get(
    "HS_RUNS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "runs"))


def _read(name):
    path = os.path.join(RUNS_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def _read_jsonl(name):
    path = os.path.join(RUNS_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def seed(path=None, force=False):
    """Import the canonical batch and scan. Returns a short report.

    Idempotent: does nothing when the store already holds runs, unless forced."""
    report = {"seeded": [], "skipped": "", "path": path or db.DEFAULT_PATH}

    try:
        existing = db.stats(path)["runs"]
    except Exception as exc:
        report["skipped"] = f"store unavailable: {exc}"
        return report

    if existing and not force:
        report["skipped"] = f"{existing} run(s) already stored"
        return report

    summary = _read("batch_canonical_summary.json")
    sessions = _read("batch_canonical_sessions.json")
    entries = _read_jsonl("batch_canonical_ledger.jsonl")

    if summary and sessions is not None:
        run_id = f"batc_canonical_{uuid.uuid4().hex[:6]}"
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO runs (run_id, kind, created_at, label, sessions, seed,"
                " payments, buyers, measured, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, "batch", time.time(), "canonical (committed)",
                 summary.get("batch_size", 0), summary.get("seed", 0),
                 summary.get("payments_backend", ""), summary.get("buyer_backend", ""),
                 1, json.dumps(summary, default=str)))
            conn.executemany(
                "INSERT OR REPLACE INTO run_sessions (run_id, session_id, payload)"
                " VALUES (?,?,?)",
                [(run_id, s["session_id"], json.dumps(s, default=str))
                 for s in sessions])
            conn.executemany(
                "INSERT OR REPLACE INTO ledger (run_id, seq, entry_id, session_id,"
                " prev_hash, hash, payload) VALUES (?,?,?,?,?,?,?)",
                [(run_id, i, e["entry_id"], e.get("session_id"), e["prev_hash"],
                  e["hash"], json.dumps(e, default=str))
                 for i, e in enumerate(entries)])
        ok, bad = db.verify_chain(run_id, path)
        report["seeded"].append({"run_id": run_id, "kind": "batch",
                                 "sessions": len(sessions),
                                 "ledger_entries": len(entries),
                                 "chain_valid": ok, "first_bad": bad})

    scan_report = _read("readiness_canonical.json")
    if scan_report:
        run_id = db.save_scan(scan_report, label="canonical (committed)", path=path)
        report["seeded"].append({"run_id": run_id, "kind": "scan",
                                 "sessions": scan_report.get("sessions", 0)})

    if not report["seeded"]:
        report["skipped"] = f"no canonical artefacts in {RUNS_DIR}"
    return report
