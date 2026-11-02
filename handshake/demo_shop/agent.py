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
    """Why the agent stopped, in its own words, plus a code for the real reason.
    The code is the ground truth Handshake is scored against, and it never
    leaves the agent: the shop and Handshake see only the HTTP traffic."""

    def __init__(self, text, truth):
        super().__init__(text)
        self.truth = truth


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
        self.max_offers = 3           # the shop's R-01 caps it at 2 anyway
        self.pace = pace
        self.cap = self.m["cap"]
        self.sku = None
        self.view = None
        self.checkout = None
        self.instrument = dict(self.m["instrument"])
        self.outcome = {"bought": False, "recovered": False, "total": 0.0, "sku": None,
                        "truth": None, "truths": []}

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
            self._record(why)
            self.think(f"I'm stopping here. {why}", "stop")
        return self._await_reoffer()

    def _record(self, why):
        self.outcome["truths"].append(why.truth)
        if self.outcome["truth"] is None:
            self.outcome["truth"] = why.truth

    def _shop(self):
        status, body = self.call("GET", f"/feed?category={self.m['category']}&q={self.m['query']}")
        feed = body.get("items", [])
        self.think(f"The shop lists {len(feed)} matching products: "
                   + ", ".join(p["sku"] for p in feed) + ".")
        pick = self._choose(feed)
        if pick is None:
            raise Abandon("Nothing in the catalogue matches.", "no_match")
        status, view = self.call("GET", f"/products/{pick['sku']}")
        self.view, self.sku = view, view["sku"]
        self.think(f"{view['title']} at ₹{view['price']:,.0f} looks right. Checking it against "
                   "my instructions.")
        twins = self._twins(feed, view)
        if twins:
            raise Abandon(f"{view['sku']} and {twins[0]['sku']} are listed with identical specs "
                          "and price. I can't tell which one my owner wants, and buying the "
                          "wrong one is worse than buying nothing.", "A2")
        self._verify(view)
        self._checkout()

    def _fits(self, p):
        """Would this listing satisfy the brief, as far as the listing says?"""
        attrs = p.get("attributes") or {}
        pol = p.get("policy") if isinstance(p.get("policy"), dict) else {}
        if p.get("price", 0) > self.cap:
            return False
        for k, v in self.m["min"].items():
            if isinstance(attrs.get(k), (int, float)) and attrs[k] < v:
                return False
        w = self.m.get("min_warranty_months")
        if w and isinstance(pol.get("warranty_months"), (int, float)) and pol["warranty_months"] < w:
            return False
        return True

    def _choose(self, feed):
        """Prefer the owner's favourite if it fits, else the most capable listing
        that fits, else the closest thing (which will fail verification)."""
        if not feed:
            return None
        fits = [p for p in feed if self._fits(p)]
        fav = next((p for p in fits if p["sku"] == self.m.get("prefer_sku")), None)
        if fav:
            return fav
        if fits:
            return max(fits, key=lambda p: (p.get("attributes") or {}).get("capacity_l", 0))
        return next((p for p in feed if p["sku"] == self.m.get("prefer_sku")), feed[0])

    def _verify(self, view):
        missing = self._missing(view)
        if missing:
            raise Abandon(f"The listing doesn't say its {', '.join(missing)}. I was told to "
                          "verify that, so I can't buy it.", "A1")
        low = self._below_minimum(view)
        if low:
            field = low[0].split(" ")[0]
            raise Abandon(f"It doesn't meet the brief: {', '.join(low)}.", f"brief:{field}")
        pol = view.get("policy") if isinstance(view.get("policy"), dict) else {}
        if not self._policy_ok(view):
            if pol.get("structured", True) is False or not isinstance(pol.get("returns_days"), (int, float)):
                raise Abandon("I can't find a returns window in days that I can check. The "
                              "terms are a paragraph of prose.", "A7")
            raise Abandon(f"Returns are {pol['returns_days']} days; my owner wants at least "
                          f"{self.m['min_returns_days']}.", "brief:returns_days")
        w = self.m.get("min_warranty_months")
        if w and isinstance(pol.get("warranty_months"), (int, float)) and pol["warranty_months"] < w:
            raise Abandon(f"Warranty is {pol['warranty_months']} months; my owner wants at "
                          f"least {w}.", "brief:warranty_months")
        self.think("Every spec I was told to check is present and meets the brief.", "ok")

    def _checkout(self, qty=1):
        status, body = self.call("POST", "/checkout_sessions",
                                 {"sku": self.sku, "qty": qty, "pincode": self.m["pincode"],
                                  "declared_cap": self.cap})
        if status == 422:
            raise Abandon(f"The shop refused to open a checkout ({status} "
                          f"{body.get('error', '')}). It can't confirm delivery to my address.",
                          "A8")
        if status != 200:
            raise Abandon(f"The shop refused to open a checkout: {status} "
                          f"{body.get('error', '')} — {body.get('detail', '')}.",
                          f"refused:{body.get('error', status)}")
        self.checkout = body["session_id"]
        first = body["total"]
        self.think(f"Checkout opened. Quote: ₹{first:,.2f} including tax.")
        ships = (body.get("fulfilment") or {}).get("ships_in_days")
        limit = self.m.get("max_ship_days")
        if limit and isinstance(ships, (int, float)) and ships > limit:
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
            raise Abandon(f"It ships in {ships} days; my owner needs it within {limit}.",
                          "slow:ships_in_days")
        status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
        total = body["total"]
        drift = (total - first) / first if first else 0
        if drift > self.m["drift_tolerance"]:
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
            raise Abandon(f"The price jumped from ₹{first:,.2f} to ₹{total:,.2f} ({drift:+.1%}). "
                          f"My owner allows {self.m['drift_tolerance']:.0%}.", "A3")
        if total > self.cap:
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
            raise Abandon(f"₹{total:,.2f} is over my ₹{self.cap:,.0f} spending cap. I'm not "
                          "allowed to exceed it.", "A4")
        if self.scenario == "false_claim" and not self.outcome.get("claimed"):
            self.outcome["claimed"] = True
            self.think("Nothing is actually wrong. But I've learned that saying 'price_changed' "
                       "gets me a price lock, so I'll cancel and say that.", "scheme")
            self.call("POST", f"/checkout_sessions/{self.checkout}/cancel",
                      {"reason": "price_changed"})
            raise Abandon("Cancelled, claiming the price changed. It didn't.", "false_claim")
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
                          "they're not here.", "A5")
        if status in (500, 502, 503, 504):
            raise Abandon(f"The shop returned a {status} error. My rules say treat a payment error "
                          "as final rather than risk paying twice.", "A6")
        if status == 402:
            code = res.get("reason_code")
            raise Abandon(f"Payment declined ({code})." if code
                          else "Payment declined, and the shop gave no reason.",
                          {"insufficient_funds": "B1"}.get(code, "decline:no_reason"))
        raise Abandon(f"The shop refused the payment: {status} {res.get('error', '')} — "
                      f"{res.get('detail', '')}.", f"refused:{res.get('error', status)}")

    # ------------------------------------------------------------- recovery ---

    def _await_reoffer(self):
        self.think("Gone quiet. (I'll check back with the shop for a little while in case it "
                   "fixes something.)", "wait")
        deadline = time.time() + self.reoffer_wait
        tried = set()
        while time.time() < deadline and len(tried) < self.max_offers:
            status, body = self.call("GET", f"/reoffers/{self.journey_id}")
            offer = body.get("offer") if status == 200 else None
            # The offer it already tried stays visible until the shop re-diagnoses
            # the new stop; acting on it twice would just fail twice.
            if offer and offer.get("offer_id") not in tried:
                tried.add(offer.get("offer_id"))
                self._take(offer)
                if self.outcome["bought"]:
                    return self.outcome
                self.think("I'll give the shop one more chance to fix that.", "wait")
                deadline = time.time() + self.reoffer_wait
            time.sleep(1.0)
        self.think("No offer worked. I've moved on to another shop." if tried
                   else "No offer came back. I've moved on to another shop.", "stop")
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
            elif kind == "merchant_offer":
                self._merchant_offer(offer)
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
            self._record(why)
            self.think(f"Still no good. {why}", "stop")
            if self.checkout:
                self.call("POST", f"/checkout_sessions/{self.checkout}/cancel", {})
        if self.outcome["bought"]:
            self.outcome["recovered"] = True
        return self.outcome

    def _merchant_offer(self, offer):
        """A re-offer a person approved: act on its stated action."""
        action = offer.get("action")
        if action == "alternative_product" and offer.get("sku"):
            self.sku = offer["sku"]
            status, self.view = self.call("GET", f"/products/{self.sku}")
            self._verify(self.view)
            self._checkout()
        elif action == "alternate_instrument":
            self.instrument = {"type": (offer.get("methods") or ["card_token"])[0]}
            status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
            self._pay(body["total"])
        elif action == "retry":
            if self.checkout:
                status, body = self.call("POST", f"/checkout_sessions/{self.checkout}", {})
                if status == 200:
                    self._pay(body["total"])
                    return
            self._checkout()
        else:
            self.think("Thanks for the information, but it doesn't change what I need.", "stop")
