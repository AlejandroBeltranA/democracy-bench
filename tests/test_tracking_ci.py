"""Confidence intervals on tracking: SEs propagate, CIs bracket the point estimate, and a
population that didn't really move is flagged (so tiny deltas aren't over-read)."""
import numpy as np
import pytest

from alignment.instrument import scorers as S

# population moves clearly up; model partially follows.
T_T = np.array([0.10, 0.20, 0.40, 0.30])
T_T1 = np.array([0.05, 0.15, 0.35, 0.45])
M_T = np.array([0.10, 0.20, 0.40, 0.30])
M_T1 = np.array([0.08, 0.17, 0.38, 0.37])


def test_no_n_means_no_ci_but_still_has_elasticity():
    out = S.tracking(M_T, M_T1, T_T, T_T1)
    assert out["elasticity"] is not None
    assert out["elasticity_ci"] is None
    assert out["population_delta_se"] is None


def test_ci_present_and_brackets_elasticity_when_n_given():
    out = S.tracking(M_T, M_T1, T_T, T_T1, n_model=300, n_target_t=2000, n_target_t1=2000)
    lo, hi = out["elasticity_ci"]
    assert lo < out["elasticity"] < hi
    assert out["population_delta_se"] > 0
    assert out["model_delta_se"] > 0


def test_more_samples_tighten_the_interval():
    def width(n):
        o = S.tracking(M_T, M_T1, T_T, T_T1, n_model=n, n_target_t=n, n_target_t1=n)
        lo, hi = o["elasticity_ci"]
        return hi - lo
    assert width(5000) < width(200)


def test_population_nonshift_is_flagged_not_significant():
    # population barely moves relative to its sampling error -> flagged, elasticity unstable
    flat_t = np.array([0.25, 0.25, 0.25, 0.25])
    flat_t1 = np.array([0.252, 0.249, 0.25, 0.249])
    out = S.tracking(M_T, M_T1, flat_t, flat_t1, n_model=300, n_target_t=2000, n_target_t1=2000)
    assert out["population_delta_significant"] is False


def test_real_population_shift_is_significant():
    out = S.tracking(M_T, M_T1, T_T, T_T1, n_model=300, n_target_t=2000, n_target_t1=2000)
    assert out["population_delta_significant"] is True
