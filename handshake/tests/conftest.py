"""Tests are hermetic.

A .env that switches on live backends must never change what the suite does:
it proves the logic offline and deterministically, and is not a connectivity
check. Use preflight.py for that.

The key variables are blanked rather than left unset, because config loads .env
with setdefault — an unset variable would still be filled from the file, and a
real key would join the pool a test thought it controlled.
"""

import os

os.environ["HS_PAYMENTS"] = "sim"
os.environ["HS_BUYERS"] = "heuristic"

for name in ["HS_LLM_API_KEY", "HS_LLM_API_KEYS", "HS_LLM_MODEL",
             "HS_LLM_MODELS", "HS_LLM_PROVIDER", "HS_LLM_BASE_URL"]:
    os.environ[name] = ""
for n in range(2, 10):
    os.environ[f"HS_LLM_API_KEY_{n}"] = ""

# A DATABASE_URL in .env must never point the suite at a real database.
# HS_TEST_DATABASE_URL opts in to running every test against PostgreSQL, each in
# a throwaway schema that is dropped afterwards.
os.environ["DATABASE_URL"] = ""
PG_URL = os.environ.get("HS_TEST_DATABASE_URL", "")

import uuid  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _database(monkeypatch):
    if not PG_URL:
        yield
        return
    import psycopg

    from handshake import database
    schema = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    sep = "&" if "?" in PG_URL else "?"
    monkeypatch.setenv("DATABASE_URL", f"{PG_URL}{sep}options=-csearch_path%3D{schema}")
    try:
        yield
    finally:
        database.close_all()
        with psycopg.connect(PG_URL, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
