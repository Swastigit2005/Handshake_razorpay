"""Tenant-scoped persistence for the live plane.

Every table carries `merchant_id`, and every query in this module filters on it.
There is no function here that reads across tenants except the sweeper's scan
for idle journeys, which returns ids only.

SQLite in WAL mode is the default because it needs no infrastructure and
survives a restart. The SQL is deliberately plain (no upsert syntax beyond
`INSERT OR IGNORE`, no JSON operators) so the module ports to Postgres by
swapping `connect()`.
"""

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from ..store.db import DEFAULT_PATH as _SIM_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,
    key_prefix      TEXT NOT NULL,
    webhook_url     TEXT NOT NULL DEFAULT '',
    webhook_secret  TEXT NOT NULL,
    policy          TEXT NOT NULL DEFAULT '{}',
    settings        TEXT NOT NULL DEFAULT '{}',
    sandbox         INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS journeys (
    merchant_id     TEXT NOT NULL,
    journey_id      TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    principal_id    TEXT NOT NULL DEFAULT '',
    checkout_id     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL,       -- open|converted|abandoned|recovering|recovered|lost|exception
    stage           TEXT NOT NULL DEFAULT 'discovery',
    sku             TEXT NOT NULL DEFAULT '',
    basket_value    REAL NOT NULL DEFAULT 0,
    recovered_value REAL NOT NULL DEFAULT 0,
    concession      REAL NOT NULL DEFAULT 0,
    opened_at       REAL NOT NULL,
    last_event_at   REAL NOT NULL,
    closed_at       REAL NOT NULL DEFAULT 0,
    close_reason    TEXT NOT NULL DEFAULT '',
    attempts        INTEGER NOT NULL DEFAULT 0,
    diagnosis       TEXT NOT NULL DEFAULT '{}',
    verdict         TEXT NOT NULL DEFAULT '{}',
    directive       TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (merchant_id, journey_id)
);
CREATE INDEX IF NOT EXISTS journeys_open ON journeys (status, last_event_at);
CREATE INDEX IF NOT EXISTS journeys_agent ON journeys (merchant_id, agent_id, opened_at);
CREATE INDEX IF NOT EXISTS journeys_checkout ON journeys (merchant_id, checkout_id);
CREATE INDEX IF NOT EXISTS journeys_recent ON journeys (merchant_id, last_event_at DESC);

CREATE TABLE IF NOT EXISTS events (
    merchant_id     TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    journey_id      TEXT NOT NULL,
    seq             INTEGER NOT NULL,
    ts              REAL NOT NULL,
    type            TEXT NOT NULL,
    http_status     INTEGER NOT NULL DEFAULT 200,
    payload         TEXT NOT NULL,
    PRIMARY KEY (merchant_id, event_id)
);
CREATE INDEX IF NOT EXISTS events_journey ON events (merchant_id, journey_id, seq);

CREATE TABLE IF NOT EXISTS catalog (
    merchant_id     TEXT NOT NULL,
    sku             TEXT NOT NULL,
    record          TEXT NOT NULL,
    updated_at      REAL NOT NULL,
    PRIMARY KEY (merchant_id, sku)
);

CREATE TABLE IF NOT EXISTS schemas (
    merchant_id     TEXT NOT NULL,
    category        TEXT NOT NULL,
    required        TEXT NOT NULL,
    PRIMARY KEY (merchant_id, category)
);

