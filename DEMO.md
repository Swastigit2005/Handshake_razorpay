# The five-minute video

Everything below is clickable in the console. No slides, no mock-ups. Total
runtime 4:50, which leaves ten seconds of headroom.

## Before you record

Record against the **deployed URL**, not localhost. A judge should watch the same
thing they can open themselves.

    https://handshake-console.onrender.com

```bash
./verify.sh          # locally, once: 57 tests, the batch, the scan, the chain
```

Then, in the browser:

1. Load the URL once and leave it loaded — the free instance sleeps after 15
   minutes and takes about a minute to wake. Never record a cold start.
2. Confirm the **Overview** tab reads the canonical committed figures:
   ₹3,50,019 recovered · 67.3 pts lift · readiness 84.3%. If it shows a smaller
   number, you ran a demo batch and the Overview is now showing *that* run —
   either say so on camera or redeploy to reset it.
3. Dismiss the Chrome default-browser banner, hide the bookmarks bar
   (`Cmd+Shift+B`), close any video-call PIP window, go full screen.
4. Pick one theme and stay in it.

Record with `Cmd+Shift+5` → *Record Entire Screen*, microphone on.

The deployed instance runs `payments: sim` and `buyers: heuristic` deliberately —
no keys on a public URL, and no stranger burning your LLM quota. The live-backend
run (`HS_PAYMENTS=razorpay`, `HS_BUYERS=llm`, 500 of 500 decisions from
`gpt-oss-20b`) is in the README, and the two land within three points of each
other. Say that out loud rather than hiding it.

---

## Beat sheet

### 0:00–0:20 · The number, first
**On screen:** Overview tab, already loaded.

> "Five hundred agent-driven checkout sessions. Three and a half lakh rupees of
> basket value recovered that would otherwise have been lost, at a cost of a
> fifth of one percent of margin. Here's why that number exists."

Do not explain the product yet. Lead with the result.

### 0:20–1:00 · The problem
**On screen:** stay on Overview, read the lead paragraph, then scroll to the
"What is real here" note.

> "AI agents now buy on people's behalf — Amazon Rufus auto-buys on price
> thresholds, Perplexity checks out in chat, and Razorpay and NPCI have Claude
> buying groceries on Reserve Pay right now. These buyers abandon far more than
> humans. When OpenAI pulled Instant Checkout in March, Walmart's agent channel
> was converting at a third of their own site.
>
> And when an agent gives up, the merchant gets a dead API session. No reason
> code. No contact channel. Every recovery tool ever built assumes a human with
> an inbox. You cannot email a bot a coupon."

### 1:00–2:10 · One recovery, slowly
**On screen:** Recovery tab → **Walkthrough**.

Let the pipeline light up and narrate the stages as they land:

> "A strict buyer with a two-thousand rupee delegated cap. The session dies —
> six thousand at risk. All the merchant saw was a feed read and a product read,
> then silence.
>
> Diagnosis: the catalogue is missing a field the buyer needed. Confidence one
> point zero, from the rule tier, not a model.
>
> Now the gate. Eleven deterministic rules, every one of them recorded — including
> the ones that passed. No language model runs here. A model can propose a cause;
> only this table decides whether money moves.
>
> One intervention: patch the catalogue from the source record, re-offer to the
> agent. It re-evaluates and buys."

### 2:10–2:50 · The audit trail
**On screen:** click any recovered session in the stream. The drawer opens.

> "Click any rupee and you get the whole thing. Top half is what the merchant
> actually saw — the raw API traffic, the 503, the retry, the capture. Bottom
> half is the audit chain: hash-linked entries, every policy check evaluated,
> and the reversal path recorded before the money moved.
>
> The injected fault is shown too, labelled as ground truth. The diagnosis
> engine never sees it — it exists only to score the engine."

### 2:50–3:30 · Attack it, and the honest numbers
**On screen:** Recovery tab, scroll to "What the gate refused" and "Diagnosis
accuracy".

> "Eighteen actions refused in this batch. R-10 ten times — a decline with no
> usable reason code, where the engine refuses to guess rather than invent a
> cause. R-04 blocked a discount that would have breached the margin floor.
>
> Macro-F1 of 0.936 against ground truth, with fourteen sessions left
> unclassified and twenty-two exceptions I could not resolve, listed in full."

