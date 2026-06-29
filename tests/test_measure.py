"""Tests for the elicitor — especially the fail-closed guarantee (no uniform fallback)."""
import numpy as np
import pytest

from alignment.instrument import measure as M

ITEM = {"id": "t", "prompt_text": "Q?", "scale": {"labels": ["a", "b", "c", "d"]}}


def test_parse_choice_valid_and_invalid():
    assert M.parse_choice("3", 4) == 2
    assert M.parse_choice("I choose 1.", 4) == 0
    assert M.parse_choice("banana", 4) is None
    assert M.parse_choice("9", 4) is None  # out of range -> None, not clamped
    assert M.parse_choice(None, 4) is None


def test_distribution_recovers_frequencies():
    # 75% "3", 25% "4"
    seq = iter(["3"] * 6 + ["4"] * 2)
    dist = M.elicit_item_distribution(lambda _p: next(seq), ITEM, n_samples=8)
    assert dist == pytest.approx([0.0, 0.0, 0.75, 0.25])
    assert dist.sum() == pytest.approx(1.0)


def test_fails_closed_on_unreadable_answers():
    # the whole point: garbage must raise, NOT silently become uniform
    with pytest.raises(M.ElicitationError):
        M.elicit_item_distribution(lambda _p: "banana", ITEM, n_samples=8)


def test_fails_closed_respects_min_valid():
    # one valid answer out of many, but min_valid=5 required -> raise
    seq = iter(["3"] + ["nope"] * 9)
    with pytest.raises(M.ElicitationError):
        M.elicit_item_distribution(lambda _p: next(seq), ITEM, n_samples=10, min_valid=5)


def test_shuffle_debiases_first_option_position_bias():
    # a model with PURE position bias: it always picks the first DISPLAYED option ("1"),
    # regardless of meaning — exactly what a small model does.
    always_first = lambda _p: "1"
    # without shuffle, that concentrates entirely on canonical option 0 (the artifact):
    biased = M.elicit_item_distribution(always_first, ITEM, n_samples=40, shuffle=False)
    assert biased[0] == 1.0
    # with shuffle, the first slot lands on each canonical option ~equally -> spread out:
    debiased = M.elicit_item_distribution(always_first, ITEM, n_samples=400, shuffle=True, seed=0)
    assert debiased[0] < 0.45, "debiasing should spread first-option bias off option 0"
    assert max(debiased) < 0.45, f"expected ~uniform, got {debiased}"


def test_shuffle_preserves_a_genuine_preference():
    # a model that genuinely always prefers label 'c' (by content, wherever it appears)
    labels = ITEM["scale"]["labels"]
    def prefers_c(prompt: str) -> str:
        # find which displayed number maps to 'c'
        for line in prompt.splitlines():
            line = line.strip()
            if line[:2] in ("1.", "2.", "3.", "4.") and line.endswith(" c"):
                return line[0]
        return "1"
    dist = M.elicit_item_distribution(prefers_c, ITEM, n_samples=200, shuffle=True, seed=1)
    assert dist[labels.index("c")] > 0.95   # genuine preference survives shuffling


def test_conditioning_is_prepended():
    prompt = M.forced_choice_prompt(ITEM, conditioning="ACT AS X")
    assert prompt.startswith("ACT AS X")
    assert "Q?" in prompt
    # unconditioned prompt does not carry a persona
    assert not M.forced_choice_prompt(ITEM).startswith("ACT AS X")
