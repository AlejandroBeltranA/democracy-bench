"""Bayesian estimation upgrade (NEXT_EXPERIMENT_DESIGN step 7) — conjugate posteriors with
credible intervals and empirical-Bayes partial pooling, dependency-free."""
import numpy as np

from alignment import estimation as E


def test_counts_helpers():
    assert E.counts_from_canonicals([0, 0, 2, None, 1], 4).tolist() == [2, 1, 1, 0]
    # reconstruct counts from a stored distribution + valid count
    assert E.counts_from_distribution([0.5, 0.25, 0.25], 20).tolist() == [10, 5, 5]


def test_posterior_mean_smooths_toward_prior():
    # all 10 obs on option 0; Jeffreys prior keeps the other options non-zero
    mean = E.posterior_mean([10, 0, 0, 0])
    assert mean[0] > 0.8
    assert all(m > 0 for m in mean)
    assert abs(mean.sum() - 1.0) < 1e-9


def test_credible_interval_shrinks_with_more_data():
    lo_small, hi_small = E.credible_interval([4, 1], draws=6000, seed=1)
    lo_big, hi_big = E.credible_interval([400, 100], draws=6000, seed=1)
    width_small = (hi_small - lo_small)[0]
    width_big = (hi_big - lo_big)[0]
    assert width_big < width_small  # more samples -> tighter posterior


def test_estimate_cell_structure():
    cell = E.estimate_cell([6, 2, 2], draws=2000, seed=0)
    assert set(cell) == {"mean", "ci_low", "ci_high", "n"}
    assert cell["n"] == 10
    assert len(cell["mean"]) == 3
    for lo, m, hi in zip(cell["ci_low"], cell["mean"], cell["ci_high"]):
        assert lo <= m <= hi


def test_partial_pooling_shrinks_small_cells_toward_group():
    # a confident group leans to option 0; a tiny, noisy cell should be pulled toward it
    cells = {
        "big_a": [80, 10, 10],
        "big_b": [78, 12, 10],
        "tiny": [0, 1, 0],   # 1 observation on option 1
    }
    pooled = E.estimate_group(cells, strength=6.0, draws=2000, seed=0)
    unpooled_tiny = E.posterior_mean([0, 1, 0])  # Jeffreys only
    pooled_tiny = np.array(pooled["tiny"]["mean"])
    # pooling moves the tiny cell's option-0 mass UP toward the group (which favours option 0)
    assert pooled_tiny[0] > unpooled_tiny[0]


def test_representation_posterior_has_interval_around_point_estimate():
    counts = [2, 6, 2]
    target = [0.2, 0.6, 0.2]
    rep = E.representation_posterior(counts, target, draws=4000, seed=0)
    assert 0.0 <= rep["ci_low"] <= rep["mean"] <= rep["ci_high"] <= 1.0
    # posterior-mean representation should be reasonably high (counts match the target shape)
    assert rep["mean"] > 0.6


def test_hierarchical_hook_delegates_to_pooling():
    cells = {"x": [5, 5], "y": [1, 9]}
    a = E.hierarchical_posteriors(cells, draws=1000, seed=0)
    b = E.estimate_group(cells, draws=1000, seed=0)
    assert a["x"]["mean"] == b["x"]["mean"]
