"""Phase 2 activation-steering pure logic: the diff-of-means direction, the safe-operating-point
selection, and the layer/verdict helpers. No mlx required — the model-touching code is smoke-tested
live, this pins the math and decision logic.
"""
import numpy as np
import pytest

from alignment.steer import activation_steer as A
from alignment import activation_steering_run as R
from alignment.instrument import scorers as S


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


# ---- R1 held-out capture: k-fold split -----------------------------------------------

def test_kfold_indices_partition_is_disjoint_and_complete():
    folds = A.kfold_test_indices(16, 4, seed=0)
    assert len(folds) == 4
    allidx = np.concatenate(folds)
    assert sorted(allidx.tolist()) == list(range(16))     # covers every index exactly once
    seen = set()
    for f in folds:
        s = set(int(i) for i in f)
        assert not (s & seen)                              # folds pairwise disjoint
        seen |= s


def test_kfold_indices_deterministic_under_seed():
    a = A.kfold_test_indices(16, 4, seed=7)
    b = A.kfold_test_indices(16, 4, seed=7)
    c = A.kfold_test_indices(16, 4, seed=8)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))     # same seed -> identical folds
    assert not all(np.array_equal(x, y) for x, y in zip(a, c)) # different seed -> different split


def test_kfold_train_and_test_never_overlap():
    n, k = 16, 4
    folds = A.kfold_test_indices(n, k, seed=3)
    for test in folds:
        test_set = set(int(i) for i in test)
        train_set = set(range(n)) - test_set
        assert not (train_set & test_set)                  # the capture/eval item sets are disjoint
        assert train_set | test_set == set(range(n))       # ...and together the full item set


def test_kfold_rejects_bad_k():
    with pytest.raises(ValueError):
        A.kfold_test_indices(4, 1, seed=0)                 # k < 2
    with pytest.raises(ValueError):
        A.kfold_test_indices(4, 5, seed=0)                 # k > n


# ---- R1 held-out capture: per-item gains ---------------------------------------------

def test_held_out_gains_are_steered_minus_baseline_over_shared_items():
    base = {"a": 0.50, "b": 0.60, "c": 0.70}
    steer = {"a": 0.62, "b": 0.55, "c": 0.80}
    gains = sorted(A.held_out_gains(base, steer))
    assert np.allclose(gains, [-0.05, 0.10, 0.12])


def test_held_out_gains_drops_items_that_broke_at_either_dose():
    base = {"a": 0.50, "b": 0.60}                          # 'c' broke at baseline
    steer = {"a": 0.62, "c": 0.90}                         # 'b' broke when steered
    gains = A.held_out_gains(base, steer)
    assert gains == [pytest.approx(0.12)]                  # only 'a' survives both


# ---- R1 held-out capture: pooled gain CI (scorers.bootstrap_mean_ci) ------------------

def test_bootstrap_mean_ci_reports_mean_and_brackets_it():
    vals = [0.05, 0.10, 0.15, 0.08, 0.12]
    out = S.bootstrap_mean_ci(vals, B=1000, seed=0)
    assert out["n"] == 5
    assert out["mean"] == pytest.approx(np.mean(vals))
    assert out["ci"][0] <= out["mean"] <= out["ci"][1]     # CI brackets the point estimate


def test_bootstrap_mean_ci_deterministic_under_seed():
    vals = [0.2, -0.1, 0.3, 0.0]
    assert S.bootstrap_mean_ci(vals, B=500, seed=1) == S.bootstrap_mean_ci(vals, B=500, seed=1)


def test_bootstrap_mean_ci_positive_sample_clears_zero():
    out = S.bootstrap_mean_ci([0.20, 0.25, 0.30, 0.22, 0.28], B=2000, seed=0)
    assert out["ci"][0] > 0.0                               # tight positive sample -> CI above zero


def test_bootstrap_mean_ci_empty_is_none():
    out = S.bootstrap_mean_ci([], B=100, seed=0)
    assert out == {"mean": None, "ci": None, "n": 0}


# ---- R1 held-out capture: per-layer summary + gate -----------------------------------

