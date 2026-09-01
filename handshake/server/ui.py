"""The console page — one self-contained document, no build step."""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Handshake — recovery for agent-driven checkout</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700&family=IBM+Plex+Serif:ital,wght@0,400;0,500;0,600;1,400&display=swap">
<style>
:root{
  --paper:#F3F5F2; --surface:#FFF; --sunk:#EAEEE9; --ink:#131C18; --soft:#4A5751;
  --faint:#6B7873; --rule:#D5DDD7; --rule2:#E4EAE5; --accent:#0F6B45;
  --accent-soft:#E2EFE7; --signal:#A8412A; --signal-soft:#F6E7E2;
  --warn:#8A6414; --warn-soft:#F5EEDC; --track:#DDE4DE;
  --fd:"IBM Plex Sans Condensed",Arial,sans-serif;
  --fb:"IBM Plex Serif",Georgia,serif;
  --fm:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --shadow:0 1px 2px rgba(19,28,24,.06), 0 8px 24px rgba(19,28,24,.06);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0D1411; --surface:#141D19; --sunk:#101815; --ink:#E3EAE5; --soft:#A9B6AF;
  --faint:#7F8D86; --rule:#25322B; --rule2:#1C2722; --accent:#5CBA8A;
  --accent-soft:#12281E; --signal:#E0805F; --signal-soft:#2B1B15;
  --warn:#D3A94D; --warn-soft:#29220F; --track:#1E2A24;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);}}
:root[data-theme="dark"]{
  --paper:#0D1411; --surface:#141D19; --sunk:#101815; --ink:#E3EAE5; --soft:#A9B6AF;
  --faint:#7F8D86; --rule:#25322B; --rule2:#1C2722; --accent:#5CBA8A;
  --accent-soft:#12281E; --signal:#E0805F; --signal-soft:#2B1B15;
  --warn:#D3A94D; --warn-soft:#29220F; --track:#1E2A24;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);}

*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--paper);color:var(--ink);font-family:var(--fb);font-size:14.5px;
 line-height:1.55;margin:0;-webkit-font-smoothing:antialiased}
.wrap{max-width:1360px;margin:0 auto;padding:0 22px 80px}

/* ---------- top bar ---------- */
.top{position:sticky;top:0;z-index:40;background:var(--paper);
 border-bottom:1px solid var(--rule);padding:14px 0 0}
.topin{max-width:1360px;margin:0 auto;padding:0 22px;display:flex;
 justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;gap:1px}
.eyebrow{font-family:var(--fm);font-size:9px;letter-spacing:.14em;
 text-transform:uppercase;color:var(--accent)}
h1{font-family:var(--fd);font-size:26px;font-weight:700;letter-spacing:-.02em;margin:0}
.badges{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{font-family:var(--fm);font-size:9.5px;padding:3px 7px;border:1px solid var(--rule);
 background:var(--surface);color:var(--soft);letter-spacing:.03em;white-space:nowrap}
.badge.live{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.badge.sim{border-color:var(--warn);color:var(--warn);background:var(--warn-soft)}
.badge.alert{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}
.iconbtn{font-family:var(--fm);font-size:10px;padding:4px 8px;border:1px solid var(--rule);
 background:var(--surface);color:var(--soft);cursor:pointer}

/* ---------- tabs ---------- */
nav.tabs{max-width:1360px;margin:12px auto 0;padding:0 22px;display:flex;gap:2px;
 flex-wrap:wrap}
nav.tabs button{font-family:var(--fd);font-size:13.5px;font-weight:600;
 padding:8px 14px;border:1px solid var(--rule);border-bottom:none;
 background:transparent;color:var(--soft);cursor:pointer;letter-spacing:.01em}
nav.tabs button[aria-selected="true"]{background:var(--surface);color:var(--ink);
 border-color:var(--rule);box-shadow:inset 0 2px 0 var(--accent)}
nav.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}

section.tab{display:none;padding-top:26px}
section.tab.on{display:block}

/* ---------- controls ---------- */
.controls{display:flex;gap:9px;align-items:center;flex-wrap:wrap;
 padding:13px 15px;background:var(--surface);border:1px solid var(--rule)}
button.act{font-family:var(--fd);font-size:13.5px;font-weight:600;padding:8px 15px;
 border:1px solid var(--ink);background:var(--ink);color:var(--paper);cursor:pointer}
button.ghost{background:transparent;color:var(--ink)}
button.act:disabled{opacity:.35;cursor:not-allowed}
button.act:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input[type=number]{font-family:var(--fm);font-size:12.5px;width:78px;padding:6px 8px;
 border:1px solid var(--rule);background:var(--paper);color:var(--ink)}
label.inline{font-family:var(--fm);font-size:10px;color:var(--faint);
 letter-spacing:.06em;text-transform:uppercase;display:flex;gap:6px;align-items:center}
.spacer{flex:1}
.switch{font-family:var(--fm);font-size:10.5px;color:var(--soft);
 border:1px solid var(--rule);padding:6px 10px;background:var(--paper);cursor:pointer}
.switch.on{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}

/* ---------- kpis ---------- */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:1px;
 background:var(--rule);border:1px solid var(--rule);margin-top:16px}
.kpi{background:var(--surface);padding:13px 15px;display:flex;flex-direction:column;gap:2px}
.kpi .k{font-family:var(--fm);font-size:8.5px;letter-spacing:.11em;
 text-transform:uppercase;color:var(--faint)}
.kpi .v{font-family:var(--fd);font-size:25px;font-weight:700;letter-spacing:-.02em;
 font-variant-numeric:tabular-nums;line-height:1.1}
.kpi .n{font-family:var(--fm);font-size:9.5px;color:var(--soft);line-height:1.4}
.kpi.good .v{color:var(--accent)}
.kpi.bad .v{color:var(--signal)}

.bar{height:3px;background:var(--track);margin-top:12px;overflow:hidden}
.bar i{display:block;height:3px;background:var(--accent);width:0;transition:width .25s linear}

/* ---------- layout ---------- */
.grid{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,1fr);gap:20px;
 margin-top:20px}
.grid.one{grid-template-columns:1fr}
@media(max-width:1020px){.grid{grid-template-columns:1fr}}
h2{font-family:var(--fd);font-size:14.5px;font-weight:700;margin:0 0 8px;
 padding-bottom:6px;border-bottom:1.5px solid var(--ink);display:flex;
 justify-content:space-between;align-items:baseline;gap:10px}
