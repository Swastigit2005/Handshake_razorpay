"""One database layer for every store in Handshake.

    DATABASE_URL=postgresql://user:pass@host:5432/handshake   → PostgreSQL (production)
    unset                                                     → SQLite file (local, tests)

Callers write SQL once, with `?` placeholders and standard `ON CONFLICT` /
`RETURNING` (SQLite ≥ 3.35 and PostgreSQL both accept them); the PostgreSQL
connection rewrites placeholders to `%s`. Rows come back as mappings on both.

PostgreSQL connections come from a pool (psycopg 3). Each `connect()` block is
one transaction: committed on success, rolled back on any exception.

`conn.lock(key)` serialises writers on a key for the rest of the transaction —
`pg_advisory_xact_lock` on PostgreSQL, `BEGIN IMMEDIATE` (a database-wide write
lock) on SQLite. The ledger uses it so two replicas can never chain onto the
same predecessor hash.

Schema changes are versioned migrations, applied once per database under a
lock, recorded in `schema_migrations`. Never edit an applied migration: add one.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager

DEFAULT_SQLITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "handshake.db")

# ------------------------------------------------------------- migrations ---
# {JSON}  → JSONB on PostgreSQL, TEXT on SQLite (queryable documents)
# {FLOAT} → DOUBLE PRECISION / REAL
# Ledger payloads stay TEXT on both: the hash is over exact bytes, and evidence
# should come back byte for byte as it was written.

MIGRATIONS = [
    (1, "simulation store", """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    created_at  {FLOAT} NOT NULL,
    label       TEXT,
    sessions    INTEGER,
    seed        BIGINT,
    payments    TEXT,
    buyers      TEXT,
    measured    INTEGER NOT NULL DEFAULT 1,
    summary     TEXT NOT NULL
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
"""),
    (2, "live plane", """
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,
    key_prefix      TEXT NOT NULL,
    webhook_url     TEXT NOT NULL DEFAULT '',
    webhook_secret  TEXT NOT NULL,
    policy          {JSON} NOT NULL DEFAULT '{}',
    settings        {JSON} NOT NULL DEFAULT '{}',
    sandbox         INTEGER NOT NULL DEFAULT 0,
    created_at      {FLOAT} NOT NULL
);
CREATE TABLE IF NOT EXISTS journeys (
    merchant_id     TEXT NOT NULL REFERENCES merchants (merchant_id) ON DELETE CASCADE,
    journey_id      TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    principal_id    TEXT NOT NULL DEFAULT '',
    checkout_id     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL,
    stage           TEXT NOT NULL DEFAULT 'discovery',
    sku             TEXT NOT NULL DEFAULT '',
    basket_value    {FLOAT} NOT NULL DEFAULT 0,
    recovered_value {FLOAT} NOT NULL DEFAULT 0,
    concession      {FLOAT} NOT NULL DEFAULT 0,
    opened_at       {FLOAT} NOT NULL,
    last_event_at   {FLOAT} NOT NULL,
    closed_at       {FLOAT} NOT NULL DEFAULT 0,
    close_reason    TEXT NOT NULL DEFAULT '',
    attempts        INTEGER NOT NULL DEFAULT 0,
    diagnosis       {JSON} NOT NULL DEFAULT '{}',
    verdict         {JSON} NOT NULL DEFAULT '{}',
    directive       {JSON} NOT NULL DEFAULT '{}',
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
    ts              {FLOAT} NOT NULL,
    type            TEXT NOT NULL,
    http_status     INTEGER NOT NULL DEFAULT 200,
    payload         {JSON} NOT NULL,
    PRIMARY KEY (merchant_id, event_id)
);
CREATE INDEX IF NOT EXISTS events_journey ON events (merchant_id, journey_id, seq);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE TABLE IF NOT EXISTS catalog (
    merchant_id     TEXT NOT NULL,
    sku             TEXT NOT NULL,
    record          {JSON} NOT NULL,
    updated_at      {FLOAT} NOT NULL,
    PRIMARY KEY (merchant_id, sku)
);
CREATE TABLE IF NOT EXISTS schemas (
    merchant_id     TEXT NOT NULL,
    category        TEXT NOT NULL,
    required        {JSON} NOT NULL,
    PRIMARY KEY (merchant_id, category)
);
CREATE TABLE IF NOT EXISTS interventions (
    merchant_id     TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    journey_id      TEXT NOT NULL,
    intervention_id TEXT NOT NULL,
    concession      {FLOAT} NOT NULL DEFAULT 0,
    mandate_retry   INTEGER NOT NULL DEFAULT 0,
    ts              {FLOAT} NOT NULL
);
CREATE INDEX IF NOT EXISTS interventions_agent ON interventions (merchant_id, agent_id, ts);
CREATE INDEX IF NOT EXISTS interventions_journey ON interventions (merchant_id, journey_id);
CREATE TABLE IF NOT EXISTS declines (
    merchant_id     TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    ts              {FLOAT} NOT NULL,
    PRIMARY KEY (merchant_id, agent_id)
);
CREATE TABLE IF NOT EXISTS reoffers (
    merchant_id     TEXT NOT NULL,
    journey_id      TEXT NOT NULL,
    offer_id        TEXT NOT NULL,
    offer           {JSON} NOT NULL,
    created_at      {FLOAT} NOT NULL,
    expires_at      {FLOAT} NOT NULL,
    fetched_at      {FLOAT} NOT NULL DEFAULT 0,
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
    payload         {JSON} NOT NULL,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at {FLOAT} NOT NULL,
    last_error      TEXT NOT NULL DEFAULT '',
    response_status INTEGER NOT NULL DEFAULT 0,
    created_at      {FLOAT} NOT NULL,
    delivered_at    {FLOAT} NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS deliveries_due ON deliveries (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS deliveries_journey ON deliveries (merchant_id, journey_id);
"""),
    (3, "re-offers are consumed once acted on", """
ALTER TABLE reoffers ADD COLUMN consumed_at {FLOAT} NOT NULL DEFAULT 0
"""),
]

TYPES = {"postgres": {"JSON": "JSONB", "FLOAT": "DOUBLE PRECISION"},
         "sqlite": {"JSON": "TEXT", "FLOAT": "REAL"}}


def target(explicit=None):
    """The database to use: an explicit path or URL, then DATABASE_URL, then the
    SQLite path from HS_LIVE_DB / HS_DB, then the default file."""
    return (explicit or os.environ.get("DATABASE_URL") or os.environ.get("HS_LIVE_DB")
            or os.environ.get("HS_DB") or DEFAULT_SQLITE)


def dialect_of(t):
    return "postgres" if t.startswith(("postgres://", "postgresql://")) else "sqlite"


def describe(t=None):
    """Where the data lives, safe to print: no password."""
    t = target(t)
    if dialect_of(t) == "sqlite":
        return f"sqlite:{t}"
    from urllib.parse import urlsplit
    u = urlsplit(t)
    host = u.hostname or "localhost"
    return f"postgresql://{u.username + '@' if u.username else ''}{host}" \
           f"{':' + str(u.port) if u.port else ''}{u.path}"


def load(value, default=None):
    """JSON columns come back parsed from PostgreSQL and as text from SQLite."""
    if value is None or value == "":
        return {} if default is None else default
    return json.loads(value) if isinstance(value, (str, bytes)) else value


# ------------------------------------------------------------- connection ---

class Conn:
    def __init__(self, raw, dialect):
        self.raw = raw
        self.dialect = dialect
        self._locked = False

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    def execute(self, sql, args=()):
        return self.raw.execute(self._sql(sql), tuple(args))

    def executemany(self, sql, rows):
        rows = [tuple(r) for r in rows]
        if not rows:
            return None
        if self.dialect == "postgres":
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), rows)
            return None
        return self.raw.executemany(sql, rows)

    def lock(self, key):
        if self.dialect == "postgres":
            self.raw.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
        elif not self._locked:
            if self.raw.in_transaction:
                self.raw.commit()
            self.raw.execute("BEGIN IMMEDIATE")
            self._locked = True

    def skip_locked(self):
        """Suffix for a claim query: rows another replica holds are skipped."""
        return " FOR UPDATE SKIP LOCKED" if self.dialect == "postgres" else ""


_pools = {}
_migrated = set()
_lock = threading.Lock()


def _pool(url):
    pool = _pools.get(url)
    if pool is None:
        with _lock:
            pool = _pools.get(url)
            if pool is None:
                try:
                    from psycopg.rows import dict_row
                    from psycopg_pool import ConnectionPool
                except ImportError as exc:                   # pragma: no cover
                    raise RuntimeError("DATABASE_URL is PostgreSQL but psycopg is not "
                                       "installed: pip install '.[postgres]'") from exc
                pool = ConnectionPool(
                    url, min_size=int(os.environ.get("HS_DB_POOL_MIN", "1")),
                    max_size=int(os.environ.get("HS_DB_POOL_MAX", "10")),
                    timeout=float(os.environ.get("HS_DB_POOL_TIMEOUT", "10")),
                    kwargs={"row_factory": dict_row, "autocommit": False},
                    check=ConnectionPool.check_connection, open=True,
                    name="handshake")
                _pools[url] = pool
    return pool


def _migrate(conn):
    conn.lock("handshake:migrations")
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY,"
                 " name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    types = TYPES[conn.dialect]
    for version, name, sql in MIGRATIONS:
        if version in done:
            continue
        for key, value in types.items():
            sql = sql.replace("{" + key + "}", value)
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES"
                     " (?, ?, CURRENT_TIMESTAMP)", (version, name))


@contextmanager
def connect(explicit=None):
    """One transaction. Commits on success, rolls back on any exception."""
    t = target(explicit)
    dialect = dialect_of(t)
    if dialect == "postgres":
        with _pool(t).connection() as raw:       # commits / rolls back on exit
            conn = Conn(raw, dialect)
            if t not in _migrated:
                _migrate(conn)
                raw.commit()
                conn = Conn(raw, dialect)
                _migrated.add(t)
            yield conn
        return

    os.makedirs(os.path.dirname(os.path.abspath(t)), exist_ok=True)
    raw = sqlite3.connect(t, timeout=15)
    raw.row_factory = sqlite3.Row
    try:
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA busy_timeout=15000")
        raw.execute("PRAGMA foreign_keys=ON")
        conn = Conn(raw, dialect)
        if t not in _migrated:
            with _lock:
                _migrate(conn)
                raw.commit()
                _migrated.add(t)
            conn = Conn(raw, dialect)
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def ping(explicit=None):
    """Readiness: can we run a query right now?"""
    with connect(explicit) as conn:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return {"database": describe(explicit), "dialect": dialect_of(target(explicit)),
            "schema_version": row["v"]}


def close_all():
    """Close every pool. Called on shutdown and between tests."""
    with _lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()
        _migrated.clear()
