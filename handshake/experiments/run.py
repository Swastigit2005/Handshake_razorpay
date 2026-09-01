"""CLI entry point.

    python -m handshake.experiments.run --sessions 500

Writes the batch report, the exception list, the session table, the exported
ledger and the operator console into runs/.
"""

import argparse
import os
import sys
import time

import random

from ..config import RunConfig
from ..console.render import render
from ..buyers.llm import LLMBudgetExhausted, LLMDecider
from ..payments.adapter import build_backend, preflight
from .batch import run_batch
from .report import compute, render_text, save

def _runs_dir():
    """Artefacts belong beside the user, not inside site-packages."""
    root = os.environ.get("HS_RUNS_DIR") or os.path.join(os.getcwd(), "runs")
    os.makedirs(root, exist_ok=True)
    return root


class _probe_persona:
    budget, cap, posture = 5000, 4000, "strict"


def _probe_view():
    return {"sku": "AUD-001", "title": "In-Ear Monitors Pro", "price": 2499,
            "tax_rate": 0.18, "attributes": {"driver_mm": 12, "battery_hours": 30},
            "policy": {"structured": True, "returns_days": 7}}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a Handshake recovery batch.")
    ap.add_argument("--sessions", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20260830)
    ap.add_argument("--fault-incidence", type=float, default=0.55)
    ap.add_argument("--kill-switch", action="store_true",
                    help="halt all money actions (rule R-11)")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args(argv)

    cfg = RunConfig()
    cfg.batch_size = args.sessions
    cfg.seed = args.seed
    cfg.fault_incidence = args.fault_incidence
    cfg.policy.kill_switch = args.kill_switch

    tag = args.tag or time.strftime("%Y%m%d-%H%M%S")
    prefix = os.path.join(_runs_dir(), f"batch_{tag}")

    def progress(done, total):
        print(f"  {done}/{total} sessions", file=sys.stderr)

    print(f"running {cfg.batch_size} sessions "
          f"(payments={cfg.payments_backend}, buyers={cfg.buyer_backend})", file=sys.stderr)

    # A live run that cannot reach its backends must not produce numbers.
    if cfg.payments_backend == "razorpay":
        try:
            backend = build_backend(cfg, random.Random(0))
        except ImportError:
            print("\naborted: HS_PAYMENTS=razorpay but the client is missing."
                  "\n         pip install razorpay", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"\naborted: {exc}", file=sys.stderr)
            return 2
        ok, why = preflight(backend)
        if not ok:
            print(f"\naborted before running: {why}", file=sys.stderr)
            return 2

    if cfg.buyer_backend == "llm":
        decider = LLMDecider(cfg)
        if not decider.available() or decider.decide(_probe_persona(), _probe_view(),
                                                     ["codec_support"]) is None:
            print(f"\naborted: HS_BUYERS=llm but the model is not usable."
                  f"\n         {decider.last_error}"
                  f"\n         Run `python3 preflight.py` to diagnose, or set "
                  f"HS_BUYERS=heuristic to run offline.", file=sys.stderr)
            return 2
    try:
        run = run_batch(cfg, progress=progress)
    except LLMBudgetExhausted as exc:
        print(f"\naborted: {exc}\n\n"
              "Options, in order of preference:\n"
              "  1. add another key:  HS_LLM_API_KEYS=key1,key2,key3\n"
              "  2. a cheaper model:  HS_LLM_MODEL=openai/gpt-oss-20b\n"
              "  3. a smaller batch:  --sessions 200\n"
              "  4. wait for the daily quota to reset, then re-run\n"
              "  5. the offline baseline: HS_BUYERS=heuristic (fully reproducible)\n",
              file=sys.stderr)
        return 3
    summary, exceptions = compute(run)
    sessions = [r.as_dict() for r in run["results"]]

    save(summary, exceptions, sessions, prefix)
    run["ledger"].export_jsonl(f"{prefix}_ledger.jsonl")
    html_path = render(summary, exceptions, sessions, run["ledger"], f"{prefix}_console.html")

    print(render_text(summary))
    print(f"\nartefacts:\n  {prefix}_summary.json\n  {prefix}_exceptions.json"
          f"\n  {prefix}_sessions.json\n  {prefix}_ledger.jsonl\n  {html_path}")
    return summary


if __name__ == "__main__":
    main()
