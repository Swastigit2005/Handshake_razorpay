# Connecting a real Shopify store

Shopify's checkout ends on a page a person fills in, so an AI agent cannot buy
from a Shopify store directly. Handshake runs an agent-facing checkout in front
of the store at `/shopify`, backed by the real store through the Admin API, and
instrumented with the Handshake SDK like any merchant integration.

| An agent does | In your store |
|---|---|
| search, view a product | reads your active products, variants, stock and spec metafields |
| open a checkout, re-quote | Shopify's own `draftOrderCalculate`: subtotal, tax, shipping rates, live each time |
| pay | a draft order, completed: a real order in your admin, tagged `handshake`, `ai-agent` (a test order in a development store) |
| (Handshake repairs a spec) | `metafieldsSet` writes it back to the product |

Agents connect over MCP at `/shopify/mcp`, exactly as with the demo store.

## Setup (since January 2026)

Shopify no longer lets new stores create custom apps with permanent tokens in
the store admin. Use the Dev Dashboard:

1. At [dev.shopify.com](https://dev.shopify.com), create a **development store**.
   Create it there: the client credentials grant only works when the app and the
   store are in the same organisation (otherwise Shopify answers
   `shop_not_permitted`).
2. Add products with a **Product type**, and specs as product metafields in the
   `custom` namespace (Settings → Custom data → Products), for example
   `battery_hours`, `driver_mm`. Optional: `ships_in_days`, `returns_days`,
   `warranty_months`.
3. In the Dev Dashboard, create an app with Admin API scopes `read_products`,
   `write_products`, `read_inventory`, `write_draft_orders`, `read_orders`. Release
   a version, and install it on the store.
4. Put the credentials in the server's environment, never in the repository:

   ```
   SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
   SHOPIFY_CLIENT_ID=…
   SHOPIFY_CLIENT_SECRET=…
   ```

   Handshake exchanges them for an access token through the client credentials
   grant. The token lasts 24 hours; it is cached, renewed a minute before expiry,
   and renewed once more if Shopify rejects it early. A legacy app's permanent
   `shpat_…` token also works, as `SHOPIFY_ADMIN_TOKEN`.
5. Restart and open `/shopify`. It shows the connection, the learned spec schema,
   a **readiness report** (listings missing specs their category carries), the MCP
   address, and a live feed of agent journeys.

## What a "required spec" is

Learned from your catalogue: a spec that at least 60% of products of a type
carry is one agents comparing that type will look for. Override with
`SHOPIFY_REQUIRED_SPECS='{"headphones": ["battery_hours", "driver_mm"]}'`.

## Real failures you can create in Shopify admin

| Do this in Shopify | What the agent meets | Handshake should say |
|---|---|---|
| delete a spec metafield that other products of the type have | a listing it can't verify | A1. If Shopify itself lacks the value, a person is asked to add it; nothing is invented |
| raise a price while an agent is checking out | the re-quote is higher | A3, and a price lock (I-03) through the signed webhook |
| set stock to 0 after the agent has looked | checkout refused, `insufficient_stock` | N1, with an in-stock alternative drafted for approval |
| remove a payment method from `SHOPIFY_ACCEPTED_METHODS` | payment refused | N1, with the alternative methods drafted |
| leave the agent's country out of your shipping zones | no shipping rate | A8 |

## Limits

- Orders are created through the Admin API and marked paid, which is right for a
  development store and wrong for a live one. A production integration would hand
  payment to Shopify's checkout or an agentic-checkout channel.
- Connecting someone else's store needs Shopify's authorization-code grant or
  token exchange (an install flow with a callback). That isn't built yet; this
  connector is for your own store.

Sources: Shopify, [client credentials grant](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/client-credentials-grant);
Shopify community, [no new legacy custom apps from 1 January 2026](https://community.shopify.dev/t/starting-january-1-2026-you-will-not-be-able-to-create-new-legacy-custom-apps-this-will-not-impact-any-existing-apps/26798).