### 3:30–3:50 · The kill switch, as a controlled pair
**On screen:** flip **KILL SWITCH · R-11** to `on` *before* the run, execute 200
sessions, then flip it off and run the identical 200 again.

Do not attempt a mid-run flip on the deployed instance — the batch finishes
faster than you can narrate. The before/after pair is stronger anyway, because
it is a comparison rather than a stunt.

> "Kill switch on. Same two hundred sessions, all forty-six failures diagnosed
> correctly — and the gate refuses every single money action under R-11.
> Recoveries drop to four, concession ratio to zero, and all forty-six failures
> route to the exception list.
>
> Those four are not the system. They are buyers who retried and succeeded on
> their own — the ledger attributes them to the buyer, not to the recovery layer.
> That is the counterfactual, and it is why there is a randomised control arm at
> all.
>
> Switch off, same two hundred sessions: thirty-six recoveries, one lakh
> thirty-six thousand rupees. The only thing that changed is a human's
> permission."

### 3:50–4:30 · Prevention, which is the bigger half
**On screen:** Prevention tab → **Scan catalogue** (or the already-loaded result).

> "Everything so far is reactive: a sale fails, I win it back. But the same
> defect fails the next session too.
>
> So: send agent buyers at the catalogue on purpose. Readiness score 84 percent.
> One missing field, on one listing, refused sixty-three thousand rupees.
>
> Then repair the top defects and re-run the *identical* buyers — same seed, same
> personas, same decisions, only the feed differs. Failures go from thirty-five
> to three. A hundred and twenty-three thousand rupees, four hundred and twelve
> thousand per thousand sessions, permanently.
>
> That version needs no integration at all. Point it at a public product feed."

### 4:30–4:55 · What's real, and what's next
**On screen:** the "What is real here" note, then the header badges.

> "This instance runs the offline reproducible path — no keys on a public URL.
> The live run is in the README: payments are Razorpay test-mode orders, and
> 500 of 500 buyer decisions came from a real model. The two agree within three
> points, which is the point: the layer does not depend on how good the buyer
> agent is.
>
> The catalogue and the faults are synthetic, and both arms of every comparison
> share that, so the lift measures the system and not the market. The badges say
> which backends any run actually used.
>
> The gap I haven't closed: no agent today polls a re-offer endpoint. That
> primitive doesn't exist in ACP or UAP. Someone has to define it, and a
> processor sitting across thousands of merchants is the natural party."

Stop recording. Don't add an outro.

---

## Rules for the recording

**Show the weaknesses on screen.** The exception list, the concession ratio, the
unclassified count, the simulated-components banner. Volunteering them is what
makes everything else believable.

**Never quote walkthrough totals.** Walkthrough forces every session into the
treatment arm so the recovery path always runs. The console says so in a banner
and suppresses the lift figure. Quote batch numbers only.

**If a live backend fails mid-take**, don't fight it. Tick offline, say "this run
is the offline reproducible path", and carry on. The offline batch reproduces to
the rupee from its seed, which is a feature worth saying out loud.

---

## The three questions you will be asked

**"Your data is fake."** The catalogue and faults are, and it's on every screen.
The payments are real test-mode orders and the buyer decisions come from a real
model. Treatment and control share the same synthetic world, so the lift measures
the system. And because I injected the faults, I have ground truth — which is the
only reason diagnosis accuracy can be reported honestly instead of asserted.

**"Your kill switch still recovered twenty-six thousand rupees."** Those are
buyers that retried and converted without help — the ledger records them as
`buyer_self_recovery`, attributed to the buyer, not the layer, and the concession
ratio is zero because no money action executed. It is the same effect the control
arm measures, and reporting it rather than zeroing it is the honest choice.

**"71% recovery is implausible."** For human abandonment, yes. Agent failures are
deterministic: supply the missing attribute and the same agent converts. The rate
is also a function of the fault mix I chose, which is why the per-cause table is
the portable result — data defects recover at 100%, consent-bound at ~52%,
funds-bound at 0–51%.

**"Is this production-ready?"** No, and the README says so in a section called
Honest limitations. It's a working prototype that proves a mechanism against real
payment infrastructure and quantifies the opportunity. The specific gaps are
listed: no PIM adapter, no multi-tenancy, priors not yet measured, and the
re-offer primitive doesn't exist in any protocol.
