# Architecture

## The one-sentence version

Instrument agent-driven checkout, classify why it failed from the API trace,
repair the input that broke, re-offer to the agent, and record every decision in
a hash-chained ledger — with a deterministic gate between the diagnosis and the
money.

---

## Components

| | Component | Responsibility | Trust level |
|---|---|---|---|
| C1 | `merchant/` | Product feed, ACP-shaped checkout sessions, fault injection | Test fixture |
| C2 | `buyers/` | Autonomous LLM buyers with budgets, caps, risk postures | External actor |
| C3 | `recorder/` | Captures every request, response and terminal state | Read-only |
| C4 | `diagnosis/` | Assigns a root cause and a confidence to a failed session | **Advisory — cannot act** |
| C5 | `policy/` | Evaluates every bound and stopping rule; permits or refuses | **Authoritative gate** |
| C6 | `executor/` | Performs the single permitted action | Acts only on a permit |
| C7 | `ledger/` | Append-only, hash-chained record | Immutable |
| C8 | `server/` + `console/` | Live console, HTTP API, generated report | Read-only over state |
| — | `readiness/` | Audit, price and prove catalogue repairs | Prevention |
| — | `store/` | SQLite persistence for runs, sessions and ledgers | Durable |

---

## Control flow

```
C2 buyer agent ──▶ C1 merchant endpoints
                        │
                        ├──▶ C3 recorder ──▶ session trace (terminal: FAILED)
                        │                          │
                        │                          ▼
                        │                    C4 diagnosis ──▶ {cause, confidence}
                        │                          │
                        │                    confidence < θ ──▶ exception queue
                        │                          │
                        │                          ▼
                        │                    C5 policy gate ──▶ REFUSE ──▶ C7 ledger
                        │                          │
                        │                        PERMIT
                        │                          ▼
                        └────────────────── C6 executor ──▶ Razorpay test mode
                                                   │              │
                                                   ▼              ▼
                                             C7 ledger      re-offer callback ──▶ C2
                                                   │
                                                   ▼
                                        C8 console  ·  store/ SQLite
```

## The design invariant

**The diagnosis engine may use a language model. The policy gate may not.**

C5 is a pure function of `(diagnosis, session, buyer history, merchant config,
global state)` returning `PERMIT(intervention, parameters)` or
`REFUSE(rule, reason)`. Eleven rules, one unit test each. Every rule evaluated is
written to the ledger, including the ones that passed, and a refusal is recorded
with the same standing as a permit.

This is the whole reason the audit trail means anything. A model proposes; the
table disposes.

---

## Failure taxonomy

**Family A — pre-payment agent abandonment.** Carries the thesis.

| ID | Class | What the merchant can see |
|---|---|---|
| A1 | attribute void | product fetched, no session opened, required field absent from the feed |
| A2 | spec ambiguity | two listings in a group identical on every distinguishing field |
| A3 | quote drift | totals differ between session create and session update |
| A4 | reserve ceiling | last quote exceeds the cap declared on session create |
| A5 | human-auth wall | 401, authentication required |
| A6 | ambiguous error | 503, then no retry |
| A7 | policy unreadable | returns terms served as prose rather than fields |
| A8 | fulfilment mismatch | 422, no serviceable route |

**Family B — post-authorisation payment failure.** Anchors the number in money
already being lost, under rules already written.

| ID | Class | Signal |
|---|---|---|
| B1 | insufficient balance | 402 `insufficient_funds` |
| B2 | issuer downtime | 402 `issuer_unavailable` |
| B3 | mandate invalid | 402 `mandate_revoked` |
| B4 | reserve exhausted | 402 `reserve_exhausted` |
| B5 | instrument decline | 402 `instrument_declined` |

Diagnosis works **from the trace alone**, because that is all a real merchant
has. Roughly a quarter of payment declines arrive with no usable reason code; the
engine returns `UNKNOWN` at confidence 0 and R-10 stops any action. That is a
designed behaviour and it is reported as a metric, not hidden as a gap.

---

## Interventions

| ID | Action | Concedes margin | Touches a human |
|---|---|---|---|
| I-01 | catalogue delta and re-offer | no | no |
| I-02 | disambiguated re-offer | no | no |
| I-03 | price-lock quote | **yes**, ceilinged | no |
| I-04 | bundle resize / split tender | no | no |
| I-05 | reserve uplift **request** | no | yes |
| I-06 | single-use approval link | no | yes |
| I-07 | structured policy document | no | no |
| I-08 | alternate instrument | no | no |
| I-09 | scheduled retry | no | no |
| I-10 | escalate to operations | no | yes |

Eight of ten cost nothing: they repair data. The concession ratio in the
reference batch is 1.67%.

---

## Escalation

Three rungs, never skipped.

1. **Machine to machine.** Repair the data, re-offer to the agent. No human is
   touched. Where most recoveries land.
2. **The human principal.** Only where policy *requires* consent — a spending-cap
   uplift, an authorisation step. A single-use expiring link, handed to the agent
   to relay. Consent basis recorded, frequency-capped, quiet-hours bounded, and
   an explicit decline is final and permanent.
3. **Merchant operations.** Anything the system cannot resolve or is not
   permitted to attempt. Terminal.

The system never contacts a human directly, never raises a spending cap on its
own authority, and never escalates a rung it has not earned.

---

## Measurement

