"""The console page. Served as one self-contained document — no build step."""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Handshake — live console</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;500;600&display=swap">
<style>
:root{
  --paper:#F3F5F2; --surface:#FFF; --sunk:#EAEEE9; --ink:#131C18; --soft:#4A5751;
  --faint:#6B7873; --rule:#D5DDD7; --rule2:#E4EAE5; --accent:#126B47;
  --accent-soft:#E2EFE7; --signal:#A8412A; --signal-soft:#F6E7E2;
  --warn:#8A6414; --warn-soft:#F5EEDC;
  --fd:"IBM Plex Sans Condensed",Arial,sans-serif;
  --fb:"IBM Plex Serif",Georgia,serif;
  --fm:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0E1512; --surface:#151E1A; --sunk:#111A16; --ink:#E2E9E4; --soft:#A8B5AE;
  --faint:#7F8D86; --rule:#26332C; --rule2:#1D2823; --accent:#57B385;
  --accent-soft:#14291F; --signal:#DE7A5E; --signal-soft:#2B1B15;
  --warn:#D0A64A; --warn-soft:#29220F;}}
:root[data-theme="dark"]{
  --paper:#0E1512; --surface:#151E1A; --sunk:#111A16; --ink:#E2E9E4; --soft:#A8B5AE;
  --faint:#7F8D86; --rule:#26332C; --rule2:#1D2823; --accent:#57B385;
  --accent-soft:#14291F; --signal:#DE7A5E; --signal-soft:#2B1B15;
  --warn:#D0A64A; --warn-soft:#29220F;}

*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--fb);font-size:14px;
 line-height:1.5;margin:0;-webkit-font-smoothing:antialiased}
.wrap{max-width:1400px;margin:0 auto;padding:20px 22px 60px}

/* ---------- header ---------- */
header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;
 flex-wrap:wrap;border-bottom:2px solid var(--ink);padding-bottom:12px}
.brand{display:flex;flex-direction:column;gap:2px}
.eyebrow{font-family:var(--fm);font-size:9.5px;letter-spacing:.13em;
 text-transform:uppercase;color:var(--accent)}
h1{font-family:var(--fd);font-size:30px;font-weight:700;letter-spacing:-.02em;margin:0}
.badges{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{font-family:var(--fm);font-size:10px;padding:3px 8px;border:1px solid var(--rule);
 background:var(--surface);color:var(--soft);letter-spacing:.03em}
.badge.live{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.badge.sim{border-color:var(--warn);color:var(--warn);background:var(--warn-soft)}

/* ---------- controls ---------- */
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
 padding:14px 0;border-bottom:1px solid var(--rule)}
button{font-family:var(--fd);font-size:13.5px;font-weight:600;padding:8px 15px;
 border:1px solid var(--ink);background:var(--ink);color:var(--paper);cursor:pointer;
 letter-spacing:.01em}
button.ghost{background:transparent;color:var(--ink)}
button.danger{border-color:var(--signal);background:var(--signal);color:#fff}
button:disabled{opacity:.4;cursor:not-allowed}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input[type=number]{font-family:var(--fm);font-size:13px;width:82px;padding:7px 9px;
 border:1px solid var(--rule);background:var(--surface);color:var(--ink)}
label.inline{font-family:var(--fm);font-size:10.5px;color:var(--faint);
 letter-spacing:.06em;text-transform:uppercase;display:flex;gap:6px;align-items:center}
.spacer{flex:1}
.switch{display:flex;align-items:center;gap:8px;font-family:var(--fm);font-size:11px;
 color:var(--soft);border:1px solid var(--rule);padding:6px 10px;background:var(--surface)}
.switch.on{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}

/* ---------- kpis ---------- */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
 background:var(--rule);border:1px solid var(--rule);margin:18px 0 0}
.kpi{background:var(--surface);padding:13px 15px;display:flex;flex-direction:column;gap:3px}
.kpi .k{font-family:var(--fm);font-size:9px;letter-spacing:.1em;text-transform:uppercase;
 color:var(--faint)}
.kpi .v{font-family:var(--fd);font-size:25px;font-weight:700;letter-spacing:-.02em;
 font-variant-numeric:tabular-nums;line-height:1.05}
.kpi .n{font-family:var(--fm);font-size:9.5px;color:var(--soft)}
.kpi.good .v{color:var(--accent)}

/* ---------- progress ---------- */
.bar{height:3px;background:var(--sunk);margin-top:14px;overflow:hidden}
.bar i{display:block;height:3px;background:var(--accent);width:0;
 transition:width .25s linear}

/* ---------- grid ---------- */
.grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:22px;
 margin-top:22px}
