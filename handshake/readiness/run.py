"""CLI for the readiness scan.

    python3 -m handshake.readiness.run --sessions 300
"""

import argparse
import json
import os
import sys

from ..config import RunConfig
from .scan import render_text, scan

def _runs_dir():
    """Artefacts belong beside the user, not inside site-packages."""
    root = os.environ.get("HS_RUNS_DIR") or os.path.join(os.getcwd(), "runs")
    os.makedirs(root, exist_ok=True)
    return root


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score and price a catalogue for AI buyers.")
    ap.add_argument("--sessions", type=int, default=300)
    ap.add_argument("--defect-rate", type=float, default=0.22,
                    help="share of listings given a permanent flaw (demo catalogue)")
    ap.add_argument("--top", type=int, default=5, help="defects to repair in the proof")
    ap.add_argument("--seed", type=int, default=20260830)
    ap.add_argument("--tag", default="scan")
    args = ap.parse_args(argv)

    cfg = RunConfig()
    cfg.seed = args.seed
    print(f"probing {args.sessions} agent sessions (buyers={cfg.buyer_backend})",
          file=sys.stderr)

    report = scan(sessions=args.sessions, defect_rate=args.defect_rate,
                  cfg=cfg, top_k=args.top)

    path = os.path.join(_runs_dir(), f"readiness_{args.tag}.json")
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    print(render_text(report))
    print(f"\nwritten: {path}")
    return report


if __name__ == "__main__":
    main()
