"""BSA/SSA extraction: weighted regional targets and England-vs-Scotland comparisons."""
from pathlib import Path

import pytest

from alignment import public_opinion as PO


def _require_microdata():
    missing = PO.missing_source_files()
    if missing:
        pytest.skip(f"BSA/SSA microdata not present: {missing[0]}")


def test_public_opinion_inventory_has_configured_variables():
    _require_microdata()
    inv = PO.build_dataset_inventory()
    assert "ENG_BSA_2024" in inv["datasets"]
    assert "SCO_SSA_2024" in inv["datasets"]
    for ds in inv["datasets"].values():
        assert not ds["missing_configured_vars"]


def test_extracts_weighted_targets_that_sum_to_one():
    _require_microdata()
    targets = PO.extract_targets()
    tax = targets["items"]["tax_spend"]
    latest = [s for s in tax["series"] if s["year"] == 2024]
    assert {s["polity"] for s in latest} == {"ENG", "SCO"}
    for s in latest:
        assert s["n_unweighted"] > 500
        assert abs(sum(s["distribution"]) - 1.0) < 1e-9


def test_computes_england_scotland_comparisons():
    _require_microdata()
    targets = PO.extract_targets()
    nhs = targets["items"]["nhs_satisfaction"]
    assert len(nhs["comparisons"]) >= 3
    latest = nhs["comparisons"][-1]
    assert latest["year"] == 2024
    assert latest["total_variation"] >= 0


def test_bsa_only_regional_config_extracts_england_scotland_wales():
    cfg = PO.load_config(PO.ROOT / "data" / "public_opinion_bsa_regions.json")
    missing = PO.missing_source_files(cfg)
    if missing:
        pytest.skip(f"BSA microdata not present: {missing[0]}")
    inv = PO.build_dataset_inventory(cfg)
    for ds in inv["datasets"].values():
        assert not ds["missing_configured_vars"]
    targets = PO.extract_targets(cfg)
    assert targets["base_size_thresholds"]["headline_min_unweighted_n"] == 300
    tax_2024 = [
        s for s in targets["items"]["tax_spend"]["series"]
        if s["year"] == 2024
    ]
    assert {s["polity"] for s in tax_2024} == {"ENG", "SCO", "WLS"}
    assert all(s["programme"] == "BSA" for s in tax_2024)
    comparisons = targets["items"]["tax_spend"]["comparisons"]
    latest_pairs = {c["pair"] for c in comparisons if c["year"] == 2024}
    assert latest_pairs == {
        "England vs Scotland",
        "England vs Wales",
        "Scotland vs Wales",
    }


def test_bsa_only_regional_targets_flag_low_n_and_skip_empty_comparisons():
    cfg = PO.load_config(PO.ROOT / "data" / "public_opinion_bsa_regions.json")
    missing = PO.missing_source_files(cfg)
    if missing:
        pytest.skip(f"BSA microdata not present: {missing[0]}")
    targets = PO.extract_targets(cfg)

    empty_tax = next(
        s for s in targets["items"]["tax_spend"]["series"]
        if s["dataset_id"] == "SCO_BSA_2023"
    )
    assert empty_tax["usable"] is False
    assert empty_tax["base_quality"] == "no_valid_responses"

    tax_comparisons_2023 = [
        c for c in targets["items"]["tax_spend"]["comparisons"]
        if c["year"] == 2023
    ]
    assert {c["pair"] for c in tax_comparisons_2023} == {"England vs Wales"}

    wales_gov = next(
        s for s in targets["items"]["governing_britain"]["series"]
        if s["dataset_id"] == "WLS_BSA_2024"
    )
    assert wales_gov["base_quality"] == "too_low"
    assert wales_gov["base_warning"]
    assert any(
        w["item"] == "governing_britain" and w["dataset_id"] == "WLS_BSA_2024"
        for w in targets["warnings"]
    )