CREATE TABLE IF NOT EXISTS interventions (
    merchant_id     TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    journey_id      TEXT NOT NULL,
    intervention_id TEXT NOT NULL,
    concession      REAL NOT NULL DEFAULT 0,
    mandate_retry   INTEGER NOT NULL DEFAULT 0,
    ts              REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS interventions_agent ON interventions (merchant_id, agent_id, ts);

CREATE TABLE IF NOT EXISTS declines (
    merchant_id     TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    ts              REAL NOT NULL,
    PRIMARY KEY (merchant_id, agent_id)
);

CREATE TABLE IF NOT EXISTS reoffers (
    merchant_id     TEXT NOT NULL,
    journey_id      TEXT NOT NULL,
    offer_id        TEXT NOT NULL,
    offer           TEXT NOT NULL,
    created_at      REAL NOT NULL,
    expires_at      REAL NOT NULL,
    fetched_at      REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (merchant_id, journey_id)
);

CREATE TABLE IF NOT EXISTS live_ledger (
    merchant_id     TEXT NOT NULL,
    seq             INTEGER NOT NULL,
    entry_id        TEXT NOT NULL,
    journey_id      TEXT,
    prev_hash       TEXT NOT NULL,
    hash            TEXT NOT NULL,
    payload         TEXT NOT NULL,
    PRIMARY KEY (merchant_id, seq)
);
CREATE INDEX IF NOT EXISTS live_ledger_journey ON live_ledger (merchant_id, journey_id);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id     TEXT PRIMARY KEY,
    merchant_id     TEXT NOT NULL,
    journey_id      TEXT NOT NULL DEFAULT '',
    event           TEXT NOT NULL,
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL,        -- pending|delivered|failed|skipped
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL,
    last_error      TEXT NOT NULL DEFAULT '',
    response_status INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    delivered_at    REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS deliveries_due ON deliveries (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS deliveries_journey ON deliveries (merchant_id, journey_id);
"""

_init_lock = threading.Lock()
_initialised = set()
_ledger_lock = threading.Lock()


def db_path():
    return os.environ.get("HS_LIVE_DB") or os.environ.get("HS_DB") or _SIM_PATH


@contextmanager
def connect(path=None):
    path = path or db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        if path not in _initialised:
            with _init_lock:
                conn.executescript(SCHEMA)
                _initialised.add(path)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _j(value):
    return json.dumps(value, default=str, separators=(",", ":"))


def _row(row, json_fields=()):
    if row is None:
        return None
    out = dict(row)
    for name in json_fields:
        if name in out and isinstance(out[name], str):
            out[name] = json.loads(out[name] or "{}")
    return out


# ------------------------------------------------------------- merchants ----

def hash_key(api_key):
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_merchant(name, webhook_url="", policy=None, settings=None, sandbox=False,
                    merchant_id=None):
    """Returns (merchant, api_key). The key is shown once and stored hashed."""
    merchant_id = merchant_id or f"m_{uuid.uuid4().hex[:12]}"
    api_key = f"hsk_{'test' if sandbox else 'live'}_{secrets.token_hex(20)}"
    secret = f"whsec_{secrets.token_hex(24)}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO merchants (merchant_id, name, key_hash, key_prefix, webhook_url,"
            " webhook_secret, policy, settings, sandbox, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (merchant_id, name, hash_key(api_key), api_key[:13], webhook_url, secret,
             _j(policy or {}), _j(settings or {}), 1 if sandbox else 0, time.time()))
    return get_merchant(merchant_id), api_key


def rotate_key(merchant_id):
    api_key = f"hsk_{'test' if get_merchant(merchant_id)['sandbox'] else 'live'}_" \
              f"{secrets.token_hex(20)}"
    with connect() as conn:
        conn.execute("UPDATE merchants SET key_hash=?, key_prefix=? WHERE merchant_id=?",
                     (hash_key(api_key), api_key[:13], merchant_id))
    return api_key


def merchant_by_key(api_key):
    if not api_key:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM merchants WHERE key_hash = ?",
                           (hash_key(api_key),)).fetchone()
    return _row(row, ("policy", "settings"))


def get_merchant(merchant_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM merchants WHERE merchant_id = ?",
                           (merchant_id,)).fetchone()
    return _row(row, ("policy", "settings"))


def update_merchant(merchant_id, **fields):
    allowed = {"name", "webhook_url", "policy", "settings"}
    sets, args = [], []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        sets.append(f"{k} = ?")
        args.append(_j(v) if k in ("policy", "settings") else v)
    if sets:
        with connect() as conn:
            conn.execute(f"UPDATE merchants SET {', '.join(sets)} WHERE merchant_id = ?",
                         args + [merchant_id])
    return get_merchant(merchant_id)


def public_merchant(m):
    """What a merchant may read about itself. Never the key hash."""
    return {"merchant_id": m["merchant_id"], "name": m["name"],
            "key_prefix": m["key_prefix"], "webhook_url": m["webhook_url"],
            "webhook_secret": m["webhook_secret"], "policy": m["policy"],
            "settings": m["settings"], "sandbox": bool(m["sandbox"]),
            "created_at": m["created_at"]}


# -------------------------------------------------------------- journeys ----

JOURNEY_JSON = ("diagnosis", "verdict", "directive")


def get_journey(merchant_id, journey_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM journeys WHERE merchant_id=? AND journey_id=?",
                           (merchant_id, journey_id)).fetchone()
    return _row(row, JOURNEY_JSON)


def journey_by_checkout(merchant_id, checkout_id):
    with connect() as conn:
        row = conn.execute("SELECT journey_id FROM journeys WHERE merchant_id=? AND"
                           " checkout_id=? ORDER BY opened_at DESC LIMIT 1",
                           (merchant_id, checkout_id)).fetchone()
    return row["journey_id"] if row else None


def open_journey_for_agent(merchant_id, agent_id, idle_after):
    with connect() as conn:
        row = conn.execute(
            "SELECT journey_id FROM journeys WHERE merchant_id=? AND agent_id=? AND"
            " status='open' AND last_event_at > ? ORDER BY last_event_at DESC LIMIT 1",
            (merchant_id, agent_id, time.time() - idle_after)).fetchone()
    return row["journey_id"] if row else None


def recovering_journey_for(merchant_id, agent_id, sku, window=86400):
    """Attribution fallback for an agent that comes back without its journey id."""
    with connect() as conn:
        row = conn.execute(
            "SELECT journey_id FROM journeys WHERE merchant_id=? AND agent_id=? AND"
            " status='recovering' AND sku=? AND closed_at > ?"
            " ORDER BY closed_at DESC LIMIT 1",
            (merchant_id, agent_id, sku, time.time() - window)).fetchone()
    return row["journey_id"] if row else None


def create_journey(merchant_id, journey_id, agent_id, principal_id="", ts=None):
    ts = ts or time.time()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO journeys (merchant_id, journey_id, agent_id, principal_id,"
            " status, opened_at, last_event_at) VALUES (?,?,?,?, 'open', ?, ?)",
            (merchant_id, journey_id, agent_id, principal_id, ts, ts))
    return get_journey(merchant_id, journey_id)


def update_journey(merchant_id, journey_id, **fields):
    if not fields:
        return
    sets, args = [], []
    for k, v in fields.items():
        sets.append(f"{k} = ?")
        args.append(_j(v) if k in JOURNEY_JSON else v)
    with connect() as conn:
        conn.execute(f"UPDATE journeys SET {', '.join(sets)} WHERE merchant_id=? AND"
                     " journey_id=?", args + [merchant_id, journey_id])


def list_journeys(merchant_id, status=None, limit=50, offset=0):
    sql = "SELECT * FROM journeys WHERE merchant_id = ?"
    args = [merchant_id]
    if status:
        statuses = [s for s in status.split(",") if s]
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        args += statuses
    sql += " ORDER BY last_event_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row(r, JOURNEY_JSON) for r in rows]


def idle_journeys(now, default_idle):
    """(merchant_id, journey_id, idle_seconds) for every open journey past its idle
    window. Per-merchant idle windows are applied by the caller."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT j.merchant_id, j.journey_id, j.last_event_at, m.settings"
            " FROM journeys j JOIN merchants m ON m.merchant_id = j.merchant_id"
            " WHERE j.status = 'open'").fetchall()
    out = []
    for r in rows:
        idle = json.loads(r["settings"] or "{}").get("idle_seconds", default_idle)
        if now - r["last_event_at"] >= idle:
            out.append((r["merchant_id"], r["journey_id"]))
    return out


def expired_recoveries(now):
    with connect() as conn:
        rows = conn.execute(
            "SELECT j.merchant_id, j.journey_id FROM journeys j JOIN reoffers r"
            " ON r.merchant_id=j.merchant_id AND r.journey_id=j.journey_id"
            " WHERE j.status='recovering' AND r.expires_at < ?", (now,)).fetchall()
    return [(r["merchant_id"], r["journey_id"]) for r in rows]


# ---------------------------------------------------------------- events ----

def insert_event(merchant_id, journey_id, event):
    """Idempotent on (merchant_id, event_id). Returns False for a duplicate."""
    with connect() as conn:
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 s FROM events WHERE"
                           " merchant_id=? AND journey_id=?",
                           (merchant_id, journey_id)).fetchone()["s"]
        cur = conn.execute(
            "INSERT OR IGNORE INTO events (merchant_id, event_id, journey_id, seq, ts, type,"
            " http_status, payload) VALUES (?,?,?,?,?,?,?,?)",
            (merchant_id, event["event_id"], journey_id, seq, event["ts"], event["type"],
             event.get("http_status", 200), _j(event)))
        return cur.rowcount == 1


