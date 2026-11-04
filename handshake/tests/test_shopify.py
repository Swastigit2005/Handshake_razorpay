"""The Shopify connector, against a stand-in that answers like Shopify's Admin
API (tests/fake_shopify.py). End to end over real HTTP: an MCP agent shops the
gateway, the gateway calls "Shopify", Handshake diagnoses from the traffic."""

import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from handshake.shopify import catalog as cat  # noqa: E402
from handshake.shopify.client import ShopifyAdmin, ShopifyError  # noqa: E402
from handshake.tests.fake_shopify import FakeShopify  # noqa: E402

DOMAIN = "raaga-audio.myshopify.com"


def admin(fake):
    return ShopifyAdmin(DOMAIN, client_id="cid", client_secret="secret", transport=fake)


# ----------------------------------------------------------------- client ---

def test_client_credentials_token_is_cached_and_renewed_once_on_401():
    fake = FakeShopify()
    a = admin(fake)
    assert a.shop()["name"] == "Raaga Audio" and fake.tokens_issued == 1
    a.shop()
    assert fake.tokens_issued == 1                     # cached for 24 h
    fake.revoke_tokens()
    a.shop()
    assert fake.tokens_issued == 2                     # renewed on the 401, once


def test_a_store_outside_the_organisation_gets_a_useful_error():
    fake = FakeShopify()
    fake.permitted = False
    with pytest.raises(ShopifyError, match="same Shopify organisation"):
        admin(fake).shop()


def test_credentials_are_never_in_the_error_text():
    fake = FakeShopify(client_secret="other")
    with pytest.raises(ShopifyError) as err:
        admin(fake).shop()
    assert "secret" not in str(err.value).replace("client secret", "")


# ---------------------------------------------------------------- catalog ---

def test_products_become_records_and_the_schema_is_learned():
    records = cat.to_records(admin(FakeShopify()).products())
    by = {r["sku"]: r for r in records}
    assert by["RG-OE"]["attributes"] == {"battery_hours": 40, "driver_mm": 45}
    assert by["RG-OE"]["fulfilment"] == {"ships_in_days": 2}
    assert by["RG-OE"]["category"] == "headphones" and by["RG-OE"]["price"] == 3999.0
    schema = cat.derive_schema(records)
    assert schema == {"headphones": ["battery_hours", "driver_mm"]}
    assert cat.gaps(records, schema) == [{"sku": "RG-LT", "title": "Raaga Lite Headphones",
                                          "category": "headphones", "missing": ["battery_hours"]}]


# -------------------------------------------------------------- end to end ---

KEEP = {"handshake", "handshake.database"}


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    import uvicorn
    monkeypatch.setenv("HS_DB", str(tmp_path / "shopify.db"))
    monkeypatch.setenv("HS_NO_SEED", "1")
    monkeypatch.setenv("HS_LOG_LEVEL", "WARNING")
    for mod in [m for m in list(sys.modules) if m.startswith("handshake")
                and m not in KEEP and not m.startswith("handshake.tests")]:
        del sys.modules[mod]
    from handshake.server import app as server
    from handshake.shopify import gateway as gw
    from handshake.shopify.client import ShopifyAdmin as Admin
    fake = FakeShopify()
    gw.ADMIN_FACTORY = lambda: Admin(DOMAIN, client_id="cid", client_secret="secret",
                                     transport=fake)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("HS_SELF_URL", f"http://127.0.0.1:{port}")
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port,
                                        log_level="warning", lifespan="on"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.time() + 15
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    from handshake.live import pipeline
    pipeline.WORKER.interval = 0.1
    yield {"base": f"http://127.0.0.1:{port}", "fake": fake, "gw": gw}
    srv.should_exit = True
    t.join(timeout=20)


def http(method, url, body=None, headers=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    def parse(raw):
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return raw.decode("utf-8", "replace")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), parse(r.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), parse(e.read())


class Agent:
    """An MCP client, as Claude would be."""

    def __init__(self, base, name="test-agent"):
        self.url = base + "/shopify/mcp"
        self.n = 0
        _, h, init = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": name, "version": "1"}})
        self.sid = h.get("mcp-session-id") or h.get("Mcp-Session-Id")
        self.server = init["result"]["serverInfo"]

    def rpc(self, method, params=None):
        self.n += 1
        headers = {"Mcp-Session-Id": self.sid} if getattr(self, "sid", None) else {}
        return http("POST", self.url, {"jsonrpc": "2.0", "id": self.n, "method": method,
                                       "params": params or {}}, headers)

    def tool(self, name, **args):
        _, _, out = self.rpc("tools/call", {"name": name, "arguments": args})
        return json.loads(out["result"]["content"][0]["text"])


