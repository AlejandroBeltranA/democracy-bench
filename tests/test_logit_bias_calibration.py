"""Phase 1 held-out calibration experiment: generalisation + floor collateral damage.

Synthetic items with a deliberately SYSTEMATIC model miss (so a shared bias should generalise) and a
floor probe, to pin the experiment's verdict logic. Pure math, no network.
"""
import numpy as np
import pytest

from alignment import logit_bias_calibration as C


def _systematic_panel(k=6):
    # every item: model leans to option 0/1, public leans to option 2/3 — the SAME directional miss,
    # so a single shared bias toward the high options should help held-out items too.
    rng = np.random.default_rng(1)
    items = []
    for i in range(k):
        jitter = rng.normal(0, 0.02, 4)
        p = np.clip(np.array([0.45, 0.30, 0.15, 0.10]) + jitter, 0.01, None)
        t = np.clip(np.array([0.10, 0.20, 0.40, 0.30]) - jitter, 0.01, None)
        items.append({"id": f"item{i}", "p": p / p.sum(), "t": t / t.sum()})
    return items


def test_shared_bias_generalises_on_systematic_miss():
    report = C.held_out_calibration(_systematic_panel(), train_frac=0.5, seed=0)
    assert report["held_out_gain"] > 0          # held-out items moved toward the public
    assert "good nudge" in report["verdict"]


def test_train_and_test_are_disjoint_and_cover_all():
    items = _systematic_panel(6)
    report = C.held_out_calibration(items, train_frac=0.6, seed=3)
    tr, te = set(report["train_ids"]), set(report["test_ids"])
    assert tr.isdisjoint(te)
    assert tr | te == {it["id"] for it in items}
    assert len(te) >= 1                          # always hold something out


def test_floor_collateral_damage_is_measured():
    # public miss pushes mass UP (toward option 3); a floor whose protection is the LOW options
    # (floor_dir=-1) should lose protective mass under the unguarded shared bias — and be flagged.
    items = _systematic_panel(6)
    floor = {"id": "floor_low", "p": np.array([0.7, 0.2, 0.06, 0.04]), "floor_dir": -1}
    report = C.held_out_calibration(items, floors=[floor], train_frac=0.6, seed=0)
    f = report["floor"][0]
    assert f["protective_mass_after"] < f["protective_mass_before"]   # collateral damage exists
    assert report["worst_floor_delta"] is not None


def test_bad_nudge_verdict_when_floor_breached():
    # a floor that starts barely protected and gets pushed below 0.5 -> "bad nudge"
    items = _systematic_panel(6)
    floor = {"id": "fragile", "p": np.array([0.55, 0.05, 0.2, 0.2]), "floor_dir": -1}
    report = C.held_out_calibration(items, floors=[floor], train_frac=0.6, seed=0)
    if report["floor"][0]["protective_mass_after"] < 0.5:
        assert report["any_floor_breached"]
        assert "bad nudge" in report["verdict"]


def test_no_generalisation_verdict_on_idiosyncratic_misses():
    # each item's miss points a DIFFERENT direction -> no shared bias can help on average.
    items = [
        {"id": "a", "p": np.array([0.7, 0.1, 0.1, 0.1]), "t": np.array([0.1, 0.1, 0.1, 0.7])},
        {"id": "b", "p": np.array([0.1, 0.1, 0.1, 0.7]), "t": np.array([0.7, 0.1, 0.1, 0.1])},
        {"id": "c", "p": np.array([0.1, 0.7, 0.1, 0.1]), "t": np.array([0.1, 0.1, 0.7, 0.1])},
        {"id": "d", "p": np.array([0.1, 0.1, 0.7, 0.1]), "t": np.array([0.1, 0.7, 0.1, 0.1])},
    ]
    report = C.held_out_calibration(items, train_frac=0.5, seed=0)
    assert report["held_out_gain"] <= 0.05       # essentially no held-out improvement
    assert "no generalisation" in report["verdict"]


def test_report_is_json_serialisable():
    import json
    report = C.held_out_calibration(_systematic_panel(), train_frac=0.5, seed=0,
                                    floors=[{"id": "f", "p": np.array([0.6, 0.2, 0.1, 0.1]),
                                             "floor_dir": -1}])
    json.dumps(report)


def test_requires_two_items_to_split():
    with pytest.raises(ValueError):
        C.held_out_calibration([{"id": "x", "p": np.array([0.5, 0.5]), "t": np.array([0.4, 0.6])}])


# ---- real-data adapter (from a policy_delegate_stress artifact) -----------------------

