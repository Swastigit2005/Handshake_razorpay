"""A small Shopify Admin GraphQL client: only what the agent gateway needs.

Configuration (environment), one of two ways:

    SHOPIFY_STORE_DOMAIN    your-store.myshopify.com              (always)

    SHOPIFY_CLIENT_ID       an app made in Shopify's Dev Dashboard (the way
    SHOPIFY_CLIENT_SECRET   since January 2026). The client credentials grant
                            gives a token valid for 24 hours; it is cached and
                            refreshed automatically. The app and the store must
                            be in the same Shopify organisation.
  or
    SHOPIFY_ADMIN_TOKEN     shpat_… from a legacy custom app made before 2026

    SHOPIFY_API_VERSION     defaults to 2026-07; Shopify serves the oldest
                            supported version if this one has been retired

Scopes the app needs: read_products, read_inventory, write_draft_orders,
read_orders, write_products (only to let Handshake write a repaired spec back).

Credentials are secrets. They are read from the environment, never logged,
never returned by any endpoint, and never sent anywhere except Shopify.
"""

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_VERSION = "2026-07"


class ShopifyError(RuntimeError):
    pass


def configured():
    return bool(os.environ.get("SHOPIFY_STORE_DOMAIN") and (
        os.environ.get("SHOPIFY_ADMIN_TOKEN")
        or (os.environ.get("SHOPIFY_CLIENT_ID") and os.environ.get("SHOPIFY_CLIENT_SECRET"))))


def _http_post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})