def _holdout_layer_stub(base, per_alpha):
    """Minimal holdout_dose_response-shaped dict for one layer (bypasses mlx)."""
    rows = [{"alpha": 0.0, "held_out_reps": base, "floor_masses": [0.8, 0.8],
             "n_contestable_ok": len(base), "n_contestable_broke": 0,
             "n_floor_ok": 2, "n_floor_broke": 0}]
    for a, reps, floors in per_alpha:
        rows.append({"alpha": a, "held_out_reps": reps, "floor_masses": floors,
                     "n_contestable_ok": len(reps), "n_contestable_broke": 0,
                     "n_floor_ok": len(floors), "n_floor_broke": 0})
    return {"k": 4, "n_orders": 4, "seed": 0, "folds": [], "per_alpha": rows}


def test_summarize_holdout_survives_when_gain_clears_zero_and_floor_holds():
    base = {f"i{j}": 0.50 for j in range(8)}
    up = {f"i{j}": 0.65 for j in range(8)}                  # +0.15 on every item, tight -> CI>0
    ho = _holdout_layer_stub(base, [(4.0, up, [0.8, 0.8])])
    summ = R._summarize_holdout_layer(ho, floor_min=0.5, B=2000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 4.0][0]
    assert row["gain_ci_clears_zero"] is True
    assert row["floor_holds"] is True
    assert row["survives"] is True
    assert summ["survives"] is True
    assert summ["best_surviving_alpha"] == 4.0


def test_summarize_holdout_killed_when_gain_straddles_zero():
    base = {f"i{j}": 0.50 for j in range(8)}
    noisy = {f"i{j}": 0.50 + (0.2 if j % 2 else -0.2) for j in range(8)}  # mean ~0, CI straddles
    ho = _holdout_layer_stub(base, [(4.0, noisy, [0.8, 0.8])])
    summ = R._summarize_holdout_layer(ho, floor_min=0.5, B=2000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 4.0][0]
    assert row["gain_ci_clears_zero"] is False
    assert row["survives"] is False
    assert summ["survives"] is False


def test_summarize_holdout_gain_up_but_floor_broken_does_not_survive():
    base = {f"i{j}": 0.50 for j in range(8)}
    up = {f"i{j}": 0.70 for j in range(8)}
    ho = _holdout_layer_stub(base, [(4.0, up, [0.30, 0.30])])   # floor mass < 0.5
    summ = R._summarize_holdout_layer(ho, floor_min=0.5, B=2000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 4.0][0]
    assert row["gain_ci_clears_zero"] is True
    assert row["floor_holds"] is False
    assert row["survives"] is False


def test_summarize_holdout_requires_baseline_alpha():
    ho = {"k": 4, "n_orders": 4, "seed": 0, "folds": [],
          "per_alpha": [{"alpha": 4.0, "held_out_reps": {"a": 0.6}, "floor_masses": [0.8],
                         "n_contestable_ok": 1, "n_contestable_broke": 0,
                         "n_floor_ok": 1, "n_floor_broke": 0}]}
    with pytest.raises(ValueError):
        R._summarize_holdout_layer(ho, floor_min=0.5, B=100, seed=0)


# ---- R2 random-direction control: matched-norm random vector --------------------------

def test_random_direction_matches_requested_norm():
    v = A.random_direction(320, norm=2.5, seed=0)
    assert v.shape == (320,)
    assert np.linalg.norm(v) == pytest.approx(2.5, rel=1e-6)


def test_random_direction_deterministic_under_seed():
    assert np.allclose(A.random_direction(64, 1.0, seed=4), A.random_direction(64, 1.0, seed=4))
    assert not np.allclose(A.random_direction(64, 1.0, seed=4), A.random_direction(64, 1.0, seed=5))


def test_random_direction_rejects_negative_norm():
    with pytest.raises(ValueError):
        A.random_direction(8, norm=-1.0, seed=0)


def test_random_direction_zero_norm_is_zero_vector():
    v = A.random_direction(16, norm=0.0, seed=1)
    assert np.linalg.norm(v) == pytest.approx(0.0)


# ---- R2 random-direction control: curve gain + comparison -----------------------------

def _curve(alpha_rep_floor):
    return [{"alpha": a, "representation": r, "floor_mass": f} for a, r, f in alpha_rep_floor]


