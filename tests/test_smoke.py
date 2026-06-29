"""Smoke tests: the scorer math and the synthetic target files load + are well-formed.

These run with no model and no Inspect — they guard the instrument and the data wiring so
a broken scorer or a malformed target vector fails loudly instead of silently producing a
plausible-looking number.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from alignment.instrument import scorers

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "wvs_items.jsonl"
TARGETS = ROOT / "data" / "targets"
COUNTRIES = ["USA", "GBR"]
WAVES = [6, 7]


def load_items():
    return [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]


# ---- scorer math ---------------------------------------------------------------------

def test_total_variation_bounds():
    p = np.array([1.0, 0.0, 0.0, 0.0])
    q = np.array([0.0, 0.0, 0.0, 1.0])
    assert scorers.total_variation(p, p) == pytest.approx(0.0)
    assert scorers.total_variation(p, q) == pytest.approx(1.0)


def test_representation_perfect_match_is_one():
    t = np.array([0.1, 0.2, 0.4, 0.3])
    assert scorers.representation_score(t, t) == pytest.approx(1.0)


def test_wasserstein_respects_ordering():
    # moving mass one step costs less than moving it three steps
    base = np.array([1.0, 0.0, 0.0, 0.0])
    near = np.array([0.0, 1.0, 0.0, 0.0])
    far = np.array([0.0, 0.0, 0.0, 1.0])
    assert scorers.wasserstein1_ordinal(base, near) < scorers.wasserstein1_ordinal(base, far)


def test_tracking_detects_frozen_model():
    target_t = np.array([0.10, 0.20, 0.40, 0.30])
    target_t1 = np.array([0.05, 0.15, 0.35, 0.45])  # population moves up
    frozen = np.array([0.10, 0.20, 0.40, 0.30])  # model does not move
    out = scorers.tracking(frozen, frozen, target_t, target_t1)
    assert out["elasticity"] == pytest.approx(0.0, abs=1e-9)


def test_tracking_none_when_no_population_shift():
    t = np.array([0.25, 0.25, 0.25, 0.25])
    out = scorers.tracking(t, t, t, t)
    assert out["direction_match"] is None


def test_floor_violation_flags_less_protective_model():
    target = np.array([0.1, 0.2, 0.3, 0.4])
    worse = np.array([0.7, 0.2, 0.1, 0.0])  # mass on low (less protective) end
    out = scorers.floor_violation(worse, floor_dir=+1, target=target)
    assert out["violation"] is True


# ---- target data wiring --------------------------------------------------------------

def test_every_item_var_resolves_in_every_country_wave():
    items = load_items()
    assert items, "no items loaded"
    for c in COUNTRIES:
        for w in WAVES:
            target = json.loads((TARGETS / f"target_{c}_wave{w}.json").read_text())
            for it in items:
                var = it["source"]["var"]
                assert var in target, f"{var} missing in {c} wave{w}"
                vec = target[var]
                assert len(vec) == len(it["scale"]["labels"]), (
                    f"{var} in {c} w{w}: vector len {len(vec)} != "
                    f"{len(it['scale']['labels'])} labels"
                )
                assert abs(sum(vec) - 1.0) < 0.02, f"{c} w{w} {var} sums to {sum(vec):.3f}"


def test_floor_items_have_floor_dir():
    for it in load_items():
        if it["class"] == "floor":
            assert it.get("floor_dir") in (-1, 1), f"{it['id']} floor item lacks floor_dir"
