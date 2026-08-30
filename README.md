# Handshake

**Revenue recovery for agent-driven checkout.**
Razorpay AI Buildathon 2026 — Track 03, AI Revenue Recovery.

When an AI agent abandons a checkout, the merchant records a dead API session
with no reason code and no way to reach the buyer. Every existing recovery tool
— cart-abandonment email, WhatsApp nudges, discount coupons — assumes a human
with an inbox. Handshake is the layer for the other kind of buyer: it detects
the failure, works out why, executes one bounded recovery, and reports in rupees
what came back and what that cost.

---

## Quickstart

Open this folder in VS Code and run:

```bash
./run_ui.sh           # live console at http://127.0.0.1:8000  <- the demo
./run.sh              # a 500-session batch, printed and saved
./verify.sh           # tests, batch, kill switch, independent chain check
python3 preflight.py  # only if you added API keys - proves they work
```

### The console

`./run_ui.sh` serves an operator console that does three things a static report
cannot, and all three are what a demo needs.

**Run batch** streams a live run: sessions appear as they resolve, the money
view updates, the cause table fills in, and every refusal the gate makes is
listed with its binding rule. Click any session to open its audit chain -
hash-linked entries, every policy check that was evaluated, including the ones
that passed.

**Walkthrough** runs six sessions at about one second a step, so a single
recovery can be narrated: the session dies, the cause is assigned with a
confidence score, the gate evaluates its bounds, one intervention executes, the
sale converts. The seven-stage pipeline lights up as it happens. Because every
session is forced into the treatment arm there is no control, the console says
so on screen, and those totals are a demonstration, never a measurement.

**Kill switch** is a live control. Flip it during a batch and watch R-11
refusals start appearing while the money view stops moving.

The header badges show which backends are actually in use and, when a key pool
is configured, how many calls and tokens each key has spent.

Nothing above needs an API key. The default path is fully offline and
deterministic: payments are simulated locally and buyer agents use a
deterministic decision policy.

### API keys — you must add these yourself

**No keys are bundled with this repo, and none can be.** Razorpay test
credentials are issued to your account and an LLM key is billed to yours;
neither can be generated on your behalf. Both are optional — the batch above
runs without them.

Copy `.env.example` to `.env` and fill in what you want to enable. `.env` is
git-ignored and loaded automatically.

**Razorpay test mode** — Razorpay Dashboard → switch the toggle to **Test
Mode** → Account & Settings → API Keys → **Generate Test Key**. You get a
`rzp_test_...` key id and a secret shown once.

```
HS_PAYMENTS=razorpay
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
```

Then `pip install razorpay`. The backend refuses any key id that does not begin
`rzp_test_`, so a live key cannot be used by accident.

**LLM buyer agents** — a key from any supported provider. The provider is
inferred from the key prefix and can be forced with `HS_LLM_PROVIDER`.

| Provider | Key prefix | Client to install | Example model |
|---|---|---|---|
| Anthropic | `sk-ant-` | `pip install anthropic` | `claude-3-5-haiku-latest` |
| OpenAI | `sk-` | `pip install openai` | `gpt-4o-mini` |
| Groq | `gsk_` | `pip install openai` | `openai/gpt-oss-120b` |
| Anything OpenAI-compatible | — | `pip install openai` | set `HS_LLM_BASE_URL` |

```
HS_BUYERS=llm
HS_LLM_API_KEYS=gsk_first,gsk_second,gsk_third
HS_LLM_MODEL=openai/gpt-oss-20b
```

**Several keys, used in order.** One free-tier key does not cover a 500-session
batch. The pool uses the first key until its *daily* quota is spent, retires it,
and continues on the next; only when every key is spent does the batch abort. A
*per-minute* limit is waited out instead — the provider states the wait and the
code uses that number, so a temporary throttle never costs you a key.

Keys may come from different providers (`HS_LLM_MODELS` sets a model per key).
If they do, the run is not homogeneous, and the report prints
`MIXED-MODEL RUN` with the models involved. Say so when reporting those figures.

`preflight.py` probes every key, prints tokens per decision, and tells you how
many sessions the pool can actually cover:

```
  PASS  key pool  3 key(s)
  PASS  key1  gsk_zO9…wgPv  openai/gpt-oss-20b  proceed=False  268 tokens
  PASS  key2  gsk_aB1…k27Q  openai/gpt-oss-20b  proceed=False  271 tokens
  ----  pool capacity  ~1,476 sessions at 200,000 tokens/day/key
  ----  500-session batch  fits
```

Model ids move. Groq retired the `llama-3.x` ids in August 2026. If a call comes
back `model_not_found`, `preflight.py` asks the provider for the list your key
can actually reach and prints it.

Start with `--sessions 60`; every session makes one model call, so a
500-session batch costs real money and real time.

**A failed LLM call falls back to the heuristic — and is counted.** The report
prints `llm buyers  N/M decisions from <provider>` and shouts if any call
failed or if the backend was requested but never became available. A run that
quietly fell back must never be presented as an LLM run.

Verify what a run actually used: the top of every report and console prints the
list of simulated components. If it still says `payments (local simulator)`, the
environment did not pick up your key.

---

## What it does

```
detect → diagnose → decide → gate → execute → record → measure
```

- **Detect** — every agent session is instrumented end to end; terminal failures
  carry the basket value that is now at risk.
- **Diagnose** — a rule tier resolves unambiguous signatures at confidence 1.0;
  everything else is scored, and anything below the threshold is routed to the
  exception queue rather than acted on.
- **Decide** — one intervention is selected from a fixed table. Never free-form.
- **Gate** — eleven deterministic rules decide whether the action happens at all.
  **No model is consulted here.** An LLM may propose a cause; only this table
  disposes.
- **Execute** — the single permitted action, idempotent, with its reversal path
  recorded before execution.
- **Record** — an append-only, hash-chained ledger. Refusals are recorded with
  the same standing as permits.
- **Measure** — against a randomised control arm, net of the margin surrendered.

---

## Results from the reference batch

`python -m handshake.experiments.run --sessions 500 --seed 20260830`

| | treatment | control |
|---|---:|---:|
| sessions | 206 | 198 |
| failed | 73 | 82 |
| at-risk GMV | ₹296,301 | ₹313,395 |
| recovered GMV | ₹201,544 | ₹14,148 |
| recovery rate | 68.0% | 4.5% |
| concession cost | ₹1,981 | ₹0 |
| concession ratio | 0.98% | — |
| net recovery | ₹42,094 | ₹3,097 |

**Lift over control: 63.5 points.** Diagnosis macro-F1 **0.93** against the
injected fault, which the engine never reads. Ledger: 453 entries, hash chain
verified. 20 sessions ended as unresolved exceptions, listed in full.

Recovery is not uniform, and the spread is the finding:

| cause | class | recovery of at-risk GMV |
|---|---|---:|
| A1 | attribute void | 100% |
| A2 | spec ambiguity | 100% |
| A6 | ambiguous error | 100% |
| A8 | fulfilment mismatch | 100% |
| A3 | quote drift | 74% |
| A4 | reserve ceiling | 55% |
| A5 | human-auth wall | 40% |
| B3 | mandate invalid | 0% |
| UNKNOWN | unclassified | 0% |

Catalogue data defects recover almost completely and cost nothing. Failures that
need a human's consent or a buyer's money recover far less. A recovery system
that reported one blended number would hide exactly this.

---

## Honest limitations

Read this section before the numbers above.

1. **Buyers are a deterministic decision policy by default, not an LLM.**
   `HS_BUYERS=llm` with an API key routes the proceed/abandon judgement to a real
   model. The default path is offline so batches are reproducible and free.
2. **Payments are simulated by default.** `HS_PAYMENTS=razorpay` with test-mode
   credentials hits the real API. The backend refuses any key id that is not
   `rzp_test_`.
3. **Delegated spending caps are ours, not UPI's.** Reserve Pay is not available
   to developers. Caps are declared on the checkout session and enforced in this
   layer, exactly as an ACP delegated payment token declares a maximum
   chargeable amount.
4. **The control arm's own recovery is buyer behaviour, not ours.** Agents that
   re-plan and return on transient failures are credited to the buyer and appear
   in both arms.