h2 span{font-family:var(--fm);font-size:9.5px;color:var(--faint);font-weight:400}
h3{font-family:var(--fd);font-size:16px;font-weight:700;margin:26px 0 8px}
.mt{margin-top:22px}
.panel{background:var(--surface);border:1px solid var(--rule)}
p{margin:0 0 12px;max-width:70ch}
.lead{font-size:16px;color:var(--soft);max-width:72ch}
.lead b{color:var(--ink);font-weight:600}

/* ---------- stream ---------- */
.stream{max-height:400px;overflow-y:auto}
.row{display:grid;grid-template-columns:74px 1fr 56px 76px 16px;gap:8px;
 padding:6px 11px;border-bottom:1px solid var(--rule2);align-items:center;
 font-family:var(--fm);font-size:10px;cursor:pointer;background:none;border-left:none;
 border-right:none;border-top:none;width:100%;text-align:left;color:inherit}
.row:hover{background:var(--sunk)}
.row:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.row .sid{color:var(--accent)}
.row .what{font-family:var(--fd);font-size:12px;color:var(--soft);overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.row .amt{text-align:right;font-variant-numeric:tabular-nums}
.row .tag{font-size:8.5px;padding:1px 4px;border:1px solid var(--rule);text-align:center}
.row.ok .tag{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.row.fail .tag{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}
.row .dot{width:6px;height:6px;border-radius:50%;background:var(--rule)}
.row.ok .dot{background:var(--accent)}
.row.fail .dot{background:var(--signal)}

/* ---------- pipeline ---------- */
.stages{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;padding:11px}
.stage{border:1px solid var(--rule);border-top:2.5px solid var(--track);padding:7px 8px;
 display:flex;flex-direction:column;gap:2px;min-height:70px;background:var(--paper);
 transition:border-color .18s,background .18s}
.stage.active{border-top-color:var(--accent);background:var(--accent-soft)}
.stage.blocked{border-top-color:var(--signal);background:var(--signal-soft)}
.stage .s-n{font-family:var(--fm);font-size:8px;color:var(--faint);letter-spacing:.09em}
.stage .s-t{font-family:var(--fd);font-weight:600;font-size:12px;line-height:1.15}
.stage .s-d{font-family:var(--fm);font-size:9px;line-height:1.35;color:var(--soft);
 word-break:break-word}
.checks{display:flex;flex-wrap:wrap;gap:4px;padding:0 11px 11px}
.chk{font-family:var(--fm);font-size:8.5px;padding:2px 5px;border:1px solid var(--rule);
 background:var(--sunk);color:var(--soft)}
.chk.fail{border-color:var(--signal);color:var(--signal);background:var(--signal-soft)}
.narrate{font-family:var(--fb);font-size:13px;color:var(--soft);padding:11px 12px 10px;
 border-bottom:1px solid var(--rule2)}
.narrate b{color:var(--ink);font-weight:600}

/* ---------- tables ---------- */
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-family:var(--fd);font-size:12.5px}
th{text-align:left;font-family:var(--fm);font-size:8.5px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--faint);font-weight:500;padding:8px 10px;
 border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:6px 10px;border-bottom:1px solid var(--rule2);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.clickable{cursor:pointer}
tr.clickable:hover td{background:var(--sunk)}
.cid{font-family:var(--fm);font-size:10.5px;color:var(--accent);white-space:nowrap}
.tbar{display:flex;align-items:center;gap:7px;min-width:150px}
.tbar span.t{flex:1;height:7px;background:var(--track);border-radius:0 2px 2px 0}
.tbar span.t i{display:block;height:7px;background:var(--accent);border-radius:0 2px 2px 0}
.tbar em{font-family:var(--fm);font-size:9.5px;color:var(--soft);font-style:normal;
 font-variant-numeric:tabular-nums;min-width:30px;text-align:right}
.empty{font-family:var(--fm);font-size:10.5px;color:var(--faint);padding:16px 12px}

/* ---------- notes ---------- */
.note{font-family:var(--fb);font-size:13px;color:var(--soft);padding:11px 14px;
 border-left:3px solid var(--accent);background:var(--accent-soft);margin:12px 0}
.note.warn{border-left-color:var(--warn);background:var(--warn-soft)}
.note.bad{border-left-color:var(--signal);background:var(--signal-soft)}
.note b{color:var(--ink)}
.note ul{margin:6px 0 0;padding-left:18px}

/* ---------- before / after ---------- */
.ba{display:grid;grid-template-columns:110px 1fr;gap:8px 12px;padding:13px;
 align-items:center}
.ba .lbl{font-family:var(--fm);font-size:9.5px;color:var(--faint);
 letter-spacing:.08em;text-transform:uppercase}
.ba .track{height:16px;background:var(--track);position:relative}
.ba .track i{display:block;height:16px;background:var(--accent)}
.ba .track b{position:absolute;right:7px;top:0;line-height:16px;font-family:var(--fm);
 font-size:9.5px;color:var(--ink);font-weight:500}
.ba .track.dim i{background:var(--faint)}

/* ---------- drawer ---------- */
.scrim{position:fixed;inset:0;background:rgba(9,14,12,.42);z-index:60;display:none}
.scrim.on{display:block}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(660px,94vw);z-index:70;
 background:var(--paper);border-left:1px solid var(--rule);box-shadow:var(--shadow);
 transform:translateX(100%);transition:transform .22s ease;overflow-y:auto}
.drawer.on{transform:translateX(0)}
.dhead{position:sticky;top:0;background:var(--paper);border-bottom:1px solid var(--rule);
 padding:14px 18px;display:flex;justify-content:space-between;align-items:flex-start;
 gap:12px;z-index:2}
.dhead .t{font-family:var(--fd);font-size:17px;font-weight:700}
.dhead .s{font-family:var(--fm);font-size:10px;color:var(--faint)}
.dbody{padding:16px 18px 60px}
.dbody h4{font-family:var(--fm);font-size:9px;letter-spacing:.12em;text-transform:uppercase;
 color:var(--faint);margin:20px 0 7px;font-weight:600}
.tl{border-left:2px solid var(--rule);padding-left:14px;margin:0}
.tl li{list-style:none;margin:0 0 10px;position:relative}
.tl li::before{content:"";position:absolute;left:-19px;top:5px;width:7px;height:7px;
 border-radius:50%;background:var(--rule);border:2px solid var(--paper)}
.tl li.ok::before{background:var(--accent)}
.tl li.err::before{background:var(--signal)}
.tl .m{font-family:var(--fm);font-size:10.5px;color:var(--ink)}
.tl .st{font-family:var(--fm);font-size:9px;padding:1px 5px;border:1px solid var(--rule);
 margin-left:6px;color:var(--soft)}
