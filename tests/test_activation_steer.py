"""Phase 2 activation-steering pure logic: the diff-of-means direction, the safe-operating-point
selection, and the layer/verdict helpers. No mlx required — the model-touching code is smoke-tested
live, this pins the math and decision logic.
"""
import numpy as np
import pytest

from alignment.steer import activation_steer as A
from alignment import activation_steering_run as R


# ---- diff_of_means -------------------------------------------------------------------

def test_diff_of_means_is_persona_minus_default():
    default = np.array([[0.0, 0.0], [2.0, 2.0]])   # mean [1,1]
    persona = np.array([[1.0, 1.0], [3.0, 3.0]])   # mean [2,2]
    assert np.allclose(A.diff_of_means(default, persona), [1.0, 1.0])


def test_diff_of_means_rejects_mismatched_shapes():
    with pytest.raises(ValueError):
        A.diff_of_means(np.zeros((3, 2)), np.zeros((2, 2)))


# ---- pick_operating_point ------------------------------------------------------------

def _curve(rows):
    return [{"alpha": a, "representation": r, "floor_mass": f} for a, r, f in rows]


def test_operating_point_picks_highest_rep_among_floor_safe():
    curve = _curve([(0, 0.50, 0.80), (2, 0.70, 0.80), (4, 0.90, 0.30)])
    op = A.pick_operating_point(curve, floor_min=0.5)
    assert op["best"]["alpha"] == 2                 # alpha 4 has higher rep but breaches the floor
    assert op["best"]["representation"] == 0.70
    assert op["improved"] is True                   # 0.70 > baseline 0.50
    assert op["floor_limited"] is True              # a higher-rep alpha existed but was floor-unsafe


def test_operating_point_no_improvement_flat_curve():
    curve = _curve([(0, 0.60, 0.80), (2, 0.60, 0.80), (4, 0.59, 0.80)])
    op = A.pick_operating_point(curve, floor_min=0.5)
    assert op["improved"] is False
    assert op["floor_limited"] is False


def test_operating_point_skips_broken_rows():
    # high-alpha rows where the model broke carry representation None -> ignored, not crashing
    curve = _curve([(0, 0.55, 0.80), (2, 0.72, 0.80)]) + [
        {"alpha": 8, "representation": None, "floor_mass": None}]
    op = A.pick_operating_point(curve, floor_min=0.5)
    assert op["best"]["alpha"] == 2
    assert op["improved"] is True


def test_operating_point_raises_when_all_broken():
    curve = [{"alpha": 8, "representation": None, "floor_mass": None}]
    with pytest.raises(ValueError):
        A.pick_operating_point(curve)


def test_operating_point_handles_no_floor_items():
    # floor_mass None everywhere (no floor probes in this group) -> all rows count as safe
    curve = [{"alpha": 0, "representation": 0.5, "floor_mass": None},
             {"alpha": 2, "representation": 0.8, "floor_mass": None}]
    op = A.pick_operating_point(curve, floor_min=0.5)
    assert op["best"]["alpha"] == 2
    assert op["floor_limited"] is False


# ---- driver helpers ------------------------------------------------------------------

def test_default_layers_spread_within_range():
    layers = R._default_layers(28)                  # Llama-3.2-3B
    assert layers == sorted(set(layers))            # sorted, deduped
    assert all(0 < l < 28 for l in layers)
    assert 14 in layers                             # the middle is included


def test_verdict_reads_operating_point():
    good = {"improved": True, "floor_limited": False}
    bad = {"improved": False, "floor_limited": True}
    none = {"improved": False, "floor_limited": False}
    assert "good steer" in R._verdict(good)
    assert "bad steer" in R._verdict(bad)
    assert "no steer" in R._verdict(none)
