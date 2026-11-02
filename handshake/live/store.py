"""Tenant-scoped persistence for the live plane.

Every table carries `merchant_id`, and every query here filters on it, except
the sweeper's scans for idle journeys and due webhooks, which return ids only.

Runs on PostgreSQL in production and SQLite locally, through
`handshake.database`. Everything that several replicas might race on is a
single conditional statement or holds an advisory lock:

  closing a journey      UPDATE … WHERE status IN (…) RETURNING  — one winner
  expiring a re-offer    UPDATE … WHERE status = 'recovering' RETURNING
  claiming a webhook     SELECT … FOR UPDATE SKIP LOCKED, leased
  appending to a ledger  advisory lock per merchant
  numbering events       advisory lock per journey

So any number of API processes and workers can run against one database.
"""

import hashlib
import json
import secrets
import time
import uuid

from ..database import connect, load
from ..database import target as _target

JOURNEY_JSON = ("diagnosis", "verdict", "directive")


def db_path():
    return _target()


def _j(value):
    return json.dumps(value, default=str, separators=(",", ":"))


def _row(row, json_fields=()):
    if row is None:
        return None
    out = dict(row)
    for name in json_fields:
        if name in out:
            out[name] = load(out[name])
    return out


# ------------------------------------------------------------- merchants ---

def hash_key(api_key):
    return hashlib.sha256(api_key.encode()).hexdigest()


def _new_key(sandbox):
    return f"hsk_{'test' if sandbox else 'live'}_{secrets.token_hex(20)}"


def create_merchant(name, webhook_url="", policy=None, settings=None, sandbox=False,
                    merchant_id=None):
    """Returns (merchant, api_key). The key is shown once and stored hashed."""
    merchant_id = merchant_id or f"m_{uuid.uuid4().hex[:12]}"
    api_key = _new_key(sandbox)
    with connect() as conn:
        conn.execute(
            "INSERT INTO merchants (merchant_id, name, key_hash, key_prefix, webhook_url,"
            " webhook_secret, policy, settings, sandbox, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (merchant_id, name, hash_key(api_key), api_key[:13], webhook_url,
             f"whsec_{secrets.token_hex(24)}", _j(policy or {}), _j(settings or {}),
             1 if sandbox else 0, time.time()))
    return get_merchant(merchant_id), api_key


def rotate_key(merchant_id):
    api_key = _new_key(get_merchant(merchant_id)["sandbox"])
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


# -------------------------------------------------------------- journeys ---

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
            "INSERT INTO journeys (merchant_id, journey_id, agent_id, principal_id,"
            " status, opened_at, last_event_at) VALUES (?,?,?,?, 'open', ?, ?)"
            " ON CONFLICT (merchant_id, journey_id) DO NOTHING",
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


def transition(merchant_id, journey_id, from_statuses, to_status, **fields):
    """Atomically move a journey between states. Returns the journey if this
    caller won, None if the journey was not in `from_statuses` — another
    replica already moved it, or it was never eligible."""
    sets = ["status = ?"] + [f"{k} = ?" for k in fields]
    args = [to_status] + [(_j(v) if k in JOURNEY_JSON else v) for k, v in fields.items()]
    marks = ",".join("?" * len(from_statuses))
    with connect() as conn:
        row = conn.execute(
            f"UPDATE journeys SET {', '.join(sets)} WHERE merchant_id=? AND journey_id=?"
            f" AND status IN ({marks}) RETURNING *",
            args + [merchant_id, journey_id] + list(from_statuses)).fetchone()
    return _row(row, JOURNEY_JSON)


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
    """(merchant_id, journey_id, status) for every journey that went quiet past
    its merchant's idle window: open journeys, and recovering ones where the agent
    took the re-offer, shopped again, and then went silent — a second stop that
    needs its own diagnosis. Eligibility only; `transition` decides who closes it."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT j.merchant_id, j.journey_id, j.status, j.last_event_at, m.settings"
            " FROM journeys j JOIN merchants m ON m.merchant_id = j.merchant_id"
            " WHERE j.last_event_at < ? AND (j.status = 'open' OR"
            " (j.status = 'recovering' AND j.last_event_at > j.closed_at))",
            (now - 1,)).fetchall()
    out = []
    for r in rows:
        idle = load(r["settings"]).get("idle_seconds", default_idle)
        if now - r["last_event_at"] >= idle:
            out.append((r["merchant_id"], r["journey_id"], r["status"]))
    return out


def expire_recoveries(now):
    """Atomically mark recovering journeys whose re-offer lapsed as lost. Each row
    is returned to exactly one caller, however many workers run this."""
    with connect() as conn:
        rows = conn.execute(
            "UPDATE journeys SET status='lost' WHERE status='recovering' AND EXISTS ("
            " SELECT 1 FROM reoffers r WHERE r.merchant_id = journeys.merchant_id"
            " AND r.journey_id = journeys.journey_id AND r.expires_at < ?)"
            " RETURNING merchant_id, journey_id", (now,)).fetchall()
    return [(r["merchant_id"], r["journey_id"]) for r in rows]


# ---------------------------------------------------------------- events ---

def insert_event(merchant_id, journey_id, event):
    """Idempotent on (merchant_id, event_id). Returns False for a duplicate.
    Sequence numbers are allocated under a per-journey lock, so two requests for
    the same journey can never be given the same position."""
    with connect() as conn:
        conn.lock(f"events:{merchant_id}:{journey_id}")
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS s FROM events WHERE"
                           " merchant_id=? AND journey_id=?",
                           (merchant_id, journey_id)).fetchone()["s"]
        cur = conn.execute(
            "INSERT INTO events (merchant_id, event_id, journey_id, seq, ts, type,"
            " http_status, payload) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT (merchant_id, event_id) DO NOTHING",
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
        ev = load(r["payload"])
        ev["seq"] = r["seq"]
        out.append(ev)
    return out


def purge_events(before):
    """Retention: drop raw events older than `before` for journeys that are closed.
    Diagnoses, verdicts and the ledger are kept; they carry the evidence."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM events WHERE ts < ? AND NOT EXISTS (SELECT 1 FROM journeys j"
            " WHERE j.merchant_id = events.merchant_id AND j.journey_id = events.journey_id"
            " AND j.status IN ('open', 'recovering'))", (before,))
        return cur.rowcount


