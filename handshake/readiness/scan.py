"""Agent-Readiness scan — prevention rather than recovery.

Recovery is per-session: a sale fails, we repair the data and win that one back.
The same defect then fails the next session, and the next. Fixing the defect
once prevents every future failure it would cause.

The scan does three things:

  1. audit    — find, by inspection, every catalogue flaw an agent stumbles on
  2. price    — run agent buyers and measure the rupees each flaw actually refuses
  3. prove    — repair the top flaws, re-run the identical buyers, report the delta

Step 3 is the one that matters. It is an A/B test on the catalogue itself: same
seed, same personas, same decisions — only the feed differs. The delta is a
measurement, not a projection.
"""

import random
from collections import defaultdict

from ..buyers.agent import BuyerAgent
from ..buyers.llm import LLMDecider
from ..buyers.personas import fleet
from ..config import RunConfig
from ..diagnosis.engine import diagnose
from ..merchant.api import MerchantAPI
from ..merchant.catalog import build_catalog, inject_defects, repair
from ..merchant.faults import FaultInjector
from ..payments.adapter import build_backend
from ..recorder.recorder import Trace
from ..taxonomy import Terminal

# What a diagnosed cause tells us about the catalogue.
CAUSE_TO_DEFECT = {
    "A1": "missing_attribute",
    "A2": "variant_collision",
    "A7": "prose_policy",
    "A8": "unserviceable",
}

# Causes that are NOT catalogue defects. A cap breach is the buyer's budget, a
# drift is a pricing race, an unreadable decline is the rail's reason code. None
# of them is a field a merchant can edit, so the scan reports them separately
# rather than filing them under "other".
NOT_CATALOGUE = {
    "A3": "price moved mid-session (pricing race, not a feed defect)",
    "A4": "buyer's own spending cap was too low",
    "A5": "checkout demanded a human step",
    "A6": "transient error the buyer read as terminal",
    "B1": "payment rail declined for funds",
    "B2": "issuer downtime",
    "B3": "mandate expired or revoked",
    "B4": "delegated reserve exhausted",
    "B5": "instrument declined",
    "UNKNOWN": "decline arrived with no usable reason code",
}

# The field a merchant edits to fix each defect class.
DEFECT_FIELD = {
    "variant_collision": "variant_group",
    "unserviceable": "serviceable_pincodes",
    "prose_policy": "policy",
    "stale_stock": "stock",
}


def _probe(catalog, personas, cfg, sessions, decider=None, sink=None):
    """Send agent buyers at a catalogue with no injected faults.

    Every failure here is the catalogue's own doing."""
    out = []
    for i in range(sessions):
        rng = random.Random(cfg.seed * 977 + i)
        persona = personas[i % len(personas)]
        trace = Trace(session_id=f"probe_{i:05d}", buyer_id=persona.id,
                      persona=persona.posture, arm="probe", spend_cap=persona.cap)
        injector = FaultInjector(None, rng)
        merchant = MerchantAPI(catalog, injector, build_backend(cfg, rng), trace)
        agent = BuyerAgent(persona, trace, rng, decider)
        agent.run(merchant)

        if trace.abandon_note == "no affordable candidate in feed":
            out.append({"session": trace.session_id, "state": "no_candidate",
                        "value": 0.0, "cause": "", "sku": "", "field": ""})
            continue

        if trace.terminal_state == Terminal.CONVERTED:
            out.append({"session": trace.session_id, "state": "converted",
                        "value": trace.converted_value, "cause": "",
                        "sku": agent.sku or "", "field": ""})
            continue

        d = diagnose(trace, merchant)
        out.append({"session": trace.session_id, "state": "failed",
                    "value": trace.basket_value, "cause": d.cause,
                    "sku": d.detail.get("sku", agent.sku or ""),
                    "field": d.detail.get("missing_attribute", ""),
                    "defect": CAUSE_TO_DEFECT.get(d.cause, "")})
        if sink:
            sink.emit("probe_failure", session_id=trace.session_id,
                      cause=d.cause, value=round(trace.basket_value, 2))
    return out


def _price(results):
    """Split refused basket value into what the catalogue caused and what it
    did not. Only the first half is something a merchant can fix by editing a
    field, and only the first half belongs in a readiness report."""
    priced = defaultdict(lambda: {"sessions": 0, "at_risk": 0.0, "skus": set()})
    other = defaultdict(lambda: {"sessions": 0, "at_risk": 0.0})

    for row in results:
        if row["state"] != "failed":
            continue
        defect = row.get("defect") or ""
        if not defect:
            cause = row.get("cause") or "UNKNOWN"
            bucket = other[cause]
            bucket["sessions"] += 1
            bucket["at_risk"] += row["value"]
            continue
        key = (defect, row.get("field") or DEFECT_FIELD.get(defect, ""))
        entry = priced[key]
        entry["sessions"] += 1
        entry["at_risk"] += row["value"]
        if row["sku"]:
            entry["skus"].add(row["sku"])

    catalogue = [{"defect": k[0], "field": k[1], "sessions": v["sessions"],
                  "at_risk": round(v["at_risk"], 2), "skus": sorted(v["skus"])}
                 for k, v in sorted(priced.items(), key=lambda kv: -kv[1]["at_risk"])]
    non_catalogue = [{"cause": k, "reason": NOT_CATALOGUE.get(k, "not a feed defect"),
                      "sessions": v["sessions"], "at_risk": round(v["at_risk"], 2)}
                     for k, v in sorted(other.items(), key=lambda kv: -kv[1]["at_risk"])]
    return catalogue, non_catalogue


