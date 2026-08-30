"""Operator console (component C8) as a self-contained HTML report.

Not a marketing page: it is the surface an operator would actually read — what
failed, why, what was done, what it cost, and what could not be resolved. Every
rupee in the headline is traceable to the ledger entries shown at the foot.
"""

import html
import json

from ..taxonomy import CAUSES, RULES

CSS = """
:root{--paper:#F3F5F2;--surface:#FFF;--sunk:#EAEEE9;--ink:#131C18;--soft:#4A5751;
--faint:#6B7873;--rule:#D5DDD7;--rule2:#E4EAE5;--accent:#126B47;--accent-soft:#E2EFE7;
--signal:#A8412A;--signal-soft:#F6E7E2;--warn:#8A6414;--warn-soft:#F5EEDC;
--fd:"IBM Plex Sans Condensed",Arial,sans-serif;--fb:"IBM Plex Serif",Georgia,serif;
--fm:"IBM Plex Mono",ui-monospace,Menlo,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0E1512;
--surface:#151E1A;--sunk:#111A16;--ink:#E2E9E4;--soft:#A8B5AE;--faint:#7F8D86;
--rule:#26332C;--rule2:#1D2823;--accent:#57B385;--accent-soft:#14291F;
--signal:#DE7A5E;--signal-soft:#2B1B15;--warn:#D0A64A;--warn-soft:#29220F;}}
:root[data-theme="dark"]{--paper:#0E1512;--surface:#151E1A;--sunk:#111A16;--ink:#E2E9E4;
--soft:#A8B5AE;--faint:#7F8D86;--rule:#26332C;--rule2:#1D2823;--accent:#57B385;
--accent-soft:#14291F;--signal:#DE7A5E;--signal-soft:#2B1B15;--warn:#D0A64A;--warn-soft:#29220F;}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--fb);font-size:15px;
line-height:1.55;margin:0;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:36px 28px 96px}
.eyebrow{font-family:var(--fm);font-size:10px;letter-spacing:.13em;text-transform:uppercase;
color:var(--accent);margin:0 0 10px}
h1{font-family:var(--fd);font-size:38px;font-weight:700;letter-spacing:-.02em;margin:0 0 6px;
line-height:1.05}
.sub{font-family:var(--fm);font-size:11.5px;color:var(--faint);letter-spacing:.02em;margin:0}
h2{font-family:var(--fd);font-size:20px;font-weight:700;letter-spacing:-.01em;margin:44px 0 12px;
padding-bottom:7px;border-bottom:1.5px solid var(--ink)}
h3{font-family:var(--fm);font-size:10px;letter-spacing:.11em;text-transform:uppercase;
color:var(--faint);margin:26px 0 8px;font-weight:600}
p{margin:0 0 12px;max-width:68ch}
.banner{border-left:3px solid var(--warn);background:var(--warn-soft);padding:12px 16px;
margin:22px 0 0;font-size:14px}
.banner b{font-weight:600}
.banner ul{margin:6px 0 0;padding-left:18px}
.banner li{margin:2px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:1px;
background:var(--rule);border:1px solid var(--rule);margin:26px 0 0}
.kpi{background:var(--surface);padding:16px 18px;display:flex;flex-direction:column;gap:5px}
.kpi .k{font-family:var(--fm);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
color:var(--faint)}
.kpi .v{font-family:var(--fd);font-size:27px;font-weight:700;letter-spacing:-.02em;
font-variant-numeric:tabular-nums;line-height:1.05}
.kpi .n{font-family:var(--fm);font-size:10.5px;color:var(--soft)}
.kpi.good .v{color:var(--accent)}
.tw{overflow-x:auto;border-top:1.5px solid var(--ink);border-bottom:1px solid var(--rule);
margin:0 0 18px}
table{border-collapse:collapse;width:100%;font-family:var(--fd);font-size:13.5px}
th{text-align:left;font-family:var(--fm);font-size:9.5px;letter-spacing:.09em;
text-transform:uppercase;color:var(--faint);font-weight:500;padding:9px 14px 9px 0;
border-bottom:1px solid var(--rule);white-space:nowrap;vertical-align:bottom}
td{padding:9px 14px 9px 0;border-bottom:1px solid var(--rule2);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
td.n{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
th.n{text-align:right}
.id{font-family:var(--fm);font-size:11.5px;color:var(--accent);white-space:nowrap}
.bar{display:block;height:9px;background:var(--sunk);border-radius:0;position:relative;
min-width:120px}
.bar i{display:block;height:9px;background:var(--accent);border-radius:0 2px 2px 0}
.lab{font-family:var(--fm);font-size:10.5px;color:var(--soft);
font-variant-numeric:tabular-nums;padding-left:8px}
.barcell{display:flex;align-items:center;gap:0;min-width:190px}
.chain{border:1px solid var(--rule);background:var(--surface);padding:0;margin:0 0 18px}
.entry{border-bottom:1px solid var(--rule2);padding:13px 16px}
.entry:last-child{border-bottom:none}
.entry .top{display:flex;justify-content:space-between;gap:14px;align-items:baseline;
flex-wrap:wrap;margin-bottom:5px}
.entry .actor{font-family:var(--fd);font-weight:600;font-size:14px}
.entry .hash{font-family:var(--fm);font-size:9.5px;color:var(--faint)}
.chk{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.chk span{font-family:var(--fm);font-size:9.5px;padding:2px 6px;border:1px solid var(--rule);
background:var(--sunk);color:var(--soft)}
.chk span.fail{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}
pre{font-family:var(--fm);font-size:11px;line-height:1.6;background:var(--sunk);
border:1px solid var(--rule2);padding:10px 12px;overflow-x:auto;margin:6px 0 0}
.note{border-left:3px solid var(--accent);background:var(--accent-soft);padding:12px 16px;
margin:0 0 18px;font-size:14px;max-width:68ch}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--rule);
font-family:var(--fm);font-size:10.5px;color:var(--faint);line-height:1.8}
"""