# --------------------------------------------------------------- catalog ----

def put_catalog(merchant_id, products):
    now = time.time()
    with connect() as conn:
        conn.executemany(
            "INSERT INTO catalog (merchant_id, sku, record, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT (merchant_id, sku) DO UPDATE SET record = excluded.record,"
            " updated_at = excluded.updated_at",
            [(merchant_id, p["sku"], _j(p), now) for p in products])
    return len(products)


def get_product(merchant_id, sku):
    with connect() as conn:
        row = conn.execute("SELECT record FROM catalog WHERE merchant_id=? AND sku=?",
                           (merchant_id, sku)).fetchone()
    return load(row["record"]) if row else None


def catalog(merchant_id):
    with connect() as conn:
        rows = conn.execute("SELECT record FROM catalog WHERE merchant_id=? ORDER BY sku",
                            (merchant_id,)).fetchall()
    return [load(r["record"]) for r in rows]


def put_schema(merchant_id, schema):
    with connect() as conn:
        conn.executemany(
            "INSERT INTO schemas (merchant_id, category, required) VALUES (?,?,?)"
            " ON CONFLICT (merchant_id, category) DO UPDATE SET required = excluded.required",
            [(merchant_id, cat, _j(list(req))) for cat, req in schema.items()])
    return get_schema(merchant_id)


def get_schema(merchant_id):
    with connect() as conn:
        rows = conn.execute("SELECT category, required FROM schemas WHERE merchant_id=?",
                            (merchant_id,)).fetchall()
    return {r["category"]: load(r["required"], []) for r in rows}


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
        conn.execute("INSERT INTO declines (merchant_id, agent_id, ts) VALUES (?,?,?)"
                     " ON CONFLICT (merchant_id, agent_id) DO UPDATE SET ts = excluded.ts",
                     (merchant_id, agent_id, time.time()))


def buyer_history(merchant_id, agent_id, journey_id, window=86400):
    since = time.time() - window
    with connect() as conn:
        iv = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(concession),0) AS c FROM interventions"
            " WHERE merchant_id=? AND agent_id=? AND ts > ?",
            (merchant_id, agent_id, since)).fetchone()
        jc = conn.execute(
            "SELECT COALESCE(SUM(mandate_retry),0) AS mr FROM interventions"
            " WHERE merchant_id=? AND journey_id=?", (merchant_id, journey_id)).fetchone()
        ab = conn.execute(
            "SELECT COUNT(*) AS n FROM journeys WHERE merchant_id=? AND agent_id=? AND"
            " journey_id != ? AND opened_at > ? AND status IN"
            " ('abandoned','recovering','recovered','lost','exception')",
            (merchant_id, agent_id, journey_id, since)).fetchone()
        dec = conn.execute("SELECT 1 AS d FROM declines WHERE merchant_id=? AND agent_id=?",
                           (merchant_id, agent_id)).fetchone()
    return {"interventions_24h": int(iv["n"]), "concession_24h": float(iv["c"]),
            "mandate_retries": int(jc["mr"]), "abandonments_24h": int(ab["n"]),
            "declined": dec is not None}


# -------------------------------------------------------------- reoffers ----

