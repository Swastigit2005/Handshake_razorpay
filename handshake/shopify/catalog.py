"""Shopify products → the records agents read and Handshake reasons over.

One record per variant, because a variant is what an agent buys.

  sku          the variant's SKU, or `v<numeric id>` when it has none
  category     the product type, as a slug ("Electric Kettle" → electric_kettle)
  attributes   spec metafields plus the variant's options (colour, size…).
               Every namespace counts except Shopify's own (global SEO tags,
               shopify--…) and apps' (app--…); SHOPIFY_SPEC_NAMESPACES="custom,specs"
               restricts it to a list
  policy       returns_days / warranty_months metafields, when present
  fulfilment   ships_in_days metafield, when present

What counts as a *required* spec is learned from the catalogue itself: a spec
that most products of a type carry is one agents comparing that type will look
for, so a product of that type without it is a defect. A merchant can override
this with SHOPIFY_REQUIRED_SPECS='{"electric_kettle": ["capacity_l", "power_watts"]}'.
"""

import json
import os
import re

POLICY_KEYS = {"returns_days", "warranty_months"}
FULFIL_KEYS = {"ships_in_days"}
REQUIRED_SHARE = 0.6


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "general"


def _value(raw, kind=""):
    """Metafield values arrive as strings; numbers become numbers."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("{"):                 # dimension / weight / volume / money
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and "value" in obj:
                    return _value(str(obj["value"]))
                if isinstance(obj, dict) and "amount" in obj:
                    return _value(str(obj["amount"]))
            except ValueError:
                pass
    if kind.startswith("list.") or (isinstance(raw, str) and raw.startswith("[")):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    if kind in ("number_integer",) or re.fullmatch(r"-?\d+", str(raw)):
        try:
            return int(raw)
        except ValueError:
            pass
    if kind in ("number_decimal",) or re.fullmatch(r"-?\d+\.\d+", str(raw)):
        try:
            return float(raw)
        except ValueError:
            pass
    if kind == "dimension" or kind == "weight" or kind == "volume":
        try:
            return json.loads(raw).get("value")
        except (ValueError, AttributeError):
            return raw
    return raw


SYSTEM_NAMESPACES = {"global", "seo", "mm-google-shopping", "descriptors", "reviews"}


def namespaces():
    """The allowed namespaces, or None for any non-system namespace."""
    listed = {n.strip() for n in os.environ.get("SHOPIFY_SPEC_NAMESPACES", "").split(",") if n.strip()}
    return listed or None


def _is_spec_namespace(ns, allowed):
    if allowed is not None:
        return ns in allowed
    return not (ns in SYSTEM_NAMESPACES or ns.startswith(("shopify", "app--", "$app")))


def to_records(products):
    spaces = namespaces()
    out = []
    for p in products:
        if p.get("isGiftCard") or slug(p.get("productType")) in ("giftcard", "gift_card"):
            continue                                  # not something an agent ships
        specs, policy, fulfilment = {}, {}, {}
        for m in (p.get("metafields") or {}).get("nodes", []):
            if not _is_spec_namespace(m["namespace"], spaces):
                continue
            value = _value(m["value"], m.get("type", ""))
            if m["key"] in POLICY_KEYS:
                policy[m["key"]] = value
            elif m["key"] in FULFIL_KEYS:
                fulfilment[m["key"]] = value
            else:
                specs[m["key"]] = value
        if policy:
            policy["structured"] = True
        for v in (p.get("variants") or {}).get("nodes", []):
            attrs = dict(specs)
            for opt in v.get("selectedOptions") or []:
                if opt["name"].lower() != "title":
                    attrs[slug(opt["name"])] = opt["value"]
            numeric = v["id"].rsplit("/", 1)[-1]
            title = p["title"] if v.get("title") in (None, "", "Default Title") \
                else f"{p['title']} – {v['title']}"
            stock = v.get("inventoryQuantity")
            if stock is None or (stock <= 0 and v.get("availableForSale")):
                # Untracked inventory (or overselling allowed): Shopify sells it
                # at any count, so it is in stock.
                stock = 1 if v.get("availableForSale", True) else 0
            out.append({
                "sku": (v.get("sku") or "").strip() or f"v{numeric}",
                "title": title, "category": slug(p.get("productType")),
                "price": float(v.get("price") or 0), "currency": None, "tax_rate": 0.0,
                "stock": stock, "available": bool(v.get("availableForSale", True)),
                "attributes": attrs, "policy": policy or {},
                "fulfilment": fulfilment, "variant_group": p.get("handle"),
                "description": p.get("description") or "",
                "shopify": {"product_id": p["id"], "variant_id": v["id"]},
            })
    return out


def derive_schema(records):
    """Required specs per category: keys most products of that category carry."""
    override = os.environ.get("SHOPIFY_REQUIRED_SPECS")
    if override:
        try:
            return {k: list(v) for k, v in json.loads(override).items()}
        except ValueError:
            pass
    by_cat = {}
    for r in records:
        by_cat.setdefault(r["category"], {}).setdefault(r["variant_group"], set()).update(
            k for k, v in r["attributes"].items() if v not in (None, ""))
    schema = {}
    for cat, groups in by_cat.items():
        if len(groups) < 2:
            continue
        counts = {}
        for keys in groups.values():
            for k in keys:
                counts[k] = counts.get(k, 0) + 1
        required = sorted(k for k, n in counts.items() if n / len(groups) >= REQUIRED_SHARE)
        if required:
            schema[cat] = required
    return schema


def gaps(records, schema):
    """Readiness: listings missing a spec their category requires."""
    out = []
    for r in records:
        missing = [k for k in schema.get(r["category"], [])
                   if r["attributes"].get(k) in (None, "")]
        if missing:
            out.append({"sku": r["sku"], "title": r["title"], "category": r["category"],
                        "missing": missing})
    return out


def public(record):
    """What an agent is served: no internal ids."""
    return {k: v for k, v in record.items() if k not in ("shopify", "description")} | \
        {"description": record.get("description", "")[:400]}