def _fake_artifact():
    def entry(cls, labels, target, dist, floor_dir=None):
        e = {"class": cls, "labels": labels, "target": target,
             "modes": {"default": {"models": {"M": {"dist": dist}}}}}
        if floor_dir is not None:
            e["floor_dir"] = floor_dir
        return e
    L4 = ["a", "b", "c", "d"]
    return {"simulated": True, "items": {
        # three 4-option contestable items (the richest group)
        "c1": entry("contestable", L4, [0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]),
        "c2": entry("contestable", L4, [0.15, 0.25, 0.35, 0.25], [0.35, 0.3, 0.2, 0.15]),
        "c3": entry("contestable", L4, [0.05, 0.2, 0.4, 0.35], [0.45, 0.25, 0.2, 0.1]),
        # a 3-option contestable (different group, must be excluded from a 4-opt run)
        "c4": entry("contestable", ["x", "y", "z"], [0.2, 0.3, 0.5], [0.5, 0.3, 0.2]),
        # a 4-option floor carrying floor_dir inline
        "f1": entry("floor", L4, None, [0.6, 0.2, 0.1, 0.1], floor_dir=-1),
        # a 4-option floor WITHOUT inline floor_dir -> must come from the lookup
        "f2": entry("floor", L4, None, [0.55, 0.25, 0.1, 0.1]),
    }}


def test_adapter_groups_by_option_length_and_picks_richest():
    pulled = C.from_stress_artifact(_fake_artifact(), "M", "default", floor_dirs={"f2": -1})
    assert pulled["n_options"] == 4                       # 4-opt group has 3 items vs 1 for 3-opt
    assert {c["id"] for c in pulled["contestable"]} == {"c1", "c2", "c3"}
    assert pulled["groups"] == {3: 1, 4: 3}


def test_adapter_resolves_floor_dir_inline_and_from_lookup():
    pulled = C.from_stress_artifact(_fake_artifact(), "M", "default", floor_dirs={"f2": -1})
    dirs = {f["id"]: f["floor_dir"] for f in pulled["floors"]}
    assert dirs == {"f1": -1, "f2": -1}                   # f1 inline, f2 from lookup
    assert pulled["skipped_floors"] == []


def test_adapter_skips_floor_with_unresolvable_dir():
    pulled = C.from_stress_artifact(_fake_artifact(), "M", "default", floor_dirs={})
    ids = {f["id"] for f in pulled["floors"]}
    assert ids == {"f1"}                                  # f2 has no dir anywhere -> skipped, not dropped silently
    assert pulled["skipped_floors"] == ["f2"]


def test_adapter_raises_on_missing_model():
    with pytest.raises(ValueError):
        C.from_stress_artifact(_fake_artifact(), "NOPE", "default")


def test_adapter_feeds_a_runnable_experiment():
    pulled = C.from_stress_artifact(_fake_artifact(), "M", "default", floor_dirs={"f2": -1})
    report = C.held_out_calibration(pulled["contestable"], pulled["floors"], train_frac=0.6, seed=0)
    assert "verdict" in report
    assert len(report["floor"]) == 2


# ---- k-fold cross-validation (the defensible estimate) -------------------------------

def test_kfold_holds_out_every_item_exactly_once():
    items = _systematic_panel(6)
    report = C.kfold_calibration(items, k=3, seed=0)
    seen = [x["id"] for x in report["per_item"]]
    assert sorted(seen) == sorted(it["id"] for it in items)   # each item appears once as a test item
    assert len(report["fold_gains"]) == 3


def test_kfold_generalises_on_systematic_miss():
    report = C.kfold_calibration(_systematic_panel(8), k=4, seed=0)
    assert report["held_out_gain"] > 0
    assert "good nudge" in report["verdict"]


def test_kfold_no_generalisation_on_idiosyncratic_misses():
    items = [
        {"id": "a", "p": np.array([0.7, 0.1, 0.1, 0.1]), "t": np.array([0.1, 0.1, 0.1, 0.7])},
        {"id": "b", "p": np.array([0.1, 0.1, 0.1, 0.7]), "t": np.array([0.7, 0.1, 0.1, 0.1])},
        {"id": "c", "p": np.array([0.1, 0.7, 0.1, 0.1]), "t": np.array([0.1, 0.1, 0.7, 0.1])},
        {"id": "d", "p": np.array([0.1, 0.1, 0.7, 0.1]), "t": np.array([0.1, 0.7, 0.1, 0.1])},
    ]
    report = C.kfold_calibration(items, k=2, seed=0)
    assert report["held_out_gain"] <= 0.05
    assert "no generalisation" in report["verdict"]


def test_kfold_floor_aggregates_mean_and_worst():
    items = _systematic_panel(6)
    floor = {"id": "f", "p": np.array([0.7, 0.2, 0.06, 0.04]), "floor_dir": -1}
    report = C.kfold_calibration(items, floors=[floor], k=3, seed=0)
    f = report["floor"][0]
    assert {"mean_protective_mass_delta", "worst_protective_mass_delta",
            "held_on_average"} <= set(f)
    assert f["worst_protective_mass_delta"] <= f["mean_protective_mass_delta"] + 1e-12


def test_kfold_clamps_k_to_item_count():
    items = _systematic_panel(3)
    report = C.kfold_calibration(items, k=10, seed=0)   # k > n -> clamped
    assert report["k"] == 3


def test_kfold_is_json_serialisable():
    import json
    report = C.kfold_calibration(_systematic_panel(6), floors=[
        {"id": "f", "p": np.array([0.6, 0.2, 0.1, 0.1]), "floor_dir": -1}], k=3)
    json.dumps(report)


