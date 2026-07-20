"""Numpy-only tests for the PURE data-prep helpers in
scripts/make_paper_figures.py (PS2).

These test the figure DATA PREP, not the matplotlib rendering. They also bind
the prepped numbers to PS1's extractor (scripts/extract_paper_results.py) so a
figure can never silently drift from docs/PAPER_RESULTS.md — the number in the
plot is the number in the table, by construction.

No matplotlib import here (the .venv has no matplotlib); build_all(render=False)
runs the whole prep path without touching the plotting backend.
"""
import importlib.util
import os

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(relpath, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mpf = _load_module("scripts/make_paper_figures.py", "make_paper_figures")
epr = _load_module("scripts/extract_paper_results.py", "extract_paper_results")


# Prepped-once fixtures (no render, no matplotlib) ---------------------------
@pytest.fixture(scope="module")
def prepped():
    return mpf.build_all(render=False)


@pytest.fixture(scope="module")
def extract():
    return epr.build()


# ---------------------------------------------------------------------------
# _domain_family: pure static mapping, deterministic, total over its inputs
# ---------------------------------------------------------------------------
def test_domain_family_maps_known_domains():
    fam = mpf._domain_family(["nhs", "welfare", "trust", "climate"])
    assert fam == ["health/care", "welfare/tax", "governance", "other"]


def test_domain_family_unknown_falls_to_other():
    assert mpf._domain_family(["totally_new_domain"]) == ["other"]


def test_domain_family_preserves_order_and_length():
    xs = ["welfare", "nhs", "nhs", "trust"]
    fam = mpf._domain_family(xs)
    assert len(fam) == len(xs)
    assert fam == ["welfare/tax", "health/care", "health/care", "governance"]


def test_family_colour_covers_all_families():
    # every family the mapper can emit must have a colour
    emitted = set(mpf._domain_family(list({
        "nhs", "social_care", "dwp", "welfare", "redistribution", "tax", "tax_spend",
        "spending", "government_responsibility", "democratic_system", "trust",
        "climate", "economy", "mystery",
    })))
    assert emitted <= set(mpf.FAMILY_COLOUR)


# ---------------------------------------------------------------------------
# F1 ladder: static summary — structure + verdict colour-key completeness
# ---------------------------------------------------------------------------
def test_f1_five_rungs_each_has_fields(prepped):
    rungs, colours = prepped["f1_ladder"]
    assert len(rungs) == 5
    for r in rungs:
        assert set(r) == {"label", "verdict", "number", "detail"}
        assert r["verdict"] in colours


def test_f1_context_is_the_only_non_fail(prepped):
    rungs, _ = prepped["f1_ladder"]
    verdicts = {r["label"].split(" ")[0].lower(): r["verdict"] for r in rungs}
    non_fail = [r for r in rungs if r["verdict"] != "fail"]
    assert len(non_fail) == 1
    assert non_fail[0]["label"].lower().startswith("context")
    assert non_fail[0]["verdict"] == "partial"


# ---------------------------------------------------------------------------
# F2 tracking: sorted by real shift, arrays aligned, numbers == PS1
# ---------------------------------------------------------------------------
def test_f2_ten_items_arrays_aligned(prepped):
    d = prepped["f2_tracking"]
    n = len(d["ids"])
    assert n == 10
    assert d["real"].shape == (n,)
    assert d["model"].shape == (n,)
    assert d["match"].shape == (n,)


def test_f2_sorted_by_real_shift_descending(prepped):
    d = prepped["f2_tracking"]
    assert np.all(np.diff(d["real"]) <= 0)


def test_f2_direction_match_count_matches_ps1(prepped, extract):
    d = prepped["f2_tracking"]
    assert d["direction_match_count"] == extract["p3_tracking"]["numbers"]["direction_match_count"]
    # and equals the boolean array's true-count
    assert int(d["match"].sum()) == d["direction_match_count"] == 8


def test_f2_elasticity_matches_ps1(prepped, extract):
    d = prepped["f2_tracking"]
    el = extract["p3_tracking"]["numbers"]["elasticity"]
    assert d["elasticity_mean"] == pytest.approx(el["mean"])
    assert d["elasticity_ci"][0] == pytest.approx(el["ci_lo"])
    assert d["elasticity_ci"][1] == pytest.approx(el["ci_hi"])
    # the honest headline: barely clears zero
    assert d["elasticity_ci"][0] > 0


def test_f2_two_mismatches_have_opposite_signs(prepped):
    d = prepped["f2_tracking"]
    for i, m in enumerate(d["match"]):
        if not m:
            # a direction mismatch means real and model shift disagree in sign
            assert np.sign(d["real"][i]) != np.sign(d["model"][i])


# ---------------------------------------------------------------------------
# F3 floors: five arms x four conditions, no_guard + guards == PS1
# ---------------------------------------------------------------------------
def test_f3_shape(prepped):
    d = prepped["f3_floors"]
    assert d["conditions"] == ["baseline", "hostile_evidence", "adversarial_prompt", "both"]
    assert d["arm_order"] == [
        "no_guard", "guard_provenance", "guard_rights_floor",
        "guard_constitution", "guard_combined",
    ]
    for arm in d["arm_order"]:
        assert d["mass"][arm].shape == (4,)
        assert d["ci_lo"][arm].shape == (4,)
        assert d["ci_hi"][arm].shape == (4,)


def test_f3_floor_line_is_half(prepped):
    assert prepped["f3_floors"]["floor_min"] == 0.5


def test_f3_no_guard_matches_ps1(prepped, extract):
    d = prepped["f3_floors"]
    p4 = extract["p4_floors"]["numbers"]
    for i, c in enumerate(d["conditions"]):
        assert d["mass"]["no_guard"][i] == pytest.approx(p4[c]["floor_mass"]["mean"])


def test_f3_hostile_cracks_every_floor_no_guard(prepped):
    d = prepped["f3_floors"]
    hostile_i = d["conditions"].index("hostile_evidence")
    baseline_i = d["conditions"].index("baseline")
    assert d["mass"]["no_guard"][baseline_i] > 0.5  # baseline holds (just)
    assert d["mass"]["no_guard"][hostile_i] < 0.5  # hostile cracks it


def test_f3_guard_arms_match_ps1(prepped, extract):
    d = prepped["f3_floors"]
    arms = extract["g1_guards"]["numbers"]["arms"]
    hostile_i = d["conditions"].index("hostile_evidence")
    baseline_i = d["conditions"].index("baseline")
    for name in ["guard_provenance", "guard_rights_floor", "guard_constitution", "guard_combined"]:
        assert d["mass"][name][hostile_i] == pytest.approx(arms[name]["hostile_floor_mass"]["mean"])
        assert d["mass"][name][baseline_i] == pytest.approx(arms[name]["baseline_floor_mass"]["mean"])


def test_f3_provenance_backfires_below_no_guard(prepped):
    # PS1: provenance LOWERS hostile floor mass vs no_guard (backfire)
    d = prepped["f3_floors"]
    h = d["conditions"].index("hostile_evidence")
    assert d["mass"]["guard_provenance"][h] < d["mass"]["no_guard"][h]


def test_f3_constitution_is_best_but_still_below_floor(prepped):
    d = prepped["f3_floors"]
    h = d["conditions"].index("hostile_evidence")
    guard_hostiles = {
        name: d["mass"][name][h]
        for name in ["guard_provenance", "guard_rights_floor", "guard_constitution", "guard_combined"]
    }
    best = max(guard_hostiles, key=guard_hostiles.get)
    assert best == "guard_constitution"
    assert guard_hostiles[best] < 0.5  # partial recovery, still below floor


# ---------------------------------------------------------------------------
# F4 geometry: layers ascending, within >= cross everywhere, R8 == PS1
# ---------------------------------------------------------------------------
def test_f4_layers_ascending(prepped):
    L = prepped["f4_geometry"]["layers"]
    assert np.all(np.diff(L) > 0)


def test_f4_within_ge_cross_all_layers(prepped):
    d = prepped["f4_geometry"]
    assert np.all(d["within"] >= d["cross"])


def test_f4_domain_fracture_grows_with_depth(prepped):
    # within - cross gap should widen toward the output layers
    d = prepped["f4_geometry"]
    gap = d["within"] - d["cross"]
    assert gap[-1] > gap[0]


def test_f4_l11_l21_offdiag_match_ps1(prepped, extract):
    d = prepped["f4_geometry"]
    w3 = extract["phase2_steering"]["numbers"]["W3_geometry"]
    L = list(d["layers"])
    i11, i21 = L.index(11), L.index(21)
    assert d["mean_offdiag"][i11] == pytest.approx(w3["L11_mean_offdiag_cosine"])
    assert d["mean_offdiag"][i21] == pytest.approx(w3["L21_mean_offdiag_cosine"])
    assert d["within"][i21] == pytest.approx(w3["L21_within_domain_cosine"])
    assert d["cross"][i21] == pytest.approx(w3["L21_cross_domain_cosine"])


def test_f4_control_cosine_matches_ps1(prepped, extract):
    d = prepped["f4_geometry"]
    r8 = extract["phase2_steering"]["numbers"]["R8_personactrl"]
    assert d["control_cosine_l11"] == pytest.approx(r8["cosine_real_control"])
    assert d["control_cosine_l11"] == pytest.approx(0.852, abs=1e-3)


# ---------------------------------------------------------------------------
# F5 fidelity: 50 items sorted ascending, n_worse == PS1's 24
# ---------------------------------------------------------------------------
def test_f5_fifty_items_sorted(prepped):
    d = prepped["f5_fidelity"]
    assert d["n_items"] == 50
    assert d["deltas"].shape == (50,)
    assert len(d["domains"]) == 50
    assert len(d["families"]) == 50
    assert np.all(np.diff(d["deltas"]) >= 0)


def test_f5_n_worse_matches_ps1(prepped, extract):
    d = prepped["f5_fidelity"]
    assert d["n_worse"] == extract["p2_fidelity"]["numbers"]["n_items_worse_with_evidence"]
    assert d["n_worse"] == 24


def test_f5_n_worse_equals_negative_count(prepped):
    d = prepped["f5_fidelity"]
    assert d["n_worse"] == int((d["deltas"] < 0).sum())


# ---------------------------------------------------------------------------
# Phase-5 8B overlays: F2 tracking markers + F3 floors panel. Every plotted 8B
# number is bound to PS1's model_robustness_8b extract so the overlay cannot
# drift from docs/PAPER_RESULTS.md §10.
# ---------------------------------------------------------------------------
def test_f2_has_8b_overlay_aligned_and_bound(prepped, extract):
    d = prepped["f2_tracking"]
    assert d["has_8b"] is True
    # 8B model shifts align to the same 10 sorted items
    assert d["model_8b"].shape == (10,)
    assert d["match_8b"].shape == (10,)
    r8 = extract["model_robustness_8b"]["numbers"]["p3_tracking"]
    assert d["direction_match_count_8b"] == r8["direction_match_count"] == 8
    assert int(d["match_8b"].sum()) == d["direction_match_count_8b"]
    assert d["elasticity_mean_8b"] == pytest.approx(r8["elasticity"]["mean"])
    assert d["elasticity_ci_8b"][0] == pytest.approx(r8["elasticity"]["ci_lo"])
    assert d["elasticity_ci_8b"][1] == pytest.approx(r8["elasticity"]["ci_hi"])
    assert d["elasticity_ci_8b"][0] > 0  # clears zero on 8B too


def test_f2_real_shift_shared_across_models(prepped):
    # real_shift is model-independent — the overlay must reuse the same `real`
    # series (the figure draws one real marker per item, both models' model-shift
    # markers hang off it).
    d = prepped["f2_tracking"]
    assert d["real"].shape == d["model_8b"].shape


def test_f3_8b_panel_shape_and_arms(prepped):
    d8 = prepped["f3_floors_8b"]
    assert d8["conditions"] == ["baseline", "hostile_evidence", "adversarial_prompt", "both"]
    # only the 3 re-run arms (provenance/combined were dominated 3B arms)
    assert d8["arm_order"] == ["no_guard", "guard_rights_floor", "guard_constitution"]
    for arm in d8["arm_order"]:
        assert d8["mass"][arm].shape == (4,)
    assert d8["floor_min"] == 0.5


def test_f3_8b_no_guard_matches_ps1(prepped, extract):
    d8 = prepped["f3_floors_8b"]
    fl = extract["model_robustness_8b"]["numbers"]["p4_floors"]
    for i, c in enumerate(d8["conditions"]):
        assert d8["mass"]["no_guard"][i] == pytest.approx(fl[c]["floor_mass"]["mean"])


def test_f3_8b_the_striking_crack_0707_to_0074(prepped):
    # The single most striking replication number gets its own panel bar.
    d8 = prepped["f3_floors_8b"]
    bi = d8["conditions"].index("baseline")
    hi = d8["conditions"].index("hostile_evidence")
    assert d8["mass"]["no_guard"][bi] == pytest.approx(0.7074, abs=1e-3)  # stronger baseline holder
    assert d8["mass"]["no_guard"][hi] == pytest.approx(0.0743, abs=1e-3)  # cracks ~3x deeper
    assert d8["mass"]["no_guard"][bi] > 0.5  # 8B baseline holds
    assert d8["mass"]["no_guard"][hi] < 0.5  # hostile cracks it hard


def test_f3_8b_guards_match_ps1_and_still_fail(prepped, extract):
    d8 = prepped["f3_floors_8b"]
    arms = extract["model_robustness_8b"]["numbers"]["g1_guards"]["arms"]
    hi = d8["conditions"].index("hostile_evidence")
    for name in ("guard_rights_floor", "guard_constitution"):
        assert d8["mass"][name][hi] == pytest.approx(arms[name]["hostile_floor_mass"]["mean"])
        assert d8["mass"][name][hi] < 0.45  # still fails the partial bar on 8B


# --- F6 cross-family floor crack + F7 AI reflex (added figures) -------------
def test_f6_crossfamily_sorted_and_universally_cracks(prepped):
    rows = prepped["f6_crossfamily"]["rows"]
    assert len(rows) == 7                                # 6 open-weight + gpt-4o-mini (frontier)
    bases = [r["baseline"] for r in rows]
    assert bases == sorted(bases, reverse=True)          # sorted by resting strength
    assert max(bases) > 0.85 and min(bases) < 0.40       # 0.90 (Phi) .. 0.36 (Nemo)
    for r in rows:
        assert r["hostile"] < 0.5                         # the universal crack
    assert any(r["model"] == "gpt-4o-mini (frontier)" for r in rows)  # frontier row present


def test_f6_matches_ps1_floor_numbers(prepped, extract):
    d = {r["model"]: r for r in prepped["f6_crossfamily"]["rows"]}
    assert d["Llama-3B"]["baseline"] == pytest.approx(
        extract["p4_floors"]["numbers"]["baseline"]["floor_mass"]["mean"])
    assert d["Llama-8B"]["hostile"] == pytest.approx(
        extract["model_robustness_8b"]["numbers"]["p4_floors"]["hostile_evidence"]["floor_mass"]["mean"])
    panel = extract["cross_family_panel"]["scored_models"]
    assert d["Phi-4-mini"]["baseline"] == pytest.approx(
        panel["phi4mini"]["numbers"]["p4_floors"]["baseline"]["floor_mass"]["mean"])
    fr = extract["frontier_crack_gpt4omini"]["numbers"]
    assert d["gpt-4o-mini (frontier)"]["baseline"] == pytest.approx(
        fr["baseline"]["floor_mass"]["mean"])
    assert d["gpt-4o-mini (frontier)"]["hostile"] == pytest.approx(
        fr["hostile_evidence"]["floor_mass"]["mean"])


def test_f7_reflex_positive_and_never_below_diagonal(prepped):
    d = prepped["f7_reflex"]
    assert len(d["series"]) == 3
    assert d["samples"] == 100
    for s in d["series"]:
        assert s["excess"] > 0                            # every model shows the reflex
        for human, ai in s["points"]:
            assert ai >= human - 1e-9                      # AI framing never lowers protection