def event_exists(merchant_id, event_id):
    with connect() as conn:
        row = conn.execute("SELECT journey_id FROM events WHERE merchant_id=? AND"
                           " event_id=?", (merchant_id, event_id)).fetchone()
    return row["journey_id"] if row else None


def journey_events(merchant_id, journey_id):
    with connect() as conn:
        rows = conn.execute("SELECT seq, payload FROM events WHERE merchant_id=? AND"
                            " journey_id=? ORDER BY seq", (merchant_id, journey_id)).fetchall()
    out = []
    for r in rows:
        ev = json.loads(r["payload"])
        ev["seq"] = r["seq"]
        out.append(ev)
    return out


# --------------------------------------------------------------- catalog ----

def put_catalog(merchant_id, products):
    now = time.time()
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO catalog (merchant_id, sku, record, updated_at)"
            " VALUES (?,?,?,?)", [(merchant_id, p["sku"], _j(p), now) for p in products])
    return len(products)


def get_product(merchant_id, sku):
    with connect() as conn:
        row = conn.execute("SELECT record FROM catalog WHERE merchant_id=? AND sku=?",
                           (merchant_id, sku)).fetchone()
    return json.loads(row["record"]) if row else None


def catalog(merchant_id):
    with connect() as conn:
        rows = conn.execute("SELECT record FROM catalog WHERE merchant_id=?",
                            (merchant_id,)).fetchall()
    return [json.loads(r["record"]) for r in rows]