class ShopifyAdmin:
    def __init__(self, domain=None, token=None, version=None, transport=None, timeout=20.0,
                 client_id=None, client_secret=None):
        self.domain = (domain or os.environ.get("SHOPIFY_STORE_DOMAIN", "")).strip()
        self.domain = self.domain.removeprefix("https://").removeprefix("http://").rstrip("/")
        self.static_token = token or os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
        self.client_id = client_id or os.environ.get("SHOPIFY_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("SHOPIFY_CLIENT_SECRET", "")
        self.version = version or os.environ.get("SHOPIFY_API_VERSION", DEFAULT_VERSION)
        self.transport = transport or _http_post
        self.timeout = timeout
        if not self.domain or not (self.static_token or (self.client_id and self.client_secret)):
            raise ShopifyError("set SHOPIFY_STORE_DOMAIN and either SHOPIFY_CLIENT_ID + "
                               "SHOPIFY_CLIENT_SECRET (Dev Dashboard app) or SHOPIFY_ADMIN_TOKEN")
        self._token, self._expires = "", 0.0
        self.calls = 0
        self.token_refreshes = 0

    @property
    def auth_mode(self):
        return "admin token" if self.static_token else "client credentials (24 h tokens)"

    def token(self, force=False):
        """The access token. Client-credentials tokens are cached and renewed a
        minute before Shopify's 24-hour expiry."""
        if self.static_token:
            return self.static_token
        if not force and self._token and time.time() < self._expires - 60:
            return self._token
        from urllib.parse import urlencode
        body = urlencode({"grant_type": "client_credentials", "client_id": self.client_id,
                          "client_secret": self.client_secret}).encode()
        status, raw, _ = self.transport(f"https://{self.domain}/admin/oauth/access_token", body,
                                        {"Content-Type": "application/x-www-form-urlencoded",
                                         "Accept": "application/json"}, self.timeout)
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {}
        if status != 200 or not data.get("access_token"):
            err = data.get("error") or data.get("errors") or f"HTTP {status}"
            hint = (" The app and the store must belong to the same Shopify organisation in "
                    "the Dev Dashboard." if "shop_not_permitted" in str(err) else "")
            raise ShopifyError(f"Shopify refused the app credentials: {err}.{hint}")
        self._token = data["access_token"]
        self._expires = time.time() + float(data.get("expires_in") or 86399)
        self.token_refreshes += 1
        return self._token

    @property
    def url(self):
        return f"https://{self.domain}/admin/api/{self.version}/graphql.json"

    def graphql(self, query, variables=None, attempts=5):
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        delay = 1.0
        renewed = False
        for attempt in range(attempts):
            headers = {"Content-Type": "application/json", "Accept": "application/json",
                       "X-Shopify-Access-Token": self.token()}
            self.calls += 1
            status, raw, resp_headers = self.transport(self.url, body, headers, self.timeout)
            if status == 401 and not self.static_token and not renewed:
                self.token(force=True)          # expired early or revoked: renew once
                renewed = True
                continue
            if status == 429 or 500 <= status < 600:
                wait = float(resp_headers.get("Retry-After") or delay)
                time.sleep(min(wait, 10.0))
                delay *= 2
                continue
            if status == 401 or status == 403:
                raise ShopifyError(f"Shopify refused the token ({status}). Check the app is "
                                   "installed and has the scopes listed in the docs.")
            if status == 404:
                raise ShopifyError(f"no Shopify store at {self.domain} (404)")
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                raise ShopifyError(f"Shopify returned non-JSON ({status})")
            errors = data.get("errors") or []
            if any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors):
                time.sleep(delay)
                delay *= 2
                continue
            if errors:
                raise ShopifyError("; ".join(e.get("message", "?") for e in errors)[:400])
            return data.get("data") or {}
        raise ShopifyError("Shopify kept throttling; try again shortly")

    # ------------------------------------------------------------ reads ---

    def shop(self):
        return self.graphql("""query Shop { shop { name currencyCode myshopifyDomain
            billingAddress { countryCodeV2 } } }""")["shop"]

    def products(self, limit=100):
        """Active products with variants and metafields. Paginates."""
        out, cursor = [], None
        while len(out) < limit:
            data = self.graphql("""query Products($cursor: String) {
              products(first: 50, after: $cursor, query: "status:active") {
                pageInfo { hasNextPage endCursor }
                nodes { id title handle productType tags description(truncateAt: 400)
                  variants(first: 25) { nodes { id sku title price inventoryQuantity
                    availableForSale selectedOptions { name value } } }
                  metafields(first: 40) { nodes { namespace key value type } } } } }""",
                                {"cursor": cursor})["products"]
            out.extend(data["nodes"])
            if not data["pageInfo"]["hasNextPage"]:
                break
            cursor = data["pageInfo"]["endCursor"]
        return out[:limit]

    # ----------------------------------------------------------- orders ---

    def quote(self, variant_id, quantity, address):
        """Shopify's own calculation: subtotal, tax, shipping rates, total."""
        data = self.graphql("""mutation Calc($input: DraftOrderInput!) {
          draftOrderCalculate(input: $input) {
            calculatedDraftOrder {
              subtotalPriceSet { shopMoney { amount currencyCode } }
              totalTaxSet { shopMoney { amount } }
              totalPriceSet { shopMoney { amount currencyCode } }
              availableShippingRates { handle title price { amount } }
              lineItems { requiresShipping } }
            userErrors { field message } } }""",
                            {"input": {"lineItems": [{"variantId": variant_id, "quantity": quantity}],
                                       "shippingAddress": address}})["draftOrderCalculate"]
        if data["userErrors"]:
            raise ShopifyError("; ".join(e["message"] for e in data["userErrors"]))
        return data["calculatedDraftOrder"]

    def place_order(self, variant_id, quantity, address, shipping_handle=None, note=""):
        """Create a draft order and complete it, which records a paid order.
        In a development store this is a test order; nothing is charged."""
        draft_input = {"lineItems": [{"variantId": variant_id, "quantity": quantity}],
                       "shippingAddress": address, "note": note,
                       "tags": ["handshake", "ai-agent"]}
        if shipping_handle:
            draft_input["shippingLine"] = {"shippingRateHandle": shipping_handle}
        created = self.graphql("""mutation DraftCreate($input: DraftOrderInput!) {
          draftOrderCreate(input: $input) { draftOrder { id }
            userErrors { field message } } }""", {"input": draft_input})["draftOrderCreate"]
        if created["userErrors"] and shipping_handle:
            # Older API versions take the shipping line differently; the order
            # matters more than the shipping line, so retry without it.
            return self.place_order(variant_id, quantity, address, None, note)
        if created["userErrors"]:
            raise ShopifyError("; ".join(e["message"] for e in created["userErrors"]))
        done = self.graphql("""mutation DraftComplete($id: ID!) {
          draftOrderComplete(id: $id) {
            draftOrder { order { id name totalPriceSet { shopMoney { amount currencyCode } } } }
            userErrors { field message } } }""",
                            {"id": created["draftOrder"]["id"]})["draftOrderComplete"]
        if done["userErrors"]:
            raise ShopifyError("; ".join(e["message"] for e in done["userErrors"]))
        return done["draftOrder"]["order"]

    # ----------------------------------------------------------- writes ---

    def set_spec(self, product_id, key, value, namespace="custom"):
        """Write one spec back to the product (Handshake's I-01 repair)."""
        data = self.graphql("""mutation SetSpecs($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) { metafields { key value }
            userErrors { field message } } }""",
                            {"metafields": [{"ownerId": product_id, "namespace": namespace,
                                             "key": key, "type": "single_line_text_field",
                                             "value": str(value)}]})["metafieldsSet"]
        if data["userErrors"]:
            raise ShopifyError("; ".join(e["message"] for e in data["userErrors"]))
        return data["metafields"]
