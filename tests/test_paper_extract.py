"""Numpy-only tests for the pure extraction/formatting helpers in
scripts/extract_paper_results.py (PS1).

These test the fail-loud contract (a missing key raises MissingKey with the
named key, never a silent default) and the small formatting helpers. They do
NOT touch MLX or the real artifacts' model runs — only the extractor's logic.
"""
import importlib.util
import os

import numpy as np
import pytest

# Load the script as a module (it lives in scripts/, not on the package path).
_SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "extract_paper_results.py",
)
_spec = importlib.util.spec_from_file_location("extract_paper_results", _SPEC_PATH)
epr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(epr)


# ---------------------------------------------------------------------------
# dig(): fail-loud path navigation
# ---------------------------------------------------------------------------
def test_dig_reads_nested_dict():
    obj = {"a": {"b": {"c": 42}}}
    assert epr.dig(obj, ["a", "b", "c"]) == 42


def test_dig_reads_list_index():
    obj = {"xs": [{"v": 1}, {"v": 2}]}
    assert epr.dig(obj, ["xs", 1, "v"]) == 2


def test_dig_negative_index_ok():
    assert epr.dig({"xs": [10, 20, 30]}, ["xs", -1]) == 30


def test_dig_missing_key_raises_named():
    with pytest.raises(epr.MissingKey) as exc:
        epr.dig({"a": {"b": 1}}, ["a", "c"], artifact="foo.json")
    msg = str(exc.value)
    assert "'c'" in msg
    assert "foo.json" in msg


def test_dig_index_out_of_range_raises():
    with pytest.raises(epr.MissingKey) as exc:
        epr.dig({"xs": [1, 2]}, ["xs", 5], artifact="bar.json")
    assert "out of range" in str(exc.value)


def test_dig_type_mismatch_dict_expected():
    with pytest.raises(epr.MissingKey):
        epr.dig({"a": [1, 2]}, ["a", "b"])  # a is a list, cannot read key 'b'


def test_dig_type_mismatch_list_expected():
    with pytest.raises(epr.MissingKey):
        epr.dig({"a": {"x": 1}}, ["a", 0])  # a is a dict, cannot index 0


# ---------------------------------------------------------------------------
# _ci_clears_zero(): significance rule
# ---------------------------------------------------------------------------
def test_ci_clears_zero_positive():
    assert epr._ci_clears_zero(0.4, [0.02, 0.81]) is True


def test_ci_clears_zero_negative():
    assert epr._ci_clears_zero(-0.19, [-0.29, -0.086]) is True


def test_ci_straddles_zero_is_not_significant():
    assert epr._ci_clears_zero(0.019, [-0.020, 0.059]) is False


def test_ci_touching_zero_lower_bound_not_significant():
    # Lower bound exactly 0 does not clear zero (strict inequality).
    assert epr._ci_clears_zero(0.1, [0.0, 0.2]) is False


