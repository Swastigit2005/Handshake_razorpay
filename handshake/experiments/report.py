"""Batch metrics (spec 13).

Every figure here is computed against a randomised control arm. Gross recovery
is reported alongside the margin it cost, because a recovery agent that buys
revenue back with discount is a loss engine.
"""

import json
from collections import Counter, defaultdict

from ..taxonomy import CAUSES, RULES, Terminal, UNKNOWN


def _rate(num, den):
    return (num / den) if den else 0.0


def compute(run):
    cfg = run["config"]
    results = run["results"]
    margin = cfg.policy.gross_margin_pct

    arms = {"treatment": [], "control": []}
    for r in results:
        arms[r.arm].append(r)

    summary = {"batch_size": len(results), "seed": cfg.seed,
               "payments_backend": cfg.payments_backend,
               "buyer_backend": cfg.buyer_backend,
               "arms": {}}

    for arm, rows in arms.items():
        failed = [r for r in rows if r.trace.terminal_state == Terminal.FAILED
                  or r.recovered]
        at_risk = sum(r.trace.basket_value for r in rows
                      if r.trace.terminal_state == Terminal.FAILED or r.recovered)
        recovered = sum(r.recovered_value for r in rows if r.recovered)
        concession = sum(r.concession for r in rows)
        actions = sum(len(r.interventions) for r in rows)
        summary["arms"][arm] = {
            "sessions": len(rows),
            "converted_first_pass": sum(
                1 for r in rows
                if r.trace.terminal_state == Terminal.CONVERTED and not r.recovered),
            "failed": len(failed),
            "at_risk_gmv": round(at_risk, 2),
            "recovered_gmv": round(recovered, 2),
            "recovery_rate": round(_rate(recovered, at_risk), 4),
            "concession_cost": round(concession, 2),
            "concession_ratio": round(_rate(concession, recovered), 4),
            "interventions": actions,
            "net_recovery": round(recovered * margin - concession
                                  - actions * cfg.policy.intervention_cost_inr, 2),
        }

    t = summary["arms"]["treatment"]
    c = summary["arms"]["control"]
    summary["lift_over_control"] = round(t["recovery_rate"] - c["recovery_rate"], 4)
    summary["headline_recovered_gmv"] = t["recovered_gmv"]
    summary["headline_net_recovery"] = t["net_recovery"]

    # ---- per-cause -----------------------------------------------------
    per_cause = defaultdict(lambda: {"failed": 0, "at_risk": 0.0, "recovered": 0.0,
                                     "recovered_n": 0, "concession": 0.0})
    for r in arms["treatment"]:
        if not (r.trace.terminal_state == Terminal.FAILED or r.recovered):
            continue
        key = r.diagnosis.cause if r.diagnosis else UNKNOWN
        row = per_cause[key]
        row["failed"] += 1
        row["at_risk"] += r.trace.basket_value
        row["concession"] += r.concession
        if r.recovered:
            row["recovered"] += r.recovered_value
            row["recovered_n"] += 1
    summary["per_cause"] = {
        k: {"name": CAUSES[k].name if k in CAUSES else "unclassified",
            "failed": v["failed"],
            "at_risk_gmv": round(v["at_risk"], 2),
            "recovered_gmv": round(v["recovered"], 2),
            "recovery_rate": round(_rate(v["recovered"], v["at_risk"]), 4),
            "recovered_sessions": v["recovered_n"],
            "concession": round(v["concession"], 2)}
        for k, v in sorted(per_cause.items(), key=lambda kv: -kv[1]["at_risk"])
    }

    # ---- diagnosis accuracy against injected ground truth ---------------
    tp = Counter(); fp = Counter(); fn = Counter()
    scored = 0
    for r in results:
        if not r.diagnosis or not r.fault:
            continue
        scored += 1
        truth, pred = r.fault, r.diagnosis.cause
        if truth == pred:
            tp[truth] += 1
        else:
            fn[truth] += 1
            fp[pred] += 1
    classes = sorted(set(list(tp) + list(fp) + list(fn)) - {UNKNOWN})
    f1s = []
    per_class = {}
    for k in classes:
        precision = _rate(tp[k], tp[k] + fp[k])
        recall = _rate(tp[k], tp[k] + fn[k])
        f1 = _rate(2 * precision * recall, precision + recall)
        f1s.append(f1)
        per_class[k] = {"precision": round(precision, 3), "recall": round(recall, 3),
                        "f1": round(f1, 3), "support": tp[k] + fn[k]}
    summary["diagnosis"] = {
        "scored_sessions": scored,
        "macro_f1": round(sum(f1s) / len(f1s), 3) if f1s else 0.0,
        "unclassified": sum(1 for r in results
                            if r.diagnosis and r.diagnosis.cause == UNKNOWN),
        "per_class": per_class,
    }

    # ---- governance evidence -------------------------------------------
    refusals = Counter()
    for r in results:
        for ref in r.refusals:
            refusals[ref["rule"]] += 1
    summary["policy_refusals"] = {k: refusals[k] for k in sorted(refusals)}
    summary["rules_observed_firing"] = sorted(refusals)
    summary["rules_not_observed"] = sorted(set(RULES) - set(refusals))

    exceptions = [r.as_dict() for r in results if r.exception]
    summary["exception_count"] = len(exceptions)

    ok, bad = run["ledger"].verify()
    summary["ledger"] = {"entries": len(run["ledger"].entries),
                         "hash_chain_valid": ok, "first_bad_entry": bad}

    # ---- what actually ran, not what was requested ----------------------
    dec = run.get("decider")
    simulated = cfg.simulated_components()
    if cfg.buyer_backend == "llm":
        if dec is None or not dec.available():
            summary["llm"] = {"active": False, "calls": 0, "failures": 0,
                              "error": getattr(dec, "last_error", "decider not built"),
                              "note": "requested but unavailable; the heuristic ran instead"}
        else:
            live = dec.calls - dec.failures
            share = live / dec.calls if dec.calls else 0.0
            models = dec.models_used()
            summary["llm"] = {"active": live > 0, "provider": dec.describe(),
                              "calls": dec.calls, "failures": dec.failures,
                              "decisions_from_model": live,
                              "model_share": round(share, 3),
                              "mixed_run": share < 0.99,
                              "fallbacks": dec.failures,
                              "waited_out_rate_limits": getattr(dec, "waits", 0),
                              "keys": len(dec.endpoints),
                              "key_rotations": dec.rotations,
                              "models_used": models,
                              "mixed_model_run": len(models) > 1,
                              "total_tokens": dec.tokens,
                              "pool": dec.pool_state(),
                              "error": dec.last_error}
            if live > 0 and dec.failures == 0:
                simulated = [x for x in simulated if not x.startswith("buyer agents")]
            elif live > 0:
                simulated = [x if not x.startswith("buyer agents")
                             else f"buyer agents (partly: {dec.failures} of {dec.calls} "
                                  f"model calls failed and fell back to the heuristic)"
                             for x in simulated]
    summary["simulated_components"] = simulated
    return summary, exceptions


