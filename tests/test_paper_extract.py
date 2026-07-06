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
                  "p3_tracking", "p4_floors", "p5_lora", "g1_guards",
                  "model_robustness_8b", "cross_family_panel"):
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


# ---------------------------------------------------------------------------
# Phase 5 — 8B replication (model_robustness_8b). Bind every headline number the
# paper's robustness section quotes to its 8B artifact, matching the REP1/REP2
# Loop-log claims in docs/PHASE5_PLAN.md.
# ---------------------------------------------------------------------------
def test_build_8b_p2_fidelity_lift_replicates_ns():
    # P2 REPLICATES: evidence lift is n.s. on 8B too (CI straddles zero), with a
    # LARGER fidelity gap (0.288 vs 3B 0.254). The one non-replication is the
    # much stronger 8B baseline floor mass (0.707 vs 3B 0.512).
    n = epr.build()["model_robustness_8b"]["numbers"]["p2_fidelity"]
    assert n["n_items"] == 50
    assert abs(n["delta"]["mean"] - 0.013656357425916288) < 1e-9
    assert n["delta"]["ci_clears_zero"] is False  # lift NOT significant
    assert abs(n["fidelity_gap"] - 0.287998374134095) < 1e-9
    assert n["fidelity_gap"] > 0.254  # a LARGER gap than 3B (0.254)
    assert abs(n["floors_no_evidence"]["mean"] - 0.7073813427357586) < 1e-9
    assert n["floors_no_evidence"]["mean"] > 0.60  # stronger floor-holder than 3B's 0.512


def test_build_8b_p3_tracking_replicates():
    # P3 REPLICATES: 8/10 direction, elasticity CI clears zero (stronger, +0.647).
    n = epr.build()["model_robustness_8b"]["numbers"]["p3_tracking"]
    assert n["direction_match_count"] == 8
    assert n["direction_match_rate"] == 0.8
    assert n["n_model_moved"] == 10
    el = n["elasticity"]
    assert abs(el["mean"] - 0.646665653166407) < 1e-9
    assert el["ci_clears_zero"] is True
    assert el["ci_lo"] > 0.0
    assert el["mean"] > 0.395  # stronger than 3B's +0.395, CIs overlap heavily


def test_build_8b_p4_floor_crack_replicates_deeper():
    # P4 REPLICATES (deeper): 8B is a stronger baseline (0.707, 4/12 below) yet
    # hostile evidence cracks it to 0.074 (11/12 below), Δ−0.633 CI excludes 0 —
    # ~3x the 3B crack (−0.194).
    fl = epr.build()["model_robustness_8b"]["numbers"]["p4_floors"]
    assert abs(fl["baseline"]["floor_mass"]["mean"] - 0.7073813427357586) < 1e-9
    assert fl["baseline"]["n_below_floor"] == 4
    assert abs(fl["hostile_evidence"]["floor_mass"]["mean"] - 0.07429789938672533) < 1e-8
    assert fl["hostile_evidence"]["n_below_floor"] == 11
    dv = fl["hostile_evidence"]["delta_vs_baseline"]
    assert abs(dv["mean"] - (-0.6330834433490332)) < 1e-9
    assert dv["ci_clears_zero"] is True  # crack is significant
    assert dv["mean"] < -0.194  # deeper than the 3B crack (−0.194)


def test_build_8b_prompt_attack_channel_asymmetry_replicates():
    # Channel asymmetry REPLICATES (sharper): the adversarial PROMPT alone is n.s.
    # on 8B too (CI straddles zero), only 1/12 below floor.
    fl = epr.build()["model_robustness_8b"]["numbers"]["p4_floors"]
    adv = fl["adversarial_prompt"]
    assert adv["delta_vs_baseline"]["ci_clears_zero"] is False  # n.s.
    assert adv["n_below_floor"] == 1  # 1/12 (vs 3B's 8/12) — sharper asymmetry


def test_build_8b_guards_fail_but_recovery_is_genuine_per_probe():
    # G1 REPLICATES: both guards FAIL (neither reaches 0.45 partial bar, 8+/12
    # below). Nuance: on 8B recovery is SIGNIFICANT-positive AND genuine per-probe
    # (hostile TV RISES vs no_guard, i.e. NOT homogenised) — unlike 3B's canned collapse.
    g = epr.build()["model_robustness_8b"]["numbers"]["g1_guards"]
    ng_tv = g["arms"]["no_guard"]["hostile_mean_pairwise_tv"]
    for name in ("guard_rights_floor", "guard_constitution"):
        arm = g["arms"][name]
        assert arm["verdict"] == "fail"
        # significant-positive partial recovery (unlike 3B rights_floor n.s.)
        assert arm["hostile_delta_vs_no_guard"]["mean"] > 0.0
        assert arm["hostile_delta_vs_no_guard"]["ci_clears_zero"] is True
        # but still fails the 0.45 partial bar and leaves 8+/12 cracked
        assert arm["hostile_floor_mass"]["mean"] < 0.45
        assert arm["hostile_below_floor"] >= 8
        # genuine per-probe recovery: TV RISES (answers stay probe-specific)
        assert arm["hostile_mean_pairwise_tv"] > ng_tv


def test_build_8b_guard_rights_floor_recovery_ci():
    # Bind the headline rights_floor recovery CI (+0.297, CI clears 0).
    g = epr.build()["model_robustness_8b"]["numbers"]["g1_guards"]
    rf = g["arms"]["guard_rights_floor"]["hostile_delta_vs_no_guard"]
    assert abs(rf["mean"] - 0.2971180853415496) < 1e-9
    assert rf["ci_lo"] > 0.0 and rf["ci_hi"] > 0.0


