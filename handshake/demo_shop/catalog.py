"""Kaveri Home & Tech — a fictional store with a hand-written catalogue.

`PIM` is the merchant's product database: the source of truth, complete and
correct. What an agent is *served* comes from the storefront feed, which in the
demo can be degraded per journey by a scenario — exactly the kind of quiet feed
bug a real shop carries for months because no human shopper ever needed the
field.
"""

import copy

SCHEMA = {
    "home_kitchen": ["capacity_l", "power_watts", "warranty_months"],
    "audio": ["driver_mm", "battery_hours", "codec_support"],
    "laptop_accessories": ["compatibility", "material", "weight_g"],
}

_POLICY = {"returns_days": 10, "warranty_months": 12, "structured": True}
_SHIP = {"serviceable_pincodes": ["560001", "560034", "400001", "110001", "600028"],
         "ships_in_days": 2}

PIM = [
    {"sku": "KET-170", "title": "Tejas Steel Electric Kettle 1.7 L", "category": "home_kitchen",
     "variant_group": "tejas-kettle-17", "price": 1999.0, "tax_rate": 0.18, "stock": 40,
     "attributes": {"capacity_l": 1.7, "power_watts": 1500, "warranty_months": 24},
     "policy": dict(_POLICY, warranty_months=24), "fulfilment": dict(_SHIP),
     "image": "kettle"},
    {"sku": "KET-150", "title": "Tejas Compact Kettle 1.5 L", "category": "home_kitchen",
     "variant_group": "tejas-kettle-15", "price": 1590.0, "tax_rate": 0.18, "stock": 60,
     "attributes": {"capacity_l": 1.5, "power_watts": 1500, "warranty_months": 12},
     "policy": dict(_POLICY), "fulfilment": dict(_SHIP), "image": "kettle"},
    {"sku": "AFR-040", "title": "Kaveri Air Fryer 4 L", "category": "home_kitchen",
     "variant_group": "kaveri-airfryer-4", "price": 4490.0, "tax_rate": 0.18, "stock": 18,
     "attributes": {"capacity_l": 4.0, "power_watts": 1400, "warranty_months": 12},
     "policy": dict(_POLICY), "fulfilment": dict(_SHIP), "image": "fryer"},
    {"sku": "FLK-075", "title": "Monsoon Vacuum Flask 750 ml", "category": "home_kitchen",
     "variant_group": "monsoon-flask", "price": 849.0, "tax_rate": 0.18, "stock": 120,
     "attributes": {"capacity_l": 0.75, "power_watts": 0, "warranty_months": 6},
     "policy": dict(_POLICY, returns_days=7, warranty_months=6), "fulfilment": dict(_SHIP),
     "image": "flask"},
    {"sku": "HPH-045", "title": "Raaga Over-Ear Wireless Headphones", "category": "audio",
     "variant_group": "raaga-overear", "price": 3999.0, "tax_rate": 0.18, "stock": 25,
     "attributes": {"driver_mm": 45, "battery_hours": 40, "codec_support": "SBC/AAC/LDAC"},
     "policy": dict(_POLICY), "fulfilment": dict(_SHIP), "image": "headphones"},
    {"sku": "IEM-010", "title": "Raaga In-Ear Monitors", "category": "audio",
     "variant_group": "raaga-iem", "price": 1499.0, "tax_rate": 0.18, "stock": 70,
     "attributes": {"driver_mm": 10, "battery_hours": 8, "codec_support": "SBC/AAC"},
     "policy": dict(_POLICY), "fulfilment": dict(_SHIP), "image": "earbuds"},
    {"sku": "LST-AL1", "title": "Deccan Aluminium Laptop Stand", "category": "laptop_accessories",
     "variant_group": "deccan-stand", "price": 1790.0, "tax_rate": 0.18, "stock": 33,
     "attributes": {"compatibility": '11"-16" laptops', "material": "anodised aluminium",
                    "weight_g": 690},
     "policy": dict(_POLICY), "fulfilment": dict(_SHIP), "image": "stand"},
    {"sku": "LST-FD2", "title": "Deccan Folding Desk Riser", "category": "laptop_accessories",
     "variant_group": "deccan-riser", "price": 2290.0, "tax_rate": 0.18, "stock": 14,
     "attributes": {"compatibility": '13"-17" laptops', "material": "bamboo composite",
                    "weight_g": 1150},
     "policy": dict(_POLICY), "fulfilment": dict(_SHIP), "image": "stand"},
]


def pim(sku):
    return next((copy.deepcopy(p) for p in PIM if p["sku"] == sku), None)


def all_products():
    return copy.deepcopy(PIM)
