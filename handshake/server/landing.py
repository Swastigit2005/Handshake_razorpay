"""The landing page — the first thing a stranger sees.

Served at `/`. The console lives at `/console`.

Modelled on how Razorpay presents its own products rather than on how a SaaS
template presents itself: light surfaces throughout, headings in a single
weight and colour, asymmetric two-column sections, generous whitespace, and a
real screenshot of the working console doing the job that a stock illustration
would otherwise be asked to do.

Deliberately absent: gradient glow blobs, grid overlays, pill eyebrow chips
with pulsing dots, and headings split across two fonts. Each of those is a
template signature, and repeated across a page they read as decoration applied
to content rather than design derived from it.

Figures are baked in from the canonical run committed in `runs/` and then
re-hydrated from `/api/overview`, so the page is correct before JavaScript runs
and current after it does.
"""

LANDING = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Handshake — revenue recovery for agent-driven checkout</title>
<meta name="description" content="AI agents abandon checkout and leave no one to email. Handshake diagnoses the dead API session, repairs what broke, re-offers to the agent, and proves the recovery in rupees.">
<meta property="og:title" content="Handshake — revenue recovery for agent-driven checkout">
<meta property="og:description" content="You can't email a bot a coupon. 67.3 points of lift over a randomised control, every rupee gated by eleven deterministic rules.">
<meta property="og:type" content="website">
<meta property="og:image" content="https://handshake-console.onrender.com/assets/social/handshake-og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@500;600;700&family=Inter:wght@400;500;600&display=swap">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='7' fill='%23050505'/><path d='M11 9v14M11 9h4a3.5 3.5 0 0 1 0 7h-4' stroke='%231364F1' stroke-width='2.6' fill='none' stroke-linecap='round'/><path d='M21 23V9M21 23h-4a3.5 3.5 0 0 1 0-7h4' stroke='%2300BD6E' stroke-width='2.6' fill='none' stroke-linecap='round'/></svg>">
<style>
/* Palette is Razorpay's Blade system, matching the console exactly so the
   screenshots below sit in the page rather than on it. */
:root{
  --blue:#1364F1; --blue-dk:#0E54CD; --blue-lt:#4287FF; --blue-100:#D6E5FF;
  --blue-50:#F5F9FF;
  --green:#009954; --green-lt:#00BD6E; --green-50:#E6F4ED; --green-100:#CEE9DB;
  --red:#DF3E30; --red-50:#FDF3F2; --red-100:#FBE6E4;
  --amber:#F56D19; --amber-50:#FFF6F0; --amber-100:#FFE7D6;

  --ink:#050505; --tx:#192839; --tx2:#4B5563; --tx3:#7B878E;
  --bg:#FFFFFF; --bg2:#F7F9FC; --bg3:#F1F5FA;
  --line:#E4E7EB; --line2:#EFF1F4;
  --navy:#080D29; --navy2:#101736;

  --fd:"Inter Tight",-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
  --f:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
  --fm:ui-monospace,SFMono-Regular,Menlo,"Roboto Mono",monospace;

  --r8:8px; --r12:12px; --r16:16px; --rmax:9999px;
  --e1:0 1px 2px rgba(5,5,5,.05);
  --e2:0 4px 16px -6px rgba(5,5,5,.10),0 1px 3px rgba(5,5,5,.05);
  --e3:0 30px 70px -28px rgba(5,5,5,.28),0 4px 14px -6px rgba(5,5,5,.08);
  --ease:cubic-bezier(.2,.7,.3,1);
  --pad:clamp(20px,5vw,56px);
  --maxw:1200px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);font-family:var(--f);font-size:16px;
  line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden}
img{max-width:100%;display:block}
a{color:inherit}
::selection{background:var(--blue-100);color:var(--ink)}
.shell{max-width:var(--maxw);margin:0 auto;padding-inline:var(--pad)}
.mono{font-family:var(--fm);font-variant-numeric:tabular-nums}

/* ------------------------------------------------------------- typography */
h1,h2,h3{font-family:var(--fd);color:var(--ink);margin:0;letter-spacing:-.03em;
  font-weight:600}
h1{font-size:clamp(38px,5.4vw,60px);line-height:1.06;letter-spacing:-.036em;font-weight:700}
h2{font-size:clamp(28px,3.5vw,40px);line-height:1.12;max-width:19ch}
h3{font-size:19px;line-height:1.3;letter-spacing:-.02em}
.eyebrow{font-size:13px;font-weight:600;letter-spacing:.02em;color:var(--blue);
  margin-bottom:14px}
.dek{font-size:17px;line-height:1.6;color:var(--tx2);max-width:60ch;margin:16px 0 0}
.dek b{color:var(--ink);font-weight:600}
.small{font-size:14.5px;line-height:1.6;color:var(--tx2)}

/* --------------------------------------------------------------------- nav */
.nav{position:sticky;top:0;z-index:80;background:rgba(255,255,255,.9);
  backdrop-filter:saturate(1.6) blur(12px);border-bottom:1px solid var(--line2)}