@media(max-width:1000px){.grid{grid-template-columns:1fr}}
h2{font-family:var(--fd);font-size:15px;font-weight:700;margin:0 0 8px;
 padding-bottom:6px;border-bottom:1.5px solid var(--ink);
 display:flex;justify-content:space-between;align-items:baseline}
h2 span{font-family:var(--fm);font-size:10px;color:var(--faint);font-weight:400}

.panel{background:var(--surface);border:1px solid var(--rule)}
.stream{max-height:420px;overflow-y:auto}
.row{display:grid;grid-template-columns:76px 1fr 62px 78px 20px;gap:8px;
 padding:7px 11px;border-bottom:1px solid var(--rule2);align-items:center;
 font-family:var(--fm);font-size:10.5px;cursor:pointer}
.row:hover{background:var(--sunk)}
.row .sid{color:var(--accent)}
.row .what{font-family:var(--fd);font-size:12.5px;color:var(--soft)}
.row .amt{text-align:right;font-variant-numeric:tabular-nums}
.row .tag{font-size:9px;padding:1px 5px;border:1px solid var(--rule);text-align:center}
.row.ok .tag{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.row.fail .tag{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}
.row .dot{width:7px;height:7px;border-radius:50%;background:var(--rule)}
.row.ok .dot{background:var(--accent)}
.row.fail .dot{background:var(--signal)}

/* ---------- pipeline ---------- */
.stages{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;padding:12px}
.stage{border:1px solid var(--rule);border-top:2.5px solid var(--rule);padding:8px 9px;
 display:flex;flex-direction:column;gap:3px;min-height:74px;background:var(--paper);
 transition:border-color .2s,background .2s}
.stage.active{border-top-color:var(--accent);background:var(--accent-soft)}
.stage.blocked{border-top-color:var(--signal);background:var(--signal-soft)}
.stage .s-n{font-family:var(--fm);font-size:8.5px;color:var(--faint);letter-spacing:.08em}
.stage .s-t{font-family:var(--fd);font-weight:600;font-size:12.5px;line-height:1.15}
.stage .s-d{font-family:var(--fm);font-size:9.5px;line-height:1.35;color:var(--soft);
 word-break:break-word}
.checks{display:flex;flex-wrap:wrap;gap:4px;padding:0 12px 12px}
.chk{font-family:var(--fm);font-size:9px;padding:2px 6px;border:1px solid var(--rule);
 background:var(--sunk);color:var(--soft)}
.chk.fail{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}
.narrate{font-family:var(--fb);font-size:13px;color:var(--soft);padding:0 12px 12px;
 border-bottom:1px solid var(--rule2);margin-bottom:10px}
.narrate b{color:var(--ink);font-weight:600}

/* ---------- tables ---------- */
table{border-collapse:collapse;width:100%;font-family:var(--fd);font-size:12.5px}
th{text-align:left;font-family:var(--fm);font-size:9px;letter-spacing:.09em;
 text-transform:uppercase;color:var(--faint);font-weight:500;padding:7px 10px 7px 0;
 border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:6px 10px 6px 0;border-bottom:1px solid var(--rule2);vertical-align:middle}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th.n{text-align:right}
.cid{font-family:var(--fm);font-size:10.5px;color:var(--accent)}
.tbar{display:block;height:7px;background:var(--sunk);min-width:70px}
.tbar i{display:block;height:7px;background:var(--accent)}
.tw{padding:0 12px 10px}

/* ---------- ledger ---------- */
.entry{border-bottom:1px solid var(--rule2);padding:10px 12px}
.entry .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;
 align-items:baseline;margin-bottom:4px}