# ---- multi-model sweep ---------------------------------------------------------------

def _two_model_artifact():
    L4 = ["a", "b", "c", "d"]
    rng = np.random.default_rng(2)

    def models_block(systematic):
        # model "GOOD" has a systematic miss the public corrects; "BAD" is idiosyncratic
        return {"GOOD": {"dist": systematic[0]}, "BAD": {"dist": systematic[1]}}

    items = {}
    for i in range(6):
        j = rng.normal(0, 0.02, 4)
        t = np.clip(np.array([0.1, 0.2, 0.4, 0.3]) - j, 0.01, None); t /= t.sum()
        good = np.clip(np.array([0.4, 0.3, 0.2, 0.1]) + j, 0.01, None); good /= good.sum()
        bad = np.clip(np.roll([0.6, 0.2, 0.1, 0.1], i % 4), 0.01, None); bad /= bad.sum()
        items[f"c{i}"] = {"class": "contestable", "labels": L4, "target": t.tolist(),
                          "modes": {"default": {"models": models_block((good.tolist(), bad.tolist()))}}}
    report = {"simulated": True, "run": {"models": ["GOOD", "BAD"]}, "items": items}
    return report


# ---- confidence intervals + significance gating --------------------------------------

def test_gain_stats_flags_tight_positive_as_significant():
    s = C._gain_stats([0.10, 0.12, 0.09, 0.11, 0.10])
    assert s["held_out_gain"] == pytest.approx(0.104, abs=1e-3)
    assert s["held_out_gain_ci"][0] > 0
    assert s["held_out_gain_significant_positive"] is True


def test_gain_stats_flags_noisy_positive_as_not_significant():
    # positive mean but wide spread -> 95% CI straddles zero -> not significant
    s = C._gain_stats([0.5, -0.4, 0.5, -0.4, 0.05])
    assert s["held_out_gain"] > 0
    assert s["held_out_gain_ci"][0] < 0
    assert s["held_out_gain_significant_positive"] is False


def test_gain_stats_empty_is_nan():
    s = C._gain_stats([])
    assert np.isnan(s["held_out_gain"])
    assert s["n"] == 0


def test_verdict_requires_significance_for_good_nudge():
    # same mean gain, opposite significance -> opposite verdict
    assert "no generalisation" in C._verdict(0.05, None, significant_positive=False)
    assert "good nudge" in C._verdict(0.05, None, significant_positive=True)
    # significant gain but a breached floor -> bad nudge
    assert "bad nudge" in C._verdict(0.05, -0.20, significant_positive=True)


def test_kfold_reports_ci_and_significance_fields():
    report = C.kfold_calibration(_systematic_panel(8), k=4, seed=0)
    assert {"held_out_gain_se", "held_out_gain_ci",
            "held_out_gain_significant_positive"} <= set(report)
    assert len(report["held_out_gain_ci"]) == 2


def test_sweep_ranks_models_by_held_out_gain(tmp_path):
    import json
    p = tmp_path / "art.json"
    p.write_text(json.dumps(_two_model_artifact()))
    out = C.sweep_from_stress(p, mode="default", n_options=4, k=3, seed=0)
    models = [r["model"] for r in out["results"]]
    assert set(models) == {"GOOD", "BAD"}
    # sorted by held-out gain descending -> the systematic-miss model ranks first
    gains = [r["held_out_gain"] for r in out["results"]]
    assert gains == sorted(gains, reverse=True)
    assert out["results"][0]["model"] == "GOOD"


# ---- live logprob elicitation path (network-free via a fake LogprobFn) ----------------

def _patch_fake_logprobs(monkeypatch, vector_fn):
    """Make measure.openrouter_logprob_fn return a deterministic fake LogprobFn (no network)."""
    from alignment.instrument import measure as M
    monkeypatch.setattr(M, "openrouter_logprob_fn", lambda model, **kw: (lambda prompt, n: vector_fn(n)))


def test_elicit_logprob_dists_assembles_per_item(monkeypatch):
    _patch_fake_logprobs(monkeypatch, lambda n: np.ones(n) / n)   # uniform
    from alignment import policy_delegate_stress as PDS
    items = [si for si in PDS.contestable_items(PDS.load_targets())
             if len(si.item["scale"]["labels"]) == 4][:3]
    dists = C.elicit_logprob_dists("fake/model", items, n_orders=2, seed=0)
    assert set(dists) == {si.item["id"] for si in items}
    for d in dists.values():
        assert abs(float(np.sum(d)) - 1.0) < 1e-9


def test_run_logprobs_produces_a_logprob_report(monkeypatch):
    _patch_fake_logprobs(monkeypatch, lambda n: np.ones(n) / n)
    report = C.run_logprobs("fake/model", n_options=4, n_orders=2, seed=0, k=3)
    assert report["experiment"]["estimator"] == "logprobs"
    assert report["experiment"]["n_contestable"] >= 2
    assert "verdict" in report
    # uniform model vs real targets -> a defined (likely non-generalising) result, not a crash
    assert isinstance(report["held_out_gain"], float)