.nav .shell{display:flex;align-items:center;gap:28px;height:66px}
.mark{display:flex;align-items:center;gap:10px;text-decoration:none;flex:none}
.mark .wm{font-family:var(--fd);font-weight:700;font-size:18px;letter-spacing:-.028em;
  color:var(--ink)}
.navlinks{display:flex;gap:26px;margin-left:10px}
.navlinks a{font-size:15px;color:var(--tx2);text-decoration:none;font-weight:500}
.navlinks a:hover{color:var(--ink)}
.nav .sp{flex:1}
@media(max-width:860px){.navlinks{display:none}}

/* ----------------------------------------------------------------- buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;
  font-family:var(--f);font-size:15px;font-weight:600;padding:11px 20px;
  border-radius:var(--r8);border:1px solid transparent;background:var(--blue);
  color:#fff;text-decoration:none;cursor:pointer;white-space:nowrap;
  transition:background .16s,border-color .16s,box-shadow .16s;box-shadow:var(--e1)}
.btn:hover{background:var(--blue-dk)}
.btn.sec{background:#fff;color:var(--ink);border-color:var(--line)}
.btn.sec:hover{background:var(--bg2);border-color:#D3D8DE}
.btn.ondark{background:#fff;color:var(--ink)}
.btn.ondark:hover{background:#EDF1F7}
.btn.ghostdark{background:transparent;color:#fff;border-color:rgba(255,255,255,.28)}
.btn.ghostdark:hover{background:rgba(255,255,255,.08)}
.btn.sm{font-size:14px;padding:8px 16px}
.arw{transition:transform .16s var(--ease)}
.btn:hover .arw{transform:translateX(2px)}
.tlink{font-size:15px;font-weight:600;color:var(--blue);text-decoration:none;
  display:inline-flex;align-items:center;gap:6px}
.tlink:hover{color:var(--blue-dk)}

/* -------------------------------------------------------------------- hero */
.hero{padding:clamp(34px,4.4vw,58px) 0 0;background:
  linear-gradient(180deg,var(--blue-50) 0%,#fff 62%)}
.hero .lead{max-width:34ch}
.hero .dek{font-size:18.5px;max-width:56ch}
.cta{display:flex;gap:12px;flex-wrap:wrap;margin-top:30px}
.underline{font-size:14px;color:var(--tx3);margin-top:16px}

/* the product, shown rather than described */
.shotwrap{max-width:1340px;margin:0 auto;padding-inline:var(--pad)}
.shot{margin-top:clamp(30px,4.4vw,48px);border-radius:var(--r16);overflow:hidden;
  border:1px solid var(--line);box-shadow:var(--e3);background:#fff;
  max-height:600px}
.shot img{width:100%;height:auto}
.shotcap{font-size:13.5px;color:var(--tx3);margin-top:14px;text-align:center}

/* trust strip — facts, not logos we do not have */
.trust{border-top:1px solid var(--line2);border-bottom:1px solid var(--line2);
  margin-top:clamp(40px,6vw,72px);background:var(--bg2)}
.trust .shell{display:grid;grid-template-columns:repeat(auto-fit,minmax(172px,1fr));
  gap:12px 24px;padding-block:18px;align-items:center}
.trust span{font-size:13.5px;color:var(--tx2);display:flex;align-items:center;gap:8px}
.trust b{color:var(--ink);font-weight:600}
.trust svg{flex:none;color:var(--green)}

/* ---------------------------------------------------------------- sections */
.band{padding:clamp(60px,8vw,104px) 0}
.band.alt{background:var(--bg2);border-block:1px solid var(--line2)}
.band.dark{background:var(--navy);color:#E8ECF4}
.band.dark h2,.band.dark h3{color:#fff}
.band.dark .dek{color:#A9B4CC}
.band.dark .dek b{color:#fff}
.band.dark .eyebrow{color:#7FA8FF}
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.12fr);
  gap:clamp(32px,5vw,72px);align-items:center}
.split.rev{grid-template-columns:minmax(0,1.12fr) minmax(0,1fr)}
@media(max-width:940px){.split,.split.rev{grid-template-columns:1fr;gap:36px}
  .split.rev > *:first-child{order:2}}
.headrow{display:flex;justify-content:space-between;align-items:flex-end;gap:32px;
  flex-wrap:wrap;margin-bottom:clamp(28px,4vw,46px)}

/* ------------------------------------------------------------- API console */
.term{background:var(--navy);border-radius:var(--r12);overflow:hidden;
  box-shadow:var(--e3);border:1px solid rgba(255,255,255,.08)}
.term .bar{display:flex;align-items:center;gap:9px;padding:12px 16px;
  border-bottom:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.02)}
.term .bar b{font-family:var(--fm);font-size:12px;color:#9AA6C2;font-weight:400}
.term .bar .sp{flex:1}
.term .bar em{font-family:var(--fm);font-size:11.5px;color:#67739A;font-style:normal}
.term ol{margin:0;padding:12px 16px 16px;list-style:none;font-family:var(--fm);
  font-size:13px;line-height:1.5}
.term li{display:grid;grid-template-columns:54px 1fr auto;gap:12px;padding:7px 0;
  align-items:baseline;border-bottom:1px solid rgba(255,255,255,.05)}
.term li:last-child{border-bottom:none}
.term .vb{color:#7FA8FF}
.term .pth{color:#B9C3DA;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.term .sc{color:#4CD494}
.term .sc.bad{color:#FF8A80}
.term .sc.non{color:#67739A}
.term .gap{display:block;text-align:center;color:#67739A;padding:15px 0 4px;
  font-size:12.5px;border-top:1px solid rgba(255,255,255,.07);margin-top:6px}
.term .gap b{color:#FF8A80;font-weight:500}

/* ------------------------------------------------------------- stage rail */
.rail{display:grid;grid-template-columns:repeat(7,1fr);gap:0;margin-top:44px;
  border:1px solid var(--line);border-radius:var(--r12);overflow:hidden;background:#fff}
@media(max-width:1020px){.rail{grid-template-columns:repeat(2,1fr)}}
@media(max-width:560px){.rail{grid-template-columns:1fr}}
.rstage{padding:20px 18px 22px;border-right:1px solid var(--line2);position:relative}
.rstage:last-child{border-right:none}
.rstage .n{width:24px;height:24px;border-radius:50%;background:var(--blue-50);
  color:var(--blue);border:1px solid var(--blue-100);display:grid;place-items:center;
  font-size:12px;font-weight:600;font-family:var(--fd)}
.rstage.key .n{background:var(--blue);color:#fff;border-color:var(--blue)}
.rstage .t{font-family:var(--fd);font-size:16px;font-weight:600;letter-spacing:-.02em;
  margin-top:14px}
.rstage .d{font-size:13.5px;color:var(--tx2);margin-top:6px;line-height:1.48}
.rstage.key{background:var(--blue-50)}

/* ------------------------------------------------------------- rule board */
.rules{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:1px;
  background:var(--line2);border:1px solid var(--line);border-radius:var(--r12);
  overflow:hidden;margin-top:36px}
.rule{background:#fff;padding:15px 16px}
.rule .id{font-family:var(--fm);font-size:12px;color:var(--blue);font-weight:500}
.rule .tx{font-size:14px;color:var(--tx2);margin-top:5px;line-height:1.45}
.rule.wide{grid-column:1/-1;background:var(--blue-50);display:flex;gap:12px;
  align-items:baseline;flex-wrap:wrap}
.rule.wide .tx{margin-top:0;color:var(--ink);font-weight:500}
.rule.wide .flag{margin-left:auto;font-size:12.5px;color:var(--green);font-weight:600}
.pull{font-family:var(--fd);font-size:clamp(22px,2.6vw,30px);line-height:1.3;
  letter-spacing:-.028em;font-weight:600;margin:0;color:var(--ink)}

/* ---------------------------------------------------------------- results */
.verdict{background:#fff;border:1px solid var(--line);border-radius:var(--r16);
  padding:clamp(22px,3vw,32px);box-shadow:var(--e1)}
.vlead{font-family:var(--fd);font-size:clamp(24px,3vw,34px);font-weight:600;
  letter-spacing:-.032em;line-height:1.18;margin:0;max-width:26ch;color:var(--ink)}
.vlead .big{color:var(--green)}
.vbar{display:flex;height:38px;border-radius:var(--r8);overflow:hidden;margin-top:22px;
  background:var(--bg3);border:1px solid var(--line)}
.vbar i{display:block;height:100%}
.vbar .rec{width:0;background:linear-gradient(180deg,var(--green-lt),var(--green));
  transition:width 1.1s var(--ease)}
.vbar .lost{flex:1;background:repeating-linear-gradient(135deg,
  #D9DFE8 0 7px,#E7EBF1 7px 14px)}
.vkey{display:flex;gap:22px;flex-wrap:wrap;margin-top:13px;font-size:14.5px;
  color:var(--tx2)}
.vkey span{display:flex;align-items:center;gap:8px}
.vkey i{width:11px;height:11px;border-radius:3px;display:block}
.vkey i.rec{background:var(--green)}
.vkey i.lost{background:#D9DFE8}
.vkey b{color:var(--ink);font-weight:600}
.vkey .ctl{color:var(--tx3);margin-left:auto}
@media(max-width:760px){.vkey .ctl{margin-left:0}}

.figs{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line2);
  border:1px solid var(--line);border-radius:var(--r12);overflow:hidden;margin-top:16px}
@media(max-width:900px){.figs{grid-template-columns:repeat(2,1fr)}}
.fig{background:#fff;padding:18px 20px}
.fig .k{font-size:13px;color:var(--tx3)}
.fig .v{font-family:var(--fd);font-size:28px;font-weight:600;letter-spacing:-.03em;
  margin-top:6px;font-variant-numeric:tabular-nums;color:var(--ink)}
.fig .v.g{color:var(--green)}
.fig .n{font-size:13px;color:var(--tx2);margin-top:6px;line-height:1.45}

.spread{margin-top:16px;border:1px solid var(--line);border-radius:var(--r12);
  background:#fff;overflow:hidden}
.spread .sh{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  padding:16px 20px;border-bottom:1px solid var(--line2);flex-wrap:wrap}
.spread .sh b{font-family:var(--fd);font-size:16px;font-weight:600;letter-spacing:-.018em}
.spread .sh em{font-size:13px;color:var(--tx3);font-style:normal}
.srow{display:grid;grid-template-columns:38px minmax(110px,1fr) minmax(0,2.4fr) 62px;
  gap:14px;align-items:center;padding:9px 20px;border-bottom:1px solid var(--line2)}
.srow:last-of-type{border-bottom:none}
.srow .cid{font-family:var(--fm);font-size:12.5px;color:var(--blue)}
.srow .nm{font-size:14.5px;color:var(--tx2)}
.srow .tr{height:8px;background:var(--bg3);border-radius:var(--rmax);overflow:hidden}
.srow .tr i{display:block;height:100%;width:0;border-radius:var(--rmax);
  background:var(--green);transition:width .9s var(--ease)}
.srow .pc{font-size:13.5px;text-align:right;font-weight:600;
  font-variant-numeric:tabular-nums}
.srow.zero .tr i{background:var(--line)}
.srow.zero .pc,.srow.zero .cid{color:var(--tx3)}
.sfoot{padding:16px 20px;background:var(--bg2);border-top:1px solid var(--line2);
  font-size:14.5px;color:var(--tx2);line-height:1.55}
.sfoot b{color:var(--ink)}

/* ------------------------------------------------------------- prevention */
.ba{display:grid;grid-template-columns:62px minmax(0,1fr) auto;gap:11px 16px;
  align-items:center;margin-top:26px}
@media(max-width:640px){.ba{grid-template-columns:62px minmax(0,1fr)}
  .ba .val{grid-column:2}}
.ba .l{font-size:13px;color:var(--tx3);text-align:right}
.ba .t{height:32px;border-radius:var(--r8);background:var(--bg3);overflow:hidden;
  border:1px solid var(--line)}
.ba .t i{display:block;height:100%;width:0;border-radius:var(--r8);
  transition:width 1s var(--ease)}
.ba .t.b i{background:var(--red)}
.ba .t.a i{background:var(--green)}
.ba .val{font-size:14.5px;font-weight:600;white-space:nowrap;
  font-variant-numeric:tabular-nums;color:var(--ink)}
.ba .val em{font-style:normal;font-weight:400;color:var(--tx3)}
.ba .val.g{color:var(--green)}
.dtab{margin-top:26px;border:1px solid var(--line);border-radius:var(--r12);
  overflow:hidden;background:#fff}
.dtab table{border-collapse:collapse;width:100%;font-size:14px}
.dtab th{text-align:left;font-size:12.5px;font-weight:500;color:var(--tx3);
  padding:11px 16px;background:var(--bg2);border-bottom:1px solid var(--line2)}
.dtab td{padding:11px 16px;border-bottom:1px solid var(--line2);color:var(--tx2)}
.dtab tr:last-child td{border-bottom:none}
.dtab td.f{font-family:var(--fm);font-size:13px;color:var(--blue)}
.dtab td.n{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);
  white-space:nowrap}
.dtab tr.hi td{background:var(--red-50)}

/* ------------------------------------------------------------------ close */
.finale{background:var(--navy);color:#fff;padding:clamp(60px,8vw,100px) 0}
.finale h2,.finale h3{color:#fff}
.finale .dek{color:#A9B4CC}
.finale .dek b{color:#fff}
.finale .eyebrow{color:#7FA8FF}
.beats{display:grid;gap:1px;background:rgba(255,255,255,.1);
  border:1px solid rgba(255,255,255,.12);border-radius:var(--r12);overflow:hidden}
.beat{background:var(--navy2);padding:18px 20px;display:grid;
  grid-template-columns:26px 1fr;gap:14px;align-items:start}
.beat .bn{width:24px;height:24px;border-radius:50%;border:1px solid rgba(127,168,255,.4);
  color:#7FA8FF;display:grid;place-items:center;font-size:12px;font-weight:600;
  font-family:var(--fd)}
.beat .bt{display:block;font-family:var(--fd);font-size:15.5px;font-weight:600;
  color:#fff;letter-spacing:-.018em}
.beat .bd{display:block;font-size:14px;color:#A9B4CC;margin-top:4px;line-height:1.5}
.beat .bd em{font-style:normal;color:#4CD494}
.cold{font-size:13.5px;color:#7B87A6;margin-top:22px;line-height:1.7}

footer{background:var(--navy);border-top:1px solid rgba(255,255,255,.1);
  padding:34px 0 44px;color:#7B87A6;font-size:14px}
footer .shell{display:flex;justify-content:space-between;gap:26px;flex-wrap:wrap}
footer a{color:#A9B4CC;text-decoration:none}
footer a:hover{color:#fff}
footer .fl{display:flex;gap:20px;flex-wrap:wrap}

.rv{opacity:0;transform:translateY(14px);
  transition:opacity .6s var(--ease),transform .6s var(--ease)}
.rv.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}
  .rv{opacity:1!important;transform:none!important}html{scroll-behavior:auto}}
</style>
</head>
<body>

<header class="nav">
  <div class="shell">
    <a class="mark" href="/">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="#050505"/>
        <path d="M11 9v14M11 9h4a3.5 3.5 0 0 1 0 7h-4" stroke="#1364F1" stroke-width="2.6" fill="none" stroke-linecap="round"/>
        <path d="M21 23V9M21 23h-4a3.5 3.5 0 0 1 0-7h4" stroke="#00BD6E" stroke-width="2.6" fill="none" stroke-linecap="round"/>
      </svg>
      <span class="wm">Handshake</span>
    </a>
    <nav class="navlinks">
      <a href="#problem">Problem</a>
      <a href="#how">How it works</a>
      <a href="#results">Results</a>
      <a href="#prevention">Prevention</a>
    </nav>
    <div class="sp"></div>
    <a class="btn sm" href="/console">Open the console <span class="arw">&rarr;</span></a>
  </div>
</header>

<!-- ================================================================ hero -->
<section class="hero">
  <div class="shell">
    <p class="eyebrow">Razorpay AI Buildathon &middot; Track 03, AI Revenue Recovery</p>
    <h1 class="lead">You can&rsquo;t email a bot a coupon.</h1>
    <p class="dek">AI agents now buy on people&rsquo;s behalf, and they abandon checkout
    for reasons a machine could fix. When an agent gives up, the merchant is left with a
    dead API session: <b>no reason code, no contact channel, no one to follow up with.</b>
    Handshake recovers those checkouts, and proves what came back in rupees.</p>
    <div class="cta">
      <a class="btn" href="/console">Open the live console <span class="arw">&rarr;</span></a>
      <a class="btn sec" href="#problem">See how it works</a>
    </div>
    <p class="underline">No sign-up, no API key. The console runs a real 200-session
    experiment in about twenty seconds.</p>

  </div>
  <div class="shotwrap">
    <figure class="shot rv" style="margin-bottom:0">
      <img src="/assets/screens/console-recovery.png" width="1380" height="900"
           alt="The Handshake console after a 200-session run, showing recovered revenue, the recovered-versus-lost split, and the resolved sessions listed individually.">
    </figure>
    <p class="shotcap">The console after a live run &mdash; not a mock-up. Every figure on
    this page came out of it.</p>
  </div>
</section>

<div class="trust">
  <div class="shell">
    <span><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 8.5 3 3 7-7"/></svg><b>Live</b>&nbsp;Razorpay test-mode orders</span>
    <span><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 8.5 3 3 7-7"/></svg><b>58 tests</b>, CI green</span>
    <span><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 8.5 3 3 7-7"/></svg><b>Hash-chained</b>&nbsp;audit ledger</span>
    <span><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 8.5 3 3 7-7"/></svg><b>Reproducible</b>&nbsp;from a seed</span>
    <span><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 8.5 3 3 7-7"/></svg><b>MIT</b>&nbsp;licensed</span>
  </div>
</div>

<!-- ============================================================= problem -->
<section class="band" id="problem">
  <div class="shell">
    <div class="split rev">
      <div>
        <p class="eyebrow">The problem</p>
        <h2>Every recovery tool ever built assumes a human with an inbox.</h2>
        <p class="dek">An abandoned human cart leaves you an email address, a phone number
        and a browsing history. An abandoned agent session leaves you four API calls and
        a silence.</p>
        <p class="dek"><b>Agents stop for machine-readable reasons</b> &mdash; a missing
        product field, two variants that cannot be told apart, a price that moved
        mid-session, a basket that came to &#8377;2,180 against a &#8377;2,000 delegated
        cap. Every one of those is fixable. None of them is visible in the trace.</p>
        <p style="margin-top:26px"><a class="tlink" href="#how">How Handshake reads the
          dead session <span class="arw">&rarr;</span></a></p>
      </div>
      <div class="term rv">
        <div class="bar"><b>What the merchant sees</b><span class="sp"></span>
          <em>sess_0f31c8 &middot; 11:04:22 IST</em></div>
        <ol>
          <li><span class="vb">POST</span><span class="pth">/checkout/sessions</span><span class="sc">201</span></li>
          <li><span class="vb">GET</span><span class="pth">/catalog/HOM-004</span><span class="sc">200</span></li>
          <li><span class="vb">PATCH</span><span class="pth">/checkout/sessions/0f31c8</span><span class="sc bad">422</span></li>
          <li><span class="vb">GET</span><span class="pth">/catalog/HOM-004?fields=capacity_l</span><span class="sc non">200</span></li>
          <li class="gap">&mdash; <b>and then nothing, ever again</b> &mdash;</li>
        </ol>
      </div>
    </div>
  </div>
</section>

<!-- ================================================================== how -->
<section class="band alt" id="how">
  <div class="shell">
    <div class="headrow">
      <div>
        <p class="eyebrow">The mechanism</p>
        <h2>Seven stages, and one of them may never use a model.</h2>
      </div>
      <p class="dek" style="margin:0;max-width:44ch">A dead session goes in. Either a
      re-offer the agent can accept comes out, or a written refusal explaining why nothing
      was attempted. Both are recorded with the same standing.</p>
    </div>

    <div class="rail">
      <div class="rstage"><div class="n">1</div><div class="t">Detect</div>
        <div class="d">Instrument the session and catch the terminal failure as it happens.</div></div>
      <div class="rstage"><div class="n">2</div><div class="t">Diagnose</div>
        <div class="d">Classify the root cause from the API trace alone, with a confidence score.</div></div>
      <div class="rstage"><div class="n">3</div><div class="t">Decide</div>
        <div class="d">Pick exactly one intervention from a fixed table of ten.</div></div>
      <div class="rstage key"><div class="n">4</div><div class="t">Gate</div>
        <div class="d">Eleven deterministic rules. No model runs at this stage, ever.</div></div>
      <div class="rstage"><div class="n">5</div><div class="t">Execute</div>
        <div class="d">Act against Razorpay and the merchant, reversal path recorded first.</div></div>
      <div class="rstage"><div class="n">6</div><div class="t">Record</div>
        <div class="d">Append a hash-chained audit entry, refusals included.</div></div>
      <div class="rstage"><div class="n">7</div><div class="t">Measure</div>
        <div class="d">Report against a randomised control arm, never against zero.</div></div>
    </div>

    <div class="split" style="margin-top:clamp(44px,6vw,72px);align-items:start">
      <div>
        <p class="pull">A model may propose a cause.<br>Only the table decides whether
        money moves.</p>
        <p class="dek">The diagnosis engine is allowed to be a language model, because a
        wrong guess there is cheap &mdash; it routes to a human. The policy gate is eleven
        if-statements with a unit test each, because a wrong guess there spends a
        merchant&rsquo;s money. <b>Every rule evaluated lands in the ledger, including the
        ones that passed.</b></p>
      </div>
      <div class="rules">
        <div class="rule"><div class="id">R-01</div><div class="tx">Re-offers per session capped at 2</div></div>
        <div class="rule"><div class="id">R-02</div><div class="tx">Interventions per buyer capped at 3 a day</div></div>
        <div class="rule"><div class="id">R-03</div><div class="tx">An explicit decline is permanent</div></div>
        <div class="rule"><div class="id">R-04</div><div class="tx">Concessions capped at 8% of basket</div></div>
        <div class="rule"><div class="id">R-05</div><div class="tx">Halt when recovery is worth less than the attempt</div></div>
        <div class="rule"><div class="id">R-06</div><div class="tx">Block repeat abandonment that farms concessions</div></div>
        <div class="rule"><div class="id">R-07</div><div class="tx">Never raise a spending cap without recorded consent</div></div>
        <div class="rule"><div class="id">R-08</div><div class="tx">Mandate retries capped, then routed to a human</div></div>
        <div class="rule"><div class="id">R-09</div><div class="tx">Quiet hours, 21:00&ndash;09:00 IST</div></div>
        <div class="rule"><div class="id">R-10</div><div class="tx">Confidence below 0.70 routes to exceptions</div></div>
        <div class="rule wide"><div class="id">R-11</div><div class="tx">Global kill switch</div>
          <div class="flag">flip it mid-run in the console</div></div>
      </div>
    </div>
  </div>
</section>

<!-- ============================================================== results -->
<section class="band" id="results">
  <div class="shell">
    <div class="headrow">
      <div>
        <p class="eyebrow">Measured, not projected</p>
        <h2>500 sessions, randomly split into treatment and control.</h2>
      </div>
      <a class="btn sec" href="/console">Reproduce it yourself <span class="arw">&rarr;</span></a>
    </div>
    <p class="dek" style="margin-top:-14px;margin-bottom:32px">Same seed, same catalogue,
    same personas, same injected faults in both arms. The only difference is whether the
    recovery layer was allowed to act &mdash; so the gap between the arms is the layer,
    not the market.</p>

    <div class="verdict rv">
      <p class="vlead"><span class="big" id="s-rec">&#8377;3,50,019</span> of the
        <span id="s-risk">&#8377;4,90,502</span> at risk came back.</p>
      <div class="vbar"><i class="rec" data-w="71.4"></i><i class="lost"></i></div>
      <div class="vkey">
        <span><i class="rec"></i>Recovered <b id="s-recb">&#8377;3,50,019</b></span>
        <span><i class="lost"></i>Still lost <b id="s-lost">&#8377;1,40,483</b></span>
        <span class="ctl">Control arm, given no help, recovered <b>&#8377;19,199</b></span>
      </div>
    </div>

    <div class="figs">
      <div class="fig"><div class="k">Lift over control</div>
        <div class="v g" id="s-lift">67.3 pts</div>
        <div class="n">71.4% recovered against the control arm&rsquo;s 4.1%</div></div>
      <div class="fig"><div class="k">Diagnosis macro-F1</div>
        <div class="v" id="s-f1">0.936</div>
        <div class="n">scored against the injected fault, which the engine never reads</div></div>
      <div class="fig"><div class="k">Margin surrendered</div>
        <div class="v" id="s-conc">1.47%</div>
        <div class="n">&#8377;5,139 conceded to bring back &#8377;3,50,019</div></div>
      <div class="fig"><div class="k">Audit chain</div>
        <div class="v">590</div>
        <div class="n">hash-chained entries, re-verified on every read</div></div>
    </div>

    <div class="spread rv">
      <div class="sh"><b>Recovery is not uniform, and the spread is the finding</b>
        <em>share of at-risk GMV recovered, by root cause</em></div>
      <div class="srow"><span class="cid">A1</span><span class="nm">attribute void</span><span class="tr"><i data-w="100"></i></span><span class="pc">100%</span></div>
      <div class="srow"><span class="cid">A2</span><span class="nm">spec ambiguity</span><span class="tr"><i data-w="100"></i></span><span class="pc">100%</span></div>
      <div class="srow"><span class="cid">A6</span><span class="nm">ambiguous error</span><span class="tr"><i data-w="100"></i></span><span class="pc">100%</span></div>
      <div class="srow"><span class="cid">A8</span><span class="nm">fulfilment mismatch</span><span class="tr"><i data-w="100"></i></span><span class="pc">100%</span></div>
      <div class="srow"><span class="cid">B1</span><span class="nm">insufficient balance</span><span class="tr"><i data-w="90"></i></span><span class="pc">90%</span></div>
      <div class="srow"><span class="cid">A5</span><span class="nm">human-auth wall</span><span class="tr"><i data-w="67"></i></span><span class="pc">67%</span></div>
      <div class="srow"><span class="cid">A3</span><span class="nm">quote drift</span><span class="tr"><i data-w="66"></i></span><span class="pc">66%</span></div>
      <div class="srow"><span class="cid">A4</span><span class="nm">reserve ceiling</span><span class="tr"><i data-w="51"></i></span><span class="pc">51%</span></div>
      <div class="srow zero"><span class="cid">B3</span><span class="nm">mandate invalid</span><span class="tr"><i data-w="0"></i></span><span class="pc">0%</span></div>
      <div class="srow zero"><span class="cid">&mdash;</span><span class="nm">unclassified</span><span class="tr"><i data-w="0"></i></span><span class="pc">0%</span></div>
      <div class="sfoot"><b>Catalogue data defects recover almost completely, and cost
      nothing.</b> Failures needing a human&rsquo;s consent or a buyer&rsquo;s money
      recover far less. Declines arriving with no usable reason code recover nothing at
      all &mdash; the engine refuses to guess, and R-10 stops any action. A single blended
      number would hide exactly this.</div>
    </div>
  </div>
</section>

<!-- =========================================================== prevention -->
<section class="band alt" id="prevention">
  <div class="shell">
    <div class="split rev">
      <div>
        <p class="eyebrow">The other direction</p>
        <h2>Recovery is reactive. Fixing the field is permanent.</h2>
        <p class="dek">Point agent buyers at a catalogue on purpose, price every defect
        they hit in refused basket value, repair the costliest ones, then re-run the
        <b>identical</b> buyers. Same seed, same personas, same decisions &mdash; only the
        feed differs, so the delta is a measurement rather than a projection.</p>

        <div class="ba">
          <span class="l">Before</span>
          <span class="t b"><i data-w="100"></i></span>
          <span class="val">35 refused <em>&middot; &#8377;11,34,605 taken</em></span>
          <span class="l">After</span>
          <span class="t a"><i data-w="8.6"></i></span>
          <span class="val g">3 refused <em>&middot; &#8377;12,58,210 taken</em></span>
        </div>
        <p class="small" style="margin-top:14px">Sessions the catalogue refused, out of 300
        identical agent probes.</p>
      </div>
      <figure class="shot rv" style="max-height:none;margin:0">
        <img src="/assets/screens/console-prevention.png" width="1080" height="540"
             alt="The Handshake console readiness scan, showing that seven fixable listings were refusing over a lakh of revenue, and the collapse in refused sessions after repair.">
      </figure>
    </div>

    <div class="dtab rv">
      <table>
        <thead><tr><th>Defect</th><th>Field to fix</th><th class="n">Sessions</th>
          <th class="n">Refused GMV</th><th class="n">Listings</th></tr></thead>
        <tbody>
          <tr class="hi"><td>missing attribute</td><td class="f">capacity_l</td><td class="n">9</td><td class="n">&#8377;63,295</td><td class="n">1</td></tr>
          <tr><td>unserviceable</td><td class="f">serviceable_pincodes</td><td class="n">12</td><td class="n">&#8377;47,684</td><td class="n">2</td></tr>
          <tr><td>variant collision</td><td class="f">variant_group</td><td class="n">12</td><td class="n">&#8377;23,789</td><td class="n">3</td></tr>
          <tr><td>prose policy</td><td class="f">policy</td><td class="n">2</td><td class="n">&#8377;1,463</td><td class="n">1</td></tr>
        </tbody>
      </table>
    </div>
    <p class="dek" style="max-width:74ch"><b>One missing field, on one listing, refused
    &#8377;63,295.</b> Repairing seven listings took 35 failed sessions down to 3 and added
    &#8377;1,23,605 &mdash; worth &#8377;4,12,017 per 1,000 agent sessions, for as long as
    the field stays filled in. Readiness score of the reference catalogue: <b>84.3%</b>.</p>
  </div>
</section>

<!-- =============================================================== finale -->
<section class="finale">
  <div class="shell">
    <div class="split">
      <div>
        <p class="eyebrow">Nothing here is a slide</p>
        <h2>Run the batch yourself.</h2>
        <p class="dek">Two hundred sessions resolve in about twenty seconds, streaming as
        they go. Every figure on this page came out of the same engine, and the console
        will reproduce it while you watch.</p>
        <div class="cta">
          <a class="btn ondark" href="/console">Open the console <span class="arw">&rarr;</span></a>
          <a class="btn ghostdark" href="https://github.com/Swastigit2005/Handshake_razorpay" target="_blank" rel="noopener">Read the source</a>
        </div>
        <p class="cold">No API key required &mdash; the default path is fully offline and
        deterministic.<br>Hosted on a free instance: if it has been idle, allow about a
        minute for a cold start.</p>
      </div>
      <div class="beats">
        <div class="beat"><span class="bn">1</span><span>
          <span class="bt">Run a 200-session batch</span>
          <span class="bd">Sessions stream in as they resolve and the money view climbs.
          The lift figure lands at the end, <em>measured against a randomised control
          arm</em> in the same batch.</span></span></div>
        <div class="beat"><span class="bn">2</span><span>
          <span class="bt">Click any session in the list</span>
          <span class="bd">A drawer opens on the raw API traffic the merchant saw, the
          diagnosis drawn from it, and <em>the hash-chained audit entries</em> behind
          every rupee.</span></span></div>
        <div class="beat"><span class="bn">3</span><span>
          <span class="bt">Flip the kill switch mid-run</span>
          <span class="bd">R-11 takes effect on the next policy evaluation. Refusals start
          appearing and <em>the money view stops moving</em> &mdash; governance
          demonstrated rather than described.</span></span></div>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="shell">
    <div>
      <div style="color:#DCE3EF;font-weight:600;font-family:var(--fd)">Handshake</div>
      <div style="margin-top:6px">Revenue recovery for agent-driven checkout.<br>
      Razorpay AI Buildathon &middot; Track 03 &middot; MIT licensed.</div>
      <div style="margin-top:12px;font-family:var(--fm);font-size:12.5px">
        Test mode only. Synthetic buyers, catalogue and mandates &mdash; no real personal data.</div>
    </div>
    <div class="fl">
      <a href="/console">Console</a>
      <a href="/healthz">Health</a>
      <a href="/docs">API</a>
      <a href="https://github.com/Swastigit2005/Handshake_razorpay" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</footer>

<script>
(function(){
"use strict";
var $=function(id){return document.getElementById(id)};
var reduce=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
var inr=function(v){return "₹"+Math.round(v).toLocaleString("en-IN")};

/* Bars fill and sections rise once, when they first come into view. */
var io=new IntersectionObserver(function(es){
  es.forEach(function(e){
    if(!e.isIntersecting)return;
    e.target.classList.add("in");
    e.target.querySelectorAll("i[data-w]").forEach(function(el,n){
      setTimeout(function(){el.style.width=el.dataset.w+"%"},reduce?0:70+n*45);
    });
    io.unobserve(e.target);
  });
},{threshold:.15,rootMargin:"0px 0px -6% 0px"});
document.querySelectorAll(".rv,.ba,.spread,.verdict").forEach(function(el){io.observe(el)});

/* The figures above are the canonical run committed in runs/. If the console has
   a newer measured batch stored, prefer it: this page must never quote a number
   the console would contradict. */
fetch("/api/overview").then(function(r){return r.json()}).then(function(d){
  var h=d.batch&&d.batch.headline; if(!h)return;
  if(h.recovered!=null){
    $("s-rec").textContent=inr(h.recovered);
    $("s-recb").textContent=inr(h.recovered);
  }
  if(h.at_risk!=null){
    $("s-risk").textContent=inr(h.at_risk);
    $("s-lost").textContent=inr(Math.max(0,h.at_risk-h.recovered));
    var bar=document.querySelector(".vbar .rec");
    if(bar) bar.dataset.w=(100*h.recovered/h.at_risk).toFixed(1);
  }
  if(h.lift!=null)$("s-lift").textContent=(100*h.lift).toFixed(1)+" pts";
  if(h.macro_f1!=null)$("s-f1").textContent=h.macro_f1;
  if(h.concession_ratio!=null)$("s-conc").textContent=(100*h.concession_ratio).toFixed(2)+"%";
}).catch(function(){/* the committed figures stand on their own */});
})();
</script>
</body>
</html>
"""
