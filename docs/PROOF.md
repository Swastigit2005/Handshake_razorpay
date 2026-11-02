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

## What this run found that seeded data never did

The first Claude run exposed three real bugs, fixed before the run above:

1. After failing again, Claude asked for an offer again and was handed the old
   one. A used offer is now retired once the agent acts on it.
2. That repeat pickup made the second stop look like a fresh attempt with no
   events, so it was diagnosed UNKNOWN. An attempt now starts where the agent
   *acts* on an offer.
3. A model thinks for 5–20 s between calls, so the sandbox's 4-second silence
   timer would call it "abandoned" mid-thought. Asking the store for an offer is
   now itself the abandonment signal, and the silence fallback is 45 s.

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

It does not prove performance on a real merchant's platform or real agent
traffic at volume. The store is still the demo store, and one agent run is one
data point. The next step is the store's SDK integration on a real platform
(see `docs/INTEGRATION.md`).
