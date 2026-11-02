# How Handshake knows why an agent stopped

## Two different questions

There are two questions here, and they are answered by two different parts of
the system. Mixing them up is the most common misreading of Handshake.

| | Question | Answered by | Output |
|---|---|---|---|
| 1 | **Why** did the agent stop? | the evidence engine, `handshake/live/detectors.py` | one of 13 causes, a confidence, and the evidence |
| 2 | **Should** we do anything about it? | the policy gate, `handshake/policy/engine.py`, which is the 11 rules | permit one intervention, or refuse and name the rule |

The 11 rules never work out *why*. They take the answer to question 1 as an
input and decide whether acting on it is allowed: is the diagnosis confident
enough (R-10), have we already tried too often (R-01, R-02), would it cost too
much margin (R-04, R-05), does it need a human's consent (R-07, R-09), has an
operator pulled the kill switch (R-11). A model may help with question 1. No
model is ever involved in question 2.

## Why an agent is easier to diagnose than a person

A person who abandons a cart leaves almost nothing behind. The page views
don't record what they were thinking.

An agent leaves something a person never does: a structured record of every
request it made and every response it got. Agents are also strict about what
they need. One that was told "buy a kettle of at least 1,200 W" will not buy a
kettle whose listing doesn't state the wattage. So if it fetched that product
and never opened a checkout, the answer is usually in the record it was served.
That record is in the merchant's own server log.

The detectors read exactly that log, plus two things the merchant already owns:

- the **schema**: which fields a category needs (`PUT /v1/schema`)
- the **catalogue**: the source-of-truth product records (`PUT /v1/catalog`)

## Three kinds of evidence, in order of trust

1. **Rail codes.** An explicit reason on a response, such as
   `402 insufficient_funds` or `401 authentication_required`. Score 0.95–0.99.
2. **Behaviour.** *Where* the agent stopped, measured against *what it was
   served*. A product view with no checkout after it, where the served record
   lacked a field the schema requires, is attribute void (A1). A quote that
   rose between create and update, followed by silence, is quote drift (A3).
   Score 0.78–0.93. Each detector also checks that the agent really stopped
   *there*: a drift the agent paid through scores 0.2, because it wasn't the
   reason.
3. **Self-report.** A reason the agent states when it cancels
   (`{"reason": "price_changed"}`). This only ever *corroborates*. If the
   traffic agrees, the matching hypothesis gains 0.06. If the traffic doesn't
   agree, the self-report becomes a hypothesis scored 0.45, which is below
   R-10's 0.70 threshold. It can never move money on its own, because an agent
   that learns "price_changed" earns a price lock will start saying it.

## Every detector runs; the margin is reported

Detection is not first-match. All nine detectors run, every hypothesis is
ranked, and the merchant sees the whole list with scores. If the top two causes
differ and are within 0.10 of each other, the diagnosis is marked **contested**
and its confidence drops by 0.15. That often pushes it under R-10, which sends
it to a person instead of acting on a coin flip.

## When nothing explains it

The answer is `UNKNOWN` at confidence 0, and R-10 sends the journey to the
exceptions queue with the observations attached. Two common cases:

- a payment declined with no reason code. Roughly a quarter of real declines
  look like this.
- an agent that viewed a complete, correct listing and left. Maybe the product
  simply wasn't what it was sent to buy.

Handshake doesn't guess in either case. A wrong guess spends margin on the
wrong fix and teaches the merchant the wrong lesson.

## The 13 causes and their signatures

| | Cause | Signature in the trace |
|---|---|---|
| A1 | attribute void | product viewed, no checkout after it, served record missing a schema field |
| A2 | spec ambiguity | listing served two SKUs in one variant group, identical in price and fields |
| A3 | quote drift | total rose between `checkout.create` and the last `checkout.update`, then the agent stopped |
| A4 | reserve ceiling | last quoted total above the `declared_cap` sent on create |
| A5 | human-auth wall | completion returned 401 / `authentication_required` / `requires_action`, never retried |
| A6 | ambiguous error | completion returned 5xx / `processing_error`, never retried |
| A7 | policy unreadable | viewed product's policy served as prose or without `returns_days` |
| A8 | fulfilment mismatch | create returned 422 `fulfilment_undetermined` / unserviceable |
| B1–B5 | payment failures | 402 with an explicit reason code, mapped from common gateway vocabularies |

## Seeing it work

Open `/demo`. Each scenario injects one fault into the demo store. The fault
reaches the store in a header the SDK never forwards, so Handshake has to work
it out from the traffic alone. After each run the page shows the hidden fault
next to Handshake's answer. `handshake/tests/test_live.py` asserts both the
diagnoses and that the scenario label never reaches Handshake's stored events.
