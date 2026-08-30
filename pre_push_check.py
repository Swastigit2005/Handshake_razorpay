#!/usr/bin/env python3
"""Run before pushing. A leaked key is the one unrecoverable mistake here.

Scans every file git would publish for credential patterns, confirms .env is
ignored, and refuses if anything looks like a real secret.
"""

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    ("Groq key", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("OpenAI key", re.compile(r"sk-(?!ant-)[A-Za-z0-9]{20,}")),
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")),
    ("Razorpay live key", re.compile(r"rzp_live_[A-Za-z0-9]{8,}")),
    ("Razorpay test key", re.compile(r"rzp_test_[A-Za-z0-9]{8,}")),
    ("Razorpay secret", re.compile(r"RAZORPAY_KEY_SECRET\s*=\s*[A-Za-z0-9]{8,}")),
]
ALLOW = {"pre_push_check.py", ".env.example", "README.md",
         "handshake/tests/test_llm_pool.py", "handshake/buyers/llm.py",
         "handshake/config.py", "preflight.py",
         "handshake/payments/adapter.py"}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"],
                             capture_output=True, text=True, check=True).stdout
        return [Path(p) for p in out.splitlines() if p]
    except Exception:
        return [p for p in Path(".").rglob("*")
                if p.is_file() and "__pycache__" not in str(p)
                and not str(p).startswith(".git/")]


def main():
    findings = []
    files = tracked_files()

    for path in files:
        if path.name == ".env":
            findings.append((str(path), "the .env file itself would be published"))
            continue
        if str(path) in ALLOW or path.suffix in (".pyc",):
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        for label, pattern in PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append((str(path), f"{label}: {match.group(0)[:12]}…"))

    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"],
                             capture_output=True).returncode == 0
    print(f"scanned {len(files)} file(s) git would publish")
    print(f".env ignored by git: {'yes' if ignored else 'NO'}")
    if not ignored and Path(".env").exists():
        findings.append((".env", "present and NOT ignored"))

    if findings:
        print("\nREFUSING TO PASS — credentials found:")
        for where, what in findings:
            print(f"  {where}: {what}")
        print("\nRemove them, and if a key was ever committed, rotate it. "
              "Deleting a file does not remove it from git history.\n")
        return 1
    print("\nclean — no credentials in anything git would publish\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