def test_curve_gain_is_relative_to_alpha_zero():
    c = _curve([(0, 0.60, 0.8), (2, 0.70, 0.7), (4, 0.55, 0.6)])
    g = R._curve_gain(c)
    assert g["baseline"] == 0.60
    assert g["gains"][2.0] == pytest.approx(0.10)
    assert g["gains"][4.0] == pytest.approx(-0.05)


def test_curve_gain_omits_broken_alphas():
    c = _curve([(0, 0.60, 0.8), (2, 0.70, 0.7)]) + [{"alpha": 8, "representation": None, "floor_mass": None}]
    g = R._curve_gain(c)
    assert 8.0 not in g["gains"]
    assert set(g["gains"]) == {0.0, 2.0}


def test_randctrl_flags_real_above_every_random_draw():
    real = _curve([(0, 0.60, 0.8), (2, 0.80, 0.7)])          # real gain +0.20
    rand = [_curve([(0, 0.60, 0.8), (2, 0.63, 0.75)]),       # random gains +0.03, +0.05
            _curve([(0, 0.60, 0.8), (2, 0.65, 0.75)])]
    comp = R._randctrl_comparison(real, rand)
    row = [r for r in comp if r["alpha"] == 2.0][0]
    assert row["real_rep_gain"] == pytest.approx(0.20)
    assert row["random_rep_gain_max"] == pytest.approx(0.05)
    assert row["real_exceeds_random"] is True


def test_randctrl_flags_real_within_random_noise():
    real = _curve([(0, 0.60, 0.8), (2, 0.64, 0.7)])          # real gain +0.04
    rand = [_curve([(0, 0.60, 0.8), (2, 0.66, 0.75)]),       # a random draw does better (+0.06)
            _curve([(0, 0.60, 0.8), (2, 0.62, 0.75)])]
    comp = R._randctrl_comparison(real, rand)
    row = [r for r in comp if r["alpha"] == 2.0][0]
    assert row["real_exceeds_random"] is False               # within perturbation noise


# ---- R3 negative dose: antisymmetry report -------------------------------------------

def test_antisymmetry_flags_concept_like_axis():
    # +alpha raises representation, -alpha lowers it -> concept-direction signature
    curve = _curve([(-2, 0.50, 0.8), (0, 0.60, 0.8), (2, 0.70, 0.7)])
    rep = R.antisymmetry_report(curve)
    assert rep["antisymmetric"] is True
    p = rep["pairs"][0]
    assert p["gain_pos"] == pytest.approx(0.10)
    assert p["gain_neg"] == pytest.approx(-0.10)
    assert p["concept_like"] is True


def test_antisymmetry_rejects_symmetric_perturbation():
    # both +alpha and -alpha LOWER representation -> a norm perturbation, not an axis
    curve = _curve([(-2, 0.55, 0.8), (0, 0.60, 0.8), (2, 0.54, 0.7)])
    rep = R.antisymmetry_report(curve)
    assert rep["antisymmetric"] is False
    p = rep["pairs"][0]
    assert p["concept_like"] is False
    assert p["opposite_signs"] is False                      # both negative gains


def test_antisymmetry_pairs_only_matched_magnitudes():
    # -1 has no +1 partner; only |2| is a complete pair
    curve = _curve([(-2, 0.5, 0.8), (-1, 0.55, 0.8), (0, 0.6, 0.8), (2, 0.7, 0.7)])
    rep = R.antisymmetry_report(curve)
    assert rep["n_pairs"] == 1
    assert rep["pairs"][0]["alpha"] == 2.0


def test_antisymmetry_requires_baseline():
    with pytest.raises(ValueError):
        R.antisymmetry_report(_curve([(-2, 0.5, 0.8), (2, 0.7, 0.7)]))


def test_antisymmetry_preserves_negative_alpha_sign_no_abs():
    # if negatives were abs()'d, -2 and +2 would collapse to one point and pairing would vanish;
    # distinct gains on the two sides prove the sign is carried through, not folded.
    curve = _curve([(-2, 0.40, 0.8), (0, 0.60, 0.8), (2, 0.72, 0.7)])
    p = R.antisymmetry_report(curve)["pairs"][0]
    assert p["gain_neg"] != p["gain_pos"]                    # sign-distinct, not abs-folded
    assert p["gain_neg"] < 0 < p["gain_pos"]


