// Contract test for the Node SDK against a running Handshake.
//   node sdk/js/smoke.mjs http://127.0.0.1:8000 hsk_test_…
// Sends one discovery-stage journey with a missing attribute, then checks that
// Handshake stored it and that a webhook signature round-trips.

import { HandshakeClient, verifyWebhook } from "./handshake.mjs";
import { createHmac, randomUUID } from "node:crypto";
import assert from "node:assert/strict";

const [baseUrl, apiKey] = process.argv.slice(2);
const hs = new HandshakeClient({ apiKey, baseUrl, flushIntervalMs: 50 });
const journey = `jr_node_${randomUUID().slice(0, 8)}`;
const common = { agent_id: "agent_node_smoke", journey_id: journey };

hs.track({ ...common, type: "feed.read", response: { count: 1 } });
hs.track({ ...common, type: "product.view", sku: "KET-170",
  response: { sku: "KET-170", category: "home_kitchen", price: 1999, tax_rate: 0.18,
              attributes: { capacity_l: 1.7, warranty_months: 24 } } });
assert.equal(await hs.flush(), true);
assert.equal(hs.stats.sent, 2, `sent ${hs.stats.sent}`);

const { status, body } = await hs.request("GET", `/v1/journeys/${journey}`);
assert.equal(status, 200);
assert.equal(body.events.length, 2);

const secret = "whsec_test", raw = JSON.stringify({ type: "ping" }), t = Math.floor(Date.now() / 1000);
const sig = `t=${t},v1=${createHmac("sha256", secret).update(`${t}.${raw}`).digest("hex")}`;
assert.deepEqual(verifyWebhook(raw, sig, secret), { type: "ping" });
assert.throws(() => verifyWebhook(raw, sig, "wrong"));

await hs.close();
console.log(`node sdk ok: journey ${journey} stored with ${body.events.length} events, stage ${body.stage}`);