.tl .st.err{border-color:var(--signal);color:var(--signal)}
.tl .d{font-family:var(--fm);font-size:9.5px;color:var(--faint);
 word-break:break-word;margin-top:2px}
pre{font-family:var(--fm);font-size:10px;line-height:1.55;background:var(--sunk);
 border:1px solid var(--rule2);padding:9px 11px;overflow-x:auto;margin:5px 0 0}
.entry{border:1px solid var(--rule);background:var(--surface);padding:11px 12px;
 margin-bottom:8px}
.entry .top2{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;
 align-items:baseline;margin-bottom:4px}
.entry .actor{font-family:var(--fd);font-weight:600;font-size:12.5px}
.entry .hash{font-family:var(--fm);font-size:8.5px;color:var(--faint)}

/* ---------- reference ---------- */
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}
dl.def{margin:0}
dl.def dt{font-family:var(--fm);font-size:10.5px;color:var(--accent);margin-top:10px}
dl.def dd{margin:2px 0 0;font-size:13px;color:var(--soft)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--rule);
 font-family:var(--fm);font-size:10px;color:var(--faint);line-height:1.8}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>

<div class="top">
  <div class="topin">
    <div class="brand">
      <span class="eyebrow">Revenue recovery for agent-driven checkout</span>
      <h1>Handshake</h1>
    </div>
    <div class="badges" id="badges"></div>
  </div>
  <nav class="tabs" role="tablist">
    <button role="tab" data-tab="overview" aria-selected="true">Overview</button>
    <button role="tab" data-tab="recovery" aria-selected="false">Recovery</button>
    <button role="tab" data-tab="prevention" aria-selected="false">Prevention</button>
    <button role="tab" data-tab="history" aria-selected="false">History</button>
    <button role="tab" data-tab="how" aria-selected="false">How it works</button>
  </nav>
</div>

<div class="wrap">

<!-- ================= OVERVIEW ================= -->
<section class="tab on" id="tab-overview">
  <p class="lead">AI agents now buy on people's behalf. They abandon checkout far more
  often than humans do &mdash; and for different reasons: a product field was missing,
  two variants were indistinguishable, the price moved mid-session, the basket came to
  &#8377;2,180 against a &#8377;2,000 spending cap. <b>When an agent gives up, the merchant
  gets a dead API session: no reason code, no contact channel.</b> Every recovery tool
  ever built assumes a human with an inbox.</p>

  <div class="grid">
    <div>
      <h2>Recovery <span>reactive, per session</span></h2>
      <div class="panel"><div class="note" style="margin:12px">
        Detect the failure, diagnose it from the API trace, repair the input that broke,
        and re-offer to the agent. Every money action passes a deterministic gate and
        lands in a hash-chained ledger.
      </div>
      <div class="tw"><table><tbody>
        <tr><td id="ov-reclbl">Recovered against a randomised control</td>
            <td class="n cid" id="ov-rec">—</td></tr>
        <tr><td>Lift over control</td><td class="n cid" id="ov-lift">—</td></tr>
        <tr><td>Margin surrendered per rupee recovered</td>
            <td class="n cid" id="ov-conc">—</td></tr>
        <tr><td>Diagnosis macro-F1 against ground truth</td>
            <td class="n cid" id="ov-f1">—</td></tr>
      </tbody></table></div></div>
      <p class="mt"><button class="act ghost" data-goto="recovery">Open recovery →</button></p>
    </div>
    <div>
      <h2>Prevention <span>proactive, per catalogue</span></h2>
      <div class="panel"><div class="note" style="margin:12px">
        Send agent buyers at a catalogue on purpose. Find every defect, price each one in
        refused basket value, repair the top ones and re-run the identical buyers to
        measure the delta. Fixing a defect once stops every future failure it causes.
      </div>
      <div class="tw"><table><tbody>
        <tr><td>Readiness score of the reference catalogue</td>
            <td class="n cid" id="ov-score">—</td></tr>
        <tr><td>Revenue recovered by repairing the top defects</td>
            <td class="n cid" id="ov-gain">—</td></tr>
        <tr><td>Projected per 1,000 agent sessions, permanently</td>
            <td class="n cid" id="ov-per1k">—</td></tr>
        <tr><td>Integration required</td><td class="n cid">none</td></tr>
      </tbody></table></div></div>
      <p class="mt"><button class="act ghost" data-goto="prevention">Open prevention →</button></p>
    </div>
  </div>

  <div class="note warn mt"><b>What is real here.</b> Payments are live Razorpay
  <i>test-mode</i> orders and buyer decisions come from a real model when keys are
  configured. The catalogue, the personas and the injected faults are synthetic and
  generated from a seed. Both arms of every comparison share that synthetic world, so
  the lift measures the system rather than the market. The header badges say which
  backends a given run actually used.</div>
</section>

<!-- ================= RECOVERY ================= -->
<section class="tab" id="tab-recovery">
  <div class="controls">
    <label class="inline">sessions <input type="number" id="sessions" value="200" min="10" max="2000" step="10"></label>
    <button class="act" id="run">Run batch</button>
    <button class="act ghost" id="walk">Walkthrough</button>
    <button class="act ghost" id="stop" disabled>Stop</button>
    <label class="inline"><input type="checkbox" id="offline"> offline</label>
    <div class="spacer"></div>
    <div class="switch" id="ks" role="button" tabindex="0">KILL SWITCH · R-11 · off</div>
  </div>

  <div class="kpis" id="kpis"></div>
  <div class="bar"><i id="prog"></i></div>
  <div id="runnotes"></div>

  <div class="grid">
    <div>
      <h2>Live sessions <span id="streamcount">idle</span></h2>
      <div class="panel stream" id="stream"><div class="empty">Run a batch to begin. Click any session for its API trace and audit chain.</div></div>

      <h2 class="mt">Recovery by root cause <span>treatment arm</span></h2>
      <div class="panel"><div class="tw"><table id="causes"><tbody>
        <tr><td class="empty">No failures yet.</td></tr></tbody></table></div></div>
    </div>
    <div>
      <h2>Current session <span id="cursid">—</span></h2>
      <div class="panel">
        <div class="narrate" id="narrate">Pick <b>Walkthrough</b> to step through one
          recovery slowly, or <b>Run batch</b> to watch the whole thing.</div>
        <div class="stages" id="stages"></div>
        <div class="checks" id="checks"></div>
      </div>

      <h2 class="mt">What the gate refused <span id="refcount"></span></h2>
      <div class="panel"><div class="tw"><table id="refusals"><tbody>
        <tr><td class="empty">Nothing refused yet.</td></tr></tbody></table></div></div>

      <h2 class="mt">Diagnosis accuracy <span id="f1note"></span></h2>
      <div class="panel"><div class="tw"><table id="perclass"><tbody>
        <tr><td class="empty">Available when a batch finishes.</td></tr></tbody></table></div></div>
    </div>
  </div>
