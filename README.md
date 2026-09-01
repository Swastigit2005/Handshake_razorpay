# Handshake

**Revenue recovery for agent-driven checkout.**
Razorpay AI Buildathon — Track 03, AI Revenue Recovery.

[![tests](https://github.com/YOURNAME/handshake/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

AI agents now buy on people's behalf. They abandon checkout far more often than
humans, and for different reasons: a product field was missing, two variants were
indistinguishable, the price moved mid-session, the basket came to ₹2,180 against
a ₹2,000 spending cap. **When an agent gives up, the merchant gets a dead API
session — no reason code, no contact channel.** Every recovery tool ever built
assumes a human with an inbox. You cannot email a bot a coupon.

Handshake is the layer for the other kind of buyer. It works in two directions:

- **Recovery** — detect the failure, diagnose it from the API trace, repair the
  input that broke, re-offer to the agent, and prove in rupees what came back.
- **Prevention** — send agent buyers at a catalogue on purpose, price every
  defect in refused basket value, then repair the top ones and re-run the
  identical buyers to measure the delta.

---

## Run it

Nothing below needs an API key. The default path is fully offline and
deterministic: payments are simulated locally and buyer agents use a
deterministic decision policy.

**Python**

```bash
pip install ".[console,dev]"
./run_ui.sh                                    # console at http://127.0.0.1:8000
```

**Docker**

```bash
docker compose up                              # console at http://127.0.0.1:8000
```

**Anything else**

```bash
./scan.sh                 # readiness scan: find and price catalogue defects
./run.sh                  # a 500-session recovery batch, printed and saved
./verify.sh               # tests, batch, kill switch, independent chain check
                          # (forces the offline backends — see below)
python3 preflight.py      # only if you added API keys — proves they work
python3 -m pytest handshake/tests -q
```

Installed console scripts: `handshake-batch`, `handshake-scan`.

`./verify.sh` deliberately forces `HS_PAYMENTS=sim` and `HS_BUYERS=heuristic`. It
is a reproducibility check, not a connectivity check: the reproducibility
assertion needs bit-identical runs, which no hosted model guarantees, and a full
pass is ~1,700 buyer decisions. Use `python3 preflight.py` to prove the live
backends work, and `./run.sh 500` for a live measured batch.

### Deploy

**[DEPLOY.md](DEPLOY.md) is the step-by-step runbook** — local verification,
GitHub push, a one-click Render Blueprint deploy with no Docker, how to test the
live URL, and how to ship changes afterwards.

A `render.yaml` and a `Procfile` are included; the image also runs anywhere that
takes a Dockerfile. The start command is:

```bash
python -m uvicorn handshake.server.app:app --host 0.0.0.0 --port $PORT
```

Health check is `GET /healthz`, which also reports which backends are live and
what the store holds.

| Variable | Effect |
|---|---|
| `HS_DEMO_MODE=1` | caps batch size (400) and enforces a cooldown between runs |
| `HS_API_TOKEN` | requires `X-Handshake-Token` on every write endpoint |
| `HS_DB` | SQLite path — runs, sessions and ledgers survive a restart |
| `HS_MAX_SESSIONS` | hard ceiling on batch size |
| `HS_NO_SEED=1` | skip importing the canonical run on startup |

One run at a time is enforced regardless; a second request gets `409`.

**Two things about free tiers, and what this repo does about them.**

Free instances have an **ephemeral filesystem** — the SQLite file is lost on every
redeploy and spin-down. So on startup the console imports the canonical run
committed in `runs/`, and re-verifies its hash chain as it does. A visitor
arriving at a cold URL sees the real figures immediately, and `/healthz` reports
what was imported. Nothing is fabricated: it is the same artefact set the README
quotes and `./verify.sh` reproduces.

Free instances also **spin down after 15 minutes of inactivity** and take about a
minute to wake. If the URL is going to be handed to a reviewer, point a free
uptime pinger at `/healthz` every 10 minutes. One always-on service costs about
744 instance-hours a month, which fits inside the 750-hour free allowance — but
only for a single service.

---

## The console

Five tabs, and everything in them is live — no slides, no mock-ups.

**Overview** hydrates from the last stored run, so a cold visitor sees real
figures before pressing anything.

**Recovery** streams a batch as it happens: sessions appear as they resolve, the
money view climbs, the cause table sorts by rupees at risk, and every refusal the
gate makes is listed with its binding rule. **Click any session** and a drawer
opens with the raw API traffic the merchant actually saw, the diagnosis, and the
hash-chained audit entries.

**Walkthrough** runs six sessions at about a second a step so one recovery can be
narrated. Every session is forced into the treatment arm, so there is no control
— the console says so on screen and suppresses the lift figure. Those totals are
a demonstration, never a measurement.

**Prevention** runs the readiness scan and shows the before/after proof.

**History** lists stored runs from SQLite. Open one and the chain is re-verified
on read, independently of the process that wrote it.

**Kill switch** is a live control in the header. Flip it during a batch and R-11
refusals start appearing while the money view stops moving.

---

## Results

### Recovery — 500 sessions, live backends

`python3 -m handshake.experiments.run --sessions 500 --seed 20260830`
with `HS_PAYMENTS=razorpay` and `HS_BUYERS=llm`.

| | treatment | control |
|---|---:|---:|
| sessions | 246 | 254 |
| failed | 98 | 105 |
| at-risk GMV | ₹449,627 | ₹434,947 |
| recovered GMV | **₹307,480** | ₹19,199 |
| recovery rate | **68.4%** | 4.4% |
| concession cost | ₹5,139 | ₹0 |
| concession ratio | **1.67%** | — |
| net recovery | ₹62,187 | ₹4,200 |

**Lift over control: 64.0 points.** Diagnosis macro-F1 **0.92** against the
injected fault, which the engine never reads. 590 ledger entries, hash chain
verified. 25 sessions left unclassified, 25 unresolved exceptions listed in full.

**500 of 500 buyer decisions came from `openai/gpt-oss-20b`** across a
three-key pool — no fallback to the heuristic, 140,237 tokens, zero rotations.

The gate refused 21 actions: R-10 thirteen times, R-04 five, R-09 three.

### The same batch with a scripted buyer instead of a model

| | scripted buyer | `gpt-oss-20b` |
|---|---:|---:|
| failed sessions | 104 | 98 |
| recovery rate | 71.4% | 68.4% |
| lift over control | 67.3 pts | 64.0 pts |
| diagnosis macro-F1 | 0.936 | 0.92 |

Within three points either way. **The layer does not depend on how good the buyer
agent is** — which matters, because agents only improve.

### Recovery is not uniform, and the spread is the finding

| cause | class | recovery of at-risk GMV |
|---|---|---:|
| A1 | attribute void | 100% |
| A2 | spec ambiguity | 100% |
| A6 | ambiguous error | 100% |
| A8 | fulfilment mismatch | 100% |
| B1 | insufficient balance | 90% |
| A5 | human-auth wall | 67% |
| A3 | quote drift | 66% |
| A4 | reserve ceiling | 51% |
| B3 | mandate invalid | 0% |
| UNKNOWN | unclassified | 0% |

Catalogue data defects recover almost completely and cost nothing. Failures that
need a human's consent or a buyer's money recover far less. Declines with no
usable reason code recover nothing, because the engine refuses to guess and R-10
stops any action. A single blended number would hide exactly this.

### Prevention — 51 listings, 300 probe sessions

`python3 -m handshake.readiness.run --sessions 300`

```
readiness score        84.3%     8 blocking defects across 8 listings

defect              field to fix          sessions   refused GMV  listings
missing attribute   capacity_l                   9        63,295         1
unserviceable       serviceable_pincodes        12        47,684         2
variant collision   variant_group               12        23,789         3
prose policy        policy                       2         1,463         1

repairing 7 listings:  35 failed sessions -> 3,  +Rs 123,605
                       Rs 412,017 per 1,000 agent sessions, permanently
```

One missing field, on one listing, refused ₹63,295. Same seed, same personas,
same decisions in both passes — only the feed differs, so the delta is a
measurement rather than a projection.

Two things are deliberately kept out of the readiness figures.

**Non-catalogue causes are reported separately.** A spending-cap breach is the
buyer's budget; a mid-session price move is a pricing race; a decline with no
reason code belongs to the rail. None is a field a merchant can edit, so the scan
lists them under *"not the catalogue's fault"* with the reason, and leaves them to
the recovery layer. Filing them as defects would send a merchant to fix the wrong
thing.

**Out-of-stock listings are advisories, not defects.** The feed withholds them, so
they refuse no basket. Counting them would inflate the score dishonestly.

---

## Honest limitations

Read this before the numbers above.

1. **No agent today polls a re-offer endpoint.** We serve offers at
   `/reoffers/{session_id}`. ACP has no re-offer primitive and neither does UAP.
   This is the deepest limitation in the system, and it is a protocol gap rather
   than a code gap.
2. **The catalogue, the personas and the faults are synthetic**, generated from a
   seed. The payments are real Razorpay test-mode orders and the buyer decisions
   come from a real model. Both arms of every comparison share the synthetic
   world, so the lift measures the system, not the market.
3. **The headline recovery rate is a function of a fault mix we chose.** Only the
   per-cause rates are portable.
4. **Delegated spending caps are ours, not UPI's.** Reserve Pay is not available
   to developers. Caps are declared on the checkout session and enforced in this
   layer, exactly as an ACP delegated payment token declares a maximum.
5. **The diagnosis task is easier than production.** One fault per session; real
   traffic carries compound causes. The 25% of declines that arrive without a
   reason code are the only realistic ambiguity, and they are what pulls macro-F1
   below 1.0.
6. **Prior success rates in the policy engine are priors**, published as such,
   until enough batches exist to replace them with measured rates.
7. **Not production-ready.** No adapter for a real PIM or checkout stack; no
   multi-tenancy; no monitoring or alerting; single-process runner.

What it is: a working prototype that proves a mechanism end to end against real
payment infrastructure and a real model buyer, and quantifies the opportunity
with honest metrics.

---

## How it works

Seven stages: **detect → diagnose → decide → gate → execute → record → measure.**

Thirteen failure classes, ten interventions, eleven stopping rules. Full detail,
including the control flow diagram, the taxonomy and the escalation ladder, is in
[ARCHITECTURE.md](ARCHITECTURE.md).

**The design decision that matters most:** the diagnosis engine may use a
language model; **the policy gate may not.** Eleven deterministic rules, one unit
test each. A model proposes a cause; only the table decides whether money moves.
Every rule evaluated lands in the ledger — including the ones that passed, and
including refusals, which carry the same standing as permits.

### The stopping rules

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
report as not observed, rather than quietly implied to be working.

---

## API keys

Both live backends are optional and neither is bundled — Razorpay test
credentials are issued to your account and an LLM key bills to yours. Copy
`.env.example` to `.env`; it is git-ignored and loaded automatically.

**Razorpay test mode** — Dashboard → switch to **Test Mode** → Account & Settings
→ API Keys → Generate Test Key.

```
HS_PAYMENTS=razorpay
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
```

The backend refuses any key id that does not begin `rzp_test_`, so a live key
cannot be used by accident.

**Model buyers** — provider is inferred from the key prefix.

| Provider | Prefix | Client | Example model |
|---|---|---|---|
| Anthropic | `sk-ant-` | `pip install anthropic` | `claude-3-5-haiku-latest` |
| OpenAI | `sk-` | `pip install openai` | `gpt-4o-mini` |
| Groq | `gsk_` | `pip install openai` | `openai/gpt-oss-20b` |
| OpenAI-compatible | — | `pip install openai` | set `HS_LLM_BASE_URL` |

```
HS_BUYERS=llm
HS_LLM_API_KEYS=key1,key2,key3       # used in order
HS_LLM_MODEL=openai/gpt-oss-20b
HS_LLM_MAX_TOKENS=256
```

**Several keys, used in order.** One free-tier key does not cover a 500-session
batch. The pool uses the first key until its *daily* quota is spent, retires it,
and continues on the next; only when every key is spent does the batch abort. A
*per-minute* limit is waited out instead — the provider states the wait and the
code uses that number.

**A failed model call falls back to the heuristic, and is counted.** The report
prints `llm buyers N/M decisions` and says `MIXED RUN` if the model share drops
below 99%. A run that quietly fell back must never be presented as a model run.

`python3 preflight.py` probes every key, prints tokens per decision, and tells
you how many sessions the pool can actually cover.

---

## Layout

```
handshake/
├── taxonomy.py        failure classes, interventions, rule ids
├── config.py          adapter switches and every policy bound
├── merchant/          C1  catalogue, feed, checkout sessions, fault injector
├── buyers/            C2  personas, agent loop, LLM pool with key rotation
├── recorder/          C3  session traces
├── diagnosis/         C4  rule tier, confidence gating
├── policy/            C5  the gate — deterministic, unit-tested
├── executor/          C6  interventions I-01 … I-10
├── ledger/            C7  append-only hash chain
├── server/            C8  FastAPI app and the live console
├── console/               generated static report
├── readiness/             audit, price and prove catalogue repairs
├── store/                 SQLite persistence
├── experiments/           batch runner, allocation, metrics, CLI
└── tests/                 57 tests: every rule, the chain, the pool, the API
```

`DEMO.md` is the five-minute video script, beat by beat, with the exact clicks.
`DEPLOY.md` is the deployment runbook.

---

## Compliance

Test mode only. Synthetic buyers, catalogue and mandates; no real personal data.
Defence-only — nothing here probes, evades or exploits any third-party system.
Every money-moving action records its reversal path before it executes. Simulated
components are printed at the top of every report and shown in the console
header. `pre_push_check.py` scans everything git would publish for credential
patterns and refuses if it finds one.

## References

- [Razorpay × NPCI — agentic UPI payments pilot](https://razorpay.com/blog/agentic-payments-and-npci/)
- [OpenAI — Agentic Commerce Protocol, key concepts](https://developers.openai.com/commerce/guides/key-concepts)
- [Digital Commerce 360 — OpenAI shifts checkout plans](https://www.digitalcommerce360.com/2026/03/06/openai-shifts-checkout-plans-agentic-commerce-strategy/)
- [Stellagent — AI shopping agent comparison, 2026](https://stellagent.ai/insights/ai-shopping-agent-comparison)
- [Business Standard — agentic AI-led UPI transactions under UAP](https://www.business-standard.com/finance/news/india-may-allow-agentic-ai-led-upi-transactions-under-new-npci-protocol-126070801343_1.html)
- [The Paypers — Razorpay AI Agent Studio](https://thepaypers.com/payments/news/razorpay-launches-ai-agent-studio-and-agentic-experience-platform)

MIT licensed.
