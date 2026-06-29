"""Policy-layer provenance consistency (NEXT_EXPERIMENT_DESIGN acceptance test #8).

The active UK policy layer is microdata-built. These tests guard against provenance drift:
no active source or item may claim to be synthetic, the active target artifacts must say
`microdata_built`, and the distributions they carry must be well-formed. They are the durable
version of the design's success criterion "no target source is mislabeled synthetic/real".
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCES = ROOT / "data" / "policy_targets" / "SOURCES.json"
POLICY_ITEMS = ROOT / "data" / "policy_items.jsonl"
REGIONAL_TARGETS = ROOT / "out" / "public_opinion_regions" / "targets.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _iter_items():
    for line in POLICY_ITEMS.read_text().splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def test_active_policy_sources_are_not_synthetic():
    sources = _load(POLICY_SOURCES)["sources"]
    for name, src in sources.items():
        if src.get("active") is False or src.get("status") == "not_built":
            continue  # legacy/unbuilt sources may remain, but must be flagged inactive
        # An active, real source must declare real data and a microdata-built status.
        assert src.get("real_available") is True, f"{name}: active source not marked real_available"
        assert src.get("status") == "microdata_built", f"{name}: active source not microdata_built"


def test_policy_items_carry_no_synthetic_claim():
    # The item definitions hold no distributions; none may imply a synthetic placeholder target,
    # which would contradict the microdata-built active layer.
    for item in _iter_items():
        note = (item.get("license_note") or "").lower()
        assert "synthetic" not in note, f"{item['id']}: stale synthetic claim in license_note"


def test_floor_probes_scaled_and_well_formed():
    floors = [it for it in _iter_items() if it.get("class") == "floor"]
    assert len(floors) >= 10, "design calls for 10-15 floor probes before external claims"
    pressures = set()
    for f in floors:
        assert f["floor_dir"] in (1, -1), f"{f['id']}: floor_dir must be +1/-1"
        assert f.get("floor_role") in ("treatment", "control"), f"{f['id']}: bad floor_role"
        assert len(f["scale"]["labels"]) == len(f["scale"]["coded"]), f"{f['id']}: label/code mismatch"
        if f.get("pressure_type"):
            pressures.add(f["pressure_type"])
    # both AI-mechanism treatments and non-AI controls exist (the AI-reflex control group)
    roles = {f["floor_role"] for f in floors}
    assert {"treatment", "control"} <= roles
    # all five tradeoff-pressure families from the design are represented
    assert {"efficiency", "security", "popularity", "scarcity", "accountability"} <= pressures


def test_floor_probes_have_2nd_person_signoff():
    # the floor directions have been through the independent (2nd-person) review
    floors = [it for it in _iter_items() if it.get("class") == "floor"]
    assert floors
    assert all(it.get("review") == "rights_floor_2nd_person" for it in floors)
    assert all(it.get("reviewed_by") for it in floors)
    # accepted directions clear needs_review; any still-flagged item must carry a reviewer note
    for it in floors:
        if it.get("needs_review"):
            assert it.get("review_note"), f"{it['id']}: flagged but no review_note"
        else:
            assert it.get("reviewed") is True, f"{it['id']}: not flagged but not marked reviewed"


def test_legacy_uk_public_bsa_is_flagged_inactive():
    legacy = _load(POLICY_SOURCES)["sources"].get("legacy_uk_public_bsa")
    assert legacy is not None
    assert legacy.get("active") is False
    assert legacy.get("real_available") is False


@pytest.mark.skipif(not REGIONAL_TARGETS.exists(), reason="regional BSA targets not built")
def test_regional_target_artifact_is_microdata_built():
    targets = _load(REGIONAL_TARGETS)
    assert targets.get("status") == "microdata_built"
    assert "synthetic" not in json.dumps(targets).lower()


@pytest.mark.skipif(not REGIONAL_TARGETS.exists(), reason="regional BSA targets not built")
def test_regional_distributions_are_wellformed():
    # Usable series must carry a proper probability vector; unusable cells (e.g. an empty
    # Scotland module) must be flagged, not silently presented as a usable distribution.
    targets = _load(REGIONAL_TARGETS)
    for iid, item in targets["items"].items():
        for series in item["series"]:
            tag = f"{iid}/{series.get('polity')}/{series.get('year')}"
            dist = series["distribution"]
            labels = series["labels"]
            assert len(dist) == len(labels), f"{tag}: dist/label length mismatch"
            assert "n_unweighted" in series, f"{tag}: missing unweighted base"
            if series.get("usable", True):
                assert abs(sum(dist) - 1.0) < 1e-6, f"{tag}: usable distribution does not sum to 1"
            else:
                # an unusable cell must declare itself: no valid base and a visible warning
                assert series.get("base_warning"), f"{tag}: unusable series has no base_warning"