</section>

<!-- ================= PREVENTION ================= -->
<section class="tab" id="tab-prevention">
  <div class="controls">
    <label class="inline">probes <input type="number" id="scansessions" value="300" min="50" max="2000" step="50"></label>
    <button class="act" id="scan">Scan catalogue</button>
    <div class="spacer"></div>
    <span class="badge" id="scanbadge">idle</span>
  </div>
  <div id="scanwrap"><div class="note mt">A scan sends agent buyers at the catalogue
    with no injected faults, so every failure is the catalogue's own doing. It then
    repairs the top defects and re-runs the identical buyers.</div></div>
</section>

<!-- ================= HISTORY ================= -->
<section class="tab" id="tab-history">
  <div class="controls">
    <button class="act ghost" id="reload">Reload</button>
    <div class="spacer"></div>
    <span class="badge">runs are stored in SQLite and survive a restart</span>
  </div>
  <h2 class="mt">Stored runs <span id="histcount"></span></h2>
  <div class="panel"><div class="tw"><table id="history"><tbody>
    <tr><td class="empty">Loading…</td></tr></tbody></table></div></div>
</section>

<!-- ================= HOW ================= -->
<section class="tab" id="tab-how">
  <h3 style="margin-top:0">The loop</h3>
  <div class="panel"><div class="stages" id="howstages"></div></div>
  <div class="note"><b>The design decision that matters.</b> The diagnosis engine may
  use a language model. The policy gate may not — eleven deterministic rules, one unit
  test each. A model proposes a cause; only the table decides whether money moves.</div>

  <div class="cols mt">
    <div>
      <h3>Failure taxonomy</h3>
      <dl class="def" id="causelist"></dl>
    </div>
    <div>
      <h3>Stopping rules</h3>
      <dl class="def" id="rulelist"></dl>
    </div>
  </div>

  <h3>Escalation</h3>
  <p>Three rungs, never skipped. <b>Machine to machine</b> first — repair the data,
  re-offer to the agent, no human touched. <b>Escalate to the human principal</b> only
  where policy requires consent, via a single-use expiring link, frequency-capped and
  quiet-hours bounded; an explicit decline is final. <b>Merchant operations</b> last,
  for anything the system cannot resolve or is not permitted to attempt.</p>
  <p>The system never contacts a human directly, never raises a spending cap on its own
  authority, and never escalates a rung it has not earned.</p>

  <footer>
    Handshake · <span id="ver"></span> · Razorpay AI Buildathon, Track 03<br>
    All payment integrations run in test mode. Simulated components are named on every
    report and in the header badges.
  </footer>
</section>

</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-label="Session detail">
  <div class="dhead">
    <div><div class="t" id="dtitle">Session</div><div class="s" id="dsub"></div></div>
    <button class="iconbtn" id="dclose">Close</button>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>

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
const CAUSES = [
  ["A1","attribute void","a required field is absent from the feed"],
  ["A2","spec ambiguity","two listings are indistinguishable"],
  ["A3","quote drift","price moved between session create and update"],
  ["A4","reserve ceiling","basket exceeds the delegated spending cap"],
  ["A5","human-auth wall","OTP or 3DS demanded with no human present"],
  ["A6","ambiguous error","a retryable error read as terminal"],
  ["A7","policy unreadable","returns terms are prose, not fields"],
  ["A8","fulfilment mismatch","no serviceable route or tax line"],
  ["B1","insufficient balance","mandate debit declined for funds"],
  ["B2","issuer downtime","failures cluster by issuer"],
  ["B3","mandate invalid","authorisation expired or revoked"],
  ["B4","reserve exhausted","cumulative spend consumed the cap"],
  ["B5","instrument decline","card expired or VPA invalid"],
];
const RULES = [
  ["R-01","maximum re-offers per session — 2"],
  ["R-02","maximum interventions per buyer per 24h — 3"],
  ["R-03","an explicit decline is permanent"],
  ["R-04","cumulative concession ceiling — 8% of basket"],
  ["R-05","halt when expected recovery is below intervention cost"],
  ["R-06","abuse pattern: repeat abandonment to farm concessions"],
  ["R-07","never raise a spending cap without recorded consent"],
  ["R-08","mandate retries capped, then routed to a human"],
  ["R-09","quiet hours on any human-facing escalation"],
  ["R-10","confidence below threshold routes to exceptions"],
  ["R-11","global kill switch"],
];

const $ = id => document.getElementById(id);
const inr = v => "₹" + Math.round(v || 0).toLocaleString("en-IN");
const pct = v => (100 * (v || 0)).toFixed(1) + "%";
let since = 0, timer = null, current = null, rows = 0, lastSummary = null;

