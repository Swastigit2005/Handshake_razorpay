"""The readiness scan: find catalogue defects, price them, prove the repair."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from handshake.config import RunConfig                                # noqa: E402
from handshake.merchant.catalog import (build_catalog, inject_defects,  # noqa: E402
                                        repair, required_attributes)
from handshake.readiness.audit import audit, by_field, readiness_score  # noqa: E402
from handshake.readiness.scan import scan                             # noqa: E402


def _flawed(rate=0.25):
    clean = build_catalog(20260830)
    return clean, inject_defects(clean, rate=rate, seed=20260830)


# ---------------- audit ----------------

def test_a_clean_catalogue_has_no_blocking_defects():
    clean = build_catalog(20260830)
    found = audit(clean)
    assert not [d for d in found if d["kind"] == "missing_attribute"]
    assert not [d for d in found if d["kind"] == "variant_collision"]


def test_out_of_stock_is_advisory_not_a_defect():
    """It is withheld from the feed, so it refuses nothing. Counting it as a
    data defect would inflate the score's denominator dishonestly."""
    clean = build_catalog(20260830)
    found = audit(clean)
    assert all(d["advisory"] for d in found), \
        "a clean catalogue should raise advisories only"
    assert readiness_score(clean, found) == 100.0


def test_the_audit_finds_what_was_planted():
    clean, (flawed, planted) = _flawed()
    found = audit(flawed)
    planted_keys = {(d["kind"], d["sku"]) for d in planted}
    found_keys = {(d["kind"], d["sku"]) for d in found}
    missed = planted_keys - found_keys
    assert not missed, f"inspection failed to find planted defects: {missed}"


def test_every_defect_names_the_field_to_fix():
    _, (flawed, _) = _flawed()
    for defect in audit(flawed):
        assert defect["field"], defect
        assert defect["severity"], defect


def test_defects_roll_up_to_fields():
    _, (flawed, _) = _flawed()
    rolled = by_field(audit(flawed))
    assert rolled
    assert all(row["sku_count"] == len(row["skus"]) for row in rolled)


def test_readiness_score_falls_when_the_catalogue_is_broken():
    clean, (flawed, _) = _flawed(rate=0.5)
    assert readiness_score(clean, audit(clean)) > readiness_score(flawed, audit(flawed))


# ---------------- repair ----------------

def test_repair_restores_the_named_listings_only():
    clean, (flawed, planted) = _flawed()
    target = next(d for d in planted if d["kind"] == "missing_attribute")
    fixed = repair(flawed, clean, {target["sku"]})
    record = next(p for p in fixed if p["sku"] == target["sku"])
    assert target["field"] in record["attributes"]

    untouched = [d for d in planted
                 if d["kind"] == "missing_attribute" and d["sku"] != target["sku"]]
    for other in untouched:
        rec = next(p for p in fixed if p["sku"] == other["sku"])
        assert other["field"] not in rec["attributes"], "repair leaked to another SKU"


def test_repair_removes_a_colliding_duplicate():
    clean, (flawed, planted) = _flawed()
    collisions = [d for d in planted if d["kind"] == "variant_collision"]
    if not collisions:
        return
    target = collisions[0]["sku"]
    assert any(p["sku"] == target + "-B" for p in flawed)
    fixed = repair(flawed, clean, {target})
    assert not any(p["sku"] == target + "-B" for p in fixed)


# ---------------- the scan end to end ----------------

def test_scan_prices_defects_and_proves_the_repair():
    report = scan(sessions=200, defect_rate=0.25)

    assert report["defects_found"], "a flawed catalogue must produce defects"
    assert report["priced"], "defects must be priced in rupees"
    assert all(row["at_risk"] > 0 for row in report["priced"])

    # the proof: repairing the ranked defects converts more of the same buyers
    assert report["after"]["converted"] > report["before"]["converted"]
    assert report["delta"]["revenue_gained"] > 0
    assert report["delta"]["sessions_recovered"] > 0


def test_scan_is_reproducible():
    a = scan(sessions=150, defect_rate=0.25)
    b = scan(sessions=150, defect_rate=0.25)
    assert a["delta"] == b["delta"]
    assert a["readiness_score"] == b["readiness_score"]


def test_a_clean_catalogue_leaves_almost_nothing_to_fix():
    report = scan(sessions=150, defect_rate=0.0)
    assert report["readiness_score"] == 100.0
    assert report["delta"]["revenue_gained"] == 0


def test_non_catalogue_causes_are_reported_separately(monkeypatch):
    """A spending-cap breach is the buyer's budget, not a feed defect. Filing it
    under a catalogue defect would misdirect the merchant's fix."""
    from handshake.readiness.scan import NOT_CATALOGUE, _price

    rows = [
        {"state": "failed", "value": 1000.0, "cause": "A1",
         "sku": "AUD-001", "field": "codec_support", "defect": "missing_attribute"},
        {"state": "failed", "value": 2000.0, "cause": "A4", "sku": "AUD-002",
         "field": "", "defect": ""},
        {"state": "failed", "value": 500.0, "cause": "UNKNOWN", "sku": "",
         "field": "", "defect": ""},
        {"state": "converted", "value": 900.0, "cause": "", "sku": "", "field": ""},
    ]
    catalogue, other = _price(rows)

    assert [r["defect"] for r in catalogue] == ["missing_attribute"]
    assert catalogue[0]["field"] == "codec_support"
    assert {r["cause"] for r in other} == {"A4", "UNKNOWN"}
    assert all(r["reason"] for r in other), "each must say why it is not a defect"
    assert sum(r["at_risk"] for r in other) == 2500.0
    assert "A4" in NOT_CATALOGUE


def test_the_scan_reports_both_buckets():
    report = scan(sessions=200, defect_rate=0.25)
    assert "non_catalogue" in report
    assert all("defect" in row for row in report["priced"])
    for row in report["priced"]:
        assert row["field"], "a catalogue defect must name the field to fix"
