"""Bayesian estimation upgrade for the forced-choice distributions (NEXT_EXPERIMENT_DESIGN
"Estimation Upgrade").

A 20-100 sample empirical distribution is noisy, especially per cell. The design asks for a
hierarchical multinomial model whose headline estimates replace the raw empirical vector. The
full Bayesian hierarchical model needs PyMC/numpyro, which are not installed here. This module
delivers the tractable, dependency-free core:

  * a Dirichlet-multinomial CONJUGATE posterior per cell (smoothing + credible intervals);
  * EMPIRICAL-BAYES PARTIAL POOLING across cells in a group (each cell shrinks toward the group
    mean by an amount set by its sample size) — the practical effect of a hierarchical prior
    without MCMC;
  * a posterior on the representation score itself.

When PyMC/numpyro are available, `hierarchical_posteriors` is the seam to swap in a full
partial-pooling multinomial; the conjugate path stays as the documented baseline.
"""
from __future__ import annotations

from collections import Counter
from typing import Mapping, Optional, Sequence

import numpy as np

# Jeffreys prior (alpha = 0.5 per option) — a mild, standard default for a multinomial.
DEFAULT_PRIOR = 0.5


def counts_from_canonicals(canonicals: Sequence[Optional[int]], n_options: int) -> np.ndarray:
    """Count selected canonical options (None = unparseable, dropped) into a length-n vector."""
    c: Counter = Counter(x for x in canonicals if x is not None)
    return np.array([c.get(i, 0) for i in range(n_options)], dtype=float)


def counts_from_distribution(dist: Sequence[float], n_valid: int) -> np.ndarray:
    """Reconstruct integer-ish counts from a stored probability vector and its valid-sample count
    (lets the estimator run on an existing artifact that kept dist + parse diagnostics but not the
    raw answers)."""
    return np.round(np.asarray(dist, dtype=float) * n_valid)


def posterior_alpha(counts: Sequence[float], prior_alpha=DEFAULT_PRIOR) -> np.ndarray:
    """Dirichlet posterior concentration = prior + observed counts (conjugacy)."""
    counts = np.asarray(counts, dtype=float)
    prior = np.asarray(prior_alpha, dtype=float)
    if prior.ndim == 0:
        prior = np.full(counts.shape, float(prior))
    return prior + counts


def posterior_mean(counts: Sequence[float], prior_alpha=DEFAULT_PRIOR) -> np.ndarray:
    a = posterior_alpha(counts, prior_alpha)
    return a / a.sum()


def _dirichlet_draws(alpha: np.ndarray, draws: int, seed: Optional[int]) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.dirichlet(alpha, size=draws)


def credible_interval(counts: Sequence[float], prior_alpha=DEFAULT_PRIOR, level: float = 0.95,
                      draws: int = 4000, seed: Optional[int] = 0):
    """Per-option central credible interval from posterior Dirichlet draws."""
    a = posterior_alpha(counts, prior_alpha)
    samples = _dirichlet_draws(a, draws, seed)
    lo = (1 - level) / 2 * 100
    hi = (1 + level) / 2 * 100
    return np.percentile(samples, lo, axis=0), np.percentile(samples, hi, axis=0)


def estimate_cell(counts: Sequence[float], prior_alpha=DEFAULT_PRIOR, level: float = 0.95,
                  draws: int = 4000, seed: Optional[int] = 0) -> dict:
    """Posterior summary for one model-item-mode cell."""
    counts = np.asarray(counts, dtype=float)
    lo, hi = credible_interval(counts, prior_alpha, level, draws, seed)
    return {
        "mean": posterior_mean(counts, prior_alpha).round(4).tolist(),
        "ci_low": lo.round(4).tolist(),
        "ci_high": hi.round(4).tolist(),
        "n": int(counts.sum()),
    }


def pooled_prior(counts_list: Sequence[Sequence[float]], strength: float = 4.0) -> np.ndarray:
    """Empirical-Bayes prior: the group's grand-mean distribution scaled by a pseudo-count
    `strength`. Used as the Dirichlet prior for each cell so small-n cells shrink toward the
    group — the partial-pooling effect of a hierarchical model, computed in closed form."""
    mat = np.array([np.asarray(c, dtype=float) for c in counts_list], dtype=float)
    per_cell = mat / np.clip(mat.sum(axis=1, keepdims=True), 1e-9, None)
    grand = per_cell.mean(axis=0)
    grand = grand / grand.sum()
    return strength * grand


def estimate_group(cells: Mapping[str, Sequence[float]], strength: float = 4.0,
                   level: float = 0.95, draws: int = 4000, seed: Optional[int] = 0) -> dict:
    """Partial-pooled posteriors for a group of cells (e.g. all items for one model+mode).

    The empirical-Bayes prior is shared across the group; each cell's posterior shrinks toward
    the group mean in inverse proportion to its sample size."""
    prior = pooled_prior(list(cells.values()), strength)
    return {key: estimate_cell(counts, prior, level, draws, seed) for key, counts in cells.items()}


def representation_posterior(counts: Sequence[float], target: Sequence[float],
                            prior_alpha=DEFAULT_PRIOR, level: float = 0.95,
                            draws: int = 4000, seed: Optional[int] = 0) -> dict:
    """Posterior on the representation score 1 - TV(model, public): propagate the Dirichlet
    posterior through the metric so the headline number carries a credible interval, not just a
    point estimate."""
    a = posterior_alpha(counts, prior_alpha)
    target = np.asarray(target, dtype=float)
    samples = _dirichlet_draws(a, draws, seed)
    rep = 1.0 - 0.5 * np.abs(samples - target).sum(axis=1)
    lo = (1 - level) / 2 * 100
    hi = (1 + level) / 2 * 100
    return {
        "mean": float(rep.mean()),
        "ci_low": float(np.percentile(rep, lo)),
        "ci_high": float(np.percentile(rep, hi)),
    }


def hierarchical_posteriors(cells: Mapping[str, Sequence[float]], **kwargs) -> dict:
    """Headline estimator. Currently the empirical-Bayes partial-pooling approximation
    (`estimate_group`). HOOK: when PyMC/numpyro are installed, replace the body with a full
    hierarchical multinomial (random effects on item and paraphrase) and keep this signature."""
    return estimate_group(cells, **kwargs)
