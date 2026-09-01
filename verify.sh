#!/usr/bin/env bash
# Everything a reviewer should be able to reproduce, in one command.
#
# This forces the OFFLINE backends. That is deliberate:
#   · it is a reproducibility check, not a connectivity check — use
#     preflight.py for that;
#   · the reproducibility assertion requires bit-identical runs, which no
#     hosted model guarantees;
#   · a full pass is ~1,700 buyer decisions, and burning a day's LLM quota to
#     re-verify a hash chain is a waste of money.
#
# For a live-backend run, use:  ./run.sh 500
set -e
cd "$(dirname "$0")"

export HS_PAYMENTS=sim
export HS_BUYERS=heuristic

echo "== backends (forced offline for reproducibility) =="
python3 -c "
import sys; sys.path.insert(0,'.')
from handshake.config import RunConfig
c = RunConfig(); print(f'  payments={c.payments_backend}  buyers={c.buyer_backend}')"

echo
echo "== tests =="
python3 -m pytest handshake/tests -q

echo
echo "== recovery batch (500 sessions) =="
python3 -m handshake.experiments.run --sessions 500 --tag verify

echo
echo "== readiness scan (300 probes) =="
python3 -m handshake.readiness.run --sessions 300 --tag verify

echo
echo "== kill switch (R-11): no money action may execute =="
python3 -m handshake.experiments.run --sessions 200 --kill-switch --tag killswitch \
  | grep -A4 "POLICY REFUSALS"

echo
echo "== audit chain, verified independently of the code that wrote it =="
python3 - <<'PY'
import json, hashlib
entries = [json.loads(l) for l in open("runs/batch_verify_ledger.jsonl")]
prev = "0" * 64
for i, e in enumerate(entries):
    payload = {k: v for k, v in e.items() if k not in ("prev_hash", "hash")}
    blob = json.dumps(payload, sort_keys=True, default=str) + prev
    assert e["prev_hash"] == prev and e["hash"] == hashlib.sha256(blob.encode()).hexdigest(), i
    prev = e["hash"]
print(f"chain verified over {len(entries)} entries")
PY

echo
echo "== reproducibility: the same seed must give the same money =="
python3 - <<'PY'
import json, subprocess, sys
a = json.load(open("runs/batch_verify_summary.json"))
subprocess.run([sys.executable, "-m", "handshake.experiments.run",
                "--sessions", "500", "--tag", "verify2"],
               check=True, stdout=subprocess.DEVNULL)
b = json.load(open("runs/batch_verify2_summary.json"))
x = a["arms"]["treatment"]["recovered_gmv"]; y = b["arms"]["treatment"]["recovered_gmv"]
assert x == y, f"not reproducible: {x} vs {y}"
print(f"reproduced to the rupee: {x}")
PY

echo
echo "== credentials =="
python3 pre_push_check.py || true

echo
echo "open runs/batch_verify_console.html, or ./run_ui.sh for the live console."