.entry .actor{font-family:var(--fd);font-weight:600;font-size:12.5px}
.entry .hash{font-family:var(--fm);font-size:9px;color:var(--faint)}
pre{font-family:var(--fm);font-size:10px;line-height:1.5;background:var(--sunk);
 border:1px solid var(--rule2);padding:8px 10px;overflow-x:auto;margin:4px 0 0}
.empty{font-family:var(--fm);font-size:11px;color:var(--faint);padding:18px 12px}
.note{font-family:var(--fb);font-size:12.5px;color:var(--soft);padding:10px 12px;
 border-left:3px solid var(--accent);background:var(--accent-soft);margin:10px 12px}
.note.warn{border-left-color:var(--warn);background:var(--warn-soft)}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="brand">
    <span class="eyebrow">Recovery layer for agent-driven checkout</span>
    <h1>Handshake</h1>
  </div>
  <div class="badges" id="badges"></div>
</header>

<div class="controls">
  <label class="inline">sessions <input type="number" id="sessions" value="200" min="10" max="2000" step="10"></label>
  <button id="run">Run batch</button>
  <button id="walk" class="ghost">Walkthrough</button>
  <button id="stop" class="ghost" disabled>Stop</button>
  <label class="inline"><input type="checkbox" id="offline"> offline</label>
  <div class="spacer"></div>
  <div class="switch" id="ks" role="button" tabindex="0">KILL SWITCH · R-11 · off</div>
</div>

<div class="kpis" id="kpis"></div>
<div class="bar"><i id="prog"></i></div>

<div class="grid">
  <section>
    <h2>Live sessions <span id="streamcount">idle</span></h2>
    <div class="panel stream" id="stream"><div class="empty">Run a batch to begin.</div></div>

    <h2 style="margin-top:22px">Recovery by root cause <span>treatment arm</span></h2>
    <div class="panel"><div class="tw"><table id="causes"><tbody>
      <tr><td class="empty">No failures yet.</td></tr></tbody></table></div></div>
  </section>

  <section>
    <h2>Current session <span id="cursid">—</span></h2>
    <div class="panel">
      <div class="narrate" id="narrate">Pick <b>Walkthrough</b> to step through one recovery slowly, or <b>Run batch</b> to watch the whole thing.</div>
      <div class="stages" id="stages"></div>
      <div class="checks" id="checks"></div>
    </div>

    <h2 style="margin-top:22px">What the gate refused <span id="refcount"></span></h2>
    <div class="panel"><div class="tw"><table id="refusals"><tbody>
      <tr><td class="empty">Nothing refused yet.</td></tr></tbody></table></div></div>

    <h2 style="margin-top:22px">Audit chain <span id="chainstate"></span></h2>
    <div class="panel" id="ledger"><div class="empty">Click a session once a run has finished.</div></div>
  </section>
</div>
</div>

<script>
const STAGES = [
  ["STAGE 1","Detect","instrument the session, catch terminal failure"],
  ["STAGE 2","Diagnose","classify root cause with a confidence score"],
  ["STAGE 3","Decide","pick one intervention from a fixed table"],
  ["STAGE 4","Gate","evaluate every bound — no model runs here"],
  ["STAGE 5","Execute","act against Razorpay and the merchant"],
  ["STAGE 6","Record","append a hash-chained audit entry"],
  ["STAGE 7","Measure","report against the control arm"],
];
let since = 0, timer = null, current = null, rows = 0;
const $ = id => document.getElementById(id);
const inr = v => "₹" + Math.round(v).toLocaleString("en-IN");