# ---- R4 error bars: CI-based per-(layer, alpha) verdict --------------------------------

def _seed_items(alpha_to_reps, alpha_to_masses):
    """A dose_response_items-shaped dict for one seed."""
    return {float(a): {"reps": dict(reps), "masses": list(alpha_to_masses[a]),
                       "broke_c": 0, "broke_f": 0}
            for a, reps in alpha_to_reps.items()}


def test_ci_layer_good_steer_when_gain_and_floor_cis_hold():
    base = {f"i{j}": 0.50 for j in range(8)}
    up = {f"i{j}": 0.66 for j in range(8)}                    # +0.16 every item, tight -> gain CI>0
    seed = _seed_items({0.0: base, 4.0: up},
                       {0.0: [0.8] * 6, 4.0: [0.75] * 6})       # floor CI well above 0.5
    summ = R.summarize_ci_layer([seed, seed], floor_min=0.5, B=2000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 4.0][0]
    assert row["gain_ci_clears_zero"] is True
    assert row["floor_ci_above_min"] is True
    assert "good steer" in row["verdict"]
    assert summ["good_steer"] is True
    assert summ["best_alpha"] == 4.0


def test_ci_layer_bad_steer_when_floor_ci_dips():
    base = {f"i{j}": 0.50 for j in range(8)}
    up = {f"i{j}": 0.70 for j in range(8)}
    seed = _seed_items({0.0: base, 4.0: up},
                       {0.0: [0.8] * 6, 4.0: [0.30] * 6})       # floor CI below 0.5
    summ = R.summarize_ci_layer([seed], floor_min=0.5, B=2000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 4.0][0]
    assert row["gain_ci_clears_zero"] is True
    assert row["floor_ci_above_min"] is False
    assert "bad steer" in row["verdict"]
    assert summ["good_steer"] is False


def test_ci_layer_no_steer_when_gain_straddles_zero():
    base = {f"i{j}": 0.50 for j in range(8)}
    noisy = {f"i{j}": 0.50 + (0.2 if j % 2 else -0.2) for j in range(8)}   # mean ~0
    seed = _seed_items({0.0: base, 4.0: noisy}, {0.0: [0.8] * 6, 4.0: [0.8] * 6})
    summ = R.summarize_ci_layer([seed], floor_min=0.5, B=2000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 4.0][0]
    assert row["gain_ci_clears_zero"] is False
    assert "no steer" in row["verdict"]


def test_ci_layer_pools_gain_over_items_and_seeds_paired_to_baseline():
    # two seeds, gain is +0.10 for every (item, seed) -> pooled gain mean 0.10, n = items*seeds
    base = {"a": 0.40, "b": 0.60}
    up = {"a": 0.50, "b": 0.70}
    s1 = _seed_items({0.0: base, 2.0: up}, {0.0: [0.8], 2.0: [0.8]})
    s2 = _seed_items({0.0: base, 2.0: up}, {0.0: [0.8], 2.0: [0.8]})
    summ = R.summarize_ci_layer([s1, s2], floor_min=0.5, B=1000, seed=0)
    row = [r for r in summ["per_alpha"] if r["alpha"] == 2.0][0]
    assert row["gain"]["mean"] == pytest.approx(0.10)
    assert row["gain"]["n"] == 4                              # 2 items x 2 seeds, paired to baseline


def test_ci_layer_requires_baseline_alpha():
    seed = _seed_items({2.0: {"a": 0.6}}, {2.0: [0.8]})
    with pytest.raises(ValueError):
        R.summarize_ci_layer([seed], floor_min=0.5, B=100, seed=0)


def test_ci_layer_requires_at_least_one_seed():
    with pytest.raises(ValueError):
        R.summarize_ci_layer([], floor_min=0.5, B=100, seed=0)


# ---- W3 arrow geometry: cosine helpers ------------------------------------------------

def test_cosine_matrix_identity_and_orthogonality():
    arrows = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    C = A.cosine_matrix(arrows)
    assert C[0, 0] == pytest.approx(1.0)
    assert C[0, 1] == pytest.approx(1.0)          # identical directions
    assert C[0, 2] == pytest.approx(0.0)          # orthogonal
    assert np.allclose(C, C.T)                     # symmetric