Allocation is randomised at session creation and **stratified by injected
fault**, so both arms carry the same failure mix. The control arm is fully
instrumented and receives no intervention; what it recovers, buyers recovered by
themselves, and that behaviour is applied identically in both arms so the lift is
not inflated.

Because the faults are injected, the injected label is ground truth — which is
the only reason diagnosis precision and recall can be reported honestly. The
label is never read by the diagnosis engine; a test asserts it does not appear in
the evidence path.

The readiness scan applies the same discipline to the catalogue: repair the
top-ranked defects, re-run the **identical** personas and seeds, and report the
delta. Only the feed differs. It is an A/B test on the catalogue itself.

---

## Data provenance

| Component | Status |
|---|---|
| Payments | **Real** Razorpay test-mode orders |
| Buyer decisions | **Real** model calls when keys are configured (499/500 in the reference run) |
| Market claims | **Real, cited** — see the README references |
| Catalogue, personas, faults | **Synthetic**, generated from a seed |
| Delegated spending caps | **Simulated** — Reserve Pay is not open to developers |

The mechanism is real; the world is synthetic. Both arms of every comparison
share that world, so what is unrealistic cancels. Every report and the console
header print which components were simulated in that specific run.

---

## Deployment

```
                    ┌──────────────────────────────┐
   browser ───────▶ │  uvicorn / FastAPI           │
                    │  handshake.server.app        │
                    │   · GET  /            console│
                    │   · GET  /healthz            │
                    │   · GET  /api/state          │
                    │   · POST /api/run     guarded│
                    │   · POST /api/readiness      │
                    │   · POST /api/killswitch     │
                    │   · GET  /api/runs, /trace   │
                    └──────────┬───────────────────┘
                               │ background thread
                    ┌──────────▼───────────┐   ┌────────────────────┐
                    │ batch / scan runner  │──▶│ SQLite (HS_DB)     │
                    │  in-process, seeded  │   │ runs · sessions ·  │
                    └──────────┬───────────┘   │ hash-chained ledger│
                               │               └────────────────────┘
                               ▼
                    Razorpay test mode  ·  LLM key pool (rotating)
```

**Guards for a public URL.** `HS_DEMO_MODE=1` caps batch size and enforces a
cooldown between runs. `HS_API_TOKEN` requires `X-Handshake-Token` on every write
endpoint. One run at a time is enforced regardless; a second request gets 409.

**State.** Runs, session tables and ledgers persist to SQLite at `HS_DB`, and the
chain is re-verified on read — independently of the process that wrote it.

**Backends.** Both adapters are swapped by environment variable and neither is
required. The Razorpay backend refuses any key id that does not begin
`rzp_test_`. The LLM backend accepts a pool of keys, rotates on a per-day quota,
waits out a per-minute limit, and aborts the batch rather than finishing half on
the heuristic.

---

## The live plane

The components above run in-process against a simulated merchant, so the
mechanism can be measured. The live plane runs the same diagnosis-then-gate
design against a real store's traffic.

```
 AI agent ──HTTP──▶ merchant checkout ──(HandshakeMiddleware: bodies only, redacted)──┐
                         ▲   ▲                                                       │
       re-offer proxy ───┘   └── signed webhook: recovery.directive                  ▼
                                                    ┌──────────── POST /v1/events ───────────┐
                                                    │ normalise · redact · stitch journey    │
                                                    │ idempotent on event_id                 │
                                                    └──────────────┬─────────────────────────┘
                              sweeper: idle window / cancel ───────▼
                                                    detectors.diagnose   ← schema + catalogue
                                                    (WHY: 13 causes, ranked, evidence)
                                                                   ▼
                                                    PolicyEngine.evaluate   (unchanged C5)
                                                    (SHOULD: 11 rules, persisted buyer history)
                                                                   ▼
                                                    directives.build → re-offer + webhook
                                                                   ▼
                                       ledger (per merchant, hash-chained) · journeys · metrics
```

| Module | Role |
|---|---|
| `live/events.py` | Seven event types, validation, PII redaction by key name |
| `live/detectors.py` | Nine detectors, three evidence tiers, contest margin, UNKNOWN |
| `live/pipeline.py` | Journey state machine, gate invocation, attribution, sweeper/worker |
| `live/directives.py` | Permit → `merchant_action` + `reoffer`, built from the synced catalogue |
| `live/webhooks.py` | HMAC-SHA256 signatures, durable queue, eight-attempt backoff |
| `live/store.py` | Tenant-scoped SQLite; every query filters on `merchant_id` |
| `live/api.py` | `/v1`: auth, rate limit, ingest, catalogue, journeys, policy, ledger |
| `sdk/` | Non-blocking client, ASGI middleware, webhook verification |

**The gate is shared, not reimplemented.** `pipeline.gate` calls the same
`PolicyEngine` the simulator uses, with buyer history loaded from the store,
so R-02 and R-06 count across journeys and restarts.

**A directive that can't be built truthfully is not sent.** If the gate
permits I-01 but the catalogue doesn't hold the missing value, the pipeline
tries the cause's next intervention, then routes the journey to a person with
the reason stated. It never invents a value.

**Journey states:** `open → converted`, or `open → abandoned → recovering →
recovered | lost`, or `abandoned → exception | lost`. If an agent resumes
after being called abandoned, the journey reopens and the earlier diagnosis
stays in the ledger.
