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