def scan(sessions=300, defect_rate=0.22, cfg=None, top_k=5, sink=None):
    """Audit, price, then prove the repair. Returns one report."""
    cfg = cfg or RunConfig()
    clean = build_catalog(cfg.seed)
    flawed, planted = inject_defects(clean, rate=defect_rate, seed=cfg.seed)

    # Personas come from the clean catalogue so that both passes shop the same
    # way. Only the feed differs between them.
    personas = fleet(cfg.seed + 1, max(40, sessions // 4), clean)
    decider = LLMDecider(cfg) if cfg.buyer_backend == "llm" else None

    from .audit import audit, blocking, by_field, readiness_score
    found = audit(flawed)
    blockers = blocking(found)

    before = _probe(flawed, personas, cfg, sessions, decider, sink)
    priced, non_catalogue = _price(before)

    # --- prove the repair -------------------------------------------------
    ranked_skus = []
    for row in priced[:top_k]:
        ranked_skus.extend(row["skus"])
    ranked_skus = list(dict.fromkeys(ranked_skus))
    repaired_catalog = repair(flawed, clean, set(ranked_skus))
    after = _probe(repaired_catalog, personas, cfg, sessions, decider)

    def totals(rows):
        return {
            "converted": sum(1 for r in rows if r["state"] == "converted"),
            "failed": sum(1 for r in rows if r["state"] == "failed"),
            "revenue": round(sum(r["value"] for r in rows
                                 if r["state"] == "converted"), 2),
            "at_risk": round(sum(r["value"] for r in rows
                                 if r["state"] == "failed"), 2),
        }

    t_before, t_after = totals(before), totals(after)
    per_1000 = (1000 / sessions) if sessions else 0

    return {
        "sessions": sessions,
        "seed": cfg.seed,
        "buyers": cfg.buyer_backend,
        "listings": len(flawed),
        "readiness_score": readiness_score(flawed, found),
        "defects_found": blockers,
        "advisories": [d for d in found if d.get("advisory")],
        "defects_by_field": sorted(by_field(blockers), key=lambda r: -r["sku_count"]),
        "planted": len(planted),
        "priced": priced,
        "non_catalogue": non_catalogue,
        "before": t_before,
        "after": t_after,
        "repaired_skus": ranked_skus,
        "delta": {
            "sessions_recovered": t_after["converted"] - t_before["converted"],
            "revenue_gained": round(t_after["revenue"] - t_before["revenue"], 2),
            "at_risk_removed": round(t_before["at_risk"] - t_after["at_risk"], 2),
            "per_1000_sessions": round(
                (t_after["revenue"] - t_before["revenue"]) * per_1000, 2),
        },
        "unpriced": [d for d in found if d.get("advisory")],
    }


def render_text(report):
    out = []
    add = out.append
    d = report["delta"]
    add("AGENT-READINESS SCAN")
    add(f"{report['listings']} listings · {report['sessions']} probe sessions · "
        f"buyers={report['buyers']} · seed {report['seed']}")
    add("")
    add(f"readiness score        {report['readiness_score']}%  "
        f"(share of listings an agent can transact against cleanly)")
    add(f"defects found          {len(report['defects_found'])} across "
        f"{len({x['sku'] for x in report['defects_found']})} listings")
    add("")
    add("WHAT THE DEFECTS COST — measured, not projected")
    add(f"{'defect':20}{'field':22}{'sessions':>9}{'refused GMV':>14}{'listings':>10}")
    for row in report["priced"]:
        add(f"{row['defect'][:19]:20}{(row['field'] or '-')[:21]:22}"
            f"{row['sessions']:>9}{row['at_risk']:>14,.0f}{len(row['skus']):>10}")
    add("")
    add("REPAIR PROVEN — same seed, same buyers, only the feed differs")
    add(f"{'':24}{'before':>12}{'after':>12}")
    add(f"{'converted sessions':24}{report['before']['converted']:>12}"
        f"{report['after']['converted']:>12}")
    add(f"{'failed sessions':24}{report['before']['failed']:>12}"
        f"{report['after']['failed']:>12}")
    add(f"{'revenue':24}{report['before']['revenue']:>12,.0f}"
        f"{report['after']['revenue']:>12,.0f}")
    add("")
    add(f"fixing {len(report['repaired_skus'])} listings recovered "
        f"{d['sessions_recovered']} sessions and ₹{d['revenue_gained']:,.0f}")
    add(f"projected at ₹{d['per_1000_sessions']:,.0f} per 1,000 agent sessions, "
        f"permanently — no per-session recovery needed")
    if report.get("non_catalogue"):
        total = sum(r["at_risk"] for r in report["non_catalogue"])
        add("")
        add(f"NOT THE CATALOGUE'S FAULT — Rs {total:,.0f} refused for reasons no "
            f"field can fix")
        for row in report["non_catalogue"]:
            add(f"  {row['cause']:8}{row['sessions']:>4} sessions "
                f"{row['at_risk']:>11,.0f}   {row['reason']}")
        add("  These belong to the recovery layer, not the readiness report.")
    if report["unpriced"]:
        add("")
        add(f"{len(report['unpriced'])} out-of-stock listings were never shown to a "
            f"buyer, so they refuse nothing measurable — they cost you the "
            f"impression, not the basket.")
    return "\n".join(out)