def put_schema(merchant_id, schema):
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO schemas (merchant_id, category, required) VALUES (?,?,?)",
            [(merchant_id, cat, _j(list(req))) for cat, req in schema.items()])
    return get_schema(merchant_id)


def get_schema(merchant_id):
    with connect() as conn:
        rows = conn.execute("SELECT category, required FROM schemas WHERE merchant_id=?",
                            (merchant_id,)).fetchall()
    return {r["category"]: json.loads(r["required"]) for r in rows}


# ------------------------------------------------ buyer history for policy ----

def record_intervention(merchant_id, agent_id, journey_id, intervention_id, concession=0.0,
                        mandate_retry=False):
    with connect() as conn:
        conn.execute(
            "INSERT INTO interventions (merchant_id, agent_id, journey_id, intervention_id,"
            " concession, mandate_retry, ts) VALUES (?,?,?,?,?,?,?)",
            (merchant_id, agent_id, journey_id, intervention_id, concession,
             1 if mandate_retry else 0, time.time()))


def record_decline(merchant_id, agent_id):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO declines (merchant_id, agent_id, ts)"
                     " VALUES (?,?,?)", (merchant_id, agent_id, time.time()))


def buyer_history(merchant_id, agent_id, journey_id, window=86400):
    since = time.time() - window
    with connect() as conn:
        iv = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(concession),0) c,"
            " COALESCE(SUM(mandate_retry),0) mr FROM interventions"
            " WHERE merchant_id=? AND agent_id=? AND ts > ?",
            (merchant_id, agent_id, since)).fetchone()
        jc = conn.execute(
            "SELECT COALESCE(SUM(concession),0) c, COALESCE(SUM(mandate_retry),0) mr"
            " FROM interventions WHERE merchant_id=? AND journey_id=?",
            (merchant_id, journey_id)).fetchone()
        ab = conn.execute(
            "SELECT COUNT(*) n FROM journeys WHERE merchant_id=? AND agent_id=? AND"
            " journey_id != ? AND opened_at > ? AND status IN"
            " ('abandoned','recovering','recovered','lost','exception')",
            (merchant_id, agent_id, journey_id, since)).fetchone()
        dec = conn.execute("SELECT 1 FROM declines WHERE merchant_id=? AND agent_id=?",
                           (merchant_id, agent_id)).fetchone()
    return {"interventions_24h": iv["n"], "concession_24h": iv["c"],
            "journey_concession": jc["c"], "mandate_retries": jc["mr"],
            "abandonments_24h": ab["n"], "declined": dec is not None}


