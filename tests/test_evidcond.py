"""Phase 3 P1: the item-loading path returns all 50 contestable items (any option count) plus
floor probes, and the option-count / distribution / evidence-line helpers generalise to 3-, 4-,
and 5-option items. Pure numpy-only tests — no MLX, no model run (that lives in `_smoke`)."""
import numpy as np
import pytest

from alignment import evidcond_run as E


# ---- pure helpers: option-count handling ---------------------------------------------

@pytest.mark.parametrize("n", [3, 4, 5])
def test_option_helpers_track_label_count(n):
    item = {"id": "x", "scale": {"labels": [f"L{i}" for i in range(n)]}}
    assert E.n_options(item) == n
    assert E.option_indices(item) == list(range(n))
    assert E.option_numbers(item) == list(range(1, n + 1))


def test_option_count_summary_counts_by_n_options():
    def si(n):
        return type("SI", (), {"item": {"scale": {"labels": ["x"] * n}}})()
    items = [si(5), si(5), si(4), si(3), si(3), si(3)]
    assert E.option_count_summary(items) == {5: 2, 4: 1, 3: 3}


# ---- pure helpers: distribution normalisation ----------------------------------------

@pytest.mark.parametrize("n", [3, 4, 5])
def test_normalise_distribution_sums_to_one(n):
    v = np.arange(1, n + 1, dtype=float)   # e.g. [1,2,3]
    d = E.normalise_distribution(v)
    assert d.shape == (n,)
    assert d.sum() == pytest.approx(1.0)
    assert np.all(d >= 0)


def test_normalise_distribution_degenerate_falls_back_to_uniform():
    d = E.normalise_distribution([0.0, 0.0, 0.0, 0.0])
    assert d.sum() == pytest.approx(1.0)
    assert np.allclose(d, 0.25)


def test_normalise_distribution_clips_negatives():
    d = E.normalise_distribution([-1.0, 2.0, 2.0])
    assert np.all(d >= 0)
    assert d.sum() == pytest.approx(1.0)
    assert d[0] == pytest.approx(0.0)


def test_normalise_distribution_rejects_bad_shape():
    with pytest.raises(ValueError):
        E.normalise_distribution([[0.5, 0.5]])
    with pytest.raises(ValueError):
        E.normalise_distribution([])


@pytest.mark.parametrize("n", [3, 4, 5])
def test_is_valid_distribution_accepts_spread_rejects_point_mass(n):
    spread = np.full(n, 1.0 / n)
    assert E.is_valid_distribution(spread)
    point = np.zeros(n)
    point[0] = 1.0
    assert not E.is_valid_distribution(point)          # degenerate: one option
    unnormalised = np.full(n, 1.0)
    assert not E.is_valid_distribution(unnormalised)   # sums to n, not 1


# ---- pure helpers: evidence-line assembly (Tier-2 style) ------------------------------

@pytest.mark.parametrize("n", [3, 4, 5])
def test_evidence_line_covers_every_option(n):
    labels = [f"opt{i}" for i in range(n)]
    item = {"id": "x", "scale": {"labels": labels}}
    dist = np.full(n, 1.0 / n)
    line = E.evidence_line(item, dist)
    for lab in labels:
        assert lab in line
    assert line.count("%") == n


def test_evidence_line_rejects_length_mismatch():
    item = {"id": "x", "scale": {"labels": ["a", "b", "c"]}}
    with pytest.raises(ValueError):
        E.evidence_line(item, [0.5, 0.5])              # 2 != 3 options


def test_evidence_line_normalises_before_stating():
    item = {"id": "x", "scale": {"labels": ["a", "b"]}}
    # counts, not probabilities -> normalised to 50/50
    assert E.evidence_line(item, [3.0, 3.0]) == "a: 50%, b: 50%"


# ---- the loader: all 50 contestable items + floors, correct split --------------------

def test_load_phase3_returns_full_bank_with_expected_split():
    bank = E.load_phase3(primary="ENG")
    contest = bank["contestable"]
    assert len(contest) == E.EXPECTED_CONTESTABLE == 50
    assert bank["option_counts"] == E.EXPECTED_OPTION_SPLIT == {5: 29, 4: 16, 3: 5}
    assert bank["matches_expected"] is True
    # every contestable item carries a public target; the loader keeps no option filter
    assert all(si.public is not None for si in contest)
    assert len(bank["floors"]) >= 10          # own-probe floor bank (>= design minimum)
    assert all(si.public is None for si in bank["floors"])


def test_load_phase3_includes_all_option_counts_phase2_dropped():
    """Phase 2's steering drivers filtered to n_options == 4 (16 items); Phase 3 must include the
    3- and 5-option items that filter dropped."""
    contest = E.load_phase3(primary="ENG")["contestable"]
    counts = {E.n_options(si.item) for si in contest}
    assert counts == {3, 4, 5}
    n5 = sum(1 for si in contest if E.n_options(si.item) == 5)
    n3 = sum(1 for si in contest if E.n_options(si.item) == 3)
    assert n5 == 29 and n3 == 5              # the items outside the 4-option filter