function drawStages(state){
  $("stages").innerHTML = STAGES.map((s,i)=>{
    const st = state[i] || {};
    const cls = st.blocked ? "stage blocked" : (st.on ? "stage active" : "stage");
    return `<div class="${cls}"><span class="s-n">${s[0]}</span>
      <span class="s-t">${s[1]}</span>
      <span class="s-d">${st.detail || s[2]}</span></div>`;
  }).join("");
}
drawStages([]);

function resetSession(sid){
  current = {sid, stages:[{},{},{},{},{},{},{}], checks:[]};
  $("cursid").textContent = sid;
  drawStages(current.stages);
  $("checks").innerHTML = "";
}

function setStage(i, detail, blocked){
  if(!current) return;
  current.stages[i] = {on:true, detail, blocked:!!blocked};
  drawStages(current.stages);
}

function narrate(html){ $("narrate").innerHTML = html; }

function addRow(e){
  const stream = $("stream");
  if(rows === 0) stream.innerHTML = "";
  const ok = e.recovered, failed = e.terminal === "FAILED" && !e.recovered;
  const cls = ok ? "row ok" : (failed ? "row fail" : "row");
  const what = ok ? ("recovered · " + (e.interventions||[]).join(", "))
    : (failed ? (e.cause ? e.cause + " · " + (e.exception || "unresolved") : "failed")
              : "converted first pass");
  const amt = ok ? e.recovered_value : (failed ? e.basket_value : e.basket_value);
  const div = document.createElement("div");
  div.className = cls;
  div.dataset.sid = e.session_id;
  div.innerHTML = `<span class="sid">${e.session_id}</span>
    <span class="what">${what}</span>
    <span class="tag">${e.arm === "treatment" ? "TREAT" : "CTRL"}</span>
    <span class="amt">${inr(amt)}</span><span class="dot"></span>`;
  div.onclick = () => loadChain(e.session_id);
  stream.insertBefore(div, stream.firstChild);
  rows++;
  while(stream.children.length > 250) stream.removeChild(stream.lastChild);
}

function handle(e){
  switch(e.kind){
    case "session_start":
      resetSession(e.session_id);
      narrate(`Agent <b>${e.buyer}</b> (${e.persona}) shopping <b>${e.category}</b>, delegated cap ${inr(e.cap)}.`);
      break;
    case "failure_detected":
      setStage(0, `at risk ${inr(e.at_risk)} — ${e.note}`);
      narrate(`Session died with <b>${inr(e.at_risk)}</b> at risk. The merchant sees an API session that opened and stopped — no reason code, no way to reach the buyer.`);
      break;
    case "diagnosis":
      setStage(1, `${e.cause} · confidence ${e.confidence.toFixed(2)} · ${e.method}`);
      narrate(`Cause assigned: <b>${e.cause}</b> at confidence ${e.confidence.toFixed(2)}, from the ${e.method} tier.`);
      break;
    case "verdict":
      $("checks").innerHTML = (e.checks||[]).map(c =>
        `<span class="chk ${c.result === "fail" ? "fail" : ""}">${c.rule} ${c.state} · ${c.result}</span>`).join("");
      if(e.permitted){
        setStage(2, "intervention " + e.intervention);
        setStage(3, "all bounds passed");
        narrate(`Gate permits <b>${e.intervention}</b>. Every rule evaluated is recorded, including the ones that passed.`);
      } else {
        setStage(2, "no action");
        setStage(3, `${e.binding_rule} — ${e.reason}`, true);
        narrate(`Gate <b>refused</b>: ${e.binding_rule} — ${e.reason}. The refusal is written to the ledger with the same standing as a permit.`);
      }
      break;
    case "action":
      setStage(4, `${e.intervention} · ${e.note}`, !e.ok);
      setStage(5, e.concession ? `concession ${inr(e.concession)}` : "no margin surrendered");
      break;
    case "recovered":
      setStage(6, `converted at ${inr(e.value)}`);
      narrate(`Recovered <b>${inr(e.value)}</b> via ${e.intervention}. Click the session to open its audit chain.`);
      break;
    case "session_end": addRow(e); break;
    case "progress":
      $("prog").style.width = (100 * e.done / Math.max(1, e.total)) + "%";
      $("streamcount").textContent = `${e.done} / ${e.total}`;
      break;
    case "done":
      narrate(`Batch complete — <b>${inr(e.recovered)}</b> recovered, lift ${(e.lift*100).toFixed(1)} points over control.`);
      break;
    case "error":
      narrate(`<b style="color:var(--signal)">Run aborted.</b> ${e.message}`);
      break;
  }
}

