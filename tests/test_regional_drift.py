"""Regional drift scores models against extracted England and Scotland public targets."""
import pytest

from alignment import public_opinion as PO
from alignment import regional_drift


def _require_microdata():
    missing = PO.missing_source_files()
    if missing:
        pytest.skip(f"BSA/SSA microdata not present: {missing[0]}")


def test_comparable_items_are_built_from_public_opinion_targets():
    _require_microdata()
    items = regional_drift.comparable_items(PO.extract_targets())
    ids = {it["id"] for it in items}
    assert {"tax_spend", "nhs_satisfaction", "governing_britain"}.issubset(ids)


def test_regional_drift_scores_closer_region():
    _require_microdata()
    report = regional_drift.run(models=None, n_samples=300, targets=PO.extract_targets())
    assert report["mode"] == "simulated"
    assert len(report["items"]) >= 3
    closer = {
        model["closer_to"]
        for item in report["items"].values()
        for model in item["models"].values()
    }
    assert "England" in closer
    assert "Scotland" in closer