def journey_of(g, predicate, timeout=20):
    from handshake.live import store
    deadline = time.time() + timeout
    while time.time() < deadline:
        for j in store.list_journeys(g["gw"].S.merchant_id, None, 50, 0):
            if predicate(j):
                return j
        time.sleep(0.2)
    raise AssertionError("no matching journey")


def test_status_page_and_readiness_report_the_real_store(gateway):
    _, _, s = http("GET", gateway["base"] + "/shopify/api/status")
    assert s["connected"] and s["shop"] == "Raaga Audio" and s["variants"] == 3
    assert s["auth_mode"].startswith("client credentials")
    assert s["gaps"][0]["sku"] == "RG-LT"
    text = json.dumps(s)
    assert "tok1" not in text and "secret" not in text      # no credential ever returned
    assert http("GET", gateway["base"] + "/shopify/")[0] == 200


def test_an_agent_buys_and_the_order_lands_in_shopify(gateway):
    a = Agent(gateway["base"])
    assert a.server["title"] == "Raaga Audio (Shopify)"
    items = a.tool("search_products", query="headphones")["items"]
    assert {i["sku"] for i in items} == {"RG-OE", "RG-ST", "RG-LT"}
    co = a.tool("create_checkout", sku="RG-OE", pincode="560034", spending_cap=5000)
    assert co["status"] == 200 and co["total"] == 4718.82          # Shopify's own calculation
    paid = a.tool("pay", checkout_id=co["checkout_id"], payment_method="card_token")
    assert paid["status"] == "captured" and paid["ref"] == "#1001"
    order = gateway["fake"].orders[0]
    assert "ai-agent" in order["tags"]
    j = journey_of(gateway, lambda j: j["status"] == "converted")
    assert j["basket_value"] == 4718.82


def test_a_missing_spec_in_the_real_catalogue_is_diagnosed(gateway):
    a = Agent(gateway["base"])
    a.tool("get_product", sku="RG-LT")                    # no battery_hours in Shopify
    a.tool("check_for_offer")                             # stops shopping, asks
    j = journey_of(gateway, lambda j: j["status"] not in ("open",))
    assert j["diagnosis"]["cause"] == "A1"
    assert j["diagnosis"]["detail"]["missing"] == ["battery_hours"]
    # Shopify itself lacks the value, so nothing is invented: a person adds it.
    assert j["status"] == "exception" and "could not be built" in j["verdict"]["reason"]


def test_a_price_raised_in_shopify_mid_checkout_is_real_drift(gateway):
    a = Agent(gateway["base"])
    co = a.tool("create_checkout", sku="RG-ST", pincode="560034", spending_cap=6000)
    gateway["fake"].set_price("RG-ST", 4999)              # the merchant edits the price
    re_quote = a.tool("refresh_checkout", checkout_id=co["checkout_id"])
    assert re_quote["total"] > co["total"]
    a.tool("cancel_checkout", checkout_id=co["checkout_id"], reason="price changed")
    j = journey_of(gateway, lambda j: j["status"] not in ("open",))
    assert j["diagnosis"]["cause"] == "A3" and j["diagnosis"]["declared"]["corroborated"]
    assert j["status"] == "recovering" and j["directive"]["intervention"] == "I-03"
    deadline = time.time() + 10                           # the signed webhook locks the quote
    while time.time() < deadline and gateway["gw"].S.sessions[co["checkout_id"]]["locked_total"] is None:
        time.sleep(0.1)
    assert gateway["gw"].S.sessions[co["checkout_id"]]["locked_total"] == co["total"]
    offer = a.tool("check_for_offer")["offer"]
    assert offer["type"] == "price_lock"
    assert a.tool("refresh_checkout", checkout_id=co["checkout_id"])["total"] == co["total"]


def test_stock_running_out_in_shopify_drafts_an_alternative(gateway):
    a = Agent(gateway["base"])
    a.tool("get_product", sku="RG-ST")
    gateway["fake"].set_available("RG-ST", False)
    http("POST", gateway["base"] + "/shopify/api/sync")
    co = a.tool("create_checkout", sku="RG-ST", pincode="560034")
    assert co["status"] == 409 and co["error"] == "insufficient_stock"
    a.tool("check_for_offer")
    j = journey_of(gateway, lambda j: j["status"] not in ("open",))
    assert j["diagnosis"]["cause"] == "N1"
    assert j["verdict"]["proposal"]["action"] == "alternative_product"


