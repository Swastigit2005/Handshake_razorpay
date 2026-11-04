# Proof with an agent nobody here wrote

The scripted shopper in `/demo` is useful, but it is circular: the same author
wrote the shopper, the store's problems and the detectors. This file records a
test without that circularity, and explains how anyone can repeat it.

## The setup

- **The agent:** Claude, through Claude Code (v2.1.220), in print mode. Its only
  tools were the store's MCP tools: no files, no shell, no web.
- **The store:** the demo store, broken through its admin settings
  (`/shop/admin`), the way a real catalogue is broken. Nothing about this reaches
  the agent or Handshake.
  - HPH-045 (the only wireless over-ear headphones): a required spec is dropped
    from the listing (`battery_hours`)
  - store-wide: UPI Reserve mandates are refused at payment
- **Handshake:** sees only what the store's SDK middleware reports, which is the
  HTTP requests and responses. It never sees the prompt, Claude's reasoning, or
  the store settings.

## The prompt (unedited)

> You are my shopping agent. Buy me wireless over-ear headphones from the Kaveri
> Home & Tech store you're connected to. My requirements: at least 30 hours of
> battery life, total under Rs 5,000 including tax, delivery to pincode 560034.
> Pay with my UPI Reserve mandate (payment method upi_reserve) — that's the
> method I've authorised you to use. Only buy if you can actually verify the
> battery life from the store's data; don't guess. If you can't complete the
> purchase, don't force it, but check whether the store comes back with an offer
> before giving up. At the end, tell me in two or three sentences exactly what
> happened and why you did or didn't buy.

## Claude's account (unedited; never sent to the store or to Handshake)

> No offer this time. Stopping here — the purchase is not made, and nothing was
> charged.
>
> **What happened:** The store's only wireless over-ear model, the Raaga Over-Ear
> (HPH-045), initially listed no battery spec at all, so I declined to buy rather
> than guess; I then checked for an offer and the store published a catalogue
> update, which I confirmed directly in the product record as `battery_hours: 40`
> — clearing your 30-hour bar at ₹4,718.82 including GST, under your ₹5,000 cap,
> shipping to 560034 in 2 days. Payment then failed: the store does not accept
> UPI Reserve mandates, and since that's the only method you authorised, I
> cancelled the checkout instead of falling back to `upi_intent` or `card_token`
> on my own. A second offer check came back empty, so nothing was bought and
> nothing was charged.
>
> The item meets every requirement — if you want it, the one decision needed from
> you is whether to authorise `upi_intent` or `card_token`, and I can complete it
> in one go.

## Handshake's account (from the store's traffic only)

What the store's server saw:

```
 2 product.view       200  opened product HPH-045            (no battery_hours)
 6 reoffer.fetch      404  asked for an offer → journey closed, diagnosed
 7 reoffer.fetch      200  collected a recovery offer (catalogue_delta)
 8 product.view       200  opened product HPH-045            (re-checked)
 9 checkout.create    200  checkout at ₹4,718.82 (cap ₹5,000)
10 checkout.update    200  re-quoted at ₹4,718.82
11 checkout.complete  400  payment_method_unsupported
12 checkout.cancel    200  cancelled, stating 'Store does not accept UPI Reserve mandates…'
13 reoffer.fetch      404  asked again → second stop diagnosed
```

| | Handshake's diagnosis | What Handshake did |
|---|---|---|
| Stop 1 | **A1 attribute void**, 0.92: the record served lacked `battery_hours`, which the category requires; the store's own catalogue has it (40) | permitted automatically (all 11 rules passed): re-offer with `battery_hours = 40`, plus a signed webhook telling the store to patch its feed |
| Stop 2 | **N1 merchant rejection**, 0.66: `400 payment_method_unsupported` at payment, then the agent stopped. No playbook entry covers this | held by R-10 (outside the playbook): drafted for a person: *"That payment method isn't accepted here. Card and UPI intent both work; please retry with one of them."* For the merchant: *accept these methods, or list accepted methods in the feed* |

Ledger for the journey: `diagnosed → intervention_permitted → diagnosed →
intervention_refused`, hash-chained and verified.

The two accounts were written independently and agree on both stops. Handshake's
drafted fix for the second stop names the same decision Claude says it needs
from its user: authorise a different payment method.

