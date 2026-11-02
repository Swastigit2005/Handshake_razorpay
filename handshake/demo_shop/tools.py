"""The store's agent-facing actions, as tools any AI agent can call.

One toolkit, two kinds of caller:

  - the MCP endpoint (`/mcp`), for agents nobody on this project wrote: Claude
    in claude.ai, Claude Desktop or Claude Code, or any MCP client
  - the built-in model shopper (`llm_agent.py`), which decides with a model
    from a brief a person types

Every tool is a real HTTP request to the store's checkout API, so it passes
through the store's Handshake SDK middleware like any agent's traffic. Nothing
here talks to Handshake. Nothing an agent thinks reaches the store or
Handshake: only the requests it chooses to make.
"""

import json
import time
import uuid

from .agent import urllib_json

TOOLS = [
    {"name": "search_products",
     "description": "List products in the store. Optional filters: a text query matched "
                    "against titles, and a category (home_kitchen, audio, "
                    "laptop_accessories). Returns each product's sku, title, price (INR, "
                    "before 18% GST), attributes and returns/warranty policy.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "words to match in the title"},
         "category": {"type": "string", "enum": ["home_kitchen", "audio", "laptop_accessories"]}},
         "additionalProperties": False}},
    {"name": "get_product",
     "description": "Fetch one product's full record by sku: price, attributes, "
                    "returns and warranty policy.",
     "input_schema": {"type": "object", "properties": {"sku": {"type": "string"}},
                      "required": ["sku"], "additionalProperties": False}},
    {"name": "create_checkout",
     "description": "Open a checkout session for a product. Returns a checkout_id, the "
                    "total including tax, and the delivery estimate (ships_in_days). "
                    "Declare the spending limit your user gave you as spending_cap.",
     "input_schema": {"type": "object", "properties": {
         "sku": {"type": "string"},
         "quantity": {"type": "integer", "minimum": 1, "default": 1},
         "pincode": {"type": "string", "description": "6-digit Indian delivery pincode"},
         "spending_cap": {"type": "number", "description": "the most your user allows, INR"}},
         "required": ["sku", "pincode"], "additionalProperties": False}},
    {"name": "refresh_checkout",
     "description": "Re-quote an open checkout before paying. Returns the current total, "
                    "which can differ from the first quote.",
     "input_schema": {"type": "object", "properties": {"checkout_id": {"type": "string"}},
                      "required": ["checkout_id"], "additionalProperties": False}},
    {"name": "pay",
     "description": "Pay for an open checkout. payment_method is one of: upi_reserve (a "
                    "delegated UPI mandate, the usual method for agents), upi_intent, "
                    "card_token. If the store asks for human approval, pass the "
                    "approval_token you were given.",
     "input_schema": {"type": "object", "properties": {
         "checkout_id": {"type": "string"},
         "payment_method": {"type": "string", "enum": ["upi_reserve", "upi_intent", "card_token"]},
         "approval_token": {"type": "string"}},
         "required": ["checkout_id", "payment_method"], "additionalProperties": False}},
    {"name": "cancel_checkout",
     "description": "Cancel an open checkout. You may give the store a short reason, or none.",
     "input_schema": {"type": "object", "properties": {
         "checkout_id": {"type": "string"}, "reason": {"type": "string"}},
         "required": ["checkout_id"], "additionalProperties": False}},
    {"name": "check_for_offer",
     "description": "After you stop shopping, ask whether the store has an offer for you "
                    "(it sometimes fixes a problem and comes back). Waits up to 15 seconds. "
                    "Returns the offer, or that there is none.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

PAYMENT = {"upi_reserve": {"type": "upi_reserve", "mandate": True},
           "upi_intent": {"type": "upi_intent"},
           "card_token": {"type": "card_token"}}


class StoreSession:
    """One agent's connection to the store. Carries the agent's identity the way
    an agent platform would: an agent id and a shopping-session id. A new
    session id starts after each successful purchase."""

    def __init__(self, base_url, agent_id, http=urllib_json, log=None, offer_wait=15.0):
        self.base = base_url.rstrip("/") + "/shop/acp"
        self.agent_id = agent_id
        self.journey_id = f"jr_{uuid.uuid4().hex[:14]}"
        self.http = http
        self.log = log if log is not None else []
        self.offer_wait = offer_wait
        self.bought = []

    def _call(self, method, path, body=None):
        headers = {"X-Agent-Id": self.agent_id, "X-Agent-Journey": self.journey_id}
        return self.http(method, self.base + path, body, headers)

    def call(self, name, args):
        """Run one tool. Returns a JSON-serialisable result; never raises."""
        args = args or {}
        try:
            return self._dispatch(name, args)
        except Exception as exc:                  # a bad argument is the agent's to fix
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _dispatch(self, name, a):
        if name == "search_products":
            q = []
            if a.get("category"):
                q.append(f"category={a['category']}")
            if a.get("query"):
                q.append(f"q={a['query']}")
            status, body = self._call("GET", "/feed" + ("?" + "&".join(q) if q else ""))
            return {"status": status, **body}
        if name == "get_product":
            status, body = self._call("GET", f"/products/{a['sku']}")
            return {"status": status, **body}
        if name == "create_checkout":
            body = {"sku": a["sku"], "qty": int(a.get("quantity") or 1),
                    "pincode": str(a.get("pincode") or "")}
            if a.get("spending_cap") is not None:
                body["declared_cap"] = float(a["spending_cap"])
            status, res = self._call("POST", "/checkout_sessions", body)
            if status == 200:
                res["checkout_id"] = res.pop("session_id", None)
            return {"status": status, **res}
        if name == "refresh_checkout":
            status, res = self._call("POST", f"/checkout_sessions/{a['checkout_id']}", {})
            return {"status": status, **res}
        if name == "pay":
            body = {"instrument": PAYMENT.get(a.get("payment_method"), {"type": a.get("payment_method")})}
            if a.get("approval_token"):
                body["approval_token"] = a["approval_token"]
            status, res = self._call("POST", f"/checkout_sessions/{a['checkout_id']}/complete", body)
            if status == 200:
                self.bought.append({"checkout_id": a["checkout_id"], "total": res.get("total"),
                                    "journey_id": self.journey_id})
                # The next purchase is a new shopping trip.
                self.journey_id = f"jr_{uuid.uuid4().hex[:14]}"
            return {"status": status, **res}
        if name == "cancel_checkout":
            body = {"reason": a["reason"]} if a.get("reason") else {}
            status, res = self._call("POST", f"/checkout_sessions/{a['checkout_id']}/cancel", body)
            return {"status": status, **res}
        if name == "check_for_offer":
            deadline = time.time() + self.offer_wait
            while True:
                status, res = self._call("GET", f"/reoffers/{self.journey_id}")
                if status == 200 and res.get("offer"):
                    offer = res["offer"]
                    return {"offer": {k: v for k, v in offer.items()
                                      if k not in ("journey_id", "offer_id", "expires_at",
                                                   "fetched_at", "expired", "intervention",
                                                   "source")}}
                if time.time() >= deadline:
                    return {"offer": None, "note": "no offer from the store"}
                time.sleep(1.5)
        return {"error": f"unknown tool {name!r}"}


def as_text(result, limit=6000):
    text = json.dumps(result, default=str, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"
