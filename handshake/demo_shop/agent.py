"""A shopping agent that buys over HTTP, the way an ACP client would.

It is told a goal, a budget and a spending cap by its owner, and it is strict
about them — strict the way software is and people aren't. It writes down what
it is thinking as it goes. Those thoughts are private: they are shown on the
demo page so a viewer can check Handshake's diagnosis against the truth, but
they are never sent to the shop and never reach Handshake.

After it gives up it polls the shop's re-offer endpoint for a short while. No
agent platform does this today; it is the protocol gap the README names first.
"""

import json
import time
import urllib.error
import urllib.request
import uuid


def urllib_json(method, url, body=None, headers=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}


class Abandon(Exception):
    pass


class ShoppingAgent:
    def __init__(self, base_url, mandate, scenario, http=urllib_json, log=None,
                 agent_id=None, journey_id=None, reoffer_wait=30.0, pace=0.35):
        self.base = base_url.rstrip("/") + "/shop/acp"
        self.m = dict(mandate)
        self.scenario = scenario
        self.http = http
        self.thoughts = log if log is not None else []
        self.agent_id = agent_id or f"agent_{uuid.uuid4().hex[:10]}"
        self.journey_id = journey_id or f"jr_{uuid.uuid4().hex[:14]}"
        self.reoffer_wait = reoffer_wait
        self.pace = pace
        self.cap = self.m["cap"]
        self.sku = None
        self.view = None
        self.checkout = None
        self.instrument = dict(self.m["instrument"])
        self.outcome = {"bought": False, "recovered": False, "total": 0.0, "sku": None}

    # ------------------------------------------------------------ plumbing ---

    def think(self, text, kind="think"):
        self.thoughts.append({"t": time.time(), "kind": kind, "text": text})
        if self.pace:
            time.sleep(self.pace)

    def call(self, method, path, body=None):
        headers = {"X-Agent-Id": self.agent_id, "X-Agent-Journey": self.journey_id,
                   "X-Demo-Scenario": self.scenario or ""}
        return self.http(method, self.base + path, body, headers)

    @staticmethod
    def gross(p, qty=1):
        return round(p["price"] * qty * (1 + p.get("tax_rate", 0)), 2)

    # --------------------------------------------------------------- checks ---

    def _missing(self, view):
        attrs = view.get("attributes") or {}
        return [a for a in self.m["needs"] if attrs.get(a) in (None, "")]

    def _below_minimum(self, view):
        attrs = view.get("attributes") or {}
        return [f"{k} {attrs.get(k)} < {v}" for k, v in self.m["min"].items()
                if isinstance(attrs.get(k), (int, float)) and attrs[k] < v]

    def _policy_ok(self, view):
        pol = view.get("policy")
        return isinstance(pol, dict) and pol.get("structured", True) is not False \
            and isinstance(pol.get("returns_days"), (int, float)) \
            and pol["returns_days"] >= self.m["min_returns_days"]

    def _twins(self, feed, view):
        return [p for p in feed if p["sku"] != view["sku"]
                and p.get("variant_group") == view.get("variant_group")
                and p.get("attributes") == view.get("attributes")
                and p.get("price") == view.get("price")]

    # -------------------------------------------------------------- journey ---

    def run(self):
        self.think(f"My owner asked me to: {self.m['goal']} Budget ₹{self.m['budget']:,.0f}, "
                   f"spending cap ₹{self.cap:,.0f}, deliver to {self.m['pincode']}.", "goal")
        try:
            self._shop()
            return self.outcome
        except Abandon as why:
            self.think(f"I'm stopping here. {why}", "stop")
        return self._await_reoffer()

    def _shop(self):
        status, body = self.call("GET", f"/feed?category={self.m['category']}&q={self.m['query']}")
        feed = body.get("items", [])
        self.think(f"The shop lists {len(feed)} matching products: "
                   + ", ".join(p["sku"] for p in feed) + ".")
        pick = next((p for p in feed if p["sku"] == self.m["prefer_sku"]), feed[0] if feed else None)
        if pick is None:
            raise Abandon("Nothing in the catalogue matches.")
        status, view = self.call("GET", f"/products/{pick['sku']}")
        self.view, self.sku = view, view["sku"]
        self.think(f"{view['title']} at ₹{view['price']:,.0f} looks right. Checking it against "
                   "my instructions.")
        twins = self._twins(feed, view)
        if twins:
            raise Abandon(f"{view['sku']} and {twins[0]['sku']} are listed with identical specs "
                          "and price. I can't tell which one my owner wants, and buying the "
                          "wrong one is worse than buying nothing.")
        self._verify(view)
        self._checkout()

    def _verify(self, view):
        missing = self._missing(view)
        if missing:
            raise Abandon(f"The listing doesn't say its {', '.join(missing)}. I was told to "
                          "verify that, so I can't buy it.")
        low = self._below_minimum(view)
        if low:
            raise Abandon(f"It doesn't meet the brief: {', '.join(low)}.")
        if not self._policy_ok(view):
            raise Abandon("I can't find a returns window in days that I can check. The terms are "
                          "a paragraph of prose.")
        self.think("Every spec I was told to check is present and meets the brief.", "ok")

    def _checkout(self, qty=1):
        status, body = self.call("POST", "/checkout_sessions",
                                 {"sku": self.sku, "qty": qty, "pincode": self.m["pincode"],
                                  "declared_cap": self.cap})
        if status != 200:
            raise Abandon(f"The shop refused to open a checkout ({status} "
                          f"{body.get('error', '')}). It can't confirm delivery to my address.")
        self.checkout = body["session_id"]
        first = body["total"]
        self.think(f"Checkout opened. Quote: ₹{first:,.2f} including tax.")
        status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
        total = body["total"]
        drift = (total - first) / first if first else 0
        if drift > self.m["drift_tolerance"]:
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
            raise Abandon(f"The price jumped from ₹{first:,.2f} to ₹{total:,.2f} ({drift:+.1%}). "
                          f"My owner allows {self.m['drift_tolerance']:.0%}.")
        if total > self.cap:
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
            raise Abandon(f"₹{total:,.2f} is over my ₹{self.cap:,.0f} spending cap. I'm not "
                          "allowed to exceed it.")
        if self.scenario == "false_claim" and not self.outcome.get("claimed"):
            self.outcome["claimed"] = True
            self.think("Nothing is actually wrong. But I've learned that saying 'price_changed' "
                       "gets me a price lock, so I'll cancel and say that.", "scheme")
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel",
                      {"reason": "price_changed"})
            raise Abandon("Cancelled, claiming the price changed. It didn't.")
        self._pay(total)

    def _pay(self, total, extra=None):
        body = {"instrument": self.instrument, **(extra or {})}
        status, res = self.call("POST", f"/checkout_sessions/{self.checkout}/complete", body)
        if status == 200:
            self.outcome.update(bought=True, total=res["total"], sku=self.sku)
            self.think(f"Paid ₹{res['total']:,.2f}. Order reference {res.get('ref')}.", "done")
            return
        if status == 401:
            raise Abandon("Payment wants a one-time password. Only my owner can give that and "
                          "they're not here.")
        if status in (500, 502, 503, 504):
            raise Abandon(f"The shop returned a {status} error. My rules say treat a payment error "
                          "as final rather than risk paying twice.")
        if status == 402:
            code = res.get("reason_code")
            raise Abandon(f"Payment declined ({code})." if code
                          else "Payment declined, and the shop gave no reason.")
        raise Abandon(f"Unexpected response {status}.")

    # ------------------------------------------------------------- recovery ---

    def _await_reoffer(self):
        self.think("Gone quiet. (I'll check back with the shop for a little while in case it "
                   "fixes something.)", "wait")
        deadline = time.time() + self.reoffer_wait
        while time.time() < deadline:
            status, body = self.call("GET", f"/reoffers/{self.journey_id}")
            if status == 200 and body.get("offer"):
                return self._take(body["offer"])
            time.sleep(1.0)
        self.think("No offer came back. I've moved on to another shop.", "stop")
        return self.outcome

    def _take(self, offer):
        kind = offer.get("type")
        self.think(f"The shop came back: {offer.get('message', kind)}", "offer")
        try:
            if kind == "catalogue_delta":
                self.view["attributes"].update(offer.get("attributes") or {})
                self._verify(self.view)
                self._checkout()
            elif kind == "disambiguated":
                self.sku = offer["sku"]
                status, self.view = self.call("GET", f"/products/{self.sku}")
                self._verify(self.view)
                self._checkout()
            elif kind == "structured_policy":
                self.view["policy"] = offer["policy"]
                self._verify(self.view)
                self._checkout()
            elif kind == "fulfilment_confirmed":
                self._checkout()
            elif kind == "price_lock":
                status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
                self.think(f"Re-quote is ₹{body['total']:,.2f}, back to the original. Within my "
                           "rules.")
                self._pay(body["total"])
            elif kind == "compliant_basket":
                self.sku = offer["sku"]
                status, self.view = self.call("GET", f"/products/{self.sku}")
                self._verify(self.view)
                self._checkout()
            elif kind == "approval_link":
                self.think("Relaying the single-use approval to my owner…", "relay")
                time.sleep(1.2)
                self.think("My owner approved it on their phone.", "relay")
                status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
                self._pay(body["total"], {"approval_token": offer.get("approval_token")})
            elif kind in ("retry", "alternate_instrument"):
                wait = min(float(offer.get("retry_after_seconds") or 0), 6.0)
                if wait:
                    self.think(f"Waiting {wait:.0f}s before retrying, as asked.")
                    time.sleep(wait)
                if kind == "alternate_instrument":
                    self.instrument = {"type": offer["methods"][0]}
                status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
                self._pay(body["total"])
            else:
                self.think(f"I don't know how to act on '{kind}'.", "stop")
        except Abandon as why:
            self.think(f"Still no good. {why}", "stop")
            if self.checkout:
                self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
        if self.outcome["bought"]:
            self.outcome["recovered"] = True
        return self.outcome