5. **The diagnosis task is easier than production.** Faults are injected one at a
   time. Real traffic carries compound and overlapping causes. The 25% of payment
   declines that arrive without a reason code — where the engine refuses to guess
   — are the only source of realistic ambiguity here, and they are what pulls
   macro-F1 below 1.0.
6. **Prior success rates in the policy engine are priors**, published as such,
   until enough batches exist to replace them with measured rates.

---

## Running it

```bash
pip install -r requirements.txt
python -m handshake.experiments.run --sessions 500
python -m pytest handshake/tests -q
```

Artefacts land in `runs/`: the summary, the full exception list, the session
table, the exported ledger as JSONL, and a self-contained operator console.

Optional live backends:

```bash
export HS_PAYMENTS=razorpay
export RAZORPAY_KEY_ID=rzp_test_xxx
export RAZORPAY_KEY_SECRET=xxx

export HS_BUYERS=llm
export HS_LLM_API_KEY=xxx
export HS_LLM_MODEL=claude-3-5-haiku-latest
```

Adversarial and governance behaviour:

```bash
python -m handshake.experiments.run --sessions 200 --kill-switch   # R-11
python -m pytest handshake/tests/test_chain_and_pipeline.py -q -k farming
```

---

## Layout

```
handshake/
├── taxonomy.py        failure classes, interventions, rule ids
├── config.py          adapter switches and every policy bound
├── merchant/          C1  catalogue, feed, checkout sessions, fault injector
├── buyers/            C2  personas, agent loop, LLM and heuristic backends
├── recorder/          C3  session traces
├── diagnosis/         C4  rule tier, confidence gating
├── policy/            C5  the gate — deterministic, unit-tested
├── executor/          C6  interventions I-01 … I-10
├── ledger/            C7  append-only hash chain
├── console/           C8  operator report
├── experiments/       batch runner, allocation, metrics, CLI
├── tests/             one test per stopping rule, plus adversarial cases
└── runs/              batch artefacts
```

---

## The failure taxonomy

**Family A — pre-payment agent abandonment.** A1 attribute void · A2 spec
ambiguity · A3 quote drift · A4 reserve ceiling · A5 human-auth wall ·
A6 ambiguous error · A7 policy unreadable · A8 fulfilment mismatch.

**Family B — post-authorisation payment failure.** B1 insufficient balance ·
B2 issuer downtime · B3 mandate invalid · B4 reserve exhausted ·
B5 instrument decline.

Family A carries the thesis. Family B anchors the number in money that is
already being lost today, under rules that are already written.

---

## The stopping rules

| | rule | default |
|---|---|---|
| R-01 | maximum re-offers per session | 2 |
| R-02 | maximum interventions per buyer per 24h | 3 |
| R-03 | explicit decline is permanent | absolute |
| R-04 | cumulative concession ceiling | 8% of basket |
| R-05 | halt when expected recovery < intervention cost | EV-gated |
| R-06 | abuse pattern — repeat abandonment to farm concessions | 3 in 24h |
| R-07 | never raise a spending cap without recorded consent | absolute |
| R-08 | mandate retries capped, then routed to a human | 2 |
| R-09 | quiet hours on human-facing escalation | 21:00–09:00 IST |
| R-10 | confidence below threshold routes to exceptions | 0.70 |
| R-11 | global kill switch | operator |

Each has a unit test. Rules that do not fire in a given batch are named in the
console as not observed, rather than quietly implied to be working.

---

## Escalation

Three rungs, never skipped. Machine-to-machine first — repair the data, re-offer
to the agent, no human touched. Escalation to the human principal only where
policy *requires* consent, via a single-use expiring link, frequency-capped and
quiet-hours bounded, with an explicit decline final and permanent. Merchant
operations last, for anything the system cannot resolve or is not permitted to
attempt.

The system never contacts a human directly, never raises a spending cap on its
own authority, and never escalates a rung it has not earned.

---

## Compliance

Test mode only. Synthetic buyers, catalogue and mandates; no real personal data.
Defence-only — nothing here probes, evades or exploits any third-party system.
Every money-moving action records its reversal path before it executes. Simulated
components are named in `config.simulated_components()` and printed at the top of
every report.