def test_real_catalogue_quirks_are_read():
    """Shapes seen in a real dev store: specs outside `custom`, unit values,
    padded numbers, untracked inventory, gift cards, SEO metafields."""
    from handshake.shopify import catalog
    from handshake.tests.fake_shopify import product
    board = product(7, "Complete Snowboard", "snowboard", "complete", 699.95, {}, qty=0)
    board["metafields"]["nodes"] = [
        {"namespace": "test_data", "key": "snowboard_length",
         "value": '{"value":159.0,"unit":"CENTIMETERS"}', "type": "dimension"},
        {"namespace": "custom", "key": "battery_hours", "value": " 30", "type": ""},
        {"namespace": "global", "key": "title_tag", "value": "SEO", "type": ""}]
    gift = product(8, "Gift Card", "giftcard", "gift-card", 10, {})
    gift["isGiftCard"] = True
    recs = catalog.to_records([board, gift])
    assert len(recs) == 1
    assert recs[0]["attributes"] == {"snowboard_length": 159.0, "battery_hours": 30}
    assert recs[0]["stock"] == 1                        # untracked: for sale at 0


def test_without_order_approval_the_store_runs_in_catalogue_mode(gateway):
    """What a Dev Dashboard app on a real store got: catalogue reads work, but
    Shopify refuses draft orders as protected customer data."""
    fake = gateway["fake"]
    fake.orders_approved = False
    a = Agent(gateway["base"])
    co = a.tool("create_checkout", sku="RG-OE", pincode="10001", spending_cap=5000)
    assert co["status"] == 200 and co["total"] == 3999.0 and "not in Shopify" in co["note"]
    fake.set_price("RG-OE", 4299)                         # still the live Shopify price
    assert a.tool("refresh_checkout", checkout_id=co["checkout_id"])["total"] == 4299.0
    paid = a.tool("pay", checkout_id=co["checkout_id"], payment_method="card_token")
    assert paid["status"] == "captured" and paid["recorded_by"] == "handshake"
    assert paid["ref"].startswith("HS-") and not fake.orders
    _, _, s = http("GET", gateway["base"] + "/shopify/api/status")
    assert s["orders"].startswith("catalogue mode")
    assert journey_of(gateway, lambda j: j["status"] == "converted")
    fake.orders_approved = True                           # approval switches it back
    co = a.tool("create_checkout", sku="RG-OE", pincode="10001", spending_cap=6000)
    assert "note" not in co
    _, _, s = http("GET", gateway["base"] + "/shopify/api/status")
    assert s["orders"] == "written to Shopify"


def test_a_cap_breach_is_not_answered_with_an_item_the_agent_passed_over(gateway):
    """From Claude's run on a real store: it saw every pair, chose the one listed
    above its cap for a spec the cheaper ones lacked, and stopped at the cap.
    Offering it a cheaper pair it had already skipped is no recovery."""
    a = Agent(gateway["base"])
    a.tool("search_products", query="headphones")          # sees all three
    co = a.tool("create_checkout", sku="RG-ST", pincode="560034", spending_cap=4000)
    a.tool("cancel_checkout", checkout_id=co["checkout_id"], reason="over my budget")
    j = journey_of(gateway, lambda j: j["status"] not in ("open",))
    assert j["diagnosis"]["cause"] == "A4"
    # Every cheaper pair was one it skipped (each has a smaller driver), so no
    # compliant basket is built; the next rung asks its owner to raise the cap.
    assert "I-04" in j["verdict"]["unbuildable"]
    assert j["directive"]["intervention"] == "I-05"
    from handshake.live import directives, store
    dg, mid = j["diagnosis"], gateway["gw"].S.merchant_id
    ctx = {"product": lambda sku: store.get_product(mid, sku),
           "events": lambda: store.journey_events(mid, j["journey_id"])}
    skipped, floors = directives.passed_over(dg, j, ctx)
    assert skipped == {"RG-OE", "RG-LT"} and floors == {"driver_mm": 45}
    note = directives.propose(dg, j, ctx)["merchant_change"]
    assert "driver mm beyond 45" in note and "₹4,000" in note and "would have sold" in note