def test_build_8b_guard_replication_check_is_cross_model_false():
    # The 8B guard artifact's replication_check compares 8B no_guard to the 3B P4
    # reference and is EXPECTEDLY within_tolerance=false (cross-model, not self-check).
    g = epr.build()["model_robustness_8b"]["numbers"]["g1_guards"]
    rc = g["replication_check"]
    assert rc["baseline_within_tolerance"] is False
    assert rc["hostile_within_tolerance"] is False
    # 8B self-consistency: guard-grid no_guard hostile == floors_8b hostile.
    fl = epr.build()["model_robustness_8b"]["numbers"]["p4_floors"]
    assert abs(rc["no_guard_hostile_floor_mass"]
               - fl["hostile_evidence"]["floor_mass"]["mean"]) < 1e-9


# ---------------------------------------------------------------------------
# Phase 5 REP4 — cross-family panel (cross_family_panel). Bind the per-family
# headline numbers the paper's robustness section quotes across FIVE families
# (Meta 3B/8B + Alibaba Qwen + Microsoft Phi + Google Gemma + Mistral-Nemo), and
# the honest coverage (one checkpoint dropped, with a recorded reason).
# ---------------------------------------------------------------------------
CF_TAGS = ("qwen7b", "phi4mini", "gemma9b", "mistralnemo")

# per-tag expected (direction_match_count, elasticity.mean, hostile_delta.mean)
_CF_EXPECT = {
    "qwen7b":      (7, 1.001936208776034,  -0.46281835799632337),
    "phi4mini":    (10, 2.4217894343784403, -0.441133533707528),
    "gemma9b":     (9, 1.408457747189643,  -0.5215991273441675),
    "mistralnemo": (9, 0.9270660115756721, -0.2373532216034462),
}


def test_build_has_cross_family_panel():
    result = epr.build()
    assert "cross_family_panel" in result
    cf = result["cross_family_panel"]
    assert set(cf["scored_models"]) == set(CF_TAGS)


def test_cross_family_tracking_positive_on_all():
    # Tracking is family-robust: direction match + elasticity CI clears zero on every
    # scored family across five model families.
    cf = epr.build()["cross_family_panel"]["scored_models"]
    for tag in CF_TAGS:
        exp_dir, exp_el, _ = _CF_EXPECT[tag]
        t = cf[tag]["numbers"]["p3_tracking"]
        assert t["direction_match_count"] == exp_dir and t["n_items"] == 10
        assert abs(t["elasticity"]["mean"] - exp_el) < 1e-9, tag
        assert t["elasticity"]["ci_clears_zero"] is True, tag


def test_cross_family_hostile_evidence_crack_on_all():
    # The hostile-evidence floor crack is family-robust: negative delta, CI clears 0
    # on every scored family.
    cf = epr.build()["cross_family_panel"]["scored_models"]
    for tag in CF_TAGS:
        _, _, exp_hostile = _CF_EXPECT[tag]
        d = cf[tag]["numbers"]["p4_floors"]["hostile_evidence"]["delta_vs_baseline"]
        assert abs(d["mean"] - exp_hostile) < 1e-9, tag
        assert d["mean"] < 0.0 and d["ci_clears_zero"] is True, tag


def test_cross_family_prompt_channel_never_cracks_floors():
    # The prompt-only channel never cracks floors: protective (positive) or n.s.,
    # never a significant NEGATIVE delta — mirroring the 3B/8B asymmetry.
    cf = epr.build()["cross_family_panel"]["scored_models"]
    for tag in CF_TAGS:
        d = cf[tag]["numbers"]["p4_floors"]["adversarial_prompt"]["delta_vs_baseline"]
        assert not (d["mean"] < 0.0 and d["ci_clears_zero"]), \
            f"{tag}: prompt-only produced a significant floor crack"


def test_cross_family_baseline_floor_strength_varies_but_crack_is_universal():
    # Baseline floor strength ranges widely (Phi strongest ~0.90, Mistral-Nemo weakest
    # ~0.36, below even the 3B's 0.512) yet the crack holds on all — the paper's point
    # that a strong baseline is not a safe evidence channel.
    cf = epr.build()["cross_family_panel"]["scored_models"]
    bases = {tag: cf[tag]["numbers"]["p4_floors"]["baseline"]["floor_mass"]["mean"]
             for tag in CF_TAGS}
    assert bases["phi4mini"] > 0.85          # strongest baseline holder
    assert bases["mistralnemo"] < 0.40       # weakest, below the 3B (0.512)
    assert max(bases.values()) - min(bases.values()) > 0.45  # wide spread


def test_cross_family_dropped_model_recorded_with_reason():
    # Coverage is honest, not silently truncated: the one dropped checkpoint carries a
    # reason. Gemma (a broken-cache artefact) and Mistral-Nemo were re-run and scored, so
    # only Mistral-7B-v0.3 (genuine fail-closed) remains dropped.
    cf = epr.build()["cross_family_panel"]
    dropped = {d["model"].split("/")[-1] for d in cf["dropped_models"]}
    assert dropped == {"Mistral-7B-Instruct-v0.3-4bit"}
    for d in cf["dropped_models"]:
        assert d["reason"].strip(), "dropped model must record WHY"
