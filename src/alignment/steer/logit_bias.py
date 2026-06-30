"""Steering rung 2: logit-bias calibration (logprobs research direction, RQ2).

Where Tier 1/2 steer through the *prompt*, this rung steers the *logits*: an API `logit_bias` adds a
constant b_i to each option-number token's logit before the softmax. Because the first-token option
distribution is p_i ∝ exp(logit_i), adding b_i gives

    q_i  ∝  p_i · exp(b_i)        i.e.   q = softmax(log p + b)

So calibrating a *single* item is closed-form and trivial: to map p onto a target t, set
b_i = log t_i − log p_i (up to an additive constant — softmax is shift-invariant). The interesting
scientific question is therefore NOT per-item fit but **generalisation**: fit ONE position-bias
vector shared across a set of items (a common ordinal scale), then ask whether it moves *held-out*
items toward the public too. It can only do so if the model's miss is systematic — a directional
prior the public corrects. That is exactly what `fit_shared_bias` estimates.

Honesty caveat (carried from Tier 2): a bias fit on an item and scored on the same item is circular.
The number that matters is held-out representation gain, and the rights-floor margin must not shrink
under the shared nudge. The experiment driver owns that split; this module is the pure math.

Pure numpy, no network — the same fail-loud-not-NaN discipline as the elicitor (zeros are floored,
never silently dropped).
"""
from __future__ import annotations

import numpy as np

from alignment.instrument import scorers as S


def _logsumexp(x: np.ndarray) -> float:
    m = float(np.max(x))
    return m + float(np.log(np.sum(np.exp(x - m))))


def _norm(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    s = v.sum()
    return v / s if s > 0 else np.full_like(v, 1.0 / len(v))


def apply_bias(p: np.ndarray, b: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Apply a logit-bias vector `b` to an option distribution `p`: returns softmax(log p + b),
    equivalently p·exp(b) renormalised. This is exactly what an API `logit_bias` on the option-number
    tokens does to the first-token option distribution. `p` is floored at `eps` (an option the model
    gives zero mass can't be reached by a finite bias — it stays ~0, surfaced rather than crashing)."""
    p = _norm(p)
    z = np.log(np.clip(p, eps, None)) + np.asarray(b, dtype=float)
    z = z - _logsumexp(z)
    return np.exp(z)


def exact_item_bias(p: np.ndarray, t: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Closed-form per-item bias mapping `p` exactly onto target `t`: b_i = log t_i − log p_i,
    returned mean-zero (the shift-invariant representative). Single-item calibration is exact and
    trivial; use `fit_shared_bias` for the generalisable, research-relevant version."""
    p, t = _norm(p), _norm(t)
    b = np.log(np.clip(t, eps, None)) - np.log(np.clip(p, eps, None))
    return b - b.mean()


def _mean_kl(T: np.ndarray, Q: np.ndarray, eps: float) -> float:
    return float(np.mean([S.kl_divergence(T[k], Q[k], eps) for k in range(len(T))]))


def fit_shared_bias(ps, ts, lr: float = 0.5, iters: int = 5000, tol: float = 1e-10,
                    eps: float = 1e-12, return_history: bool = False):
    """Fit ONE position-bias vector `b` shared across items, minimising Σ_k KL(t_k ‖ softmax(log p_k + b)).

    Items must share an aligned ordinal option structure (same length, same meaning per position) —
    e.g. a common 1–4 Likert scale. The objective is convex (a sum of log-sum-exp terms), so plain
    gradient descent converges; gradient_i = Σ_k (q_{k,i} − t_{k,i}). At the optimum Σ_k q_k = Σ_k t_k:
    a shared bias matches the panel's AVERAGE target marginal, not each item — which is precisely the
    'is the model's miss a systematic, correctable prior?' test.

    Returns the mean-zero `b` (and, if `return_history`, the per-iteration mean-KL trace)."""
    P = np.array([_norm(p) for p in ps], dtype=float)
    T = np.array([_norm(t) for t in ts], dtype=float)
    if P.shape != T.shape:
        raise ValueError(f"ps and ts must align: got {P.shape} vs {T.shape}")
    b = np.zeros(P.shape[1])
    hist: list[float] = []
    for _ in range(iters):
        Q = np.array([apply_bias(P[k], b, eps) for k in range(len(P))])
        if return_history:
            hist.append(_mean_kl(T, Q, eps))
        grad = (Q - T).sum(axis=0)
        if np.linalg.norm(grad) < tol:
            break
        b = b - lr * grad / len(P)
        b = b - b.mean()
    return (b, hist) if return_history else b


if __name__ == "__main__":
    # exact single-item calibration is a closed-form round-trip
    p = np.array([0.45, 0.30, 0.15, 0.10])
    t = np.array([0.10, 0.20, 0.40, 0.30])
    b = exact_item_bias(p, t)
    print("exact round-trip:", np.round(apply_bias(p, b), 3).tolist(), "== target", t.tolist())

    # shared bias across three items with the SAME systematic miss -> recovers it
    ps = [p, np.array([0.5, 0.25, 0.15, 0.10]), np.array([0.40, 0.35, 0.15, 0.10])]
    ts = [t, np.array([0.12, 0.18, 0.40, 0.30]), np.array([0.08, 0.22, 0.40, 0.30])]
    bs, hist = fit_shared_bias(ps, ts, return_history=True)
    print("shared bias:", np.round(bs, 3).tolist())
    print("mean KL: %.4f -> %.4f" % (hist[0], hist[-1]))