def put_reoffer(merchant_id, journey_id, offer, ttl_seconds):
    offer_id = f"ro_{uuid.uuid4().hex[:14]}"
    now = time.time()
    offer = dict(offer, offer_id=offer_id, expires_at=now + ttl_seconds)
    with connect() as conn:
        conn.execute(
            "INSERT INTO reoffers (merchant_id, journey_id, offer_id, offer, created_at,"
            " expires_at, fetched_at) VALUES (?,?,?,?,?,?,0)"
            " ON CONFLICT (merchant_id, journey_id) DO UPDATE SET offer_id = excluded.offer_id,"
            " offer = excluded.offer, created_at = excluded.created_at,"
            " expires_at = excluded.expires_at, fetched_at = 0, consumed_at = 0",
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
    out = load(row["offer"])
    out["fetched_at"] = row["fetched_at"] or (time.time() if mark_fetched else 0)
    out["expired"] = row["expires_at"] < time.time()
    out["consumed"] = bool(row["consumed_at"])
    return out


def consume_reoffer(merchant_id, journey_id):
    """The agent has acted on its offer. It is not served again: if this attempt
    fails too, the next offer comes from a fresh diagnosis, not a repeat."""
    with connect() as conn:
        cur = conn.execute("UPDATE reoffers SET consumed_at=? WHERE merchant_id=? AND"
                           " journey_id=? AND fetched_at > 0 AND consumed_at = 0",
                           (time.time(), merchant_id, journey_id))
        return cur.rowcount == 1


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
    # Round-trip through JSON first so the hash is over exactly what is stored.
    payload = json.loads(json.dumps(payload, default=str))
    with connect() as conn:
        conn.lock(f"ledger:{merchant_id}")
        last = conn.execute("SELECT seq, hash FROM live_ledger WHERE merchant_id=?"
                            " ORDER BY seq DESC LIMIT 1", (merchant_id,)).fetchone()
        seq = (last["seq"] + 1) if last else 0
        prev = last["hash"] if last else "0" * 64
        entry = dict(payload, prev_hash=prev, hash=_digest(payload, prev))
        conn.execute("INSERT INTO live_ledger (merchant_id, seq, entry_id, journey_id,"
                     " prev_hash, hash, payload) VALUES (?,?,?,?,?,?,?)",
                     (merchant_id, seq, entry["entry_id"], journey_id, prev, entry["hash"],
                      json.dumps(entry, default=str)))
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

def enqueue_delivery(merchant_id, journey_id, event, payload, status="pending",
                     last_error=""):
    delivery_id = f"wh_{uuid.uuid4().hex[:16]}"
    now = time.time()
    with connect() as conn:
        conn.execute(
            "INSERT INTO deliveries (delivery_id, merchant_id, journey_id, event, payload,"
            " status, next_attempt_at, created_at, last_error) VALUES (?,?,?,?,?,?,?,?,?)",
            (delivery_id, merchant_id, journey_id or "", event, _j(payload), status, now, now,
             last_error))
    return delivery_id


def claim_deliveries(now, limit=25, lease=60.0):
    """Take up to `limit` due deliveries and push their next attempt `lease`
    seconds out, so a crashed sender's rows come back on their own and no two
    workers send the same row at once."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM deliveries WHERE status='pending' AND next_attempt_at <= ?"
            " ORDER BY next_attempt_at LIMIT ?" + conn.skip_locked(), (now, limit)).fetchall()
        claimed = [_row(r, ("payload",)) for r in rows]
        if claimed:
            marks = ",".join("?" * len(claimed))
            conn.execute(f"UPDATE deliveries SET next_attempt_at = ? WHERE delivery_id IN"
                         f" ({marks})", [now + lease] + [r["delivery_id"] for r in claimed])
    return claimed


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
        dl = conn.execute("SELECT status, COUNT(*) AS n FROM deliveries WHERE merchant_id=?"
                          " GROUP BY status", (merchant_id,)).fetchall()
    out = {"journeys": len(rows), "open": 0, "converted": 0, "converted_value": 0.0,
           "abandoned": 0, "at_risk_value": 0.0, "recovering": 0, "recovered": 0,
           "recovered_value": 0.0, "lost": 0, "exceptions": 0, "concession": 0.0,
           "by_cause": {}, "refusals": {}, "interventions": {},
           "webhooks": {r["status"]: int(r["n"]) for r in dl}}
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
        dg = load(r["diagnosis"])
        cause = dg.get("cause") or "UNKNOWN"
        row = out["by_cause"].setdefault(cause, {"name": dg.get("name", ""), "count": 0,
                                                 "at_risk": 0.0, "recovered": 0.0})
        row["count"] += 1
        row["at_risk"] += r["basket_value"]
        row["recovered"] += r["recovered_value"] if st == "recovered" else 0.0
        vd = load(r["verdict"])
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


def counts():
    """Operator-level totals for /metrics. No tenant data."""
    with connect() as conn:
        j = conn.execute("SELECT status, COUNT(*) AS n FROM journeys GROUP BY status").fetchall()
        d = conn.execute("SELECT status, COUNT(*) AS n FROM deliveries GROUP BY status").fetchall()
        m = conn.execute("SELECT COUNT(*) AS n FROM merchants").fetchone()
        e = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
    return {"journeys": {r["status"]: int(r["n"]) for r in j},
            "deliveries": {r["status"]: int(r["n"]) for r in d},
            "merchants": int(m["n"]), "events": int(e["n"])}
