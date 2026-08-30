"""Audit ledger (component C7).

Append-only and hash-chained: each entry carries the hash of its predecessor,
so a retroactive edit is detectable. There is no update or delete path.
Refusals are recorded with the same standing as permits — they are the evidence
that the gate exists.
"""

import hashlib
import json
import time
import uuid


class Ledger:
    def __init__(self):
        self.entries = []
        self._last_hash = "0" * 64

    @staticmethod
    def _digest(payload, prev_hash):
        blob = json.dumps(payload, sort_keys=True, default=str) + prev_hash
        return hashlib.sha256(blob.encode()).hexdigest()

    def append(self, session_id, actor, action, trigger=None, diagnosis=None,
               policy_checks=None, outcome=None, reversal=None):
        payload = {
            "entry_id": f"ae_{uuid.uuid4().hex[:16]}",
            "ts": time.time(),
            "session_id": session_id,
            "actor": actor,
            "action": action,
            "trigger": trigger or {},
            "diagnosis": diagnosis or {},
            "policy_checks": policy_checks or [],
            "outcome": outcome or {},
            "reversal": reversal or {},
        }
        entry = dict(payload)
        entry["prev_hash"] = self._last_hash
        entry["hash"] = self._digest(payload, self._last_hash)
        self._last_hash = entry["hash"]
        self.entries.append(entry)
        return entry

    def verify(self):
        """Recompute the chain. Returns (ok, index_of_first_bad_entry)."""
        prev = "0" * 64
        for i, entry in enumerate(self.entries):
            payload = {k: v for k, v in entry.items() if k not in ("prev_hash", "hash")}
            if entry["prev_hash"] != prev or entry["hash"] != self._digest(payload, prev):
                return False, i
            prev = entry["hash"]
        return True, -1

    def for_session(self, session_id):
        return [e for e in self.entries if e["session_id"] == session_id]

    def export_jsonl(self, path):
        with open(path, "w") as fh:
            for entry in self.entries:
                fh.write(json.dumps(entry, default=str) + "\n")
        return path
