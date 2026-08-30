#!/usr/bin/env bash
# Full end-to-end check: tests, a batch, the kill switch, and the audit chain.
set -e
cd "$(dirname "$0")"
echo "== tests =="
python3 -m pytest handshake/tests -q
echo
echo "== batch (500 sessions) =="
python3 -m handshake.experiments.run --sessions 500 --tag verify
echo
echo "== kill switch (R-11): no money action may execute =="
python3 -m handshake.experiments.run --sessions 200 --kill-switch --tag killswitch | grep -A3 "POLICY REFUSALS"
echo
echo "== audit chain =="
python3 - <<'PY'
import json, hashlib
entries = [json.loads(l) for l in open("runs/batch_verify_ledger.jsonl")]
prev = "0" * 64
for i, e in enumerate(entries):
    payload = {k: v for k, v in e.items() if k not in ("prev_hash", "hash")}
    blob = json.dumps(payload, sort_keys=True, default=str) + prev
    assert e["prev_hash"] == prev and e["hash"] == hashlib.sha256(blob.encode()).hexdigest(), i
    prev = e["hash"]
print(f"chain verified independently over {len(entries)} entries")
PY
echo
echo "open runs/batch_verify_console.html in a browser for the operator report."
