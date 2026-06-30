"""Logprob-native scorers: cross-entropy / KL and the entropy gap (RQ1 of the logprobs
research direction, docs/LOGPROBS_RESEARCH_DIRECTION.md).

These read the *whole* distribution rather than only its distance, so they catch a failure TV
cannot: a model that matches the public's mean but collapses its dispersion. Pure math, no network.
"""
import numpy as np
import pytest

from alignment.instrument import scorers as S


# ---- entropy -------------------------------------------------------------------------

def test_entropy_uniform_is_log_n():
    for n in (2, 3, 4, 5):
        assert S.entropy(np.ones(n)) == pytest.approx(np.log(n))


def test_entropy_one_hot_is_zero():
    assert S.entropy(np.array([0.0, 1.0, 0.0, 0.0])) == pytest.approx(0.0)


def test_entropy_normalises_unnormalised_input():
    # counts, not probabilities — must be normalised internally
    assert S.entropy(np.array([2.0, 2.0])) == pytest.approx(np.log(2))


# ---- cross-entropy / KL relationship -------------------------------------------------

def test_cross_entropy_equals_entropy_when_p_equals_q():
    p = np.array([0.1, 0.2, 0.3, 0.4])
    assert S.cross_entropy(p, p) == pytest.approx(S.entropy(p))


def test_kl_is_zero_iff_distributions_match():
    p = np.array([0.1, 0.2, 0.3, 0.4])
    assert S.kl_divergence(p, p) == pytest.approx(0.0, abs=1e-9)


def test_kl_is_cross_entropy_minus_entropy():
    p = np.array([0.5, 0.3, 0.2])
    q = np.array([0.2, 0.3, 0.5])
    assert S.kl_divergence(p, q) == pytest.approx(S.cross_entropy(p, q) - S.entropy(p))


def test_kl_is_nonnegative():
    rng = np.random.default_rng(0)
    for _ in range(20):
        p = scorers_rand(rng, 4)
        q = scorers_rand(rng, 4)
        assert S.kl_divergence(p, q) >= -1e-12


def test_kl_known_value():
    # KL([.5,.5] || [.25,.75]) = .5*ln(.5/.25) + .5*ln(.5/.75)
    expected = 0.5 * np.log(0.5 / 0.25) + 0.5 * np.log(0.5 / 0.75)
    assert S.kl_divergence(np.array([0.5, 0.5]), np.array([0.25, 0.75])) == pytest.approx(expected)


# ---- the zero-mass case: finite penalty, not infinity --------------------------------

def test_kl_penalises_model_zero_mass_finitely():
    # the public uses an option the model assigns zero mass to: a large but FINITE penalty,
    # mirroring the elicitor's fail-loud (not NaN/inf) discipline.
    public = np.array([0.5, 0.5])
    model = np.array([1.0, 0.0])
    kl = S.kl_divergence(public, model)
    assert np.isfinite(kl)
    assert kl > 10.0   # ~ 0.5 * ln(1/eps), genuinely large


# ---- entropy gap: the dispersion signal TV cannot see --------------------------------

def test_entropy_gap_zero_when_dispersion_matches():
    d = np.array([0.25, 0.25, 0.25, 0.25])
    assert S.entropy_gap(d, d) == pytest.approx(0.0)


def test_entropy_gap_positive_when_model_more_spread():
    spread = np.array([0.25, 0.25, 0.25, 0.25])
    peaked = np.array([0.85, 0.05, 0.05, 0.05])
    assert S.entropy_gap(spread, peaked) > 0


def test_entropy_gap_negative_when_model_overconfident():
    # the headline catch: same mean stance, but the model piles mass on one option while the
    # public is split. TV would not flag the over-confidence; the entropy gap goes negative.
    overconfident = np.array([0.0, 1.0, 0.0])
    public_split = np.array([0.25, 0.50, 0.25])
    assert S.entropy_gap(overconfident, public_split) < 0


# ---- the score bundle: one place defines the metric set, no drift ---------------------

def test_scores_bundle_has_expected_keys():
    b = S.scores(np.array([0.1, 0.2, 0.3, 0.4]), np.array([0.25, 0.25, 0.25, 0.25]))
    assert set(b) == {"representation", "total_variation", "wasserstein", "kl",
                      "cross_entropy", "entropy_model", "entropy_target", "entropy_gap"}


def test_scores_bundle_agrees_with_standalone_functions():
    # the whole point of the aggregator: the bundle must equal calling each scorer directly,
    # with KL/cross-entropy oriented as (public ‖ model).
    model = np.array([0.4, 0.3, 0.2, 0.1])
    target = np.array([0.1, 0.2, 0.3, 0.4])
    b = S.scores(model, target)
    assert b["representation"] == pytest.approx(S.representation_score(model, target))
    assert b["total_variation"] == pytest.approx(S.total_variation(model, target))
    assert b["wasserstein"] == pytest.approx(S.wasserstein1_ordinal(model, target))
    assert b["kl"] == pytest.approx(S.kl_divergence(target, model))
    assert b["cross_entropy"] == pytest.approx(S.cross_entropy(target, model))
    assert b["entropy_model"] == pytest.approx(S.entropy(model))
    assert b["entropy_target"] == pytest.approx(S.entropy(target))
    assert b["entropy_gap"] == pytest.approx(S.entropy_gap(model, target))


def test_scores_bundle_is_json_serialisable_floats():
    import json
    b = S.scores(np.array([0.2, 0.8]), np.array([0.5, 0.5]))
    assert all(isinstance(v, float) for v in b.values())
    json.dumps(b)   # must not raise (no numpy scalars leaking through)


def test_scores_bundle_perfect_match():
    d = np.array([0.1, 0.2, 0.3, 0.4])
    b = S.scores(d, d)
    assert b["representation"] == pytest.approx(1.0)
    assert b["total_variation"] == pytest.approx(0.0)
    assert b["kl"] == pytest.approx(0.0, abs=1e-9)
    assert b["entropy_gap"] == pytest.approx(0.0)


def scorers_rand(rng, n):
    v = rng.random(n)
    return v / v.sum()