# -------------------------------------------------------------- reoffers ----

def put_reoffer(merchant_id, journey_id, offer, ttl_seconds):
    offer_id = f"ro_{uuid.uuid4().hex[:14]}"
    now = time.time()
    offer = dict(offer, offer_id=offer_id, expires_at=now + ttl_seconds)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reoffers (merchant_id, journey_id, offer_id, offer,"
            " created_at, expires_at) VALUES (?,?,?,?,?,?)",
            (merchant_id, journey_id, offer_id, _j(offer), now, now + ttl_seconds))
    return offer


def get_reoffer(merchant_id, journey_id, mark_fetched=True):
    with connect() as conn:
        row = conn.execute("SELECT * FROM reoffers WHERE merchant_id=? AND journey_id=?",
                           (merchant_id, journey_id)).fetchone()
        if row and mark_fetched and not row["fetched_at"]:
            conn.execute("UPDATE reoffers SET fetched_at=? WHERE merchant_id=? AND"
                         " journey_id=?", (time.time(), merchant_id, journey_id))
    if row is None:
        return None
    out = json.loads(row["offer"])
    out["fetched_at"] = row["fetched_at"] or (time.time() if mark_fetched else 0)
    out["expired"] = row["expires_at"] < time.time()
    return out


# ---------------------------------------------------------------- ledger ----

def _digest(payload, prev_hash):
    # Identical to ledger.chain.Ledger._digest, so one verifier reads both.
    blob = json.dumps(payload, sort_keys=True, default=str) + prev_hash
    return hashlib.sha256(blob.encode()).hexdigest()


def ledger_append(merchant_id, journey_id, actor, action, **body):
    payload = {"entry_id": f"ae_{uuid.uuid4().hex[:16]}", "ts": time.time(),
               "merchant_id": merchant_id, "session_id": journey_id,
               "actor": actor, "action": action}
    for key in ("trigger", "diagnosis", "policy_checks", "outcome", "reversal"):
        payload[key] = body.get(key) or ({} if key != "policy_checks" else [])
    # One writer at a time per process; BEGIN IMMEDIATE serialises across
    # processes, so two writers can never read the same predecessor hash.
    with _ledger_lock, connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        last = conn.execute("SELECT seq, hash FROM live_ledger WHERE merchant_id=?"
                            " ORDER BY seq DESC LIMIT 1", (merchant_id,)).fetchone()
        seq = (last["seq"] + 1) if last else 0
        prev = last["hash"] if last else "0" * 64
        entry = dict(payload, prev_hash=prev, hash=_digest(payload, prev))
        conn.execute("INSERT INTO live_ledger (merchant_id, seq, entry_id, journey_id,"
                     " prev_hash, hash, payload) VALUES (?,?,?,?,?,?,?)",
                     (merchant_id, seq, entry["entry_id"], journey_id, prev, entry["hash"],
                      _j(entry)))
    return entry


def ledger(merchant_id, journey_id=None, limit=None):
    sql = "SELECT payload FROM live_ledger WHERE merchant_id=?"
    args = [merchant_id]
    if journey_id:
        sql += " AND journey_id=?"
        args.append(journey_id)
    sql += " ORDER BY seq"
    if limit:
        sql += " LIMIT ?"
        args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def verify_ledger(merchant_id):
    prev = "0" * 64
    entries = ledger(merchant_id)
    for i, entry in enumerate(entries):
        payload = {k: v for k, v in entry.items() if k not in ("prev_hash", "hash")}
        if entry["prev_hash"] != prev or entry["hash"] != _digest(payload, prev):
            return {"valid": False, "entries": len(entries), "first_bad": i}
        prev = entry["hash"]
    return {"valid": True, "entries": len(entries), "first_bad": -1, "head": prev}