function kpis(t, s){
  const lift = s ? (s.lift*100).toFixed(1) + " pts" : "—";
  const liftNote = s ? `control ${(s.control.recovery_rate*100).toFixed(1)}%` : "at end of run";
  $("kpis").innerHTML = `
    <div class="kpi"><span class="k">At-risk GMV</span><span class="v">${inr(t.at_risk)}</span>
      <span class="n">${t.failed} failed sessions</span></div>
    <div class="kpi good"><span class="k">Recovered GMV</span><span class="v">${inr(t.recovered)}</span>
      <span class="n">${(t.rate*100).toFixed(1)}% of at-risk</span></div>
    <div class="kpi good"><span class="k">Lift over control</span><span class="v">${lift}</span>
      <span class="n">${liftNote}</span></div>
    <div class="kpi"><span class="k">Concession ratio</span><span class="v">${(t.concession_ratio*100).toFixed(2)}%</span>
      <span class="n">${inr(t.concession)} of margin</span></div>
    <div class="kpi"><span class="k">Recoveries</span><span class="v">${t.recovered_n}</span>
      <span class="n">${s ? "macro-F1 " + s.macro_f1 : "sessions won back"}</span></div>`;
}

function causes(c){
  const keys = Object.keys(c);
  if(!keys.length){
    $("causes").innerHTML = '<tbody><tr><td class="empty">No failures yet.</td></tr></tbody>';
    return;
  }
  const max = Math.max(...keys.map(k => c[k].at_risk));
  $("causes").innerHTML = "<thead><tr><th>Cause</th><th>Class</th><th class='n'>Failed</th>"
    + "<th class='n'>At risk</th><th class='n'>Recovered</th><th>Rate</th></tr></thead><tbody>"
    + keys.map(k => {
        const v = c[k];
        return `<tr><td class="cid">${k}</td><td>${v.name.replace(/_/g," ")}</td>
        <td class="n">${v.failed}</td><td class="n">${inr(v.at_risk)}</td>
        <td class="n">${inr(v.recovered)}</td>
        <td><span class="tbar"><i style="width:${(100*v.recovered/(v.at_risk||1)).toFixed(0)}%"></i></span></td></tr>`;
      }).join("") + "</tbody>";
}

function refusals(r){
  const keys = Object.keys(r);
  $("refcount").textContent = keys.length ? keys.length + " rule(s)" : "";
  if(!keys.length){
    $("refusals").innerHTML = '<tbody><tr><td class="empty">Nothing refused yet.</td></tr></tbody>';
    return;
  }
  $("refusals").innerHTML = "<tbody>" + keys.map(k =>
    `<tr><td class="cid">${k}</td><td>${r[k].rule}</td><td class="n">${r[k].count}</td></tr>`
  ).join("") + "</tbody>";
}

function badges(b, pool, ks, sim){
  const out = [];
  out.push(`<span class="badge ${b.payments === "razorpay" ? "live" : "sim"}">payments: ${b.payments}</span>`);
  out.push(`<span class="badge ${b.buyers === "llm" ? "live" : "sim"}">buyers: ${b.buyers}</span>`);
  (pool||[]).forEach(p => out.push(
    `<span class="badge ${p.exhausted ? "sim" : ""}">${p.key} ${p.calls} calls · ${p.tokens.toLocaleString()} tok${p.exhausted ? " · spent" : ""}</span>`));
  if(ks) out.push('<span class="badge sim">KILL SWITCH ON</span>');
  $("badges").innerHTML = out.join("");
}

