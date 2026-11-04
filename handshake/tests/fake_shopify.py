"""A stand-in for Shopify's Admin API, for tests.

It answers the requests `handshake.shopify.client` makes, in the shapes
Shopify documents: the client-credentials token exchange, and the GraphQL
operations Shop, Products, Calc (draftOrderCalculate), DraftCreate,
DraftComplete and SetSpecs (metafieldsSet). Prices, stock and specs can be
changed mid-test, the way a merchant changes them in Shopify admin.
"""

import json
import re
from urllib.parse import parse_qs


def product(pid, title, ptype, handle, price, specs, sku=None, available=True, qty=10):
    return {"id": f"gid://shopify/Product/{pid}", "title": title, "handle": handle,
            "productType": ptype, "tags": [], "description": f"{title}.",
            "variants": {"nodes": [{"id": f"gid://shopify/ProductVariant/{pid}0", "sku": sku or "",
                                    "title": "Default Title", "price": f"{price:.2f}",
                                    "inventoryQuantity": qty, "availableForSale": available,
                                    "selectedOptions": [{"name": "Title", "value": "Default Title"}]}]},
            "metafields": {"nodes": [{"namespace": "custom", "key": k, "value": str(v),
                                      "type": "number_integer" if isinstance(v, int)
                                      else "single_line_text_field"} for k, v in specs.items()]}}


class FakeShopify:
    def __init__(self, products=None, client_id="cid", client_secret="secret", tax_rate=0.18):
        self.products = products if products is not None else [
            product(1, "Raaga Over-Ear Headphones", "Headphones", "raaga-over-ear", 3999,
                    {"battery_hours": 40, "driver_mm": 45, "ships_in_days": 2}, sku="RG-OE"),
            product(2, "Raaga Studio Headphones", "Headphones", "raaga-studio", 4499,
                    {"battery_hours": 30, "driver_mm": 50, "ships_in_days": 3}, sku="RG-ST"),
            product(3, "Raaga Lite Headphones", "Headphones", "raaga-lite", 2499,
                    {"driver_mm": 40, "ships_in_days": 2}, sku="RG-LT"),   # no battery spec
        ]
        self.client_id, self.client_secret = client_id, client_secret
        self.tax_rate = tax_rate
        self.tokens_issued = 0
        self.valid_tokens = set()
        self.orders = []
        self.drafts = {}
        self.spec_writes = []
        self.permitted = True
        self.orders_approved = True       # False: refuse orders as protected customer data

    # --- helpers a test uses to play the merchant ---

    def variant(self, sku):
        for p in self.products:
            for v in p["variants"]["nodes"]:
                if v["sku"] == sku:
                    return p, v
        raise KeyError(sku)

    def set_price(self, sku, price):
        self.variant(sku)[1]["price"] = f"{price:.2f}"

    def set_available(self, sku, available):
        self.variant(sku)[1]["availableForSale"] = available

    def revoke_tokens(self):
        self.valid_tokens.clear()

    # --- the transport ---

    def __call__(self, url, body, headers, timeout):
        if url.endswith("/admin/oauth/access_token"):
            form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
            if not self.permitted:
                return 400, json.dumps({"error": "shop_not_permitted"}).encode(), {}
            if form != {"grant_type": "client_credentials", "client_id": self.client_id,
                        "client_secret": self.client_secret}:
                return 401, json.dumps({"error": "invalid_client"}).encode(), {}
            self.tokens_issued += 1
            token = f"tok{self.tokens_issued}"
            self.valid_tokens.add(token)
            return 200, json.dumps({"access_token": token, "scope": "read_products",
                                    "expires_in": 86399}).encode(), {}
        if headers.get("X-Shopify-Access-Token") not in self.valid_tokens:
            return 401, b'{"errors":"[API] Invalid API key or access token"}', {}
        req = json.loads(body)
        op = re.search(r"(query|mutation)\s+(\w+)", req["query"]).group(2)
        if not self.orders_approved and op in ("Calc", "DraftCreate", "DraftComplete"):
            obj = "CalculatedDraftOrder" if op == "Calc" else "DraftOrder"
            return 200, json.dumps({"errors": [{
                "message": f"This app is not approved to access the {obj} object. See "
                           "https://shopify.dev/docs/apps/launch/protected-customer-data for more details.",
                "extensions": {"code": "ACCESS_DENIED"}}]}).encode(), {}
        data = getattr(self, "op_" + op)(req.get("variables") or {})
        return 200, json.dumps({"data": data}).encode(), {}

    def op_Shop(self, v):
        return {"shop": {"name": "Raaga Audio", "currencyCode": "INR",
                         "myshopifyDomain": "raaga-audio.myshopify.com",
                         "billingAddress": {"countryCodeV2": "IN"}}}

    def op_Products(self, v):
        return {"products": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                             "nodes": self.products}}

    def _calc(self, inp):
        line = inp["lineItems"][0]
        _, variant = next((p, x) for p in self.products for x in p["variants"]["nodes"]
                          if x["id"] == line["variantId"])
        sub = round(float(variant["price"]) * line["quantity"], 2)
        tax = round(sub * self.tax_rate, 2)
        money = lambda a: {"shopMoney": {"amount": f"{a:.2f}", "currencyCode": "INR"}}
        zip_code = (inp.get("shippingAddress") or {}).get("zip", "")
        rates = [] if zip_code.startswith("9") else [
            {"handle": "standard", "title": "Standard", "price": {"amount": "0.00"}}]
        return {"subtotalPriceSet": money(sub), "totalTaxSet": money(tax),
                "totalPriceSet": money(sub + tax), "availableShippingRates": rates,
                "lineItems": [{"requiresShipping": True}]}

    def op_Calc(self, v):
        return {"draftOrderCalculate": {"calculatedDraftOrder": self._calc(v["input"]),
                                        "userErrors": []}}

    def op_DraftCreate(self, v):
        did = f"gid://shopify/DraftOrder/{len(self.drafts) + 1}"
        self.drafts[did] = v["input"]
        return {"draftOrderCreate": {"draftOrder": {"id": did}, "userErrors": []}}

    def op_DraftComplete(self, v):
        inp = self.drafts[v["id"]]
        calc = self._calc(inp)
        order = {"id": f"gid://shopify/Order/{len(self.orders) + 1001}",
                 "name": f"#{len(self.orders) + 1001}", "totalPriceSet": calc["totalPriceSet"],
                 "tags": inp.get("tags"), "note": inp.get("note")}
        self.orders.append(order)
        return {"draftOrderComplete": {"draftOrder": {"order": order}, "userErrors": []}}

    def op_SetSpecs(self, v):
        for m in v["metafields"]:
            self.spec_writes.append(m)
            for p in self.products:
                if p["id"] == m["ownerId"]:
                    p["metafields"]["nodes"].append({"namespace": m["namespace"], "key": m["key"],
                                                     "value": m["value"], "type": m["type"]})
        return {"metafieldsSet": {"metafields": [{"key": m["key"], "value": m["value"]}
                                                 for m in v["metafields"]], "userErrors": []}}
