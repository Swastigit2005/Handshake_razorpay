"""The operator console — one self-contained document, no build step.

Served at `/console`; the landing page at `/` sends people here.

Built on Razorpay's own Blade design system rather than an impression of it.
The palette is Blade's `azure` and `blueGrayLight` scales converted from their
HSL source, the type is Inter (Blade's text family), the radii and spacing come
from Blade's token scales, and the shell follows the Razorpay Dashboard pattern:
a fixed left rail, a light working surface, and a persistent test-mode marker.

Light by default, because every Razorpay product surface is. The marketing
navy belongs on the landing page and stays there.

The one rule this file follows above the others: a person who has never seen
the project should understand what happened from a sentence, not from arithmetic
performed on a wall of figures. Numbers support the sentence; they do not
replace it.
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Console — Handshake</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='7' fill='%23050505'/><path d='M11 9v14M11 9h4a3.5 3.5 0 0 1 0 7h-4' stroke='%231364F1' stroke-width='2.6' fill='none' stroke-linecap='round'/><path d='M21 23V9M21 23h-4a3.5 3.5 0 0 1 0-7h4' stroke='%2300BD6E' stroke-width='2.6' fill='none' stroke-linecap='round'/></svg>">
<style>
/* ===========================================================================
   Tokens — Razorpay Blade, converted from the HSL source in
   razorpay/blade/packages/blade/src/tokens/global/colors.ts
   =========================================================================== */
:root{
  --az50:#F5F9FF; --az100:#D6E5FF; --az200:#A8C8FF; --az300:#75AAFF;
  --az400:#4287FF; --az500:#1364F1; --az600:#0E54CD; --az700:#0A44A9;
  --az800:#073688; --az900:#052761; --az1000:#021331;

  --n0:#FFFFFF; --n50:#F7F7F7; --n200:#DEE1E3; --n300:#C8CDD0; --n400:#AFB6BB;
  --n500:#96A0A6; --n600:#7B878E; --n700:#616D75; --n800:#4F585F; --n900:#434B51;
  --ink:#050505;

  --pos50:#E6F4ED; --pos100:#CEE9DB; --pos500:#009954; --pos600:#008F47;
  --neg50:#FDF3F2; --neg100:#FBE6E4; --neg500:#DF3E30; --neg600:#D01E11;
  --not50:#FFF6F0; --not100:#FFE7D6; --not500:#F56D19; --not600:#E05E00;
  --inf50:#E7F7FD; --inf100:#CCEBFA; --inf500:#00A1E6;

  /* semantic */
  --bg:var(--n50); --surface:var(--n0); --sunk:#FAFAFA;
  --line:var(--n200); --line-soft:#EDEFF0;
  --tx:var(--ink); --tx2:var(--n700); --tx3:var(--n600);
  --brand:var(--az500); --brand-hi:var(--az600); --brand-wash:var(--az50);
  --rail:#050505;

  --f:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
  --fm:"Menlo","SF Mono",ui-monospace,"Roboto Mono",monospace;

  /* Blade border.radius */
  --r4:4px; --r8:8px; --r12:12px; --r16:16px; --rmax:9999px;
  /* Blade elevation, midRaised / highRaised */
  --e1:0 1px 2px rgba(5,5,5,.05);
  --e2:0 3px 8px rgba(5,5,5,.06),0 1px 2px rgba(5,5,5,.04);
  --e3:0 18px 44px -12px rgba(5,5,5,.22);
  --ease:cubic-bezier(.2,.7,.3,1);
  --railw:236px;
}
:root[data-theme="dark"]{
  --bg:#0B1020; --surface:#121829; --sunk:#0E1424;
  --line:#232B41; --line-soft:#1B2237;
  --tx:#F2F5FA; --tx2:#A7B2C6; --tx3:#8592AA;
  --brand:#4287FF; --brand-hi:#75AAFF; --brand-wash:rgba(19,100,241,.16);
  --pos50:rgba(0,189,110,.14); --pos100:rgba(0,189,110,.28); --pos500:#49D08C;
  --neg50:rgba(223,62,48,.14); --neg100:rgba(223,62,48,.3); --neg500:#F0968E;
  --not50:rgba(245,109,25,.14); --not100:rgba(245,109,25,.3); --not500:#FFA66B;
  --inf50:rgba(0,161,230,.14); --inf500:#6AC6F1;
  --rail:#070B16;
  --e1:0 1px 2px rgba(0,0,0,.4); --e2:0 3px 10px rgba(0,0,0,.45);
  --e3:0 22px 50px -14px rgba(0,0,0,.75);
}

*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--tx);font-family:var(--f);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;
  font-feature-settings:"cv05","ss01"}
::selection{background:var(--az200);color:var(--ink)}
.mono{font-family:var(--fm);font-variant-numeric:tabular-nums}
.num{font-variant-numeric:tabular-nums;letter-spacing:-.01em}

/* ============================================================== shell ==== */
.app{display:grid;grid-template-columns:var(--railw) minmax(0,1fr);min-height:100vh}
@media(max-width:1000px){.app{grid-template-columns:1fr}}

/* --------------------------------------------------------------- rail --- */
.rail{background:var(--rail);color:#EDEFF2;display:flex;flex-direction:column;
  position:sticky;top:0;height:100vh;padding:18px 0 14px}
@media(max-width:1000px){.rail{position:static;height:auto;padding-bottom:8px}}
.rail .brand{display:flex;align-items:center;gap:10px;padding:0 18px 20px;
  text-decoration:none;color:#fff}
.rail .brand .nm{font-size:16px;font-weight:600;letter-spacing:-.02em}
.rail .grp{padding:0 12px;margin-bottom:2px}
.rail .glbl{font-size:11px;font-weight:500;letter-spacing:.07em;text-transform:uppercase;
  color:#6C7686;padding:12px 8px 6px}
.navitem{display:flex;align-items:center;gap:11px;width:100%;text-align:left;
  padding:9px 10px;border:0;border-radius:var(--r8);background:transparent;
  color:#B6BECC;font-family:var(--f);font-size:14px;font-weight:500;cursor:pointer;
  transition:background .14s,color .14s}
.navitem:hover{background:rgba(255,255,255,.06);color:#fff}
.navitem[aria-selected="true"]{background:var(--az500);color:#fff}
.navitem[aria-selected="true"] svg{opacity:1}
.navitem svg{opacity:.75;flex:none}
.navitem:focus-visible{outline:2px solid var(--az300);outline-offset:1px}
.rail .sp{flex:1}
.railfoot{padding:0 18px;border-top:1px solid rgba(255,255,255,.08);margin-top:12px;
  padding-top:14px;display:flex;flex-direction:column;gap:12px}
@media(max-width:1000px){.rail .sp{display:none}
  .railfoot{flex-direction:row;align-items:center;flex-wrap:wrap}}
.envrow{display:flex;flex-direction:column;gap:6px}
.envttl{font-size:11px;font-weight:500;letter-spacing:.07em;text-transform:uppercase;
  color:#6C7686}
.envpills{display:flex;flex-wrap:wrap;gap:5px}
.pill{font-size:11px;font-family:var(--fm);padding:3px 8px;border-radius:var(--rmax);
  border:1px solid rgba(255,255,255,.16);color:#AEB7C4;white-space:nowrap}
.pill.sim{border-color:rgba(245,109,25,.5);color:#FFB98A;background:rgba(245,109,25,.14)}
.pill.live{border-color:rgba(0,189,110,.5);color:#7FE0AF;background:rgba(0,189,110,.14)}
.railback{font-size:13px;color:#8A93A3;text-decoration:none}
.railback:hover{color:#fff}

/* kill switch */
.ks{display:flex;align-items:center;gap:10px;width:100%;padding:9px 11px;
  border-radius:var(--r8);border:1px solid rgba(255,255,255,.14);
  background:rgba(255,255,255,.04);color:#C3CAD6;cursor:pointer;font-family:var(--f);
  font-size:13px;font-weight:500;transition:.16s;user-select:none;text-align:left}
.ks:hover{border-color:rgba(255,255,255,.3);color:#fff}
.ks .lbl{flex:1}
.ks .tog{width:30px;height:17px;border-radius:var(--rmax);background:rgba(255,255,255,.2);
  position:relative;transition:background .2s;flex:none}
.ks .tog::after{content:"";position:absolute;top:2px;left:2px;width:13px;height:13px;
  border-radius:50%;background:#fff;transition:transform .2s var(--ease)}
.ks.on{border-color:var(--neg500);background:rgba(223,62,48,.22);color:#fff}
.ks.on .tog{background:var(--neg500)}
.ks.on .tog::after{transform:translateX(13px)}
.ks:focus-visible{outline:2px solid var(--az300);outline-offset:1px}

/* --------------------------------------------------------------- main --- */
.main{min-width:0;display:flex;flex-direction:column}
.topbar{background:var(--surface);border-bottom:1px solid var(--line);
  padding:0 clamp(16px,2.4vw,28px);position:sticky;top:0;z-index:30}
.tbin{display:flex;align-items:center;gap:16px;min-height:62px;flex-wrap:wrap;
  padding:10px 0}
.ptitle{font-size:19px;font-weight:600;letter-spacing:-.022em;margin:0}
.psub{font-size:13px;color:var(--tx3);margin:1px 0 0}
.topbar .sp{flex:1}
.tmode{display:flex;align-items:center;gap:7px;font-size:12.5px;font-weight:500;
  color:var(--not600);background:var(--not50);border:1px solid var(--not100);
  padding:5px 11px;border-radius:var(--rmax);white-space:nowrap}
.tmode i{width:6px;height:6px;border-radius:50%;background:var(--not500);display:block}
.ghosticon{font-family:var(--f);font-size:13px;font-weight:500;color:var(--tx2);
  background:transparent;border:1px solid var(--line);padding:6px 12px;
  border-radius:var(--r8);cursor:pointer}
.ghosticon:hover{background:var(--n50);color:var(--tx)}
.page{padding:clamp(16px,2.4vw,28px);flex:1}
section.tab{display:none}
section.tab.on{display:block;animation:in .22s var(--ease)}
@keyframes in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

/* ============================================================ buttons ==== */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;
  font-family:var(--f);font-size:14px;font-weight:600;letter-spacing:-.006em;
  padding:9px 16px;border-radius:var(--r8);border:1px solid transparent;
  background:var(--brand);color:#fff;cursor:pointer;white-space:nowrap;
  text-decoration:none;transition:background .16s,box-shadow .16s,border-color .16s;
  box-shadow:var(--e1)}
.btn:hover:not(:disabled){background:var(--brand-hi)}
.btn:disabled{opacity:.45;cursor:not-allowed;box-shadow:none}
.btn:focus-visible{outline:2px solid var(--az400);outline-offset:2px}
.btn.sec{background:var(--surface);color:var(--tx);border-color:var(--line)}
.btn.sec:hover:not(:disabled){background:var(--n50);border-color:var(--n300)}
.btn.sm{font-size:13px;padding:7px 13px}
.btn.lg{font-size:15px;padding:11px 22px}

.field{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--tx2);
  font-weight:500;white-space:nowrap}
input[type=number]{font-family:var(--f);font-size:14px;font-weight:600;width:78px;
  padding:8px 10px;border:1px solid var(--line);border-radius:var(--r8);
  background:var(--surface);color:var(--tx);font-variant-numeric:tabular-nums}
input[type=number]:focus{outline:2px solid var(--az400);outline-offset:-1px;
  border-color:var(--az400)}
input[type=checkbox]{accent-color:var(--brand);width:15px;height:15px}

/* ============================================================== cards ==== */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r12);
  box-shadow:var(--e1)}
.card > .hd{display:flex;align-items:baseline;justify-content:space-between;gap:14px;
  padding:14px 16px;border-bottom:1px solid var(--line-soft);flex-wrap:wrap}
.card > .hd h3{font-size:14.5px;font-weight:600;letter-spacing:-.014em;margin:0}
.card > .hd .meta{font-size:12px;color:var(--tx3);font-family:var(--fm)}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:14px 16px;
  background:var(--surface);border:1px solid var(--line);border-radius:var(--r12);
  box-shadow:var(--e1)}
.toolbar .sp{flex:1}
.hint{font-size:12.5px;color:var(--tx3)}

/* ====================================================== result banner ==== */
/* One sentence, one number. Everything else is support. */
.result{margin-top:14px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r12);box-shadow:var(--e1);overflow:hidden}
.rtop{padding:20px 22px 18px;display:grid;grid-template-columns:minmax(0,1fr) auto;
  gap:22px;align-items:start}
@media(max-width:820px){.rtop{grid-template-columns:1fr}}
.rlead{font-size:26px;font-weight:600;letter-spacing:-.032em;line-height:1.2;margin:0;
  max-width:30ch}
.rlead .big{color:var(--pos600);font-weight:700}
.rlead .zero{color:var(--tx3)}
.rsub{font-size:14px;color:var(--tx2);margin:9px 0 0;max-width:62ch;line-height:1.5}
.rsub b{color:var(--tx);font-weight:600}
.rstate{display:flex;flex-direction:column;align-items:flex-end;gap:8px;white-space:nowrap}
@media(max-width:820px){.rstate{align-items:flex-start}}
.chipstat{display:inline-flex;align-items:baseline;gap:7px;padding:7px 13px;
  border-radius:var(--rmax);background:var(--pos50);border:1px solid var(--pos100);
  font-size:13px;color:var(--pos600);font-weight:600}
.chipstat.flat{background:var(--n50);border-color:var(--line);color:var(--tx2)}

/* the one chart: where the at-risk money went */
.split{padding:0 22px 8px}
.splitbar{display:flex;height:34px;border-radius:var(--r8);overflow:hidden;
  background:var(--n50);border:1px solid var(--line)}
.splitbar i{display:block;height:100%;transition:width .7s var(--ease);position:relative}
.splitbar .rec{background:linear-gradient(180deg,var(--pos500),var(--pos600))}
.splitbar .lost{background:repeating-linear-gradient(135deg,
  var(--n300) 0 6px,var(--n200) 6px 12px)}
.splitkey{display:flex;gap:20px;flex-wrap:wrap;padding:11px 22px 18px;font-size:13px}
.splitkey span{display:flex;align-items:center;gap:8px;color:var(--tx2)}
.splitkey i{width:10px;height:10px;border-radius:3px;display:block}
.splitkey i.rec{background:var(--pos500)}
.splitkey i.lost{background:var(--n300)}
.splitkey b{color:var(--tx);font-weight:600}

.rfoot{display:flex;gap:0;border-top:1px solid var(--line-soft);flex-wrap:wrap}
.rfoot div{flex:1;min-width:150px;padding:13px 22px;border-right:1px solid var(--line-soft)}
.rfoot div:last-child{border-right:none}
.rfoot .k{font-size:12px;color:var(--tx3)}
.rfoot .v{font-size:17px;font-weight:600;letter-spacing:-.02em;margin-top:2px;
  font-variant-numeric:tabular-nums}
.rfoot .v.pos{color:var(--pos600)}
.rfoot .v.mut{color:var(--tx3);font-size:14px;font-weight:500}

/* ================================================== empty / first-run ==== */
.zero-state{padding:44px 26px;text-align:center;max-width:560px;margin:0 auto}
.zero-state svg{margin-bottom:16px}
.zero-state h4{font-size:18px;font-weight:600;letter-spacing:-.02em;margin:0 0 7px}
.zero-state p{font-size:14px;color:var(--tx2);margin:0 auto 18px;max-width:44ch;
  line-height:1.55}
.zero-state .steps{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;
  margin-top:20px;font-size:12.5px;color:var(--tx3)}
.zero-state .steps span{background:var(--n50);border:1px solid var(--line);
  padding:5px 11px;border-radius:var(--rmax)}

/* ============================================================= layout ==== */
.cols{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:14px;
  margin-top:14px;align-items:start}
@media(max-width:1180px){.cols{grid-template-columns:1fr}}
.stack{display:flex;flex-direction:column;gap:14px}

/* the method note that replaces the old warning panel: one line, not a box */
.prov{margin:12px 2px 0;font-family:var(--fm);font-size:11.5px;color:var(--tx3);
  letter-spacing:.01em;line-height:1.6}
.prov b{color:var(--tx2);font-weight:600}

/* the drawer opens on what happened, in words, before any API trace */
.lead{border-left:3px solid var(--az400);padding:1px 0 1px 14px;margin:0 0 18px;
  font-size:14.5px;line-height:1.62;color:var(--tx2)}
.lead p{margin:0 0 9px}
.lead p:last-child{margin:0}
.lead b{color:var(--tx);font-weight:600}

/* ============================================================= stream ==== */
.stream{max-height:452px;overflow-y:auto}
.srow{display:grid;grid-template-columns:14px 82px minmax(0,1fr) auto;gap:11px;
  align-items:center;padding:10px 16px;border-bottom:1px solid var(--line-soft);
  width:100%;text-align:left;background:none;border-left:0;border-right:0;border-top:0;
  cursor:pointer;font-family:var(--f);font-size:13.5px;color:inherit;transition:background .12s}
.srow:last-child{border-bottom:none}
.srow:hover{background:var(--n50)}
.srow:focus-visible{outline:2px solid var(--az400);outline-offset:-2px}
.srow .ic{width:14px;height:14px;border-radius:50%;display:grid;place-items:center;
  flex:none}
.srow .ic.ok{background:var(--pos500)}
.srow .ic.no{background:var(--neg500)}
.srow .ic.pass{background:var(--n300)}
.srow .sid{font-family:var(--fm);font-size:11.5px;color:var(--tx3)}
.srow .what{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--tx2)}
.srow .what b{color:var(--tx);font-weight:600}
.srow .amt{font-variant-numeric:tabular-nums;font-weight:600;font-size:13px}
.srow.ok .amt{color:var(--pos600)}
.srow.fail .amt{color:var(--tx3)}
.srow.new{animation:slide .28s var(--ease)}
@keyframes slide{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:none}}
.armtag{font-size:10.5px;font-family:var(--fm);color:var(--tx3);border:1px solid var(--line);
  padding:1px 6px;border-radius:var(--r4);margin-left:6px}

/* =========================================================== the flow ==== */
/* A pipeline should read as a pipeline: a single line, in order, with the
   step that stopped it marked. Seven equal boxes read as a feature grid. */
.flow{padding:6px 16px 16px}
.fstep{display:grid;grid-template-columns:26px minmax(0,1fr);gap:12px;
  position:relative;padding:9px 0}
.fstep .node{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;
  background:var(--n50);border:1.5px solid var(--line);font-size:11px;font-weight:600;
  color:var(--tx3);z-index:1;transition:.2s}
.fstep::before{content:"";position:absolute;left:12.5px;top:30px;bottom:-9px;width:1.5px;
  background:var(--line)}
.fstep:last-child::before{display:none}
.fstep.done .node{background:var(--brand);border-color:var(--brand);color:#fff}
.fstep.done::before{background:var(--az200)}
.fstep.win .node{background:var(--pos500);border-color:var(--pos500);color:#fff}
.fstep.stop .node{background:var(--neg500);border-color:var(--neg500);color:#fff}
.fstep .lb{font-size:13.5px;font-weight:600;letter-spacing:-.012em;line-height:1.35;
  padding-top:4px}
.fstep.idle .lb{color:var(--tx3);font-weight:500}
.fstep .dt{display:block;font-size:12.5px;color:var(--tx2);margin-top:3px;
  line-height:1.45;font-family:var(--fm);word-break:break-word}
.fstep.stop .dt{color:var(--neg600)}
.fstep.win .dt{color:var(--pos600)}
.narrate{padding:14px 16px;border-bottom:1px solid var(--line-soft);font-size:13.5px;
  color:var(--tx2);line-height:1.55}
.narrate b{color:var(--tx);font-weight:600}
.checks{display:flex;flex-wrap:wrap;gap:5px;padding:0 16px 14px}
.chk{font-size:11px;font-family:var(--fm);padding:3px 8px;border-radius:var(--r4);
  border:1px solid var(--line);background:var(--n50);color:var(--tx2)}
.chk.fail{border-color:var(--neg100);color:var(--neg600);background:var(--neg50)}

/* ============================================================= tables ==== */
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font-size:11.5px;font-weight:500;color:var(--tx3);padding:10px 16px;
  border-bottom:1px solid var(--line);white-space:nowrap;background:var(--sunk)}
td{padding:10px 16px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.clickable{cursor:pointer}
tr.clickable:hover td{background:var(--n50)}
.cid{font-family:var(--fm);font-size:12px;color:var(--brand)}
.mini{display:flex;align-items:center;gap:9px;min-width:132px}
.mini .t{flex:1;height:6px;background:var(--n50);border-radius:var(--rmax);overflow:hidden;
  border:1px solid var(--line-soft)}
.mini .t i{display:block;height:100%;background:var(--pos500);border-radius:var(--rmax);
  transition:width .5s var(--ease)}
.mini em{font-style:normal;font-size:12px;color:var(--tx2);min-width:34px;text-align:right;
  font-variant-numeric:tabular-nums}
.empty{font-size:13.5px;color:var(--tx3);padding:24px 16px;text-align:center}
.empty b{display:block;color:var(--tx2);font-weight:600;font-size:14px;margin-bottom:4px}

/* ============================================================== notes ==== */
.note{font-size:13px;color:var(--tx2);padding:12px 14px;border-radius:var(--r8);
  background:var(--brand-wash);border:1px solid var(--az100);line-height:1.5}
.note.warn{background:var(--not50);border-color:var(--not100)}
.note.bad{background:var(--neg50);border-color:var(--neg100)}
.note b{color:var(--tx);font-weight:600}
.note ul{margin:6px 0 0;padding-left:17px}
.note li{margin:2px 0}

/* =========================================================== disclosure == */
details.adv{margin-top:14px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r12);box-shadow:var(--e1);overflow:hidden}
details.adv > summary{list-style:none;cursor:pointer;padding:14px 16px;display:flex;
  align-items:center;gap:12px;font-size:14px}
details.adv > summary::-webkit-details-marker{display:none}
details.adv > summary b{font-weight:600;letter-spacing:-.012em}
details.adv > summary small{color:var(--tx3);font-size:12.5px}
details.adv > summary .sp{flex:1}
details.adv > summary .cv{color:var(--tx3);transition:transform .2s}
details.adv[open] > summary{border-bottom:1px solid var(--line-soft)}
details.adv[open] > summary .cv{transform:rotate(180deg)}
.advbody{padding:16px}
.advbody h4{font-size:13px;font-weight:600;margin:0 0 8px;letter-spacing:-.01em}
.advbody h4:not(:first-child){margin-top:22px}

/* ============================================================= drawer ==== */
.scrim{position:fixed;inset:0;background:rgba(5,5,5,.4);z-index:60;display:none}
.scrim.on{display:block;animation:in .18s}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(740px,96vw);z-index:70;
  background:var(--bg);border-left:1px solid var(--line);box-shadow:var(--e3);
  transform:translateX(100%);transition:transform .24s var(--ease);overflow-y:auto}
.drawer.on{transform:translateX(0)}
.dhead{position:sticky;top:0;background:var(--surface);border-bottom:1px solid var(--line);
  padding:15px 20px;display:flex;justify-content:space-between;align-items:flex-start;
  gap:14px;z-index:2}
.dhead .t{font-size:16px;font-weight:600;font-family:var(--fm);letter-spacing:-.01em}
.dhead .s{font-size:12.5px;color:var(--tx3);margin-top:2px}
.dbody{padding:18px 20px 72px}
.dbody h4{font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:var(--tx3);margin:22px 0 9px}
.dbody h4:first-child{margin-top:0}
.tl{border-left:1.5px solid var(--line);padding-left:16px;margin:0}
.tl li{list-style:none;margin:0 0 11px;position:relative}
.tl li::before{content:"";position:absolute;left:-21px;top:5px;width:8px;height:8px;
  border-radius:50%;background:var(--n300);border:2px solid var(--bg)}
.tl li.ok::before{background:var(--pos500)}
.tl li.err::before{background:var(--neg500)}
.tl .m{font-family:var(--fm);font-size:12px;color:var(--tx)}
.tl .st{font-family:var(--fm);font-size:10.5px;padding:1px 6px;border-radius:var(--r4);
  border:1px solid var(--line);margin-left:7px;color:var(--tx2)}
.tl .st.err{border-color:var(--neg100);color:var(--neg600);background:var(--neg50)}
.tl .d{font-family:var(--fm);font-size:11px;color:var(--tx3);word-break:break-word;
  margin-top:3px;line-height:1.5}
pre{font-family:var(--fm);font-size:11.5px;line-height:1.6;background:var(--sunk);
  border:1px solid var(--line);border-radius:var(--r8);padding:12px 14px;overflow-x:auto;
  margin:0;color:var(--tx2)}
.entry{border:1px solid var(--line);border-radius:var(--r8);background:var(--surface);
  padding:12px 14px;margin-bottom:9px}
.entry .top2{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
  align-items:baseline;margin-bottom:6px}
.entry .actor{font-weight:600;font-size:13px;letter-spacing:-.012em}
.entry .hash{font-family:var(--fm);font-size:10.5px;color:var(--tx3)}
.dclose{font-family:var(--f);font-size:13px;font-weight:500;padding:6px 13px;
  border-radius:var(--r8);border:1px solid var(--line);background:var(--surface);
  color:var(--tx2);cursor:pointer}
.dclose:hover{background:var(--n50);color:var(--tx)}

/* ============================================================ ba chart ==== */
.ba{display:grid;grid-template-columns:58px minmax(0,1fr) auto;gap:10px 14px;
  padding:16px;align-items:center}
@media(max-width:620px){.ba{grid-template-columns:58px minmax(0,1fr)}
  .ba .val{grid-column:2}}
.ba .lbl{font-size:12px;color:var(--tx3);text-align:right}
.ba .track{height:26px;background:var(--n50);border:1px solid var(--line-soft);
  border-radius:var(--r8);overflow:hidden}
.ba .track i{display:block;height:100%;border-radius:var(--r8);transition:width .7s var(--ease)}
.ba .track.b i{background:linear-gradient(180deg,var(--neg500),var(--neg600))}
.ba .track.a i{background:linear-gradient(180deg,var(--pos500),var(--pos600))}
.ba .val{font-size:13.5px;font-weight:600;font-variant-numeric:tabular-nums;
  white-space:nowrap}
.ba .val em{font-style:normal;font-weight:400;color:var(--tx3)}
.ba .val.good{color:var(--pos600)}
footer{margin-top:26px;font-size:12.5px;color:var(--tx3);line-height:1.7}
footer a{color:var(--tx2)}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="app">

<!-- ================================================================ rail -->
<aside class="rail">
  <a class="brand" href="/">
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#12172A" stroke="rgba(255,255,255,.14)"/>
      <path d="M11 9v14M11 9h4a3.5 3.5 0 0 1 0 7h-4" stroke="#4287FF" stroke-width="2.6" fill="none" stroke-linecap="round"/>
      <path d="M21 23V9M21 23h-4a3.5 3.5 0 0 1 0-7h4" stroke="#00BD6E" stroke-width="2.6" fill="none" stroke-linecap="round"/>
    </svg>
    <span class="nm">Handshake</span>
  </a>

  <div class="grp" role="tablist" aria-label="Console sections">
    <div class="glbl">Workspace</div>
    <button class="navitem" role="tab" data-tab="recovery" aria-selected="true">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4.5V9h4.5"/></svg>
      Recovery
    </button>
    <button class="navitem" role="tab" data-tab="prevention" aria-selected="false">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.8 4.5 6v6c0 4.4 3.1 7.7 7.5 9 4.4-1.3 7.5-4.6 7.5-9V6L12 2.8Z"/><path d="m9 12 2.2 2.2L15.4 10"/></svg>
      Prevention
    </button>
    <button class="navitem" role="tab" data-tab="history" aria-selected="false">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7v5l3.2 1.9"/><circle cx="12" cy="12" r="9"/></svg>
      History
    </button>
  </div>

  <div class="sp"></div>

  <div class="railfoot">
    <div class="envrow">
      <span class="envttl">Environment</span>
      <div class="envpills" id="badges"></div>
    </div>
    <button class="ks" id="ks" aria-pressed="false"
            title="Rule R-11 — takes effect on the next policy evaluation, mid-run">
      <span class="lbl">Kill switch</span><span class="tog"></span>
    </button>
    <a class="railback" href="/">&larr; Project overview</a>
  </div>
</aside>

<!-- ================================================================ main -->
<div class="main">
  <div class="topbar">
    <div class="tbin">
      <div>
        <h1 class="ptitle" id="ptitle">Recovery</h1>
        <p class="psub" id="psub">Recover revenue from agent checkouts that already failed.</p>
      </div>
      <div class="sp"></div>
      <span class="tmode"><i></i>Test mode &middot; no real money moves</span>
      <button class="ghosticon" id="themebtn">Theme</button>
    </div>
  </div>

  <div class="page">

  <!-- ========================================================= RECOVERY -->
  <section class="tab on" id="tab-recovery">
    <div class="toolbar">
      <span class="field">Shopping attempts <input type="number" id="sessions" value="200" min="10" max="2000" step="10"></span>
      <button class="btn" id="run">Run batch</button>
      <button class="btn sec" id="walk">Walkthrough</button>
      <button class="btn sec" id="stop" disabled>Stop</button>
      <span class="field"><input type="checkbox" id="offline"> Force offline</span>
      <div class="sp"></div>
      <span class="hint" id="ctlhint">Takes about twenty seconds.</span>
    </div>

    <p class="prov" id="prov">Press <b>Run batch</b> to send agent buyers at the merchant
    and measure what comes back, or <b>Walkthrough</b> to follow a single agent end to
    end.</p>

    <div id="runnotes"></div>

    <!-- the whole outcome, in one sentence -->
    <div class="result" id="result">
      <div class="rtop">
        <div>
          <p class="rlead" id="r-lead">No run yet in this session.</p>
          <p class="rsub" id="r-sub">Press <b>Run batch</b> to send agent buyers at the
          merchant, let some of them fail, and watch Handshake try to win them back.</p>
        </div>
        <div class="rstate"><span class="chipstat flat" id="r-chip">idle</span></div>
      </div>
      <div class="split" id="r-split" hidden>
        <div class="splitbar">
          <i class="rec" id="sp-rec" style="width:0"></i>
          <i class="lost" id="sp-lost" style="width:100%"></i>
        </div>
        <div class="splitkey">
          <span><i class="rec"></i>Recovered <b id="sk-rec">&#8377;0</b></span>
          <span><i class="lost"></i>Still lost <b id="sk-lost">&#8377;0</b></span>
        </div>
      </div>
      <div class="rfoot" id="r-foot" hidden>
        <div><div class="k">Recovery rate</div><div class="v pos" id="rf-rate">&mdash;</div></div>
        <div><div class="k">Control arm did</div><div class="v mut" id="rf-ctrl">&mdash;</div></div>
        <div><div class="k">Lift over control</div><div class="v" id="rf-lift">&mdash;</div></div>
        <div><div class="k">Margin given up</div><div class="v" id="rf-conc">&mdash;</div></div>
      </div>
    </div>

    <div class="cols">
      <div class="card">
        <div class="hd"><h3>Agent shopping attempts</h3><span class="meta" id="streamcount">idle</span></div>
        <div class="stream" id="stream">
          <div class="zero-state">
            <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#C8CDD0" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 9.5h19M6.5 14h4"/></svg>
            <h4>Nothing has run yet</h4>
            <p>Each agent checkout will appear here the moment it resolves. Click any one
            to read the raw API traffic the merchant saw and the audit trail behind it.</p>
            <button class="btn lg" id="zrun">Run a batch</button>
            <div class="steps"><span>1 &middot; run</span><span>2 &middot; click a session</span><span>3 &middot; flip the kill switch</span></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="hd"><h3>What happened to one session</h3><span class="meta" id="cursid">&mdash;</span></div>
        <div class="narrate" id="narrate">Run a batch, or pick <b>Walkthrough</b> to step
          through a single recovery slowly enough to narrate.</div>
        <div class="flow" id="stages"></div>
        <div class="checks" id="checks"></div>
      </div>
    </div>

    <details class="adv">
      <summary><b>Evidence</b>&nbsp;<small>root causes, policy refusals and diagnosis scoring</small><span class="sp"></span><span class="cv">&#9662;</span></summary>
      <div class="advbody">
        <h4>Recovery by root cause</h4>
        <div class="card"><div class="tw"><table id="causes"><tbody>
          <tr><td class="empty">No failures yet.</td></tr></tbody></table></div></div>
        <h4>What the gate refused <span id="refcount" style="color:var(--tx3);font-weight:400"></span></h4>
        <div class="card"><div class="tw"><table id="refusals"><tbody>
          <tr><td class="empty">Nothing refused yet.</td></tr></tbody></table></div></div>
        <h4>Diagnosis accuracy <span id="f1note" style="color:var(--tx3);font-weight:400"></span></h4>
        <div class="card"><div class="tw"><table id="perclass"><tbody>
          <tr><td class="empty">Available when a batch finishes.</td></tr></tbody></table></div></div>
      </div>
    </details>
    <div class="bar" style="display:none"><i id="prog"></i></div>
  </section>

  <!-- ======================================================= PREVENTION -->
  <section class="tab" id="tab-prevention">
    <div class="toolbar">
      <span class="field">Probe sessions <input type="number" id="scansessions" value="300" min="50" max="2000" step="50"></span>
      <button class="btn" id="scan">Scan catalogue</button>
      <div class="sp"></div>
      <span class="hint" id="scanbadge">idle</span>
    </div>
    <div id="scanwrap">
      <div class="card" style="margin-top:14px"><div class="zero-state">
        <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#C8CDD0" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="10.5" cy="10.5" r="7"/><path d="M15.5 15.5 21 21"/></svg>
        <h4>Find the leaks before checkout</h4>
        <p>A scan sends agent buyers at the catalogue with no injected faults, so every
        failure they hit is the catalogue&rsquo;s own doing. It then repairs the costliest
        listings and re-runs the identical buyers to measure what changed.</p>
        <button class="btn lg" id="zscan">Scan the catalogue</button>
      </div></div>
    </div>
  </section>

  <!-- ========================================================== HISTORY -->
  <section class="tab" id="tab-history">
    <div class="toolbar">
      <button class="btn sec" id="reload">Reload</button>
      <div class="sp"></div>
      <span class="hint">Stored in SQLite and re-verified on read, independently of the
        process that wrote them.</span>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="hd"><h3>Stored runs</h3><span class="meta" id="histcount"></span></div>
      <div class="tw"><table id="history"><tbody>
        <tr><td class="empty">Loading&hellip;</td></tr></tbody></table></div>
    </div>
    <footer>
      Handshake <span id="ver"></span> &middot; Razorpay AI Buildathon, Track 03 &middot;
      <a href="/">landing</a> &middot; <a href="/healthz">health</a> &middot; <a href="/docs">API</a><br>
      Test mode only. Synthetic catalogue, buyers and mandates; delegated caps simulated.
      The backends behind any figure are named on the line above it.
    </footer>
  </section>

  </div>
</div>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-label="Session detail">
  <div class="dhead">
    <div><div class="t" id="dtitle">Session</div><div class="s" id="dsub"></div></div>
    <button class="dclose" id="dclose">Close</button>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>

<script>
const STAGES = [
  ["Detect","instrument the session, catch the terminal failure"],
  ["Diagnose","classify the root cause from the trace alone"],
  ["Decide","pick one intervention from a fixed table of ten"],
  ["Gate","evaluate every bound — no model runs here"],
  ["Execute","act against Razorpay and the merchant"],
  ["Record","append a hash-chained audit entry"],
  ["Measure","report against the randomised control arm"],
];
const CAUSE_NAMES = {
  A1:"attribute void", A2:"spec ambiguity", A3:"quote drift", A4:"reserve ceiling",
  A5:"human-auth wall", A6:"ambiguous error", A7:"policy unreadable",
  A8:"fulfilment mismatch", B1:"insufficient balance", B2:"issuer downtime",
  B3:"mandate invalid", B4:"reserve exhausted", B5:"instrument decline",
};
/* The same taxonomy, in the words a merchant would use. The codes stay on
   screen next to them — this is a translation, not a replacement. */
const PLAIN = {
  A1:"the listing was missing a spec it needed to commit",
  A2:"two listings were impossible to tell apart",
  A3:"the price moved after it had been quoted",
  A4:"the basket came in over its delegated spending cap",
  A5:"checkout demanded a step only a human can do",
  A6:"a temporary error looked permanent to the agent",
  A7:"the returns policy was prose, not machine-readable fields",
  A8:"it could not be delivered to that pincode",
  B1:"the account was short of funds",
  B2:"the issuing bank was down",
  B3:"the payment mandate had expired or been revoked",
  B4:"the delegated reserve was already used up",
  B5:"the payment method was declined",
};
const FIXES = {
  "I-01":"filled in the missing spec and offered it again",
  "I-02":"separated the two listings and offered one",
  "I-03":"honoured the original quoted price",
  "I-04":"offered a smaller basket that fits the cap",
  "I-05":"asked the buyer's owner to raise the cap",
  "I-06":"sent the owner a single-use approval link",
  "I-07":"served the policy as machine-readable fields",
  "I-08":"retried on a different payment method",
  "I-09":"retried inside the permitted cooldown",
  "I-10":"handed it to a human queue",
  "none_buyer_self_recovery":"did nothing — the agent retried and succeeded on its own",
};
const PAGES = {
  recovery:  ["Recovery","Recover revenue from agent checkouts that already failed."],
  prevention:["Prevention","Find and price catalogue defects before they refuse a basket."],
  history:   ["History","Every stored run, re-verified on read."],
};

const $ = id => document.getElementById(id);
const inr = v => "₹" + Math.round(v || 0).toLocaleString("en-IN");
const pct = v => (100 * (v || 0)).toFixed(1) + "%";
let since = 0, timer = null, current = null, pending = null, lastGated = null, rows = 0;
let scanProgress = "";

/* ---------- navigation ---------- */
function showTab(name){
  document.querySelectorAll(".navitem").forEach(b =>
    b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll("section.tab").forEach(s =>
    s.classList.toggle("on", s.id === "tab-" + name));
  const p = PAGES[name] || PAGES.recovery;
  $("ptitle").textContent = p[0];
  $("psub").textContent = p[1];
  if(name === "history") loadHistory();
  if(location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  window.scrollTo({top:0});
}
const navItems = Array.from(document.querySelectorAll(".navitem"));
navItems.forEach((b,i) => {
  b.onclick = () => showTab(b.dataset.tab);
  b.onkeydown = e => {
    let n = null;
    if(e.key === "ArrowDown") n = (i + 1) % navItems.length;
    if(e.key === "ArrowUp") n = (i - 1 + navItems.length) % navItems.length;
    if(n !== null){ e.preventDefault(); navItems[n].focus(); navItems[n].click(); }
  };
});

/* ---------- theme ---------- */
function applyTheme(t){
  if(t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
  try { localStorage.setItem("hs-theme", t || ""); } catch(e) {}
}
/* Light is the default here, matching every Razorpay product surface. ?theme=
   forces one for a projector without disturbing the stored preference. */
const forced = new URLSearchParams(location.search).get("theme");
if(forced === "light" || forced === "dark"){
  document.documentElement.setAttribute("data-theme", forced);
} else {
  try { applyTheme(localStorage.getItem("hs-theme") || ""); } catch(e) {}
}
$("themebtn").onclick = () => {
  const now = document.documentElement.getAttribute("data-theme");
  applyTheme(now === "dark" ? "light" : "dark");
};

/* ---------- the flow ---------- */
function drawFlow(state){
  $("stages").innerHTML = STAGES.map((s,i) => {
    const st = (state || [])[i] || {};
    let cls = "fstep idle";
    if(st.blocked) cls = "fstep stop";
    else if(st.on) cls = (i === 6 ? "fstep win" : "fstep done");
    return `<div class="${cls}"><span class="node">${i+1}</span>
      <span><span class="lb">${s[0]}</span>
      <span class="dt">${st.detail || s[1]}</span></span></div>`;
  }).join("");
}
drawFlow([]);

function resetSession(sid, buyer){ pending = {sid, buyer, stages:[{},{},{},{},{},{},{}]}; }
/* A session only takes over the panel once it actually fails: most convert on
   the first pass and would otherwise blank the diagram every few milliseconds. */
function commitSession(){
  if(!pending) return;
  current = pending; pending = null;
  $("cursid").textContent = current.sid;
  drawFlow(current.stages);
  $("checks").innerHTML = "";
}
function setStage(i, detail, blocked){
  if(!current) return;
  current.stages[i] = {on:true, detail, blocked:!!blocked};
  drawFlow(current.stages);
  /* Hold a reference, not a copy: the session object keeps accumulating its
     later stages and its narration, and commitSession() replaces `current`
     with a fresh object rather than mutating this one. */
  if(i >= 3) lastGated = current;
}
function narrate(html){
  $("narrate").innerHTML = html;
  if(current) current.note = html;
}

/* ---------- session stream ---------- */
function addRow(e){
  const stream = $("stream");
  if(rows === 0) stream.innerHTML = "";
  const ok = e.recovered, failed = e.terminal === "FAILED" && !e.recovered;
  const item = e.product || "an item";
  let what;
  if(ok){
    const act = FIXES[(e.interventions || [])[0]] || "recovered";
    what = `<b>${item}</b> &mdash; ${act}`;
  } else if(failed){
    what = `<b>${item}</b> &mdash; agent stopped: `
      + (PLAIN[e.cause] || "the decline carried no usable reason code")
      + (e.cause ? ` <span class="mono">${e.cause}</span>` : "");
  } else {
    what = `<b>${item}</b> &mdash; bought on the first pass`;
  }
  const b = document.createElement("button");
  b.className = (ok ? "srow ok" : (failed ? "srow fail" : "srow")) + " new";
  b.innerHTML = `<span class="ic ${ok ? "ok" : (failed ? "no" : "pass")}"></span>
    <span class="sid">${e.session_id}</span>
    <span class="what">${what}<span class="armtag">${e.arm === "treatment" ? "treatment" : "control"}</span></span>
    <span class="amt">${inr(ok ? e.recovered_value : e.basket_value)}</span>`;
  b.onclick = () => openSession(e.session_id);
  stream.insertBefore(b, stream.firstChild);
  rows++;
  while(stream.children.length > 250) stream.removeChild(stream.lastChild);
}

function handle(e){
  switch(e.kind){
    case "session_start":
      resetSession(e.session_id, e.buyer);
      break;
    case "probe_progress":
      /* A scan is two passes over the same buyers: the flawed feed, then the
         repaired one. Say which pass and how far, so a long scan is a number
         rather than a spinner. */
      scanProgress = `pass ${e.phase === "after" ? 2 : 1} of 2 · `
        + `${e.done} of ${e.total} probes`;
      break;
    case "probe_failure":
      break;
    case "failure_detected":
      commitSession();
      setStage(0, `${inr(e.at_risk)} at risk — ${e.note}`);
      narrate(`An agent was buying <b>${e.product || "an item"}</b> and stopped with
               <b>${inr(e.at_risk)}</b> on the table. All the merchant sees is a session
               that opened and went quiet.`);
      break;
    case "diagnosis":
      setStage(1, `${e.cause} ${CAUSE_NAMES[e.cause] ? "· " + CAUSE_NAMES[e.cause] : ""} · confidence ${e.confidence.toFixed(2)}`);
      break;
    case "verdict":
      $("checks").innerHTML = (e.checks||[]).map(c =>
        `<span class="chk ${c.result === "fail" ? "fail" : ""}">${c.rule} ${c.state}</span>`).join("");
      if(e.permitted){
        setStage(2, "intervention " + e.intervention);
        setStage(3, "every bound passed");
      } else {
        setStage(2, "no action taken");
        setStage(3, `refused by ${e.binding_rule} — ${e.reason}`, true);
        narrate(`The gate <b>refused</b> to act: ${e.binding_rule} — ${e.reason}.
                 The refusal is written to the ledger with the same standing as a permit.`);
      }
      break;
    case "action":
      setStage(4, `${e.intervention} · ${e.note}`, !e.ok);
      setStage(5, e.concession ? `concession ${inr(e.concession)} recorded`
                               : "no margin surrendered");
      break;
    case "recovered":
      setStage(6, `converted at ${inr(e.value)}`);
      narrate(`Won back <b>${inr(e.value)}</b> with ${e.intervention}. Open the session
               for its API trace and hash-chained audit entries.`);
      break;
    case "session_end": addRow(e); break;
    case "progress":
      $("prog").style.width = (100 * e.done / Math.max(1, e.total)) + "%";
      $("streamcount").textContent = `${e.done} of ${e.total}`;
      break;
    case "done":
      if(lastGated && (!current || !current.stages[3].on)){
        current = lastGated;
        drawFlow(current.stages);
        if(current.note) $("narrate").innerHTML = current.note;
      }
      if(current) $("cursid").textContent = current.sid;
      break;
    case "error":
      narrate(`<b style="color:var(--neg600)">Run aborted.</b> ${e.message}`);
      break;
  }
}

/* ---------- the result, as a sentence ---------- */
/* A reviewer should learn the outcome by reading one line. The figures beneath
   it are there to be checked, not to be assembled into the answer. */
function renderResult(t, s, running, measured){
  const lost = Math.max(0, t.at_risk - t.recovered);
  if(!t.failed && !t.recovered){
    $("r-lead").innerHTML = running
      ? "Running&hellip;" : "No run yet in this session.";
    $("r-sub").innerHTML = running
      ? "Sessions are resolving now. Failures will start appearing below."
      : "Press <b>Run batch</b> to send agent buyers at the merchant, let some of them fail, and watch Handshake try to win them back.";
    $("r-chip").textContent = running ? "in progress" : "idle";
    $("r-chip").className = "chipstat flat";
    $("r-split").hidden = true; $("r-foot").hidden = true;
    return;
  }
  $("r-split").hidden = false; $("r-foot").hidden = false;

  $("r-lead").innerHTML = t.recovered
    ? `<span class="big">${inr(t.recovered)}</span> recovered from checkouts that had already failed.`
    : `<span class="zero">Nothing recovered yet.</span>`;
  $("r-sub").innerHTML = `<b>${t.failed}</b> of the sessions in the treatment arm failed,
    putting <b>${inr(t.at_risk)}</b> at risk. Handshake won back
    <b>${t.recovered_n}</b> of them` +
    (s && measured !== false
      ? `, against a randomised control arm that recovered ${pct(s.control.recovery_rate)} of its own at-risk value.`
      : `. ${measured === false
          ? "Every session is forced into the treatment arm here, so there is no control to compare against."
          : "The comparison against the control arm appears when the run finishes."}`);

  if(measured === false){
    $("r-chip").textContent = "demonstration — not measured";
    $("r-chip").className = "chipstat flat";
  } else if(s){
    $("r-chip").textContent = `+${(s.lift*100).toFixed(1)} pts vs control`;
    $("r-chip").className = "chipstat";
  } else {
    $("r-chip").textContent = running ? "in progress" : "awaiting control";
    $("r-chip").className = "chipstat flat";
  }

  const total = t.at_risk || 1;
  $("sp-rec").style.width = (100 * t.recovered / total) + "%";
  $("sp-lost").style.width = (100 * lost / total) + "%";
  $("sk-rec").textContent = inr(t.recovered);
  $("sk-lost").textContent = inr(lost);

  $("rf-rate").textContent = pct(t.rate);
  $("rf-ctrl").textContent = s ? pct(s.control.recovery_rate) : "—";
  $("rf-lift").textContent = (s && measured !== false)
    ? (s.lift*100).toFixed(1) + " pts" : "—";
  $("rf-conc").textContent = t.recovered
    ? (100*t.concession_ratio).toFixed(2) + "% of recovery" : "—";
}

function causes(c){
  const keys = Object.keys(c);
  if(!keys.length){
    $("causes").innerHTML = '<tbody><tr><td class="empty">No failures yet.</td></tr></tbody>';
    return;
  }
  $("causes").innerHTML = "<thead><tr><th>Cause</th><th class='n'>Failed</th>"
    + "<th class='n'>At risk</th><th class='n'>Recovered</th><th>Share won back</th>"
    + "</tr></thead><tbody>" + keys.map(k => {
      const v = c[k], w = (100*v.recovered/(v.at_risk||1)).toFixed(0);
      return `<tr><td><span class="cid">${k}</span> ${v.name.replace(/_/g," ")}</td>
        <td class="n">${v.failed}</td><td class="n">${inr(v.at_risk)}</td>
        <td class="n">${inr(v.recovered)}</td>
        <td><span class="mini"><span class="t"><i style="width:${w}%"></i></span>
        <em>${w}%</em></span></td></tr>`;
    }).join("") + "</tbody>";
}

function refusals(r){
  const keys = Object.keys(r);
  $("refcount").textContent = keys.length ? "· " + keys.length + " rule(s) bound" : "";
  if(!keys.length){
    $("refusals").innerHTML = '<tbody><tr><td class="empty">Nothing refused yet.</td></tr></tbody>';
    return;
  }
  $("refusals").innerHTML = "<thead><tr><th>Rule</th><th>What it binds</th>"
    + "<th class='n'>Times</th></tr></thead><tbody>" + keys.map(k =>
    `<tr><td class="cid">${k}</td><td>${r[k].rule}</td><td class="n">${r[k].count}</td></tr>`
  ).join("") + "</tbody>";
}

function perClass(s){
  if(!s || !s.per_class) return;
  const keys = Object.keys(s.per_class);
  $("f1note").textContent = "· macro-F1 " + s.macro_f1 + ", " + s.unclassified + " unclassified";
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
    "<b>Walkthrough mode.</b> Every session is forced into the treatment arm so the "
    + "recovery path always runs. There is no control arm, so these totals demonstrate "
    + "the mechanism rather than measure it. Use <b>Run batch</b> for figures to quote."]);
  const llm = d.summary && d.summary.llm;
  if(llm && !llm.active) out.push(['bad',
    "<b>Model buyers requested but not active.</b> " + (llm.error || "")
    + " The heuristic ran instead — do not report this as a model run."]);
  if(llm && llm.active && llm.mixed_run) out.push(['bad',
    "<b>Mixed run.</b> Only " + pct(llm.model_share) + " of decisions came from the model; "
    + llm.failures + " fell back to the heuristic. These figures are attributable to neither."]);
  if(llm && llm.active && !llm.mixed_run && llm.fallbacks) out.push(['warn',
    llm.fallbacks + " of " + llm.calls + " calls fell back to the heuristic ("
    + pct(llm.model_share) + " from the model). Substantially a model run — disclose it."]);
  $("runnotes").innerHTML = out.map(([c, html]) =>
    `<div class="note ${c}" style="margin-top:14px">${html}</div>`).join("");
}

/* One line of provenance, next to the figures it belongs to. Not a warning
   panel: a method note, of the kind any measured result carries. */
function provenance(d){
  if(!d.summary) return;
  const b = d.backends || {}, s = d.summary, llm = s.llm, bits = [];
  const n = (s.treatment && s.control && s.treatment.sessions != null)
    ? s.treatment.sessions + s.control.sessions : null;
  if(n) bits.push(n + " agent checkouts");
  bits.push(b.payments === "razorpay" ? "payments: <b>Razorpay test mode</b>"
                                      : "payments: simulated rail");
  if(llm && llm.active){
    const model = (llm.models_used && llm.models_used.length)
      ? llm.models_used.join(", ") : "model";
    bits.push("buyers: <b>" + model + "</b>"
      + (llm.model_share != null ? " (" + pct(llm.model_share) + " of decisions)" : ""));
  } else {
    bits.push("buyers: scripted decision policy");
  }
  if(s.simulated && s.simulated.length)
    bits.push("delegated caps and catalogue simulated");
  $("prov").innerHTML = bits.join(" &middot; ");
}

function badges(d){
  const b = d.backends, out = [];
  out.push(`<span class="pill ${b.payments === "razorpay" ? "live" : "sim"}">payments: ${b.payments}</span>`);
  out.push(`<span class="pill ${b.buyers === "llm" ? "live" : "sim"}">buyers: ${b.buyers}</span>`);
  (d.pool || []).forEach(p => out.push(
    `<span class="pill ${p.exhausted ? "sim" : ""}">${p.key} · ${p.calls} calls</span>`));
  if(d.demo_mode) out.push('<span class="pill">demo mode</span>');
  $("badges").innerHTML = out.join("");
  $("ver").textContent = "v" + (d.version || "");
  $("ks").classList.toggle("on", !!d.kill_switch);
  $("ks").setAttribute("aria-pressed", String(!!d.kill_switch));
}

/* A cold visitor should see a real stored result before pressing anything. */
async function hydrate(){
  let d;
  try { d = await (await fetch("/api/overview")).json(); } catch(e) { return; }
  if(d.batch && d.batch.headline && rows === 0){
    const h = d.batch.headline;
    $("r-split").hidden = false; $("r-foot").hidden = false;
    $("r-lead").innerHTML =
      `<span class="big">${inr(h.recovered)}</span> recovered from checkouts that had already failed.`;
    $("r-sub").innerHTML = `${h.failed != null ? `<b>${h.failed}</b> checkouts failed in the
      treatment arm of the last stored run` : "From the last stored run"} of
      <b>${d.batch.sessions}</b> sessions, measured against a randomised control arm.
      Run one yourself to reproduce it.`;
    if(h.lift != null){
      $("r-chip").textContent = `+${(100*h.lift).toFixed(1)} pts vs control`;
      $("r-chip").className = "chipstat";
      $("rf-lift").textContent = (100*h.lift).toFixed(1) + " pts";
    }
    if(h.at_risk){
      $("sp-rec").style.width = (100*h.recovered/h.at_risk) + "%";
      $("sp-lost").style.width = (100*(h.at_risk-h.recovered)/h.at_risk) + "%";
      $("sk-rec").textContent = inr(h.recovered);
      $("sk-lost").textContent = inr(h.at_risk - h.recovered);
    }
    if(h.recovery_rate != null) $("rf-rate").textContent = pct(h.recovery_rate);
    if(h.control_rate != null) $("rf-ctrl").textContent = pct(h.control_rate);
    if(h.concession_ratio != null)
      $("rf-conc").textContent = (100*h.concession_ratio).toFixed(2) + "% of recovery";
    $("streamcount").textContent = "last stored run";
  }
}

/* ---------- prevention ---------- */
function renderScan(d){
  if(d.scanning){
    $("scanbadge").textContent = scanProgress || "probing…";
    $("scanwrap").innerHTML = '<div class="card" style="margin-top:14px"><div class="zero-state"><h4>Sending agent buyers at the catalogue</h4><p>No faults are injected, so every failure they hit belongs to the feed itself.</p></div></div>';
    return;
  }
  scanProgress = "";
  const r = d.readiness;
  if(!r) return;
  if(r.error){
    $("scanbadge").textContent = "failed";
    $("scanwrap").innerHTML = `<div class="note bad" style="margin-top:14px">${r.error}</div>`;
    return;
  }
  $("scanbadge").textContent = r.listings + " listings · " + r.sessions + " probes";
  const priced = r.priced.map(x =>
    `<tr><td>${x.defect.replace(/_/g," ")}</td><td class="cid">${x.field}</td>
     <td class="n">${x.sessions}</td><td class="n">${inr(x.at_risk)}</td>
     <td class="n">${x.skus.length}</td></tr>`).join("");
  const defects = r.defects_by_field.map(x =>
    `<tr><td>${x.kind.replace(/_/g," ")}</td><td class="cid">${x.field}</td>
     <td class="n">${x.sku_count}</td><td>${x.detail}</td></tr>`).join("");
  const worst = r.priced && r.priced.length ? r.priced[0] : null;

  $("scanwrap").innerHTML = `
    <div class="result">
      <div class="rtop">
        <div>
          <p class="rlead"><span class="big">${inr(r.delta.revenue_gained)}</span>
            was being refused by ${r.repaired_skus.length} fixable listings.</p>
          <p class="rsub">${worst ? `The worst single defect is a missing
            <b>${worst.field}</b> on ${worst.skus.length === 1 ? "one listing" : worst.skus.length + " listings"},
            which alone refused <b>${inr(worst.at_risk)}</b>. ` : ""}Repairing them took
            failed sessions from <b>${r.before.failed}</b> down to <b>${r.after.failed}</b>
            across ${r.sessions} identical agent probes.</p>
        </div>
        <div class="rstate"><span class="chipstat">readiness ${r.readiness_score}%</span></div>
      </div>
      <div class="ba">
        <span class="lbl">before</span>
        <span class="track b"><i style="width:100%"></i></span>
        <span class="val">${r.before.failed} refused <em>· ${inr(r.before.revenue)} taken</em></span>
        <span class="lbl">after</span>
        <span class="track a"><i style="width:${Math.max(2, 100*r.after.failed/(r.before.failed||1))}%"></i></span>
        <span class="val good">${r.after.failed} refused <em>· ${inr(r.after.revenue)} taken</em></span>
      </div>
      <div class="rfoot">
        <div><div class="k">Worth per 1,000 sessions</div>
          <div class="v pos">${inr(r.delta.per_1000_sessions)}</div></div>
        <div><div class="k">Blocking defects</div>
          <div class="v">${r.defects_found.length}</div></div>
        <div><div class="k">Sessions won back</div>
          <div class="v">${r.delta.sessions_recovered}</div></div>
        <div><div class="k">Integration needed</div>
          <div class="v mut">none — read-only feed</div></div>
      </div>
    </div>

    <details class="adv">
      <summary><b>Evidence</b>&nbsp;<small>${r.defects_found.length} defects, their measured cost, and every affected field</small><span class="sp"></span><span class="cv">&#9662;</span></summary>
      <div class="advbody">
        <h4>What each defect cost</h4>
        <div class="card"><div class="tw"><table><thead><tr><th>Defect</th>
          <th>Field to fix</th><th class="n">Sessions</th><th class="n">Value refused</th>
          <th class="n">Listings</th></tr></thead><tbody>${priced}</tbody></table></div></div>
        <h4>Every defect found by inspection <span style="color:var(--tx3);font-weight:400">· no agents needed</span></h4>
        <div class="card"><div class="tw"><table><thead><tr><th>Kind</th><th>Field</th>
          <th class="n">Listings</th><th>Detail</th></tr></thead>
          <tbody>${defects}</tbody></table></div></div>
        ${(r.non_catalogue && r.non_catalogue.length) ? `
          <h4>Not the catalogue's fault <span style="color:var(--tx3);font-weight:400">· no field can fix these</span></h4>
          <div class="card"><div class="tw"><table><thead><tr><th>Cause</th><th>Why</th>
            <th class="n">Sessions</th><th class="n">Value refused</th></tr></thead><tbody>`
          + r.non_catalogue.map(x => `<tr><td class="cid">${x.cause}</td><td>${x.reason}</td>
            <td class="n">${x.sessions}</td><td class="n">${inr(x.at_risk)}</td></tr>`).join("")
          + `</tbody></table></div></div>
          <div class="note" style="margin-top:10px">These belong to the recovery layer, not
            the readiness report. A spending cap that was too low is the buyer's budget,
            not a defect in your feed.</div>` : ""}
        ${r.unpriced.length ? '<div class="note warn" style="margin-top:10px">'
          + r.unpriced.length + ' out-of-stock listings are withheld from the feed, so they '
          + 'refuse nothing measurable — they cost the impression, not the basket. They are '
          + 'reported as advisories and kept out of the readiness score.</div>' : ""}
      </div>
    </details>`;
}

/* ---------- history ---------- */
async function loadHistory(){
  const r = await fetch("/api/runs?limit=30");
  const d = await r.json();
  const runs = d.runs || [];
  $("histcount").textContent = runs.length ? runs.length + " stored" : "";
  if(!runs.length){
    $("history").innerHTML = '<tbody><tr><td class="empty"><b>No runs stored yet</b>Run a batch or a scan and it will appear here.</td></tr></tbody>';
    return;
  }
  $("history").innerHTML = "<thead><tr><th>When</th><th>Kind</th><th class='n'>Sessions</th>"
    + "<th>Backends</th><th>Outcome</th><th></th></tr></thead><tbody>"
    + runs.map(x => {
      const when = new Date(x.created_at * 1000).toLocaleString();
      const h = x.headline || {};
      const head = x.kind === "scan"
        ? `readiness ${h.readiness}% · ${inr(h.revenue_gained)} unlocked`
        : `${inr(h.recovered)} recovered${h.lift != null ? " · +" + (100*h.lift).toFixed(1) + " pts" : ""}`;
      return `<tr class="clickable" data-run="${x.run_id}">
        <td>${when}</td><td>${x.kind}${x.measured ? "" : " (demo)"}</td>
        <td class="n">${x.sessions}</td>
        <td class="cid">${x.payments}/${x.buyers}</td><td>${head}</td>
        <td class="n cid">open →</td></tr>`;
    }).join("") + "</tbody>";
  $("history").querySelectorAll("tr[data-run]").forEach(tr =>
    tr.onclick = () => openRun(tr.dataset.run));
}

/* ---------- drawer ---------- */
function openDrawer(title, sub, html){
  $("dtitle").textContent = title; $("dsub").textContent = sub;
  $("dbody").innerHTML = html;
  $("drawer").classList.add("on"); $("scrim").classList.add("on");
}
function closeDrawer(){
  $("drawer").classList.remove("on"); $("scrim").classList.remove("on");
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
      `<span class="chk ${c.result === "fail" ? "fail" : ""}">${c.rule} ${c.state}</span>`).join("");
    return `<div class="entry"><div class="top2">
      <span class="actor">${e.actor.replace(/_/g," ")} — ${e.action.replace(/_/g," ")}</span>
      <span class="hash">prev ${e.prev_hash.slice(0,10)} → ${e.hash.slice(0,10)}</span></div>
      ${Object.keys(body).length ? "<pre>" + JSON.stringify(body,null,2) + "</pre>" : ""}
      ${chips ? '<div class="checks" style="padding:8px 0 0">' + chips + "</div>" : ""}</div>`;
  }).join("");
}

async function openSession(sid){
  openDrawer(sid, "loading…", '<div class="empty">Fetching the trace…</div>');
  let trace = null, chain = null;
  try { const r = await fetch("/api/trace/" + sid); if(r.ok) trace = await r.json(); } catch(e) {}
  try { const r = await fetch("/api/session/" + sid); if(r.ok) chain = await r.json(); } catch(e) {}
  let html = "";
  if(trace){
    $("dsub").textContent = `${trace.buyer} · ${trace.persona} · ${trace.arm} arm · `
      + `${trace.terminal}${trace.recovered ? " → recovered" : ""}`;
    const item = (trace.basket && trace.basket[0]) || {};
    const cz = trace.diagnosed ? trace.diagnosed.cause : "";
    let story;
    if(trace.recovered){
      story = "It stopped because " + (PLAIN[cz] || "the failure could not be classified")
        + ". Handshake " + (FIXES[(trace.interventions || [])[0]] || "acted")
        + ", and the agent came back and paid <b>" + inr(trace.recovered_value) + "</b>.";
    } else if(trace.terminal === "FAILED"){
      story = "It stopped because "
        + (PLAIN[cz] || "the decline carried no usable reason code")
        + ", and nothing was recovered.";
    } else {
      story = "It completed on the first pass, with no help needed.";
    }
    html += `<div class="lead">
      <p>An AI shopping agent was buying
      <b>${item.title || item.sku || "an item"}</b> at
      <b>${inr(trace.basket_value)}</b>, against a delegated spending cap of
      ${inr(trace.spend_cap)}.</p>
      <p>${story}</p></div>`;
    html += `<div class="note">Basket ${inr(trace.basket_value)} · declared cap
      ${inr(trace.spend_cap)}${trace.diagnosed ? " · diagnosed <b>" + trace.diagnosed.cause
      + "</b> at confidence " + trace.diagnosed.confidence : ""}${trace.recovered
      ? " · recovered " + inr(trace.recovered_value) + " via " + trace.interventions.join(", ")
      : ""}</div>`;
    html += "<h4>What the merchant actually saw</h4><ul class='tl'>"
      + trace.events.map(ev => {
        const bad = ev.http_status >= 400;
        return `<li class="${bad ? "err" : (ev.http_status === 200 ? "ok" : "")}">
          <span class="m">${ev.type}</span>
          <span class="st ${bad ? "err" : ""}">${ev.http_status}</span>
          <div class="d">${JSON.stringify(ev.response).slice(0,190)}</div></li>`;
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
    html += `<h4>Audit chain — ${chain.chain_valid ? "verified" : "BROKEN at " + chain.first_bad}</h4>`
      + chainHtml(chain.entries);
  } else if(trace){
    html += '<h4>Audit chain</h4><div class="empty">No ledger entries — this session did not fail.</div>';
  }
  if(!trace && !chain)
    html = '<div class="empty"><b>Not in the current run</b>This session belongs to an earlier run. Open it from History.</div>';
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
    html += `<h4>Readiness</h4><pre>${JSON.stringify({readiness_score: s.readiness_score,
      listings: s.listings, delta: s.delta, priced: s.priced}, null, 2)}</pre>`;
  } else {
    html += `<h4>Summary</h4><pre>${JSON.stringify({arms: s.arms,
      lift_over_control: s.lift_over_control,
      diagnosis: {macro_f1: s.diagnosis.macro_f1, unclassified: s.diagnosis.unclassified},
      policy_refusals: s.policy_refusals, exception_count: s.exception_count,
      ledger: s.ledger, simulated_components: s.simulated_components}, null, 2)}</pre>`;
    const failed = (d.sessions || []).filter(x => x.recovered || x.terminal_state === "FAILED");
    html += `<h4>Sessions (${failed.length} at risk of the ${d.sessions.length} stored)</h4>`
      + '<div class="card"><div class="tw"><table><thead><tr><th>Session</th><th>Cause</th>'
      + '<th class="n">Basket</th><th>Outcome</th></tr></thead><tbody>'
      + failed.slice(0,60).map(x => `<tr><td class="cid">${x.session_id}</td>
        <td class="cid">${x.diagnosed_cause || "—"}</td>
        <td class="n">${inr(x.basket_value)}</td>
        <td>${x.recovered ? "recovered " + inr(x.recovered_value) : (x.exception || "unresolved")}</td>
        </tr>`).join("") + "</tbody></table></div></div>";
  }
  $("dbody").innerHTML = html;
}

/* ---------- polling ---------- */
async function poll(){
  let d;
  try { d = await (await fetch("/api/state?since=" + since)).json(); } catch(e) { return; }
  since = d.next;
  d.events.forEach(handle);
  renderResult(d.totals, d.summary, d.running, d.measured);
  causes(d.totals.causes);
  refusals(d.totals.refusals);
  perClass(d.summary);
  runNotes(d);
  badges(d);
  provenance(d);
  renderScan(d);
  const busy = d.running || d.scanning;
  ["run","walk","scan","zrun","zscan"].forEach(id => { const el = $(id); if(el) el.disabled = busy; });
  $("stop").disabled = !d.running;
  $("ctlhint").textContent = busy
    ? "Running — click any session for its trace."
    : "Takes about twenty seconds.";
  if(!busy && timer){ clearInterval(timer); timer = null; }
}

async function post(url, body){
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(body || {})});
  if(!r.ok){
    const j = await r.json().catch(() => ({}));
    showTab("recovery");
    $("runnotes").innerHTML = `<div class="note bad" style="margin-top:14px"><b>${j.error || r.status}</b></div>`;
    return false;
  }
  return true;
}

async function start(mode){
  since = 0; rows = 0; current = null; pending = null; lastGated = null;
  $("stream").innerHTML = '<div class="empty">starting…</div>';
  drawFlow([]);
  $("checks").innerHTML = "";
  showTab("recovery");
  const ok = await post("/api/run", {sessions: +$("sessions").value, mode,
    offline: $("offline").checked});
  if(!ok) return;
  if(timer) clearInterval(timer);
  timer = setInterval(poll, mode === "walkthrough" ? 240 : 420);
  poll();
}
async function startScan(){
  showTab("prevention");
  const ok = await post("/api/readiness", {sessions: +$("scansessions").value});
  if(!ok) return;
  if(timer) clearInterval(timer);
  timer = setInterval(poll, 600);
  poll();
}

$("run").onclick = () => start("batch");
$("zrun").onclick = () => start("batch");
$("walk").onclick = () => start("walkthrough");
$("stop").onclick = () => post("/api/stop");
$("scan").onclick = startScan;
$("zscan").onclick = startScan;
$("reload").onclick = loadHistory;
$("ks").onclick = async () => {
  const on = !$("ks").classList.contains("on");
  await post("/api/killswitch", {on});
  $("ks").classList.toggle("on", on);
  $("ks").setAttribute("aria-pressed", String(on));
};

const initial = location.hash.slice(1);
showTab(PAGES[initial] ? initial : "recovery");
poll();
loadHistory();
hydrate();
</script>
</body>
</html>
"""