def render_text(summary):
    a = summary["arms"]
    out = []
    add = out.append
    add("HANDSHAKE — BATCH REPORT")
    add(f"sessions {summary['batch_size']}   seed {summary['seed']}   "
        f"payments={summary['payments_backend']}  buyers={summary['buyer_backend']}")
    add("")
    add(f"{'':22}{'treatment':>14}{'control':>14}")
    for label, key in [("sessions", "sessions"), ("failed", "failed"),
                       ("at-risk GMV", "at_risk_gmv"), ("recovered GMV", "recovered_gmv"),
                       ("recovery rate", "recovery_rate"),
                       ("concession cost", "concession_cost"),
                       ("concession ratio", "concession_ratio"),
                       ("interventions", "interventions"),
                       ("net recovery", "net_recovery")]:
        add(f"{label:22}{a['treatment'][key]:>14}{a['control'][key]:>14}")
    add("")
    add(f"lift over control      {summary['lift_over_control']:.4f}")
    add(f"diagnosis macro-F1     {summary['diagnosis']['macro_f1']}  "
        f"(unclassified {summary['diagnosis']['unclassified']})")
    add(f"ledger entries         {summary['ledger']['entries']}  "
        f"chain valid: {summary['ledger']['hash_chain_valid']}")
    add(f"exceptions             {summary['exception_count']}")
    llm = summary.get("llm")
    if llm:
        if not llm["active"]:
            add("")
            add("!! LLM BUYERS REQUESTED BUT NOT ACTIVE — the heuristic ran instead.")
            add(f"   {llm['error']}")
        else:
            add(f"llm buyers             {llm['decisions_from_model']}/{llm['calls']} "
                f"decisions · {llm['provider']}")
            if llm.get("keys", 1) > 1:
                add(f"key pool               {llm['keys']} keys, "
                    f"{llm['key_rotations']} rotation(s), "
                    f"{llm['total_tokens']:,} tokens")
                for row in llm.get("pool", []):
                    state = "spent" if row["exhausted"] else "live"
                    add(f"   {row['key']:5} {row['model'][:28]:28} "
                        f"{row['calls']:>5} calls  {row['tokens']:>8,} tok  {state}"
                        + (f"  ({row['error'][:40]})" if row["error"] else ""))
            if llm.get("mixed_model_run"):
                add(f"   !! MIXED-MODEL RUN — decisions came from "
                    f"{', '.join(llm['models_used'])}. The buyer fleet was not "
                    f"homogeneous; say so when reporting these figures.")
            if llm["failures"]:
                n = llm["failures"]
                word = "call" if n == 1 else "calls"
                if llm["mixed_run"]:
                    add(f"   !! MIXED RUN — {llm['model_share']:.1%} of decisions came "
                        f"from the model; {n} {word} fell back to the heuristic.")
                    add("   !! These figures are attributable to neither backend. "
                        "Do not report them as an LLM run.")
                else:
                    add(f"   note: {n} {word} of {llm['calls']} fell back to the "
                        f"heuristic ({llm['model_share']:.1%} from the model). "
                        f"Disclose it; the run is substantially a model run.")
                add(f"   last error: {llm['error']}")
    add("")
    add("RECOVERY BY ROOT CAUSE (treatment)")
    add(f"{'cause':6}{'name':24}{'failed':>7}{'at-risk':>12}{'recovered':>12}{'rate':>8}")
    for k, v in summary["per_cause"].items():
        add(f"{k:6}{v['name'][:23]:24}{v['failed']:>7}{v['at_risk_gmv']:>12.0f}"
            f"{v['recovered_gmv']:>12.0f}{v['recovery_rate']:>8.2f}")
    add("")
    add("POLICY REFUSALS BY BINDING RULE")
    for k, n in summary["policy_refusals"].items():
        add(f"  {k}  {n:>4}  {RULES[k]}")
    add("")
    add("SIMULATED COMPONENTS")
    for s in summary["simulated_components"]:
        add(f"  - {s}")
    return "\n".join(out)


def save(summary, exceptions, sessions, path_prefix):
    with open(f"{path_prefix}_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    with open(f"{path_prefix}_exceptions.json", "w") as fh:
        json.dump(exceptions, fh, indent=2, default=str)
    with open(f"{path_prefix}_sessions.json", "w") as fh:
        json.dump(sessions, fh, indent=2, default=str)
