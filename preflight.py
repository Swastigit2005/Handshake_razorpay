#!/usr/bin/env python3
"""Preflight: prove the live backends actually work before spending a batch on them.

    python3 preflight.py

Checks, in order: the .env file is found, provider resolution, client libraries,
one real model call, one real Razorpay test-mode order. Secrets are masked.
Exits non-zero if anything a live run depends on is broken.
"""

import os
import random
import sys

sys.path.insert(0, ".")

from handshake.buyers.llm import (                     # noqa: E402
    LLMDecider, _parse_decision as _parse)
from handshake.config import DOTENV_PATH, RunConfig    # noqa: E402
from handshake.payments.adapter import build_backend   # noqa: E402

OK, BAD, INFO = "  PASS ", "  FAIL ", "  ---- "

PROBE = ('Shopping agent. Budget 5000, cap 4000 INR. Posture strict '
         '(strict=refuse on any missing detail).\n'
         '{"title":"In-Ear Monitors Pro","price_inr":2499,'
         '"stated":{"driver_mm":12,"battery_hours":30},'
         '"missing":["codec_support"],"policy_machine_readable":true}\n'
         'Proceed to checkout? JSON only: {"proceed":true} or {"proceed":false}')
failures = []


def line(state, label, detail=""):
    print(f"{state} {label}" + (f"  {detail}" if detail else ""))


def mask(v):
    return (v[:9] + "…" + v[-4:]) if len(v) > 14 else ("set" if v else "")


def _suggest_models(decider, endpoint):
    """A rejected model id is worth one extra call: ask what is actually served."""
    try:
        ids = [m.id for m in endpoint.client.models.list().data]
    except Exception as exc:
        line(INFO, "model list", f"could not be fetched ({type(exc).__name__})")
        return
    chat = [i for i in sorted(ids)
            if not any(t in i.lower() for t in
                       ("whisper", "tts", "guard", "orpheus", "embed", "rerank"))]
    line(INFO, "models available to this key", f"{len(chat)} chat models")
    for i in chat:
        print(f"          {i}")
    for preferred in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"):
        if preferred in chat:
            print(f"\n        Set HS_LLM_MODEL={preferred} in .env and re-run.")
            break


def main():
    cfg = RunConfig()
    print("\nHANDSHAKE PREFLIGHT\n" + "-" * 66)

    line(OK if DOTENV_PATH else INFO, ".env",
         DOTENV_PATH or "not found — using process environment only")
    line(INFO, "payments backend", cfg.payments_backend)
    line(INFO, "buyer backend", cfg.buyer_backend)

    # ---------------- LLM ----------------
    print()
    if cfg.buyer_backend != "llm":
        line(INFO, "LLM", "not requested (HS_BUYERS=heuristic) — skipping")
    else:
        decider = LLMDecider(cfg)
        if not decider.endpoints:
            line(BAD, "keys", "none found — set HS_LLM_API_KEYS or HS_LLM_API_KEY")
            failures.append("llm keys")
        else:
            line(OK, "key pool", f"{len(decider.endpoints)} key(s)")
            line(INFO, "max tokens", os.environ.get("HS_LLM_MAX_TOKENS", "512"))

            per_key_tokens = []
            for endpoint in decider.endpoints:
                if not endpoint.client:
                    line(BAD, endpoint.label, f"{endpoint.masked}  {endpoint.error}")
                    failures.append(f"{endpoint.label} client")
                    continue
                before = endpoint.calls
                try:
                    text = decider._call(endpoint, PROBE, {})
                    answer = _parse(text)
                except Exception as exc:
                    answer, text = None, ""
                    endpoint.error = f"{type(exc).__name__}: {str(exc)[:150]}"
                if answer is None:
                    line(BAD, endpoint.label,
                         f"{endpoint.masked}  {endpoint.model}  {endpoint.error or 'no decision in reply'}")
                    failures.append(f"{endpoint.label} call")
                    if "model_not_found" in endpoint.error or "does not exist" in endpoint.error:
                        _suggest_models(decider, endpoint)
                else:
                    spent = endpoint.tokens
                    per_key_tokens.append(spent or 0)
                    line(OK, endpoint.label,
                         f"{endpoint.masked}  {endpoint.model}  "
                         f"proceed={answer}  {spent} tokens")
                endpoint.calls = before + 1

            models = {e.model for e in decider.endpoints}
            if len(models) > 1:
                line(INFO, "note",
                     "keys use different models — the buyer fleet will not be "
                     "homogeneous, and the report will say so")

            if per_key_tokens:
                per = max(per_key_tokens)
                quota = int(os.environ.get("HS_LLM_DAILY_QUOTA", "200000"))
                capacity = (quota // per) * len(per_key_tokens) if per else 0
                line(INFO, "tokens per decision", f"~{per}")
                line(INFO, "pool capacity",
                     f"~{capacity:,} sessions at {quota:,} tokens/day/key")
                for n in (200, 500):
                    verdict = "fits" if capacity >= n else "DOES NOT FIT"
                    line(INFO, f"{n}-session batch", verdict)
                if capacity < 500:
                    print("          Add another key (HS_LLM_API_KEYS=k1,k2,k3), "
                          "use a cheaper\n          model, or run --sessions "
                          f"{max(50, capacity // 50 * 50)}.")

    # ---------------- payments ----------------
    print()
    if cfg.payments_backend != "razorpay":
        line(INFO, "Razorpay", "not requested (HS_PAYMENTS=sim) — skipping")
    else:
        line(OK if cfg.razorpay_key_id.startswith("rzp_test_") else BAD,
             "RAZORPAY_KEY_ID", mask(cfg.razorpay_key_id)
             or "missing — must begin rzp_test_")
        line(OK if cfg.razorpay_key_secret else BAD, "RAZORPAY_KEY_SECRET",
             "set" if cfg.razorpay_key_secret else "missing")
        try:
            backend = build_backend(cfg, random.Random(0))
            result = backend.charge(1234.56, {"type": "card_token", "state": "active"})
            if result.ok:
                line(OK, "test order created", result.ref)
            else:
                line(BAD, "test order", result.reason_code)
                failures.append("razorpay order")
        except Exception as exc:
            line(BAD, "test order", f"{type(exc).__name__}: {exc}")
            failures.append("razorpay order")

    # ---------------- verdict ----------------
    print("-" * 66)
    if failures:
        print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}")
        print("A batch would silently fall back to the offline path. Fix these first.\n")
        return 1
    print("\nAll requested backends are live. Suggested first run:\n"
          "    python3 -m handshake.experiments.run --sessions 500 --tag live\n"
          "Confirm the report header says payments=razorpay buyers=llm and that\n"
          "'simulated components' no longer lists them.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