def _inr(x):
    return f"₹{x:,.0f}"


def _bar(value, total, label):
    pct = (value / total * 100) if total else 0
    return (f'<div class="barcell"><span class="bar"><i style="width:{pct:.1f}%"></i></span>'
            f'<span class="lab">{label}</span></div>')


def render(summary, exceptions, sessions, ledger, path):
    t = summary["arms"]["treatment"]
    c = summary["arms"]["control"]
    d = summary["diagnosis"]

    # a recovered session with the fullest chain, for the audit trail panel
    recovered = [s for s in sessions if s["recovered"] and s["interventions"]
                 and s["interventions"][0] != "none_buyer_self_recovery"]
    sample = max(recovered, key=lambda s: s["recovered_value"], default=None)
    chain = ledger.for_session(sample["session_id"]) if sample else []

    out = []
    a = out.append
    a('<title>Handshake Batch Console</title>')
    a('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700'
      '&family=IBM+Plex+Serif:wght@400;500;600&display=swap">')
    a(f"<style>{CSS}</style>")
    a('<div class="wrap">')

    a('<p class="eyebrow">Batch report · Razorpay AI Buildathon · Track 03</p>')
    a("<h1>Handshake</h1>")
    a(f'<p class="sub">{summary["batch_size"]} sessions &nbsp;·&nbsp; seed {summary["seed"]}'
      f' &nbsp;·&nbsp; payments={summary["payments_backend"]}'
      f' &nbsp;·&nbsp; buyers={summary["buyer_backend"]}</p>')

    # ---- money view ----
    a('<div class="kpis">')
    a(f'<div class="kpi"><span class="k">At-risk GMV</span>'
      f'<span class="v">{_inr(t["at_risk_gmv"])}</span>'
      f'<span class="n">{t["failed"]} failed sessions</span></div>')
    a(f'<div class="kpi good"><span class="k">Recovered GMV</span>'
      f'<span class="v">{_inr(t["recovered_gmv"])}</span>'
      f'<span class="n">{t["recovery_rate"]*100:.1f}% of at-risk</span></div>')
    a(f'<div class="kpi good"><span class="k">Lift over control</span>'
      f'<span class="v">{summary["lift_over_control"]*100:.1f} pts</span>'
      f'<span class="n">control recovered {c["recovery_rate"]*100:.1f}%</span></div>')
    a(f'<div class="kpi"><span class="k">Concession ratio</span>'
      f'<span class="v">{t["concession_ratio"]*100:.2f}%</span>'
      f'<span class="n">{_inr(t["concession_cost"])} of margin given up</span></div>')
    a(f'<div class="kpi"><span class="k">Net recovery</span>'
      f'<span class="v">{_inr(t["net_recovery"])}</span>'
      f'<span class="n">margin − concession − action cost</span></div>')
    a("</div>")

    llm = summary.get("llm")
    if llm:
        if not llm.get("active"):
            a('<div class="banner"><b>Buyer agents: model requested but not active.</b>'
              f'<ul><li>{html.escape(str(llm.get("error", "")))[:300]}</li>'
              '<li>The heuristic ran instead — do not report this as a model run.</li>'
              '</ul></div>')
        else:
            rows = [f"{llm['decisions_from_model']} of {llm['calls']} decisions from "
                    f"{html.escape(llm['provider'])}"]
            if llm.get("keys", 1) > 1:
                rows.append(f"{llm['keys']} keys, {llm['key_rotations']} rotation(s), "
                            f"{llm['total_tokens']:,} tokens")
            if llm.get("mixed_run"):
                rows.append("<b>MIXED RUN — these figures are attributable to "
                            "neither backend.</b>")
            elif llm.get("fallbacks"):
                rows.append(f"{llm['fallbacks']} call(s) fell back to the heuristic "
                            f"({llm['model_share']:.1%} from the model)")
            if llm.get("mixed_model_run"):
                rows.append("<b>MIXED-MODEL RUN — "
                            f"{', '.join(llm['models_used'])}</b>")
            a('<div class="banner"><b>Run provenance.</b><ul>'
              + "".join(f"<li>{r}</li>" for r in rows) + "</ul></div>")

    a('<div class="banner"><b>Simulated in this run.</b><ul>'
      + "".join(f"<li>{html.escape(s)}</li>" for s in summary["simulated_components"])
      + "</ul></div>")

    # ---- arms ----
    a("<h2>Treatment against control</h2>")
    a('<p>Allocation is randomised at session creation and stratified by injected fault, '
      'so both arms carry the same failure mix. The control arm is fully instrumented and '
      'receives no intervention; what it recovers, buyers recovered by themselves.</p>')
    a('<div class="tw"><table><thead><tr><th>Measure</th><th class="n">Treatment</th>'
      '<th class="n">Control</th></tr></thead><tbody>')
    rows = [("Sessions", "sessions", "{:,}"), ("Failed", "failed", "{:,}"),
            ("At-risk GMV", "at_risk_gmv", "₹{:,.0f}"),
            ("Recovered GMV", "recovered_gmv", "₹{:,.0f}"),
            ("Recovery rate", "recovery_rate", "{:.2%}"),
            ("Concession cost", "concession_cost", "₹{:,.0f}"),
            ("Concession ratio", "concession_ratio", "{:.2%}"),
            ("Interventions executed", "interventions", "{:,}"),
            ("Net recovery", "net_recovery", "₹{:,.0f}")]
    for label, key, fmt in rows:
        a(f'<tr><td>{label}</td><td class="n">{fmt.format(t[key])}</td>'
          f'<td class="n">{fmt.format(c[key])}</td></tr>')
    a("</tbody></table></div>")

    # ---- per cause ----
    a("<h2>Recovery by root cause</h2>")
    a('<p>Bars show recovered GMV as a share of the GMV at risk in that class. '
      'The spread is the finding: data defects recover almost completely, '
      'consent-bound and funds-bound failures do not.</p>')
    a('<div class="tw"><table><thead><tr><th>Cause</th><th>Class</th><th class="n">Failed</th>'
      '<th class="n">At-risk</th><th class="n">Recovered</th><th>Recovery of at-risk GMV</th>'
      '</tr></thead><tbody>')
    for k, v in summary["per_cause"].items():
        name = CAUSES[k].name if k in CAUSES else "unclassified"
        pct = f"{v['recovery_rate'] * 100:.0f}%"
        a(f'<tr><td class="id">{k}</td><td>{name.replace("_", " ")}</td>'
          f'<td class="n">{v["failed"]}</td><td class="n">{_inr(v["at_risk_gmv"])}</td>'
          f'<td class="n">{_inr(v["recovered_gmv"])}</td>'
          f'<td>{_bar(v["recovered_gmv"], v["at_risk_gmv"], pct)}</td></tr>')
    a("</tbody></table></div>")

    # ---- diagnosis ----
    a("<h2>Diagnosis accuracy</h2>")
    a(f'<p>Scored against the injected fault, which the engine never reads. '
      f'Macro-F1 <b>{d["macro_f1"]}</b> across {d["scored_sessions"]} labelled sessions. '
      f'{d["unclassified"]} sessions were left unclassified: where a rail returns a decline '
      f'with no usable reason code, the engine refuses to guess and rule R-10 stops any action.</p>')
    a('<div class="tw"><table><thead><tr><th>Cause</th><th>Class</th><th class="n">Support</th>'
      '<th class="n">Precision</th><th class="n">Recall</th><th class="n">F1</th>'
      '</tr></thead><tbody>')
    for k, v in d["per_class"].items():
        name = CAUSES[k].name if k in CAUSES else k
        a(f'<tr><td class="id">{k}</td><td>{name.replace("_", " ")}</td>'
          f'<td class="n">{v["support"]}</td><td class="n">{v["precision"]:.2f}</td>'
          f'<td class="n">{v["recall"]:.2f}</td><td class="n">{v["f1"]:.2f}</td></tr>')
    a("</tbody></table></div>")

    # ---- governance ----
    a("<h2>What the gate refused</h2>")
    a('<p>Refusals are recorded with the same standing as permits. They are the evidence '
      'that the policy engine exists and that an LLM never had the last word on money.</p>')
    a('<div class="tw"><table><thead><tr><th>Rule</th><th>What it stops</th>'
      '<th class="n">Times fired</th></tr></thead><tbody>')
    for k, n in summary["policy_refusals"].items():
        a(f'<tr><td class="id">{k}</td><td>{RULES[k]}</td><td class="n">{n}</td></tr>')
    a("</tbody></table></div>")
    not_fired = [r for r in summary["rules_not_observed"]]
    if not_fired:
        a(f'<p class="sub">Not observed refusing in this batch: {", ".join(not_fired)} '
          f'— each is covered by a unit test instead.</p>')

    # ---- exceptions ----
    a("<h2>Exceptions we could not resolve</h2>")
    a(f'<p>{summary["exception_count"]} sessions ended without recovery. The full list '
      f'ships with the run; the largest by value are shown here.</p>')
    top = sorted(exceptions, key=lambda e: -e["basket_value"])[:12]
    a('<div class="tw"><table><thead><tr><th>Session</th><th>Cause</th>'
      '<th class="n">At risk</th><th>Why it stopped</th></tr></thead><tbody>')
    for e in top:
        a(f'<tr><td class="id">{e["session_id"]}</td>'
          f'<td class="id">{e["diagnosed_cause"]}</td>'
          f'<td class="n">{_inr(e["basket_value"])}</td>'
          f'<td>{html.escape(e["exception"])}</td></tr>')
    a("</tbody></table></div>")

    # ---- audit trail ----
    if chain:
        a("<h2>Audit trail for one recovery</h2>")
        a(f'<p>Session <span class="id">{sample["session_id"]}</span>, '
          f'{_inr(sample["basket_value"])} at risk, recovered at '
          f'{_inr(sample["recovered_value"])} via '
          f'{", ".join(sample["interventions"])}. Every rule evaluated is recorded, '
          f'including the ones that passed.</p>')
        a('<div class="chain">')
        for e in chain:
            a('<div class="entry"><div class="top">'
              f'<span class="actor">{e["actor"].replace("_", " ")} — {e["action"].replace("_", " ")}</span>'
              f'<span class="hash">prev {e["prev_hash"][:10]} → {e["hash"][:10]}</span></div>')
            body = {k: v for k, v in e.items()
                    if k in ("trigger", "diagnosis", "outcome", "reversal") and v}
            if body:
                a(f"<pre>{html.escape(json.dumps(body, indent=2, default=str))}</pre>")
            if e["policy_checks"]:
                a('<div class="chk">')
                for chk in e["policy_checks"]:
                    cls = " class='fail'" if chk["result"] == "fail" else ""
                    a(f"<span{cls}>{chk['rule']} {chk['state']} · {chk['result']}</span>")
                a("</div>")
            a("</div>")
        a("</div>")
        ok, bad = ledger.verify()
        a(f'<div class="note">Hash chain over the whole batch: '
          f'<b>{"verified" if ok else "BROKEN at entry " + str(bad)}</b> across '
          f'{summary["ledger"]["entries"]} entries.</div>')

    a("<footer>Handshake — recovery layer for agent-driven checkout · "
      "Razorpay AI Buildathon 2026, Track 03<br>"
      "All payment integrations run in test mode. Figures are from the batch named above "
      "and reproduce exactly from its seed.</footer>")
    a("</div>")

    with open(path, "w") as fh:
        fh.write("\n".join(out))
    return path
