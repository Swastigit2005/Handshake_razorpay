# The five-minute video

Everything below is clickable in the console. No slides, no mock-ups. Total
runtime 4:50, which leaves ten seconds of headroom.

## Before you record

```bash
pip install ".[console,dev]"
python3 -m pytest handshake/tests -q          # 53 passing
python3 -m handshake.experiments.run --sessions 500 --tag canonical
python3 -m handshake.readiness.run  --sessions 300 --tag canonical
./run_ui.sh
```

Running the batch and the scan **before** you record matters: the Overview tab
hydrates from the last stored run, so the page already shows real figures when
the video opens. Then set the browser to 1440×900, hide bookmarks, and pick one
theme and stay in it.

If you have keys configured, run `python3 preflight.py` first and check that
the header badges read `payments: razorpay` and `buyers: llm` in green. If a
key is spent, tick **offline** — an honest offline run beats a broken live one.

---

## Beat sheet

### 0:00–0:20 · The number, first
**On screen:** Overview tab, already loaded.

> "Five hundred agent-driven checkout sessions. Three lakh seven thousand rupees
> of basket value recovered that would otherwise have been lost, at a cost of
> under one percent of margin. Here's why that number exists."

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
accuracy". Flip the **kill switch** on and off once.

> "Eighteen actions refused in this batch. R-10 ten times — a decline with no
> usable reason code, where the engine refuses to guess rather than invent a
> cause. R-04 blocked a discount that would have breached the margin floor.
>
> Macro-F1 of 0.92 against ground truth, with twenty sessions left unclassified
> and twenty-two exceptions I could not resolve, listed in full.
>
> And the kill switch is live — flip it mid-batch and every money action stops."

### 3:30–4:20 · Prevention, which is the bigger half
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

### 4:20–4:50 · What's real, and what's next
**On screen:** the "What is real here" note, then the header badges.

> "Payments are live Razorpay test-mode orders. Buyer decisions came from a real
> model — 499 of 500. The catalogue and the faults are synthetic, and both arms
> of every comparison share that, so the lift measures the system and not the
> market. The badges say which backends any run actually used.
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

**"68% recovery is implausible."** For human abandonment, yes. Agent failures are
deterministic: supply the missing attribute and the same agent converts. The rate
is also a function of the fault mix I chose, which is why the per-cause table is
the portable result — data defects recover at 100%, consent-bound at 67%,
funds-bound at 0–40%.

**"Is this production-ready?"** No, and the README says so in a section called
Honest limitations. It's a working prototype that proves a mechanism against real
payment infrastructure and quantifies the opportunity. The specific gaps are
listed: no PIM adapter, no multi-tenancy, priors not yet measured, and the
re-offer primitive doesn't exist in any protocol.
