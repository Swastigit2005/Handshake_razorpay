// Handshake merchant SDK for Node 18+ (no dependencies).
//
//   import { HandshakeClient, expressMiddleware, verifyWebhook } from "./handshake.mjs";
//   const hs = new HandshakeClient({ apiKey: process.env.HANDSHAKE_KEY, baseUrl });
//   app.use(express.json(), expressMiddleware(hs));
//
// Same contract as the Python SDK: track() never blocks and never throws; a
// timer batches events to POST /v1/events; failures retry with backoff and are
// then dropped and counted. Event ids make retries idempotent.

import { createHmac, randomUUID, timingSafeEqual, createHash } from "node:crypto";

export const DEFAULT_ROUTES = [
  ["GET", /\/feed(?:\.json)?$/, "feed.read"],
  ["GET", /\/products\/(?<sku>[^/]+)$/, "product.view"],
  ["POST", /\/checkout_sessions$/, "checkout.create"],
  ["POST", /\/checkout_sessions\/(?<checkout_id>[^/]+)\/complete$/, "checkout.complete"],
  ["POST", /\/checkout_sessions\/(?<checkout_id>[^/]+)\/cancel$/, "checkout.cancel"],
  ["POST", /\/checkout_sessions\/(?<checkout_id>[^/]+)$/, "checkout.update"],
  ["GET", /\/reoffers\/(?<checkout_id>[^/]+)$/, "reoffer.fetch"],
];

const RETRY = new Set([0, 408, 429, 500, 502, 503, 504]);

export class HandshakeClient {
  constructor({ apiKey, baseUrl = "http://127.0.0.1:8000", flushIntervalMs = 500,
                batchSize = 200, maxQueue = 10000, maxRetries = 5, fetchImpl } = {}) {
    if (!apiKey) throw new Error("apiKey is required");
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.batchSize = Math.min(batchSize, 500);
    this.maxQueue = maxQueue;
    this.maxRetries = maxRetries;
    this.fetch = fetchImpl || globalThis.fetch;
    this.queue = [];
    this.sending = null;
    this.stats = { queued: 0, sent: 0, dropped: 0, failed: 0, retries: 0 };
    this.timer = setInterval(() => this.#pump(), flushIntervalMs);
    this.timer.unref?.();
  }

  track(event) {
    if (this.queue.length >= this.maxQueue) { this.stats.dropped++; return; }
    this.queue.push({ event_id: `ev_${randomUUID().replace(/-/g, "")}`, ts: Date.now() / 1000, ...event });
    this.stats.queued++;
  }

  async request(method, path, body) {
    let res;
    try {
      res = await this.fetch(this.baseUrl + path, {
        method, body: body === undefined ? undefined : JSON.stringify(body),
        headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json",
                   "User-Agent": "handshake-node/1" },
      });
    } catch (e) {
      return { status: 0, body: { error: { message: String(e) } } };
    }
    return { status: res.status, body: await res.json().catch(() => ({})) };
  }

  async #pump() {
    if (this.sending || !this.queue.length) return;
    const batch = this.queue.splice(0, this.batchSize);
    this.sending = this.#send(batch).finally(() => { this.sending = null; });
  }

  async #send(batch) {
    let delay = 250;
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const { status, body } = await this.request("POST", "/v1/events", { events: batch });
      if ((status >= 200 && status < 300) || status === 422) {
        this.stats.sent += body.accepted || 0;
        return;
      }
      if (!RETRY.has(status)) break;
      this.stats.retries++;
      await new Promise(r => setTimeout(r, delay));
      delay = Math.min(delay * 2, 8000);
    }
    this.stats.failed += batch.length;
  }

  async flush(timeoutMs = 10000) {
    const end = Date.now() + timeoutMs;
    while ((this.queue.length || this.sending) && Date.now() < end) {
      await this.#pump();
      if (this.sending) await this.sending;
    }
    return !this.queue.length;
  }

  async close() { await this.flush(); clearInterval(this.timer); }

  async getReoffer(ref) {
    const { status, body } = await this.request("GET", `/v1/reoffers/${encodeURIComponent(ref)}`);
    return status === 200 ? body.offer : null;
  }
  async syncCatalog(products) { return (await this.request("PUT", "/v1/catalog", { products })).body; }
  async putSchema(schema) { return (await this.request("PUT", "/v1/schema", { schema })).body; }
}

function agentIdFrom(req) {
  if (req.headers["x-agent-id"]) return String(req.headers["x-agent-id"]);
  const h = createHash("sha1").update(`${req.headers["user-agent"] || ""}|${req.socket?.remoteAddress || ""}`);
  return "anon_" + h.digest("hex").slice(0, 16);
}

// Express/Connect middleware. Mount after a JSON body parser so req.body is set.
export function expressMiddleware(client, { routes = DEFAULT_ROUTES, agentId = agentIdFrom } = {}) {
  return (req, res, next) => {
    const path = (req.originalUrl || req.url).split("?")[0];
    const route = routes.find(([m, re]) => m === req.method && re.test(path));
    if (!route) return next();
    const params = path.match(route[1]).groups || {};
    const started = process.hrtime.bigint();
    const chunks = [];
    const write = res.write.bind(res), end = res.end.bind(res);
    res.write = (c, ...a) => { if (c) chunks.push(Buffer.from(c)); return write(c, ...a); };
    res.end = (c, ...a) => { if (c && typeof c !== "function") chunks.push(Buffer.from(c)); return end(c, ...a); };
    res.on("finish", () => {
      try {
        let response = {};
        try { const v = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
              response = Array.isArray(v) ? { items: v } : v; } catch { response = { _unparsed: true }; }
        const request = { ...(req.query || {}), ...(typeof req.body === "object" ? req.body : {}) };
        client.track({
          type: route[2], agent_id: agentId(req),
          journey_id: req.headers["x-agent-journey"] || "",
          principal_id: req.headers["x-agent-principal"] || "",
          checkout_id: params.checkout_id || response.session_id || "",
          sku: params.sku || request.sku || response.sku || "",
          method: req.method, path, http_status: res.statusCode,
          latency_ms: Number(process.hrtime.bigint() - started) / 1e6,
          request, response,
        });
      } catch { /* never break checkout */ }
    });
    next();
  };
}

export function verifyWebhook(rawBody, header, secret, toleranceSec = 300) {
  const parts = Object.fromEntries(String(header || "").split(",").map(p => p.split("=")));
  const ts = Number(parts.t);
  if (!ts || !parts.v1) throw new Error("malformed Handshake-Signature header");
  if (Math.abs(Date.now() / 1000 - ts) > toleranceSec) throw new Error("signature timestamp outside tolerance");
  const body = Buffer.isBuffer(rawBody) ? rawBody : Buffer.from(rawBody);
  const mac = createHmac("sha256", secret).update(`${ts}.`).update(body).digest("hex");
  const a = Buffer.from(mac), b = Buffer.from(parts.v1);
  if (a.length !== b.length || !timingSafeEqual(a, b)) throw new Error("signature mismatch");
  return JSON.parse(body.toString("utf8"));
}