async function loadChain(sid){
  const r = await fetch("/api/session/" + sid);
  if(!r.ok){ $("ledger").innerHTML = '<div class="empty">The chain is available once the run finishes.</div>'; return; }
  const d = await r.json();
  $("chainstate").textContent = d.chain_valid ? "verified" : "BROKEN at " + d.first_bad;
  if(!d.entries.length){ $("ledger").innerHTML = '<div class="empty">No ledger entries — this session did not fail.</div>'; return; }
  $("ledger").innerHTML = d.entries.map(e => {
    const body = {};
    ["trigger","diagnosis","outcome","reversal"].forEach(k => {
      if(e[k] && Object.keys(e[k]).length) body[k] = e[k]; });
    const chips = (e.policy_checks||[]).map(c =>
      `<span class="chk ${c.result === "fail" ? "fail" : ""}">${c.rule} ${c.state} · ${c.result}</span>`).join("");
    return `<div class="entry"><div class="top">
      <span class="actor">${e.actor.replace(/_/g," ")} — ${e.action.replace(/_/g," ")}</span>
      <span class="hash">prev ${e.prev_hash.slice(0,10)} → ${e.hash.slice(0,10)}</span></div>
      ${Object.keys(body).length ? "<pre>" + JSON.stringify(body,null,2) + "</pre>" : ""}
      ${chips ? '<div class="checks" style="padding:6px 0 0">' + chips + "</div>" : ""}</div>`;
  }).join("");
}

async function poll(){
  const r = await fetch("/api/state?since=" + since);
  const d = await r.json();
  since = d.next;
  d.events.forEach(handle);
  kpis(d.totals, d.measured === false ? null : d.summary);
  const warn = d.measured === false;
  document.getElementById("kpis").style.opacity = warn ? "0.85" : "1";
  if(warn && !document.getElementById("walkwarn")){
    const n = document.createElement("div");
    n.id = "walkwarn"; n.className = "note warn";
    n.innerHTML = "<b>Walkthrough mode.</b> Every session is in the treatment arm so the "
      + "recovery path always runs. There is no control arm, so these totals are a "
      + "demonstration, not a measurement. Use <b>Run batch</b> for figures you can quote.";
    document.querySelector(".kpis").after(n);
  }
  if(!warn && document.getElementById("walkwarn")) document.getElementById("walkwarn").remove();
  causes(d.totals.causes);
  refusals(d.totals.refusals);
  badges(d.backends, d.pool, d.kill_switch, d.summary && d.summary.simulated);
  $("run").disabled = d.running; $("walk").disabled = d.running;
  $("stop").disabled = !d.running;
  if(!d.running && timer){ clearInterval(timer); timer = null; $("prog").style.width = "100%"; }
}

async function start(mode){
  since = 0; rows = 0;
  $("stream").innerHTML = '<div class="empty">starting…</div>';
  $("ledger").innerHTML = '<div class="empty">Click a session once the run has finished.</div>';
  await fetch("/api/run", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({sessions: +$("sessions").value, mode,
      offline: $("offline").checked})});
  if(timer) clearInterval(timer);
  timer = setInterval(poll, mode === "walkthrough" ? 250 : 450);
  poll();
}

$("run").onclick = () => start("batch");
$("walk").onclick = () => start("walkthrough");
$("stop").onclick = () => fetch("/api/stop", {method:"POST"});
$("ks").onclick = async () => {
  const on = !$("ks").classList.contains("on");
  await fetch("/api/killswitch", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({on})});
  $("ks").classList.toggle("on", on);
  $("ks").textContent = "KILL SWITCH · R-11 · " + (on ? "ON" : "off");
};
$("ks").onkeydown = e => { if(e.key === "Enter" || e.key === " ") $("ks").click(); };

kpis({at_risk:0,recovered:0,failed:0,recovered_n:0,rate:0,concession:0,concession_ratio:0});
poll();
</script>
</body>
</html>
"""