def test_ci_clears_zero_matches_manual_over_random_intervals():
    rng = np.random.default_rng(0)
    for _ in range(200):
        lo, hi = sorted(rng.uniform(-1, 1, size=2).tolist())
        manual = (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
        assert epr._ci_clears_zero((lo + hi) / 2, [lo, hi]) == manual


# ---------------------------------------------------------------------------
# stat(): stat-block extraction and fail-loud contract
# ---------------------------------------------------------------------------
def test_stat_flattens_block():
    obj = {"h": {"mean": 0.5, "ci": [0.4, 0.6], "n": 12}}
    s = epr.stat(obj, ["h"])
    assert s["mean"] == 0.5
    assert s["ci_lo"] == 0.4 and s["ci_hi"] == 0.6
    assert s["n"] == 12
    assert s["ci_clears_zero"] is True


def test_stat_missing_mean_raises():
    with pytest.raises(epr.MissingKey) as exc:
        epr.stat({"h": {"ci": [0.1, 0.2]}}, ["h"], artifact="x")
    assert "mean" in str(exc.value)


def test_stat_missing_ci_raises():
    with pytest.raises(epr.MissingKey) as exc:
        epr.stat({"h": {"mean": 0.5}}, ["h"], artifact="x")
    assert "ci" in str(exc.value)


def test_stat_malformed_ci_raises():
    with pytest.raises(epr.MissingKey):
        epr.stat({"h": {"mean": 0.5, "ci": [0.1]}}, ["h"])  # ci not length 2


def test_stat_n_defaults_to_none_not_zero():
    s = epr.stat({"h": {"mean": 0.0, "ci": [0.0, 0.0]}}, ["h"])
    assert s["n"] is None  # explicit None, never a silent 0


# ---------------------------------------------------------------------------
# find_layer / find_alpha / curve_point: fail-loud lookups
# ---------------------------------------------------------------------------
def test_find_layer_returns_match():
    per = [{"layer": 7, "v": 1}, {"layer": 11, "v": 2}]
    assert epr.find_layer(per, 11)["v"] == 2


def test_find_layer_missing_raises_with_available():
    with pytest.raises(epr.MissingKey) as exc:
        epr.find_layer([{"layer": 7}], 11, artifact="a")
    assert "[7]" in str(exc.value)


def test_find_alpha_returns_match():
    per = [{"alpha": 0.0}, {"alpha": 4.0, "gain": 0.1}]
    assert epr.find_alpha(per, 4.0)["gain"] == 0.1


def test_find_alpha_missing_raises():
    with pytest.raises(epr.MissingKey):
        epr.find_alpha([{"alpha": 0.0}], 4.0)


def test_curve_point_reads_field():
    curve = [{"alpha": 0.0, "representation": 0.69}, {"alpha": 4.0, "representation": 0.75}]
    assert epr.curve_point(curve, 4, "representation") == 0.75
    # int alpha argument is coerced to float for matching
    assert epr.curve_point(curve, 0, "representation") == 0.69


def test_curve_point_missing_field_raises():
    with pytest.raises(epr.MissingKey):
        epr.curve_point([{"alpha": 4.0}], 4, "representation")


# ---------------------------------------------------------------------------
# End-to-end: the real build must succeed and expose known headline numbers.
# (Reads committed artifacts read-only; no model run.)
# ---------------------------------------------------------------------------
def test_build_succeeds_and_has_all_claims():
    result = epr.build()
    for claim in ("phase1_logit_bias", "phase2_steering", "p2_fidelity",
                  "p3_tracking", "p4_floors", "p5_lora", "g1_guards"):
        assert claim in result, f"missing claim section {claim}"


def test_build_p3_elasticity_matches_artifact():
    result = epr.build()
    el = result["p3_tracking"]["numbers"]["elasticity"]
    # Flagship positive: mean +0.395, CI lower bound +0.020 (clears zero, barely).
    assert abs(el["mean"] - 0.3945785448359917) < 1e-9
    assert el["ci_clears_zero"] is True
    assert el["ci_lo"] > 0.0
    assert el["ci_lo"] < 0.03  # the "must not claim a big positive" lower bound


def test_build_p2_heterogeneity_matches_artifact():
    result = epr.build()
    n = result["p2_fidelity"]["numbers"]
    assert n["n_items_worse_with_evidence"] == 24
    assert n["n_items"] == 50
    assert abs(n["fidelity_gap"] - 0.2540182218447762) < 1e-9
    assert n["delta"]["ci_clears_zero"] is False  # lift is NOT significant


def test_build_p5_tracking_destroyed():
    result = epr.build()
    n = result["p5_lora"]["numbers"]
    # Tuned elasticity collapses to ~0 — the adapter destroyed P3's positive.
    assert n["tracking_tuned_elasticity"]["mean"] < 0.01
    assert n["offtask_tuned_accuracy"] == 0.0


def test_build_g1_provenance_backfires():
    result = epr.build()
    prov = result["g1_guards"]["numbers"]["arms"]["guard_provenance"]
    # provenance LOWERS hostile floor mass (delta negative, CI clears zero).
    assert prov["hostile_delta_vs_no_guard"]["mean"] < 0.0
    assert prov["hostile_delta_vs_no_guard"]["ci_clears_zero"] is True
    assert prov["baseline_degraded"] is True
