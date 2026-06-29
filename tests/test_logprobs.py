"""Direct option-logprob scoring (NEXT_EXPERIMENT_DESIGN step 7, estimation upgrade).

Scoring options from the model's first-token logprobs avoids making the temperature setting the
measurement target. These tests cover the pure logic with synthetic logprob maps — no network.
"""
import math

import numpy as np
import pytest

from alignment.instrument import measure as M

ITEM = {
    "id": "demo",
    "prompt_text": "Pick one.",
    "scale": {"labels": ["A", "B", "C", "D"]},
}


def _lp(p):
    """logprob of probability p."""
    return math.log(p)


def test_option_logprob_vector_normalises_over_option_tokens():
    # raw token probs 0.1/0.2/0.3/0.4 (+ an irrelevant token that must be ignored)
    top = {"1": _lp(0.1), "2": _lp(0.2), "3": _lp(0.3), "4": _lp(0.4), "the": _lp(0.05)}
    vec = M.option_logprob_vector(top, 4)
    assert np.allclose(vec, [0.1, 0.2, 0.3, 0.4], atol=1e-9)
    assert abs(vec.sum() - 1.0) < 1e-9


def test_option_logprob_vector_handles_token_variants_and_whitespace():
    # " 2", "3." and "(4" must still count for options 2, 3, 4
    top = {" 2": _lp(0.5), "3.": _lp(0.3), "(4": _lp(0.2)}
    vec = M.option_logprob_vector(top, 4)
    assert vec[0] == 0.0                 # option 1 absent
    assert np.allclose(vec[1:], [0.5, 0.3, 0.2], atol=1e-9)


def test_option_logprob_vector_fails_closed_when_no_option_token():
    with pytest.raises(M.ElicitationError):
        M.option_logprob_vector({"hello": _lp(0.9), "world": _lp(0.1)}, 4)


def test_elicit_item_logprobs_maps_display_back_to_canonical():
    # Fake logprob_fn that ALWAYS puts all mass on display position 0, regardless of order.
    # Averaged over several random orders, the mass should spread across canonical options —
    # exactly the position-debiasing the order-averaging is meant to provide.
    def always_first(prompt, n):
        v = np.zeros(n)
        v[0] = 1.0
        return v

    dist = M.elicit_item_logprobs(always_first, ITEM, n_orders=4, seed=7)
    assert abs(dist.sum() - 1.0) < 1e-9
    # more than one canonical option received mass because the displayed order varied
    assert np.count_nonzero(dist) > 1


def test_elicit_item_logprobs_recovers_a_clean_distribution_without_shuffle_noise():
    # logprob_fn that reports a fixed CANONICAL distribution, presented in display order.
    target = np.array([0.1, 0.2, 0.3, 0.4])

    def fn(prompt, n):
        # the prompt lists options in some display order; we must return DISPLAY-position probs.
        # Reconstruct the order from the option lines so the test mirrors real behaviour.
        order = _display_order_from_prompt(prompt, ITEM["scale"]["labels"])
        return np.array([target[c] for c in order])

    dist = M.elicit_item_logprobs(fn, ITEM, n_orders=6, seed=1)
    assert np.allclose(dist, target, atol=1e-9)


def _display_order_from_prompt(prompt, labels):
    """Recover the canonical index shown at each display position from a rendered prompt."""
    order = []
    for line in prompt.splitlines():
        line = line.strip()
        for ci, lab in enumerate(labels):
            if line.endswith(lab) and line[:2].strip().rstrip(".").isdigit():
                order.append(ci)
    return order
