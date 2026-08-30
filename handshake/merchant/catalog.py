"""Synthetic merchant catalogue.

Deliberately imperfect: the generator produces a clean catalogue, and the fault
injector (faults.py) degrades it per session. Required-attribute lists per
category are what a real agent would need before it will commit.
"""

import random

CATEGORIES = {
    "laptop_accessories": {
        "required": ["compatibility", "material", "weight_g"],
        "titles": ["Aluminium Laptop Stand", "Folding Desk Riser", "Ventilated Cooling Pad",
                   "Adjustable Arm Mount", "Compact Travel Stand"],
        "price_range": (899, 4499),
    },
    "audio": {
        "required": ["driver_mm", "battery_hours", "codec_support"],
        "titles": ["Over-Ear Wireless Headphones", "In-Ear Monitors", "Desktop Speaker Pair",
                   "Bone-Conduction Headset", "Studio Reference Cans"],
        "price_range": (1299, 12999),
    },
    "everyday_small": {
        "required": ["pack_size", "material", "shelf_life_months"],
        "titles": ["Steel Water Bottle", "Silicone Spatula Set", "Cotton Tote",
                   "Desk Cable Organiser", "Ceramic Mug Pair"],
        "price_range": (149, 899),
    },
    "home_kitchen": {
        "required": ["capacity_l", "power_watts", "warranty_months"],
        "titles": ["Stainless Electric Kettle", "Compact Air Fryer", "Vacuum Insulated Flask",
                   "Induction Cooktop", "Cold Brew Carafe"],
        "price_range": (749, 8999),
    },
}

MATERIALS = ["anodised aluminium", "ABS polymer", "stainless steel", "bamboo composite"]
CODECS = ["SBC/AAC", "SBC/AAC/aptX", "SBC/AAC/LDAC"]
PINCODES = ["560001", "560034", "400001", "110001", "600028", "700019", "500081"]


def _attributes(rng, category):
    if category == "laptop_accessories":
        return {
            "compatibility": rng.choice(['11"-16" laptops', '13"-17" laptops', 'up to 15.6"']),
            "material": rng.choice(MATERIALS),
            "weight_g": rng.choice([420, 560, 690, 880, 1150]),
        }
    if category == "audio":
        return {
            "driver_mm": rng.choice([10, 12, 40, 45, 50]),
            "battery_hours": rng.choice([8, 20, 30, 45, 60]),
            "codec_support": rng.choice(CODECS),
        }
    if category == "everyday_small":
        return {
            "pack_size": rng.choice([1, 2, 4, 6]),
            "material": rng.choice(MATERIALS),
            "shelf_life_months": rng.choice([12, 24, 36]),
        }
    return {
        "capacity_l": rng.choice([0.5, 1.0, 1.7, 2.5, 4.0]),
        "power_watts": rng.choice([600, 900, 1200, 1500, 1800]),
        "warranty_months": rng.choice([6, 12, 24]),
    }


def build_catalog(seed=20260830, n=48):
    """Return a list of SKU records. Deterministic for a given seed."""
    rng = random.Random(seed)
    catalog = []
    per_cat = max(1, n // len(CATEGORIES))
    for category, meta in CATEGORIES.items():
        for i in range(per_cat):
            base = rng.choice(meta["titles"])
            lo, hi = meta["price_range"]
            price = round(rng.uniform(lo, hi) / 10) * 10
            sku = f"{category[:3].upper()}-{i:03d}"
            catalog.append({
                "sku": sku,
                "title": f"{base} {rng.choice(['Mk I', 'Mk II', 'Pro', 'Lite', 'Studio'])}",
                "category": category,
                "price": float(price),
                "currency": "INR",
                "stock": rng.choice([0, 3, 12, 40, 120]),
                "tax_rate": 0.18,
                "attributes": _attributes(rng, category),
                "variant_group": f"{category}-{base}".replace(" ", "_").lower(),
                "policy": {
                    "returns_days": rng.choice([7, 10, 14, 30]),
                    "warranty_months": rng.choice([6, 12, 24]),
                    "structured": True,
                },
                "fulfilment": {
                    "serviceable_pincodes": PINCODES,
                    "ships_in_days": rng.choice([1, 2, 4, 7]),
                },
            })
    return catalog


def required_attributes(category):
    return list(CATEGORIES[category]["required"])