## A second run, on the deployed site

Against `https://handshake-console.onrender.com/mcp`, with a different product
and problem: the aluminium laptop stand (LST-AL1) quietly ships in 9 days,
which is not in its listing. The prompt asked for a stand for a 15.6" laptop,
under ₹3,000, that must ship within 4 days, paid by card.

**Claude (unedited excerpt):** "The cheaper Deccan Aluminium Stand (₹2,112.20)
would also have fit, but it quoted 9 days to your pincode, so I cancelled that
checkout rather than risk it missing your travel date." It then bought the
Deccan Folding Desk Riser (LST-FD2) for ₹2,702.20, shipping in 2 days.

**Handshake (from traffic only):** **N2 offer mismatch**, corroborated by the
agent's stated reason: *"LST-AL1 was the weakest of the agent's options on ships
in days: 9 against 2 for LST-FD2."* The re-offer it drafted for a person to
approve: *"Deccan Folding Desk Riser (LST-FD2) has ships in days 2, against 9
on LST-AL1."* That is the product Claude chose itself. The journey then
reopened and was recorded as converted at ₹2,702.20. No rule for "slow
delivery" exists; the weakest-option detector found it.

The first attempt at this run, on the previous version, was diagnosed UNKNOWN.
Claude compared products from search results without opening a product page,
and its reason was free text. Both are now handled; see below.

## A real Shopify store

The runs above used the demo store. These used a real Shopify development store
(`merchant-store-fqztqjgz.myshopify.com`, USD), connected through the Shopify
gateway (`docs/SHOPIFY.md`) with a Dev Dashboard app. The catalogue is the
store's own: Shopify's sample snowboards plus three headphones the merchant
added, with `battery_hours` as a product metafield. Nothing was seeded, and no
store fault was injected: the brief simply asked for more than the catalogue
has.

- Wireless Headphones: $190, `battery_hours` 30, in stock
- Studio Headphones: $280, `battery_hours` 40, in stock
- Gaming Headset: $145, `battery_hours` 20, out of stock

**Orders.** Shopify refuses this app draft orders and orders as protected
customer data (`ACCESS_DENIED: This app is not approved to access the
CalculatedDraftOrder object`, request `b424993e-7485-4c4f-893d-d1b36bdf1d15-1793781146`,
API 2026-07), even with every scope granted; Dev Dashboard apps have no form to
request it. So the gateway ran in catalogue mode: products, specs, stock and
prices are read live from Shopify, and a paid checkout would have been recorded
by Handshake, not in the Shopify admin. Nothing was paid in these runs.

### The prompt (unedited, both runs)

> You are my shopping agent. Buy me a pair of headphones from the store you're
> connected to. My requirements: at least 35 hours of battery life, total under
> $250 including any tax and shipping, delivery to ZIP code 10001. Pay by card
> (payment method card_token). Only buy if you can verify the battery life from
> the store's data; don't guess. If you can't find something that fits, don't
> force it, but check whether the store comes back with an offer before giving
> up. At the end, tell me in two or three sentences exactly what happened and
> why you did or didn't buy.

### Run 1: right diagnosis, wrong offer

Handshake: **A4 reserve_ceiling, 0.99**. The basket came to $280 against the
$250 cap the agent declared. Correct.

But the recovery it sent (I-04, a compliant basket) was the $190 Wireless pair,
which Claude had already seen and skipped. Claude's account:

> I then checked for an offer as you asked; the store came back twice with the
> same thing — the 30 h Wireless pair at $190, labeled a "compliant_basket" — but
> that's only compliant on price, since it still fails the battery requirement,
> so I declined rather than stretch your spec.

The explanation also said "₹280" for a dollar store.

### The fix

When an agent chooses an item whose *listed* price is already above its cap,
with cheaper items of the same kind in front of it, it is not choosing on price.
Handshake now reads the attempt's events for what the agent saw and skipped
(`directives.passed_over`): the skipped items are never offered back, and on
each facet where the pick beat all of them (here `battery_hours` > 30) an
alternative has to beat them too. If nothing qualifies, I-04 is unbuildable and
the next rung applies. When the pick looked affordable and only tax or shipping
pushed it over, any cheaper item is still a fair offer. Amounts are now written
in the store's currency.