# ------------------------------------------------------------ deliveries ----

def enqueue_delivery(merchant_id, journey_id, event, payload):
    delivery_id = f"wh_{uuid.uuid4().hex[:16]}"
    now = time.time()
    with connect() as conn:
        conn.execute(
            "INSERT INTO deliveries (delivery_id, merchant_id, journey_id, event, payload,"
            " status, next_attempt_at, created_at) VALUES (?,?,?,?,?, 'pending', ?, ?)",
            (delivery_id, merchant_id, journey_id, event, _j(payload), now, now))
    return delivery_id


def due_deliveries(now, limit=25):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM deliveries WHERE status='pending' AND"
                            " next_attempt_at <= ? ORDER BY next_attempt_at LIMIT ?",
                            (now, limit)).fetchall()
    return [_row(r, ("payload",)) for r in rows]


def mark_delivery(delivery_id, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE deliveries SET {sets} WHERE delivery_id = ?",
                     list(fields.values()) + [delivery_id])


def deliveries(merchant_id, journey_id=None, limit=50):
    sql = "SELECT * FROM deliveries WHERE merchant_id=?"
    args = [merchant_id]
    if journey_id:
        sql += " AND journey_id=?"
        args.append(journey_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row(r, ("payload",)) for r in rows]


# --------------------------------------------------------------- metrics ----

def metrics(merchant_id, since=0.0):
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, basket_value, recovered_value, concession, diagnosis, verdict"
            " FROM journeys WHERE merchant_id=? AND opened_at >= ?",
            (merchant_id, since)).fetchall()
        dl = conn.execute("SELECT status, COUNT(*) n FROM deliveries WHERE merchant_id=?"
                          " GROUP BY status", (merchant_id,)).fetchall()
    out = {"journeys": len(rows), "open": 0, "converted": 0, "converted_value": 0.0,
           "abandoned": 0, "at_risk_value": 0.0, "recovering": 0, "recovered": 0,
           "recovered_value": 0.0, "lost": 0, "exceptions": 0, "concession": 0.0,
           "by_cause": {}, "refusals": {}, "interventions": {},
           "webhooks": {r["status"]: r["n"] for r in dl}}
    for r in rows:
        st = r["status"]
        if st == "open":
            out["open"] += 1
            continue
        if st == "converted":
            out["converted"] += 1
            out["converted_value"] += r["basket_value"]
            continue
        out["abandoned"] += 1
        out["at_risk_value"] += r["basket_value"]
        out["concession"] += r["concession"]
        if st in ("recovering", "recovered", "lost", "exception"):
            out[{"recovering": "recovering", "recovered": "recovered", "lost": "lost",
                 "exception": "exceptions"}[st]] += 1
        if st == "recovered":
            out["recovered_value"] += r["recovered_value"]
        dg = json.loads(r["diagnosis"] or "{}")
        cause = dg.get("cause") or "UNKNOWN"
        row = out["by_cause"].setdefault(cause, {"name": dg.get("name", ""), "count": 0,
                                                 "at_risk": 0.0, "recovered": 0.0})
        row["count"] += 1
        row["at_risk"] += r["basket_value"]
        row["recovered"] += r["recovered_value"] if st == "recovered" else 0.0
        vd = json.loads(r["verdict"] or "{}")
        if vd and not vd.get("permitted", True):
            rule = vd.get("binding_rule", "?")
            out["refusals"][rule] = out["refusals"].get(rule, 0) + 1
        elif vd.get("intervention_id"):
            iid = vd["intervention_id"]
            out["interventions"][iid] = out["interventions"].get(iid, 0) + 1
    out["recovery_rate"] = (round(out["recovered_value"] / out["at_risk_value"], 4)
                            if out["at_risk_value"] else 0.0)
    for k in ("converted_value", "at_risk_value", "recovered_value", "concession"):
        out[k] = round(out[k], 2)
    return out
