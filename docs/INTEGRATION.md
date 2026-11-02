# Integrating a store with Handshake

This guide is for the engineer who owns a store's agent-facing checkout. By the
end, every AI agent journey on your store shows up in the merchant dashboard,
abandoned journeys are diagnosed, and permitted recoveries reach you as signed
webhooks.

The demo store in `handshake/demo_shop/app.py` is a complete working example.
It is wired up exactly as described below and talks to Handshake only over HTTP.

## 0 · Get an API key

An operator with `HS_ADMIN_TOKEN` creates your merchant:

```bash
curl -X POST https://handshake.example.com/v1/merchants \
  -H "Authorization: Bearer $HS_ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Your Store", "webhook_url": "https://your-store.example/webhooks/handshake"}'
```

The response contains `api_key` (shown once; only its hash is stored) and
`merchant.webhook_secret`. Rotate the key at any time with `POST /v1/me/rotate-key`.

## 1 · Report agent traffic

### Python (any ASGI framework)

```python
from handshake.sdk import HandshakeClient, HandshakeMiddleware

hs = HandshakeClient(api_key=os.environ["HANDSHAKE_KEY"],
                     base_url="https://handshake.example.com")
app.add_middleware(HandshakeMiddleware, client=hs)
```

### Node / Express

```js
import { HandshakeClient, expressMiddleware } from "./sdk/js/handshake.mjs";
const hs = new HandshakeClient({ apiKey: process.env.HANDSHAKE_KEY, baseUrl });
app.use(express.json(), expressMiddleware(hs));
```

Both SDKs have the same contract: **instrumentation never slows down or breaks
checkout.** `track()` puts the event on a bounded in-memory queue and returns. A
background sender batches up to 200 events per request, retries network errors,
429s and 5xx with exponential backoff, and then drops and counts what it
couldn't send. It never raises into your request path. Events carry client-side
ids, so retries are idempotent.

### Route mapping

The defaults follow the Agentic Commerce Protocol's checkout-session shape and
match on the path *suffix*, so `/api/v2/acp/checkout_sessions` works unchanged:

| Method | Path suffix | Event |
|---|---|---|
| GET | `/feed`, `/feed.json` | `feed.read` |
| GET | `/products/{sku}` | `product.view` |
| POST | `/checkout_sessions` | `checkout.create` |
| POST | `/checkout_sessions/{id}` | `checkout.update` |
| POST | `/checkout_sessions/{id}/complete` | `checkout.complete` |
| POST | `/checkout_sessions/{id}/cancel` | `checkout.cancel` |
| GET | `/reoffers/{id}` | `reoffer.fetch` |

If your API is shaped differently, pass `routes=[(method, regex, event_type), …]`.

### Identifying the agent

A journey is stitched together from, in order:

1. `X-Agent-Journey`, if the agent platform sends a session id
2. the checkout id, once a session exists
3. `X-Agent-Id` plus activity within the idle window
4. without `X-Agent-Id`, a hash of user agent and client address, prefixed
   `anon_`. This is weaker, and the prefix says so.

### What leaves your server

Only request and response **bodies** of the matched routes, plus the three agent
headers. No other headers, no cookies. Fields named like card numbers, CVV,
OTP, tokens, passwords, email, phone or street address are redacted, at any
depth. The SDK redacts them, and the server redacts them again, so a
misconfigured client still can't store them.

### No Python or Node?

Post events directly:

```bash
curl -X POST https://handshake.example.com/v1/events \
  -H "Authorization: Bearer $HANDSHAKE_KEY" -H "Content-Type: application/json" \
  -d '{"events":[{"event_id":"e1","type":"product.view","agent_id":"agent-42",
        "sku":"KET-170","http_status":200,
        "response":{"sku":"KET-170","category":"home_kitchen","price":1999,
                    "attributes":{"capacity_l":1.7}}}]}'
```

The full schema is at `/docs` (OpenAPI), and the closed vocabulary is at
`GET /v1/taxonomy`.

## 2 · Tell Handshake what a complete product looks like

```python
hs.put_schema({"home_kitchen": ["capacity_l", "power_watts", "warranty_months"]})
hs.sync_catalog(products)   # source-of-truth records, not the storefront feed
```

The schema is how Handshake knows a missing field matters. The catalogue is
where it finds the real value to repair it with. Without the catalogue, the
diagnosis still works, but repairs that need a value go to a person instead of
being invented.

## 3 · Act on directives

Every permitted intervention arrives as a `recovery.directive` webhook:

```python
from handshake.sdk import verify_webhook

@app.post("/webhooks/handshake")
async def handshake_webhook(request: Request):
    event = verify_webhook(await request.body(),
                           request.headers["Handshake-Signature"], WEBHOOK_SECRET)
    if event["type"] == "recovery.directive":
        apply(event["data"]["merchant_action"])
    return {"ok": True}
```

`merchant_action.type` is one of:

| type | from | what to do |
|---|---|---|
| `patch_catalog` | I-01 | set `set` on `sku` in your feed |
| `repair_fulfilment` | I-01 (A8) | restore delivery data for `sku` |
| `disambiguate` | I-02 | withdraw or differentiate `collides_with` |
| `price_lock` | I-03 | honour `locked_total` on `checkout_id` for `ttl_minutes` |
| `issue_approval` | I-06 | accept `approval_token` once on `checkout_id` |
| `structure_policy` | I-07 | publish `policy` as fields on `sku` |
| `schedule_retry`, `offer_alternate_instrument` | I-09, I-08 | allow the retry |
| `escalate` | I-10 | route to your operations queue |
| `none` | I-04, I-05 | nothing on your side; the agent is told directly |

Other events: `journey.abandoned` (with diagnosis), `journey.exception` (a rule
refused, with the rule and evidence), `journey.recovered` (with the value), and
`journey.lost`.

Signature: `Handshake-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>`.
Reject anything older than five minutes. Failed deliveries are retried for up
to eight attempts with backoff, and each attempt is visible under Webhooks in
the dashboard.

## 4 · Serve re-offers to returning agents

```python
@app.get("/acp/reoffers/{ref}")
def reoffer(ref: str):
    offer = hs.get_reoffer(ref)        # ref = journey id or checkout id
    return {"pending": bool(offer), "offer": offer}
```

When the same agent later pays, Handshake attributes the recovered value to the
intervention, and the ledger records it.

**Honest limitation:** no agent platform polls a re-offer endpoint today, and
neither ACP nor UAP has a re-offer primitive. Catalogue repairs (I-01, I-02,
I-07) help the *next* agent regardless, because your feed is fixed.

## 5 · Tune the rules

`PATCH /v1/policy` or the dashboard's *Rules & policy* tab. Every change is
written to the hash-chained ledger. `kill_switch: true` refuses every
intervention under R-11 until it is switched off.

## Operating notes

- `GET /healthz` reports the worker, the global kill switch and the store.
- One process runs the sweeper and webhook worker. With several replicas, set
  `HS_LIVE_WORKER=0` on all but one.
- Storage is SQLite (WAL). The SQL in `handshake/live/store.py` is deliberately
  portable, and moving to Postgres means swapping `connect()`.
- The rate limiter is per process. Behind a load balancer, enforce limits there.
- Set `HS_DEMO_SANDBOX=0` on any deployment that holds real merchants. It
  disables the demo store's auto-login endpoint.