### Run 2: the same brief, after the fix

Handshake: **A4 reserve_ceiling, 0.99**, "The basket came to $280.00 against a
spending cap of $250.00". I-04 was unbuildable (both cheaper pairs had been
skipped), so it sent **I-05**: ask the agent's owner to approve a $280 cap.
Claude's account (unedited, private):

> I didn't buy anything. The store carries exactly two headphone products, and
> neither satisfies both constraints: Wireless Headphones fit the budget at $190
> but their store record lists `battery_hours: 30`, below your 35-hour floor, and
> Studio Headphones verify at `battery_hours: 40` but quoted $280 all-in to ZIP
> 10001 ($0 tax, $0 shipping) — confirmed twice via re-quote — which is $30 over
> your $250 cap. I cancelled that checkout and did check for an offer as you
> asked: the store came back not with a discount but with a request that you
> approve raising the cap to $280, which I declined to do on my own since $250
> was your limit.
>
> If you want those 40-hour Studio Headphones, tell me to approve $280 and I'll
> complete it by card; otherwise there's nothing here that meets your spec.

The offer reached the person who can say yes, through the agent, and the agent
did not overstep its mandate. That is the recovery path working as designed.

### What the real store found that the stand-in never did

1. python.org's macOS Python has no root certificates: every call failed TLS.
2. Shopify grants a Dev Dashboard app no scopes until a version is released and
   the update approved; then refuses orders as protected customer data anyway.
   Hence catalogue mode, which Shopify approval switches off by itself.
3. Real metafields: specs outside `custom` (`test_data`), JSON unit values,
   `" 30"` with a space, untracked inventory reported as 0, a gift card.
4. Products with no product type, mixed into one category, produced a false
   readiness gap.
5. The re-offer and currency bugs above.

## What these runs found that seeded data never did

The first Claude run exposed three real bugs, fixed before the run above:

1. After failing again, Claude asked for an offer again and was handed the old
   one. A used offer is now retired once the agent acts on it.
2. That repeat pickup made the second stop look like a fresh attempt with no
   events, so it was diagnosed UNKNOWN. An attempt now starts where the agent
   *acts* on an offer.
3. A model thinks for 5–20 s between calls, so the sandbox's 4-second silence
   timer would call it "abandoned" mid-thought. Asking the store for an offer is
   now itself the abandonment signal, and the silence fallback is 45 s.
4. The weakest-option detector required a product page; it now judges the
   record served in search results.
5. An agent's free-text reason was ignored. It can now corroborate what the
   traffic shows, but never create a hypothesis by itself.
6. Offer polls after a purchase opened an empty journey that was then filed as
   an unexplained abandonment. Polls no longer open journeys.

## Repeat it yourself

1. Open `https://handshake-console.onrender.com/shop/admin` and break something.
2. Add `https://handshake-console.onrender.com/mcp` to Claude as a remote MCP
   server: in claude.ai, Settings → Connectors → Add custom connector. In
   Claude Code: `claude mcp add --transport http kaveri <url>`.
3. Ask Claude to buy something, in your own words, with your own requirements.
4. Compare its explanation with the journey in `/demo` (live feed) or
   `/merchant`.

Or from a terminal, exactly as recorded here:

```bash
echo '{"mcpServers":{"shop":{"type":"http","url":"https://handshake-console.onrender.com/mcp"}}}' > mcp.json
claude -p "<your shopping request>" --mcp-config mcp.json --strict-mcp-config \
  --allowedTools "mcp__shop__search_products" "mcp__shop__get_product" \
  "mcp__shop__create_checkout" "mcp__shop__refresh_checkout" "mcp__shop__pay" \
  "mcp__shop__cancel_checkout" "mcp__shop__check_for_offer"
```

## What this does and does not prove

It proves Handshake explains the stops of an independent, model-driven agent
correctly, from traffic alone, including a failure no rule was written for. It
also shows the safety split working: the confident, known fix was sent
automatically, and the novel one waited for a person.

The Shopify runs add a real platform: a real catalogue, read live, and a stop
that no one staged. They do not prove volume: these are a handful of runs by one
agent on a development store. Orders were not written to Shopify, pending
Shopify's protected-customer-data approval for the app.