def test_cosine_matrix_zero_row_is_zero_not_nan():
    arrows = np.array([[0.0, 0.0], [1.0, 1.0]])
    C = A.cosine_matrix(arrows)
    assert not np.isnan(C).any()
    assert C[0, 1] == pytest.approx(0.0)


def test_cosine_matrix_rejects_non_2d():
    with pytest.raises(ValueError):
        A.cosine_matrix(np.array([1.0, 2.0, 3.0]))


def test_within_cross_domain_separates_aligned_clusters():
    # two domains; arrows within a domain are identical, across domains orthogonal
    arrows = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    domains = ["a", "a", "b", "b"]
    out = A.within_cross_domain_cosine(arrows, domains)
    assert out["within_mean"] == pytest.approx(1.0)   # same-domain arrows aligned
    assert out["cross_mean"] == pytest.approx(0.0)     # cross-domain arrows orthogonal
    assert out["within_n"] == 2 and out["cross_n"] == 4


def test_within_cross_domain_length_mismatch_raises():
    with pytest.raises(ValueError):
        A.within_cross_domain_cosine(np.zeros((3, 2)), ["a", "b"])


def test_cosine_to_mean_high_when_aligned_low_when_divergent():
    aligned = np.array([[1.0, 0.0], [1.0, 0.01], [1.0, -0.01]])
    assert A.cosine_to_mean(aligned)["mean"] > 0.99    # all point ~same way -> mean represents them

    # opposing pairs: the mean cancels toward zero and represents no arrow well
    divergent = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]])
    out = A.cosine_to_mean(divergent)
    assert out["mean_arrow_norm"] == pytest.approx(0.0)  # mean washes out
    assert out["mean"] == pytest.approx(0.0)


def test_cosine_to_mean_rejects_non_2d():
    with pytest.raises(ValueError):
        A.cosine_to_mean(np.array([1.0, 2.0]))


def test_diff_of_means_equals_mean_of_item_arrows():
    # capture_direction == mean of the per-item arrows capture_item_directions returns
    default = np.array([[0.0, 0.0], [1.0, 2.0], [3.0, 1.0]])
    persona = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    arrows = persona - default
    assert np.allclose(A.diff_of_means(default, persona), arrows.mean(axis=0))


# ---- R7 off-task coherence: exact-match scoring ---------------------------------------

def test_off_task_match_finds_answer_token_amid_prose():
    assert R.off_task_match("The answer is 45.", "45") is True
    assert R.off_task_match("Paris is the capital.", "paris") is True
    assert R.off_task_match("BLUE", "blue") is True


def test_off_task_match_is_token_level_not_substring():
    assert R.off_task_match("The answer is 17.", "7") is False    # '7' must not match inside '17'
    assert R.off_task_match("42", "2") is False


def test_off_task_match_rejects_wrong_answer():
    assert R.off_task_match("London", "paris") is False
    assert R.off_task_match("", "45") is False
    assert R.off_task_match("I am not sure about that", "45") is False


def test_off_task_match_case_and_punctuation_insensitive():
    assert R.off_task_match("  tokyo!!! ", "Tokyo") is True
    assert R.off_task_match("Earth.", "earth") is True


def test_off_task_probes_are_well_formed():
    # the hardcoded probe set: 10 items, each with a prompt and a normalisable expected answer
    assert len(R.OFF_TASK_PROBES) == 10
    for p in R.OFF_TASK_PROBES:
        assert p["prompt"] and p["expected"]
        assert R.off_task_match(p["expected"], p["expected"])   # expected matches itself


# ---- R8 wrong-persona control: control persona is clearly irrelevant ------------------

def test_control_persona_is_irrelevant_and_distinct():
    from alignment.steer import tier1_prompt as T1
    real = T1.persona("GBR", 2024).lower()
    ctrl = R.CONTROL_PERSONA.lower()
    assert ctrl and ctrl != real                              # a distinct persona string
    assert "1850" in ctrl and "farmer" in ctrl                # clearly irrelevant to UK-2024 opinion
    assert "2024" not in ctrl and "great britain" not in ctrl
