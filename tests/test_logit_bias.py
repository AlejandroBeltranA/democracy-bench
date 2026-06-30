"""Logit-bias calibration math (logprobs research direction, RQ2 rung 2).

The closed form q = softmax(log p + b) means single-item calibration is exact; the shared-bias fit
is the generalisable version. Pure math, no network.
"""
import numpy as np
import pytest

from alignment.steer import logit_bias as LB
from alignment.instrument import scorers as S


# ---- apply_bias ----------------------------------------------------------------------

def test_apply_zero_bias_is_identity():
    p = np.array([0.4, 0.3, 0.2, 0.1])
    assert np.allclose(LB.apply_bias(p, np.zeros(4)), p)


def test_apply_bias_matches_softmax_of_logp_plus_b():
    p = np.array([0.4, 0.3, 0.2, 0.1])
    b = np.array([0.5, -0.2, 0.0, 1.0])
    z = np.log(p) + b
    expected = np.exp(z) / np.exp(z).sum()
    assert np.allclose(LB.apply_bias(p, b), expected)


def test_apply_bias_is_shift_invariant():
    # adding a constant to every bias entry leaves the distribution unchanged (softmax property)
    p = np.array([0.4, 0.3, 0.2, 0.1])
    b = np.array([0.5, -0.2, 0.0, 1.0])
    assert np.allclose(LB.apply_bias(p, b), LB.apply_bias(p, b + 3.7))


def test_apply_bias_returns_normalised_vector():
    q = LB.apply_bias(np.array([0.7, 0.2, 0.1]), np.array([1.0, -1.0, 2.0]))
    assert q.sum() == pytest.approx(1.0)


# ---- exact_item_bias: closed-form single-item calibration ----------------------------

def test_exact_bias_round_trips_to_target():
    p = np.array([0.45, 0.30, 0.15, 0.10])
    t = np.array([0.10, 0.20, 0.40, 0.30])
    assert np.allclose(LB.apply_bias(p, LB.exact_item_bias(p, t)), t, atol=1e-9)


def test_exact_bias_is_mean_zero():
    b = LB.exact_item_bias(np.array([0.5, 0.3, 0.2]), np.array([0.2, 0.3, 0.5]))
    assert b.mean() == pytest.approx(0.0)


# ---- fit_shared_bias -----------------------------------------------------------------

def test_shared_bias_recovers_a_common_systematic_shift():
    # three items that all need the SAME correction -> the shared bias matches every one
    p = np.array([0.45, 0.30, 0.15, 0.10])
    t = np.array([0.10, 0.20, 0.40, 0.30])
    ps = [p, p, p]
    ts = [t, t, t]
    b = LB.fit_shared_bias(ps, ts)
    for pk, tk in zip(ps, ts):
        assert np.allclose(LB.apply_bias(pk, b), tk, atol=1e-4)


def test_shared_bias_matches_average_target_marginal():
    # the optimum condition: Σ_k apply_bias(p_k, b) == Σ_k t_k (a shared bias fixes the mean, not
    # each item). Verify the fitted bias drives the panel-average prediction onto the panel-average
    # target even when items differ.
    ps = [np.array([0.5, 0.3, 0.15, 0.05]),
          np.array([0.4, 0.35, 0.2, 0.05]),
          np.array([0.6, 0.25, 0.1, 0.05])]
    ts = [np.array([0.1, 0.2, 0.4, 0.3]),
          np.array([0.15, 0.25, 0.35, 0.25]),
          np.array([0.05, 0.2, 0.45, 0.3])]
    b = LB.fit_shared_bias(ps, ts)
    mean_pred = np.mean([LB.apply_bias(p, b) for p in ps], axis=0)
    mean_target = np.mean(ts, axis=0)
    assert np.allclose(mean_pred, mean_target, atol=1e-3)


def test_shared_bias_reduces_mean_kl():
    ps = [np.array([0.5, 0.3, 0.15, 0.05]),
          np.array([0.4, 0.35, 0.2, 0.05]),
          np.array([0.6, 0.25, 0.1, 0.05])]
    ts = [np.array([0.1, 0.2, 0.4, 0.3]),
          np.array([0.15, 0.25, 0.35, 0.25]),
          np.array([0.05, 0.2, 0.45, 0.3])]
    _, hist = LB.fit_shared_bias(ps, ts, return_history=True)
    assert hist[-1] < hist[0]                  # the fit improved agreement
    assert hist[-1] < 0.05                     # and got most of the way there


def test_shared_bias_improves_mean_representation():
    # the experiment-level claim in miniature: after the shared nudge, mean representation rises.
    ps = [np.array([0.5, 0.3, 0.15, 0.05]),
          np.array([0.4, 0.35, 0.2, 0.05]),
          np.array([0.6, 0.25, 0.1, 0.05])]
    ts = [np.array([0.1, 0.2, 0.4, 0.3]),
          np.array([0.15, 0.25, 0.35, 0.25]),
          np.array([0.05, 0.2, 0.45, 0.3])]
    b = LB.fit_shared_bias(ps, ts)
    before = np.mean([S.representation_score(p, t) for p, t in zip(ps, ts)])
    after = np.mean([S.representation_score(LB.apply_bias(p, b), t) for p, t in zip(ps, ts)])
    assert after > before


def test_fit_rejects_misaligned_shapes():
    with pytest.raises(ValueError):
        LB.fit_shared_bias([np.array([0.5, 0.5])], [np.array([0.3, 0.3, 0.4])])
