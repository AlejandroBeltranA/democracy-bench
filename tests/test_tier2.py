"""Tier 2 preference injection: the conditioning carries the distribution, and Tier 2 lands
representation at least as high as Tier 1 (a richer signal than a bare label)."""
import pytest

from alignment import compare_tiers
from alignment.steer import tier2_preference as T2

ITEM = {"id": "x", "source": {"var": "Q"}, "prompt_text": "Q?",
        "scale": {"labels": ["a", "b", "c", "d"]}}


def test_preference_string_injects_percentages_and_marker():
    s = T2.preference("Great Britain", 2022, ITEM, [0.1, 0.2, 0.3, 0.4])
    assert "were distributed approximately" in s        # the marker the sims key on
    assert "a 10%" in s and "d 40%" in s
    assert "2022" in s and "Great Britain" in s


def test_preference_rejects_length_mismatch():
    with pytest.raises(ValueError):
        T2.preference("X", 2022, ITEM, [0.5, 0.5])      # 2 != 4 options


def test_tier2_beats_or_matches_tier1_and_both_beat_default():
    r = compare_tiers.run(country="GBR", wave=7, model=None, n_samples=500)
    assert "SIMULATED" in r["mode"]
    for cid, c in r["items"].items():
        assert c["rep_tier1"] >= c["rep_default"] - 0.02, f"{cid}: tier1 below default"
        assert c["rep_tier2"] >= c["rep_tier1"] - 0.02, f"{cid}: tier2 below tier1"
    # Tier 2 should give a clear lift over default for at least one item (the demo's point)
    assert any(c["rep_tier2"] - c["rep_default"] > 0.05 for c in r["items"].values())