/* ---------- tabs ---------- */
function showTab(name){
  document.querySelectorAll("nav.tabs button").forEach(b =>
    b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll("section.tab").forEach(s =>
    s.classList.toggle("on", s.id === "tab-" + name));
  if(name === "history") loadHistory();
  window.scrollTo({top:0});
}
document.querySelectorAll("nav.tabs button").forEach(b =>
  b.onclick = () => showTab(b.dataset.tab));
document.querySelectorAll("[data-goto]").forEach(b =>
  b.onclick = () => showTab(b.dataset.goto));

/* ---------- theme ---------- */
function applyTheme(t){
  if(t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
  try { localStorage.setItem("hs-theme", t || ""); } catch(e) {}
}
try { applyTheme(localStorage.getItem("hs-theme") || ""); } catch(e) {}

/* ---------- pipeline ---------- */
function drawStages(el, state){
  el.innerHTML = STAGES.map((s,i)=>{
    const st = (state || [])[i] || {};
    const cls = st.blocked ? "stage blocked" : (st.on ? "stage active" : "stage");
    return `<div class="${cls}"><span class="s-n">${s[0]}</span>
      <span class="s-t">${s[1]}</span>
      <span class="s-d">${st.detail || s[2]}</span></div>`;
  }).join("");
}
drawStages($("stages"), []);
drawStages($("howstages"), STAGES.map(() => ({on:true})));
$("causelist").innerHTML = CAUSES.map(c =>
  `<dt>${c[0]} · ${c[1]}</dt><dd>${c[2]}</dd>`).join("");
$("rulelist").innerHTML = RULES.map(r =>
  `<dt>${r[0]}</dt><dd>${r[1]}</dd>`).join("");

function resetSession(sid){
  current = {sid, stages:[{},{},{},{},{},{},{}]};
  $("cursid").textContent = sid;
  drawStages($("stages"), current.stages);
  $("checks").innerHTML = "";
}
function setStage(i, detail, blocked){
  if(!current) return;
  current.stages[i] = {on:true, detail, blocked:!!blocked};
  drawStages($("stages"), current.stages);
}
const narrate = html => { $("narrate").innerHTML = html; };

/* ---------- stream ---------- */
function addRow(e){
  const stream = $("stream");
  if(rows === 0) stream.innerHTML = "";
  const ok = e.recovered, failed = e.terminal === "FAILED" && !e.recovered;
  const what = ok ? ("recovered · " + (e.interventions||[]).join(", "))
    : (failed ? (e.cause ? e.cause + " · " + (e.exception || "unresolved") : "failed")
              : "converted first pass");
  const amt = ok ? e.recovered_value : e.basket_value;
  const b = document.createElement("button");
  b.className = ok ? "row ok" : (failed ? "row fail" : "row");
  b.innerHTML = `<span class="sid">${e.session_id}</span>
    <span class="what">${what}</span>
    <span class="tag">${e.arm === "treatment" ? "TREAT" : "CTRL"}</span>
    <span class="amt">${inr(amt)}</span><span class="dot"></span>`;
  b.onclick = () => openSession(e.session_id);
  stream.insertBefore(b, stream.firstChild);
  rows++;
  while(stream.children.length > 250) stream.removeChild(stream.lastChild);
}

function handle(e){
  switch(e.kind){
    case "session_start":
      resetSession(e.session_id);
      narrate(`Agent <b>${e.buyer}</b> (${e.persona}) shopping <b>${e.category}</b>,
               delegated cap ${inr(e.cap)}.`);
      break;
    case "failure_detected":
      setStage(0, `at risk ${inr(e.at_risk)} — ${e.note}`);
      narrate(`Session died with <b>${inr(e.at_risk)}</b> at risk. The merchant sees an
               API session that opened and stopped — no reason code, no way to reach
               the buyer.`);
      break;
    case "diagnosis":
      setStage(1, `${e.cause} · confidence ${e.confidence.toFixed(2)} · ${e.method}`);
      narrate(`Cause assigned: <b>${e.cause}</b> at confidence
               ${e.confidence.toFixed(2)}, from the ${e.method} tier.`);
      break;
    case "verdict":
      $("checks").innerHTML = (e.checks||[]).map(c =>
        `<span class="chk ${c.result === "fail" ? "fail" : ""}">${c.rule} ${c.state} · ${c.result}</span>`).join("");
      if(e.permitted){
        setStage(2, "intervention " + e.intervention);
        setStage(3, "all bounds passed");
        narrate(`Gate permits <b>${e.intervention}</b>. Every rule evaluated is
                 recorded, including the ones that passed.`);
      } else {
        setStage(2, "no action");
        setStage(3, `${e.binding_rule} — ${e.reason}`, true);
        narrate(`Gate <b>refused</b>: ${e.binding_rule} — ${e.reason}. The refusal is
                 written to the ledger with the same standing as a permit.`);
      }
      break;
    case "action":
      setStage(4, `${e.intervention} · ${e.note}`, !e.ok);
      setStage(5, e.concession ? `concession ${inr(e.concession)}` : "no margin surrendered");
      break;
    case "recovered":
      setStage(6, `converted at ${inr(e.value)}`);
      narrate(`Recovered <b>${inr(e.value)}</b> via ${e.intervention}. Click the
               session for its API trace and audit chain.`);
      break;
    case "session_end": addRow(e); break;
    case "progress":
      $("prog").style.width = (100 * e.done / Math.max(1, e.total)) + "%";
      $("streamcount").textContent = `${e.done} / ${e.total}`;
      break;
    case "done":
      narrate(`Batch complete — <b>${inr(e.recovered)}</b> recovered, lift
               ${(e.lift*100).toFixed(1)} points over control.`);
      break;
    case "error":
      narrate(`<b style="color:var(--signal)">Run aborted.</b> ${e.message}`);
      break;
  }
}

/* ---------- panels ---------- */
function kpis(t, s){
  $("kpis").innerHTML = `
    <div class="kpi"><span class="k">At-risk GMV</span><span class="v">${inr(t.at_risk)}</span>
      <span class="n">${t.failed} failed sessions</span></div>
    <div class="kpi good"><span class="k">Recovered GMV</span><span class="v">${inr(t.recovered)}</span>
      <span class="n">${pct(t.rate)} of at-risk</span></div>
    <div class="kpi good"><span class="k">Lift over control</span>
      <span class="v">${s ? (s.lift*100).toFixed(1) + " pts" : "—"}</span>
      <span class="n">${s ? "control " + pct(s.control.recovery_rate) : "at end of run"}</span></div>
    <div class="kpi"><span class="k">Concession ratio</span>
      <span class="v">${(100*t.concession_ratio).toFixed(2)}%</span>
      <span class="n">${inr(t.concession)} of margin</span></div>
    <div class="kpi"><span class="k">Recoveries</span><span class="v">${t.recovered_n}</span>
      <span class="n">${s ? "exceptions " + s.exceptions : "sessions won back"}</span></div>`;
}

function causes(c){
  const keys = Object.keys(c);
  if(!keys.length){
    $("causes").innerHTML = '<tbody><tr><td class="empty">No failures yet.</td></tr></tbody>';
    return;
  }
  $("causes").innerHTML = "<thead><tr><th>Cause</th><th>Class</th><th class='n'>Failed</th>"
    + "<th class='n'>At risk</th><th class='n'>Recovered</th><th>Recovery of at-risk</th>"
    + "</tr></thead><tbody>" + keys.map(k => {
      const v = c[k], w = (100*v.recovered/(v.at_risk||1)).toFixed(0);
      return `<tr><td class="cid">${k}</td><td>${v.name.replace(/_/g," ")}</td>
        <td class="n">${v.failed}</td><td class="n">${inr(v.at_risk)}</td>
        <td class="n">${inr(v.recovered)}</td>
        <td><span class="tbar"><span class="t"><i style="width:${w}%"></i></span>
        <em>${w}%</em></span></td></tr>`;
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

function perClass(s){
  if(!s || !s.per_class){ return; }
  const keys = Object.keys(s.per_class);
  $("f1note").textContent = "macro-F1 " + s.macro_f1 + " · " + s.unclassified + " unclassified";
  $("perclass").innerHTML = "<thead><tr><th>Cause</th><th class='n'>Support</th>"
    + "<th class='n'>Precision</th><th class='n'>Recall</th><th class='n'>F1</th>"
    + "</tr></thead><tbody>" + keys.map(k => {
      const v = s.per_class[k];
      return `<tr><td class="cid">${k}</td><td class="n">${v.support}</td>
        <td class="n">${v.precision.toFixed(2)}</td><td class="n">${v.recall.toFixed(2)}</td>
        <td class="n">${v.f1.toFixed(2)}</td></tr>`;
    }).join("") + "</tbody>";
}

function runNotes(d){
  const out = [];
  if(d.measured === false) out.push(['warn',
    "<b>Walkthrough mode.</b> Every session is in the treatment arm so the recovery path "
    + "always runs. There is no control arm, so these totals are a demonstration, not a "
    + "measurement. Use <b>Run batch</b> for figures you can quote."]);
  const llm = d.summary && d.summary.llm;
  if(llm && !llm.active) out.push(['bad',
    "<b>Model buyers requested but not active.</b> " + (llm.error || "") +
    " The heuristic ran instead — do not report this as a model run."]);
  if(llm && llm.active && llm.mixed_run) out.push(['bad',
    "<b>Mixed run.</b> Only " + pct(llm.model_share) + " of decisions came from the model; "
    + llm.failures + " fell back to the heuristic. These figures are attributable to neither."]);
  if(llm && llm.active && !llm.mixed_run && llm.fallbacks) out.push(['warn',
    llm.fallbacks + " of " + llm.calls + " calls fell back to the heuristic ("
    + pct(llm.model_share) + " from the model). Substantially a model run — disclose it."]);
  if(d.summary && d.summary.simulated && d.summary.simulated.length) out.push(['warn',
    "<b>Simulated in this run.</b><ul>" +
    d.summary.simulated.map(x => "<li>" + x + "</li>").join("") + "</ul>"]);
  $("runnotes").innerHTML = out.map(([c, html]) =>
    `<div class="note ${c}">${html}</div>`).join("");
}

function badges(d){
  const b = d.backends, out = [];
  out.push(`<span class="badge ${b.payments === "razorpay" ? "live" : "sim"}">payments: ${b.payments}</span>`);
  out.push(`<span class="badge ${b.buyers === "llm" ? "live" : "sim"}">buyers: ${b.buyers}</span>`);
  (d.pool||[]).forEach(p => out.push(`<span class="badge ${p.exhausted ? "sim" : ""}">${p.key} ${p.calls} calls · ${(p.tokens||0).toLocaleString()} tok${p.exhausted ? " · spent" : ""}</span>`));
  if(d.kill_switch) out.push('<span class="badge alert">KILL SWITCH ON</span>');
  if(d.demo_mode) out.push('<span class="badge">demo mode</span>');
  out.push('<button class="iconbtn" id="themebtn">theme</button>');
  $("badges").innerHTML = out.join("");
  $("ver").textContent = "v" + (d.version || "");
  $("themebtn").onclick = () => {
    const now = document.documentElement.getAttribute("data-theme");
    applyTheme(now === "dark" ? "light" : now === "light" ? "" : "dark");
  };
}

function overview(d){
  const s = d.summary || lastSummary;
  if(s){
    lastSummary = s;
    $("ov-rec").textContent = inr(s.treatment.recovered_gmv);
    $("ov-lift").textContent = (s.lift*100).toFixed(1) + " pts";
    $("ov-conc").textContent = (100*s.treatment.concession_ratio).toFixed(2) + "%";
    $("ov-f1").textContent = s.macro_f1;
    $("ov-reclbl").textContent =
      `Recovered on ${s.treatment.sessions + s.control.sessions} sessions against a randomised control`;
  }
  const r = d.readiness;
  if(r && !r.error){
    $("ov-score").textContent = r.readiness_score + "%";
    $("ov-gain").textContent = inr(r.delta.revenue_gained);
    $("ov-per1k").textContent = inr(r.delta.per_1000_sessions);
  }
}

/* A cold visitor should see real figures before pressing anything. */
async function hydrateOverview(){
  let d;
  try { d = await (await fetch("/api/overview")).json(); } catch(e) { return; }
  if(d.batch){
    const h = d.batch.headline || {};
    $("ov-rec").textContent = inr(h.recovered);
    $("ov-lift").textContent = h.lift != null ? (100*h.lift).toFixed(1) + " pts" : "—";
    $("ov-conc").textContent = h.concession_ratio != null
      ? (100*h.concession_ratio).toFixed(2) + "%" : "—";
    $("ov-f1").textContent = h.macro_f1 ?? "—";
    $("ov-reclbl").textContent =
      `Recovered on ${d.batch.sessions} sessions against a randomised control`;
  }
  if(d.scan){
    const h = d.scan.headline || {};
    $("ov-score").textContent = h.readiness != null ? h.readiness + "%" : "—";
    $("ov-gain").textContent = inr(h.revenue_gained);
    $("ov-per1k").textContent = inr(h.per_1000);
  }
}

/* ---------- prevention ---------- */
function renderScan(d){
  if(d.scanning){
    $("scanbadge").textContent = "probing…";
    $("scanwrap").innerHTML = '<div class="panel mt"><div class="empty">Sending agent buyers at the catalogue…</div></div>';
    return;
  }
  const r = d.readiness;
  if(!r) return;
  if(r.error){
    $("scanbadge").textContent = "failed";
    $("scanwrap").innerHTML = `<div class="note bad mt">${r.error}</div>`;
    return;
  }
  $("scanbadge").textContent = r.listings + " listings · " + r.sessions + " probes";
  const max = Math.max(r.before.revenue, r.after.revenue) || 1;
  const priced = r.priced.map(x =>
    `<tr><td>${x.defect.replace(/_/g," ")}</td><td class="cid">${x.field}</td>
     <td class="n">${x.sessions}</td><td class="n">${inr(x.at_risk)}</td>
     <td class="n">${x.skus.length}</td></tr>`).join("");
  const defects = r.defects_by_field.map(x =>
    `<tr><td>${x.kind.replace(/_/g," ")}</td><td class="cid">${x.field}</td>
     <td class="n">${x.sku_count}</td><td>${x.detail}</td></tr>`).join("");
  $("scanwrap").innerHTML = `
    <div class="kpis">
      <div class="kpi"><span class="k">Readiness score</span>
        <span class="v">${r.readiness_score}%</span>
        <span class="n">${r.defects_found.length} blocking defects</span></div>
      <div class="kpi good"><span class="k">Recovered by fixing</span>
        <span class="v">${inr(r.delta.revenue_gained)}</span>
        <span class="n">${r.repaired_skus.length} listings repaired</span></div>
      <div class="kpi good"><span class="k">Per 1,000 sessions</span>
        <span class="v">${inr(r.delta.per_1000_sessions)}</span>
        <span class="n">permanent, not per-session</span></div>
      <div class="kpi"><span class="k">Sessions won back</span>
        <span class="v">${r.delta.sessions_recovered}</span>
        <span class="n">${r.before.failed} failed &rarr; ${r.after.failed}</span></div>
    </div>

    <h2 class="mt">Proven repair <span>same seed, same buyers, only the feed differs</span></h2>
    <div class="panel"><div class="ba">
      <span class="lbl">before</span>
      <span class="track dim"><i style="width:${100*r.before.revenue/max}%"></i>
        <b>${inr(r.before.revenue)} · ${r.before.failed} failed</b></span>
      <span class="lbl">after</span>
      <span class="track"><i style="width:${100*r.after.revenue/max}%"></i>
        <b>${inr(r.after.revenue)} · ${r.after.failed} failed</b></span>
    </div></div>

    <h2 class="mt">What the defects cost <span>measured, not projected</span></h2>
    <div class="panel"><div class="tw"><table><thead><tr><th>Defect</th>
      <th>Field to fix</th><th class="n">Sessions</th><th class="n">Refused GMV</th>
      <th class="n">Listings</th></tr></thead><tbody>${priced}</tbody></table></div></div>

    <h2 class="mt">Every defect found by inspection <span>no agents needed</span></h2>
    <div class="panel"><div class="tw"><table><thead><tr><th>Kind</th><th>Field</th>
      <th class="n">Listings</th><th>Detail</th></tr></thead>
      <tbody>${defects}</tbody></table></div></div>

    ${(r.non_catalogue && r.non_catalogue.length) ? `
      <h2 class="mt">Not the catalogue's fault <span>no field can fix these</span></h2>
      <div class="panel"><div class="tw"><table><thead><tr><th>Cause</th><th>Why</th>
        <th class="n">Sessions</th><th class="n">Refused GMV</th></tr></thead><tbody>`
      + r.non_catalogue.map(x => `<tr><td class="cid">${x.cause}</td>
        <td>${x.reason}</td><td class="n">${x.sessions}</td>
        <td class="n">${inr(x.at_risk)}</td></tr>`).join("")
      + `</tbody></table></div>
      <div class="note">These belong to the recovery layer, not the readiness
        report. A spending cap that was too low is the buyer's budget, not a
        defect in your feed.</div></div>` : ""}

    ${r.unpriced.length ? '<div class="note warn">' + r.unpriced.length +
      ' out-of-stock listings are withheld from the feed, so they refuse nothing '
      + 'measurable — they cost the impression, not the basket. They are reported as '
      + 'advisories and kept out of the readiness score.</div>' : ""}`;
}

/* ---------- history ---------- */
async function loadHistory(){
  const r = await fetch("/api/runs?limit=30");
  const d = await r.json();
  const runs = d.runs || [];
  $("histcount").textContent = runs.length ? runs.length + " stored" : "";
  if(!runs.length){
    $("history").innerHTML = '<tbody><tr><td class="empty">No runs stored yet.</td></tr></tbody>';
    return;
  }
  $("history").innerHTML = "<thead><tr><th>When</th><th>Kind</th><th class='n'>Sessions</th>"
    + "<th>Backends</th><th>Headline</th><th></th></tr></thead><tbody>"
    + runs.map(x => {
      const when = new Date(x.created_at * 1000).toLocaleString();
      const h = x.headline || {};
      const head = x.kind === "scan"
        ? `readiness ${h.readiness}% · +${inr(h.revenue_gained)}`
        : `${inr(h.recovered)} recovered · lift ${h.lift != null ? (100*h.lift).toFixed(1) + " pts" : "—"} · F1 ${h.macro_f1 ?? "—"}`;
      return `<tr class="clickable" data-run="${x.run_id}">
        <td class="cid">${when}</td><td>${x.kind}${x.measured ? "" : " (demo)"}</td>
        <td class="n">${x.sessions}</td>
        <td class="cid">${x.payments}/${x.buyers}</td><td>${head}</td>
        <td class="n cid">open →</td></tr>`;
    }).join("") + "</tbody>";
  $("history").querySelectorAll("tr[data-run]").forEach(tr =>
    tr.onclick = () => openRun(tr.dataset.run));
}

/* ---------- drawer ---------- */
function openDrawer(title, sub, html){
  $("dtitle").textContent = title;
  $("dsub").textContent = sub;
  $("dbody").innerHTML = html;
  $("drawer").classList.add("on");
  $("scrim").classList.add("on");
}
function closeDrawer(){
  $("drawer").classList.remove("on");
  $("scrim").classList.remove("on");
}
$("dclose").onclick = closeDrawer;
$("scrim").onclick = closeDrawer;
document.addEventListener("keydown", e => { if(e.key === "Escape") closeDrawer(); });

function chainHtml(entries){
  return entries.map(e => {
    const body = {};
    ["trigger","diagnosis","outcome","reversal"].forEach(k => {
      if(e[k] && Object.keys(e[k]).length) body[k] = e[k]; });
    const chips = (e.policy_checks||[]).map(c =>
      `<span class="chk ${c.result === "fail" ? "fail" : ""}">${c.rule} ${c.state} · ${c.result}</span>`).join("");
    return `<div class="entry"><div class="top2">
      <span class="actor">${e.actor.replace(/_/g," ")} — ${e.action.replace(/_/g," ")}</span>
      <span class="hash">prev ${e.prev_hash.slice(0,10)} → ${e.hash.slice(0,10)}</span></div>
      ${Object.keys(body).length ? "<pre>" + JSON.stringify(body,null,2) + "</pre>" : ""}
      ${chips ? '<div class="checks" style="padding:6px 0 0">' + chips + "</div>" : ""}</div>`;
  }).join("");
}

async function openSession(sid){
  openDrawer(sid, "loading…", '<div class="empty">Fetching the trace…</div>');
  let trace = null, chain = null;
  try { const r = await fetch("/api/trace/" + sid); if(r.ok) trace = await r.json(); } catch(e) {}
  try { const r = await fetch("/api/session/" + sid); if(r.ok) chain = await r.json(); } catch(e) {}

  let html = "";
  if(trace){
    $("dsub").textContent = `${trace.buyer} · ${trace.persona} · ${trace.arm} · `
      + `${trace.terminal}${trace.recovered ? " → recovered" : ""}`;
    html += `<div class="note">Basket ${inr(trace.basket_value)} · declared cap
      ${inr(trace.spend_cap)}${trace.diagnosed ? " · diagnosed <b>" +
      trace.diagnosed.cause + "</b> at confidence " + trace.diagnosed.confidence : ""}
      ${trace.recovered ? " · recovered " + inr(trace.recovered_value) + " via " +
      trace.interventions.join(", ") : ""}</div>`;
    html += "<h4>What the merchant actually saw</h4><ul class='tl'>" +
      trace.events.map(ev => {
        const bad = ev.http_status >= 400;
        const cls = bad ? "err" : (ev.http_status === 200 ? "ok" : "");
        const detail = JSON.stringify(ev.response).slice(0, 190);
        return `<li class="${cls}"><span class="m">${ev.type}</span>
          <span class="st ${bad ? "err" : ""}">${ev.http_status}</span>
          <div class="d">${detail}</div></li>`;
      }).join("") + "</ul>";
    if(trace.abandon_note)
      html += `<div class="note warn">Terminal state: ${trace.abandon_note}. That is the
        whole of what a real merchant has to diagnose from.</div>`;
    if(trace.injected_fault)
      html += `<div class="note"><b>Ground truth:</b> ${trace.injected_fault} was the
        injected fault. The diagnosis engine never sees this — it exists only to score
        the engine.</div>`;
  }
  if(chain && chain.entries && chain.entries.length){
    html += `<h4>Audit chain — ${chain.chain_valid ? "verified" : "BROKEN at " + chain.first_bad}</h4>`;
    html += chainHtml(chain.entries);
  } else if(trace) {
    html += '<h4>Audit chain</h4><div class="empty">No ledger entries — this session did not fail.</div>';
  }
  if(!trace && !chain) html = '<div class="empty">This session belongs to an earlier run. Open it from the History tab.</div>';
  $("dbody").innerHTML = html;
}

async function openRun(runId){
  openDrawer(runId, "stored run", '<div class="empty">Loading…</div>');
  const r = await fetch("/api/runs/" + runId);
  if(!r.ok){ $("dbody").innerHTML = '<div class="empty">Not found.</div>'; return; }
  const d = await r.json();
  const s = d.summary;
  let html = `<div class="note">Chain ${d.chain_valid ? "verified" : "BROKEN at entry " + d.first_bad}
    on re-read from SQLite, independently of the process that wrote it.</div>`;
  if(d.kind === "scan"){
    html += `<h4>Readiness</h4><pre>${JSON.stringify({
      readiness_score: s.readiness_score, listings: s.listings,
      delta: s.delta, priced: s.priced}, null, 2)}</pre>`;
  } else {
    html += `<h4>Summary</h4><pre>${JSON.stringify({
      arms: s.arms, lift_over_control: s.lift_over_control,
      diagnosis: {macro_f1: s.diagnosis.macro_f1, unclassified: s.diagnosis.unclassified},
      policy_refusals: s.policy_refusals, exception_count: s.exception_count,
      ledger: s.ledger, simulated_components: s.simulated_components}, null, 2)}</pre>`;
    const failed = (d.sessions || []).filter(x => x.recovered || x.terminal_state === "FAILED");
    html += `<h4>Sessions (${failed.length} at risk of the ${d.sessions.length} stored)</h4>`;
    html += '<div class="tw"><table><thead><tr><th>Session</th><th>Cause</th>'
      + '<th class="n">Basket</th><th>Outcome</th></tr></thead><tbody>'
      + failed.slice(0, 60).map(x => `<tr><td class="cid">${x.session_id}</td>
        <td class="cid">${x.diagnosed_cause || "—"}</td>
        <td class="n">${inr(x.basket_value)}</td>
        <td>${x.recovered ? "recovered " + inr(x.recovered_value) : (x.exception || "unresolved")}</td>
        </tr>`).join("") + "</tbody></table></div>";
  }
  $("dbody").innerHTML = html;
}

/* ---------- polling ---------- */
async function poll(){
  let d;
  try { d = await (await fetch("/api/state?since=" + since)).json(); }
  catch(e) { return; }
  since = d.next;
  d.events.forEach(handle);
  kpis(d.totals, d.summary);
  causes(d.totals.causes);
  refusals(d.totals.refusals);
  perClass(d.summary);
  runNotes(d);
  badges(d);
  overview(d);
  renderScan(d);
  const busy = d.running || d.scanning;
  $("run").disabled = busy; $("walk").disabled = busy; $("scan").disabled = busy;
  $("stop").disabled = !d.running;
  if(!busy && timer){ clearInterval(timer); timer = null; $("prog").style.width = "100%"; }
}

async function post(url, body){
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(body || {})});
  if(!r.ok){
    const j = await r.json().catch(() => ({}));
    narrate(`<b style="color:var(--signal)">${j.error || r.status}</b>`);
    return false;
  }
  return true;
}

async function start(mode){
  since = 0; rows = 0;
  $("stream").innerHTML = '<div class="empty">starting…</div>';
  showTab("recovery");
  const ok = await post("/api/run", {sessions: +$("sessions").value, mode,
    offline: $("offline").checked});
  if(!ok) return;
  if(timer) clearInterval(timer);
  timer = setInterval(poll, mode === "walkthrough" ? 240 : 420);
  poll();
}

$("run").onclick = () => start("batch");
$("walk").onclick = () => start("walkthrough");
$("stop").onclick = () => post("/api/stop");
$("reload").onclick = loadHistory;
$("scan").onclick = async () => {
  showTab("prevention");
  const ok = await post("/api/readiness", {sessions: +$("scansessions").value});
  if(!ok) return;
  if(timer) clearInterval(timer);
  timer = setInterval(poll, 600);
  poll();
};
$("ks").onclick = async () => {
  const on = !$("ks").classList.contains("on");
  await post("/api/killswitch", {on});
  $("ks").classList.toggle("on", on);
  $("ks").textContent = "KILL SWITCH · R-11 · " + (on ? "ON" : "off");
};
$("ks").onkeydown = e => { if(e.key === "Enter" || e.key === " ") $("ks").click(); };

kpis({at_risk:0,recovered:0,failed:0,recovered_n:0,rate:0,concession:0,concession_ratio:0});
poll();
loadHistory();
hydrateOverview();
</script>
</body>
</html>
"""
