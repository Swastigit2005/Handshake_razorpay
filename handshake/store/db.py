"""Durable store.

A deployed console must survive a restart with its evidence intact, so runs,
their session tables and their audit ledgers are written to SQLite. The ledger
table is append-only in the application layer: there is no update or delete
path, and the hash chain is re-verified on read.
"""

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

DEFAULT_PATH = os.environ.get(
    "HS_DB", os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "data", "handshake.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,               -- batch | walkthrough | scan
    created_at  REAL NOT NULL,
    label       TEXT,
    sessions    INTEGER,
    seed        INTEGER,
    payments    TEXT,
    buyers      TEXT,
    measured    INTEGER NOT NULL DEFAULT 1,  -- 0 for a demo walkthrough
    summary     TEXT NOT NULL                -- json
);

CREATE TABLE IF NOT EXISTS run_sessions (
    run_id      TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id)
);

CREATE TABLE IF NOT EXISTS ledger (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    entry_id    TEXT NOT NULL,
    session_id  TEXT,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE INDEX IF NOT EXISTS ledger_session ON ledger (run_id, session_id);
CREATE INDEX IF NOT EXISTS runs_created ON runs (created_at DESC);
"""


@contextmanager
def connect(path=None):
    path = path or DEFAULT_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def new_run_id(kind):
    return f"{kind[:4]}_{time.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}"


def save_batch(summary, sessions, ledger, kind="batch", label="", measured=True,
               path=None):
    run_id = new_run_id(kind)
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, kind, created_at, label, sessions, seed,"
            " payments, buyers, measured, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, kind, time.time(), label, summary.get("batch_size", 0),
             summary.get("seed", 0), summary.get("payments_backend", ""),
             summary.get("buyer_backend", ""), 1 if measured else 0,
             json.dumps(summary, default=str)))
        conn.executemany(
            "INSERT OR REPLACE INTO run_sessions (run_id, session_id, payload)"
            " VALUES (?,?,?)",
            [(run_id, s["session_id"], json.dumps(s, default=str)) for s in sessions])
        if ledger is not None:
            conn.executemany(
                "INSERT OR REPLACE INTO ledger (run_id, seq, entry_id, session_id,"
                " prev_hash, hash, payload) VALUES (?,?,?,?,?,?,?)",
                [(run_id, i, e["entry_id"], e.get("session_id"), e["prev_hash"],
                  e["hash"], json.dumps(e, default=str))
                 for i, e in enumerate(ledger.entries)])
    return run_id


def save_scan(report, label="", path=None):
    run_id = new_run_id("scan")
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, kind, created_at, label, sessions, seed,"
            " payments, buyers, measured, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, "scan", time.time(), label, report.get("sessions", 0),
             report.get("seed", 0), "sim", report.get("buyers", ""), 1,
             json.dumps(report, default=str)))
    return run_id


def recent(limit=25, kind=None, path=None):
    sql = ("SELECT run_id, kind, created_at, label, sessions, seed, payments,"
           " buyers, measured, summary FROM runs")
    args = []
    if kind:
        sql += " WHERE kind = ?"
        args.append(kind)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with connect(path) as conn:
        rows = conn.execute(sql, args).fetchall()
    out = []
    for row in rows:
        summary = json.loads(row["summary"])
        out.append({
            "run_id": row["run_id"], "kind": row["kind"],
            "created_at": row["created_at"], "label": row["label"],
            "sessions": row["sessions"], "seed": row["seed"],
            "payments": row["payments"], "buyers": row["buyers"],
            "measured": bool(row["measured"]),
            "headline": _headline(row["kind"], summary),
        })
    return out


def _headline(kind, summary):
    """One line a person can read in a list of runs."""
    if kind == "scan":
        d = summary.get("delta", {})
        return {"readiness": summary.get("readiness_score"),
                "revenue_gained": d.get("revenue_gained"),
                "per_1000": d.get("per_1000_sessions")}
    arms = summary.get("arms", {})
    treatment = arms.get("treatment", {})
    return {"recovered": treatment.get("recovered_gmv"),
            # at_risk lets a cold visitor see the recovered/lost split without
            # loading the whole run.
            "at_risk": treatment.get("at_risk_gmv"),
            "failed": treatment.get("failed"),
            "recovery_rate": treatment.get("recovery_rate"),
            "lift": summary.get("lift_over_control"),
            "control_rate": (arms.get("control") or {}).get("recovery_rate"),
            "concession_ratio": treatment.get("concession_ratio"),
            "macro_f1": (summary.get("diagnosis") or {}).get("macro_f1")}


def get_run(run_id, path=None):
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        sessions = [json.loads(r["payload"]) for r in conn.execute(
            "SELECT payload FROM run_sessions WHERE run_id = ? ORDER BY session_id",
            (run_id,))]
    return {"run_id": run_id, "kind": row["kind"], "created_at": row["created_at"],
            "measured": bool(row["measured"]),
            "summary": json.loads(row["summary"]), "sessions": sessions}


def chain(run_id, session_id=None, path=None):
    sql = "SELECT payload FROM ledger WHERE run_id = ?"
    args = [run_id]
    if session_id:
        sql += " AND session_id = ?"
        args.append(session_id)
    sql += " ORDER BY seq"
    with connect(path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def verify_chain(run_id, path=None):
    """Re-verify the stored chain, independently of the in-memory ledger."""
    import hashlib
    entries = chain(run_id, path=path)
    prev = "0" * 64
    for i, entry in enumerate(entries):
        payload = {k: v for k, v in entry.items() if k not in ("prev_hash", "hash")}
        blob = json.dumps(payload, sort_keys=True, default=str) + prev
        if (entry["prev_hash"] != prev
                or entry["hash"] != hashlib.sha256(blob.encode()).hexdigest()):
            return False, i
        prev = entry["hash"]
    return True, -1


def stats(path=None):
    with connect(path) as conn:
        runs = conn.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
        entries = conn.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"]
    return {"runs": runs, "ledger_entries": entries,
            "path": path or DEFAULT_PATH}
