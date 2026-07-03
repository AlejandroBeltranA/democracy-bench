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


# ---- P2 pure aggregation helpers -----------------------------------------------------

def test_representation_matches_scorer_and_normalises():
    """`representation` is 1 - TV against the target, normalising both vectors first — an exact
    match scores 1.0 regardless of whether the inputs are pre-normalised."""
    model = [2.0, 6.0, 2.0]          # un-normalised, proportional to [0.2,0.6,0.2]
    target = [0.2, 0.6, 0.2]
    assert E.representation(model, target) == pytest.approx(1.0)
    # a half-shifted distribution loses exactly the shifted mass
    assert E.representation([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_fidelity_gap_is_one_minus_representation():
    assert E.fidelity_gap(1.0) == pytest.approx(0.0)
    assert E.fidelity_gap(0.7) == pytest.approx(0.3)
    assert E.fidelity_gap(0.0) == pytest.approx(1.0)


def test_condition_summary_reports_mean_ci_n():
    reps = [0.5, 0.6, 0.7, 0.8]
    s = E.condition_summary(reps, seed=0)
    assert s["n"] == 4
    assert s["mean"] == pytest.approx(0.65)
    lo, hi = s["ci"]
    assert lo <= s["mean"] <= hi


def test_delta_summary_is_paired_itemwise():
    """The delta is per-item (evidence − no-evidence), so a constant +0.1 lift gives mean +0.1
    with a zero-width CI, not the difference of the two condition means computed separately."""
    no_ev = [0.4, 0.5, 0.6]
    ev = [0.5, 0.6, 0.7]
    d = E.delta_summary(no_ev, ev, seed=0)
    assert d["mean"] == pytest.approx(0.1)
    assert d["ci"][0] == pytest.approx(0.1) and d["ci"][1] == pytest.approx(0.1)


def test_delta_summary_rejects_misaligned_lists():
    with pytest.raises(ValueError):
        E.delta_summary([0.1, 0.2], [0.1], seed=0)


def test_delta_summary_sign_can_be_negative():
    """A negative delta (evidence made representation WORSE) is reported faithfully — the P2
    surprise case must not be clamped."""
    d = E.delta_summary([0.8, 0.7], [0.5, 0.6], seed=0)
    assert d["mean"] == pytest.approx(-0.2)


def test_group_condition_summaries_slices_and_summarises():
    rows = [
        {"n_options": 3, "domain": "tax", "representation_no_evidence": 0.5,
         "representation_evidence": 0.7},
        {"n_options": 3, "domain": "nhs", "representation_no_evidence": 0.6,
         "representation_evidence": 0.8},
        {"n_options": 4, "domain": "tax", "representation_no_evidence": 0.4,
         "representation_evidence": 0.4},
    ]
    by_n = E.group_condition_summaries(rows, "n_options", seed=0)
    assert set(by_n) == {"3", "4"}
    assert by_n["3"]["n_items"] == 2
    assert by_n["3"]["no_evidence"]["mean"] == pytest.approx(0.55)
    assert by_n["3"]["evidence"]["mean"] == pytest.approx(0.75)
    assert by_n["3"]["delta"]["mean"] == pytest.approx(0.2)
    assert by_n["3"]["fidelity_gap"] == pytest.approx(0.25)
    # the 4-option group has zero lift
    assert by_n["4"]["delta"]["mean"] == pytest.approx(0.0)
    by_dom = E.group_condition_summaries(rows, "domain", seed=0)
    assert set(by_dom) == {"nhs", "tax"}
    assert by_dom["nhs"]["n_items"] == 1


def test_group_condition_summaries_empty_is_empty():
    assert E.group_condition_summaries([], "n_options", seed=0) == {}


# ---- P3 pure helpers: evidence tracking ----------------------------------------------

def _delta_check_fixture():
    """A minimal in-memory delta-check with two 5-option harmonised sig items and one item
    that must be REJECTED (not harmonised) — enough to exercise sig_year_data's mapping+guards
    without touching out/_bsa_delta_check.json."""
    def item(iid, harmon, labels, d22, d24, delta, has_pair=True, has22=True):
        dists = {"2024": {"distribution": d24, "labels": labels, "n_unweighted": 800}}
        if has22:
            dists["2022"] = {"distribution": d22, "labels": labels, "n_unweighted": 1000}
        pairs = ([{"pair": "2022->2024", "delta": delta, "mean_position_shift": 0.3}]
                 if has_pair else [])
        return {"id": iid, "harmonised_labels": harmon, "distributions": dists, "pairs": pairs}
    labels = ["a", "b", "c", "d", "e"]
    return {"items": [
        item("nhs_satisfaction", True, labels,
             [0.10, 0.30, 0.20, 0.25, 0.15], [0.05, 0.20, 0.20, 0.30, 0.25],
             [-0.05, -0.10, 0.0, 0.05, 0.10]),
        item("redistribution", True, labels,
             [0.20, 0.30, 0.20, 0.20, 0.10], [0.15, 0.25, 0.25, 0.20, 0.15],
             [-0.05, -0.05, 0.05, 0.0, 0.05]),
        item("not_harmon", False, labels,
             [0.2] * 5, [0.2] * 5, [0.0] * 5),
    ]}


def test_sig_year_data_pulls_years_and_delta():
    dc = _delta_check_fixture()
    yd = E.sig_year_data(dc, ids=("nhs_satisfaction", "redistribution"))
    assert set(yd) == {"nhs_satisfaction", "redistribution"}
    r = yd["nhs_satisfaction"]
    assert r["dist2022"][0] == pytest.approx(0.10)
    assert r["dist2024"][-1] == pytest.approx(0.25)
    assert r["n2022"] == 1000 and r["n2024"] == 800
    assert r["labels"] == ["a", "b", "c", "d", "e"]
    assert r["real_delta"] == [-0.05, -0.10, 0.0, 0.05, 0.10]


def test_sig_year_data_rejects_non_harmonised():
    dc = _delta_check_fixture()
    with pytest.raises(ValueError):
        E.sig_year_data(dc, ids=("not_harmon",))


def test_sig_year_data_rejects_missing_id():
    dc = _delta_check_fixture()
    with pytest.raises(KeyError):
        E.sig_year_data(dc, ids=("does_not_exist",))


def test_sig_year_data_rejects_missing_2022():
    dc = {"items": [{"id": "x", "harmonised_labels": True,
                     "distributions": {"2024": {"distribution": [0.5, 0.5],
                                                "labels": ["a", "b"], "n_unweighted": 5}},
                     "pairs": []}]}
    with pytest.raises(ValueError):
        E.sig_year_data(dc, ids=("x",))


def test_mean_position_matches_scorer_definition():
    # a distribution skewed to higher indices has a higher mean position
    lo = E.mean_position([0.7, 0.2, 0.1])
    hi = E.mean_position([0.1, 0.2, 0.7])
    assert hi > lo
    # uniform over 5 options -> mean index 2.0
    assert E.mean_position([0.2] * 5) == pytest.approx(2.0)


def test_tracking_row_direction_match_when_model_moves_with_population():
    # population moves up (mass to higher indices); model moves up too -> match, E>0
    t22 = [0.4, 0.3, 0.2, 0.1]
    t24 = [0.1, 0.2, 0.3, 0.4]
    m22 = [0.35, 0.30, 0.20, 0.15]
    m24 = [0.15, 0.20, 0.30, 0.35]
    row = E.tracking_row("x", "nhs", m22, m24, t22, t24)
    assert row["real_shift"] > 0
    assert row["model_shift"] > 0
    assert row["direction_match"] is True
    assert row["elasticity"] > 0


def test_tracking_row_direction_mismatch_when_model_moves_opposite():
    t22 = [0.4, 0.3, 0.2, 0.1]
    t24 = [0.1, 0.2, 0.3, 0.4]   # population up
    m22 = [0.15, 0.20, 0.30, 0.35]
    m24 = [0.35, 0.30, 0.20, 0.15]   # model down
    row = E.tracking_row("x", "nhs", m22, m24, t22, t24)
    assert row["direction_match"] is False
    assert row["elasticity"] < 0


def test_tracking_row_frozen_model_has_zero_shift():
    t22 = [0.4, 0.3, 0.2, 0.1]
    t24 = [0.1, 0.2, 0.3, 0.4]
    m = [0.25, 0.25, 0.25, 0.25]
    row = E.tracking_row("x", "nhs", m, m, t22, t24)
    assert row["model_shift"] == pytest.approx(0.0)
    assert row["direction_match"] is False   # sign(0) != sign(pop)
    assert row["elasticity"] == pytest.approx(0.0)


def test_tracking_summary_rate_and_moved_count():
    rows = [
        {"direction_match": True, "elasticity": 0.8, "model_shift": 0.2},
        {"direction_match": True, "elasticity": 1.2, "model_shift": 0.3},
        {"direction_match": False, "elasticity": -0.5, "model_shift": -0.1},
        {"direction_match": None, "elasticity": None, "model_shift": 0.0},
    ]
    s = E.tracking_summary(rows, seed=0)
    assert s["n_items"] == 4
    assert s["n_trackable"] == 3
    assert s["direction_match_count"] == 2
    assert s["direction_match_rate"] == pytest.approx(2 / 3)
    assert s["elasticity"]["mean"] == pytest.approx((0.8 + 1.2 - 0.5) / 3)
    assert s["n_model_moved"] == 3


def test_tracking_summary_empty_trackable_is_none_rate():
    rows = [{"direction_match": None, "elasticity": None, "model_shift": 0.0}]
    s = E.tracking_summary(rows, seed=0)
    assert s["direction_match_rate"] is None
    assert s["elasticity"]["mean"] is None
    assert s["n_trackable"] == 0
