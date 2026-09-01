"""Static catalogue audit.

Finds by inspection what an agent would refuse to buy over. No agents run here
and nothing is guessed: a required field is present or it is not.

This is the cheap half. It says *what is wrong*. The scan (scan.py) says what
it costs, which is the half a merchant will act on.
"""

from collections import defaultdict

from ..merchant.catalog import required_attributes

# An out-of-stock listing is ordinary commerce, not a data defect: the feed
# never shows it, so it refuses no basket. It is reported as advisory and kept
# out of the readiness score, which measures data quality, not inventory.
ADVISORY = {"stale_stock"}

SEVERITY = {
    "missing_attribute": "blocks a strict or balanced buyer outright",
    "variant_collision": "buyer cannot choose between identical listings",
    "unserviceable": "checkout session refused before it opens",
    "prose_policy": "risk-averse buyer abandons rather than guess the terms",
    "stale_stock": "listed to an agent that cannot buy it",
}


def audit(catalog):
    """Return a list of defect records found by inspection alone."""
    defects = []
    by_group = defaultdict(list)

    for product in catalog:
        sku = product["sku"]
        category = product.get("category", "")

        for field in required_attributes(category) if category else []:
            if field not in product.get("attributes", {}):
                defects.append({
                    "kind": "missing_attribute", "sku": sku, "field": field,
                    "category": category,
                    "detail": f"required attribute {field} absent from the feed"})

        if not product.get("policy", {}).get("structured", True):
            defects.append({
                "kind": "prose_policy", "sku": sku, "field": "policy",
                "category": category,
                "detail": "returns and warranty are prose, not machine-readable fields"})

        if not product.get("fulfilment", {}).get("serviceable_pincodes"):
            defects.append({
                "kind": "unserviceable", "sku": sku, "field": "serviceable_pincodes",
                "category": category, "detail": "no serviceable route stated"})

        if product.get("stock", 0) <= 0:
            defects.append({
                "kind": "stale_stock", "sku": sku, "field": "stock",
                "category": category,
                "detail": "out of stock — withheld from the feed, so it costs "
                          "the impression rather than the basket"})

        by_group[product.get("variant_group", sku)].append(product)

    for group, members in by_group.items():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if (a.get("attributes") == b.get("attributes")
                        and a.get("price") == b.get("price")):
                    defects.append({
                        "kind": "variant_collision", "sku": a["sku"],
                        "field": "variant_group", "category": a.get("category", ""),
                        "detail": f"indistinguishable from {b['sku']}"})

    for defect in defects:
        defect["severity"] = SEVERITY.get(defect["kind"], "")
        defect["advisory"] = defect["kind"] in ADVISORY
    return defects


def blocking(defects):
    """Defects that actually refuse baskets."""
    return [d for d in defects if not d.get("advisory")]


def by_field(defects):
    """Roll defects up to the thing a merchant actually fixes: one field."""
    rolled = defaultdict(lambda: {"skus": [], "kind": "", "detail": ""})
    for defect in defects:
        key = (defect["kind"], defect["field"], defect.get("category", ""))
        row = rolled[key]
        row["kind"], row["field"] = defect["kind"], defect["field"]
        row["category"] = defect.get("category", "")
        row["detail"] = defect["detail"]
        row["skus"].append(defect["sku"])
    return [{**v, "sku_count": len(v["skus"])} for v in rolled.values()]


def readiness_score(catalog, defects):
    """Share of listings an agent can transact against without stumbling."""
    listings = max(1, len(catalog))
    affected = len({d["sku"] for d in defects if not d.get("advisory")})
    return round(100 * (1 - affected / listings), 1)
