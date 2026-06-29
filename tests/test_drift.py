"""Decision-drift over the REAL BSA/SSA public-opinion items + the AI floor probe:
providers diverge, get scored vs the England public, and the floor probe yields a verdict."""
from alignment import drift, policy_data


def test_real_public_opinion_data_is_loaded():
    assert policy_data.available(), "expected out/public_opinion/targets.json"
    items, public, compare, meta = drift.load_policy()
    assert meta["primary"][0] == "ENG" and meta["comparison"][0] == "SCO"
    # real BSA items + the appended AI floor probe
    assert any(it["id"] == drift.FLOOR_PROBE_ID for it in items)
    assert len(public) >= 3


def test_drift_runs_simulated_panel_on_real_targets():
    r = drift.run(models=None, n_samples=200)
    assert r["simulated"] is True
    assert r["primary"][0] == "ENG"
    assert r["status"] == "microdata_built"          # real public targets, not synthetic
    assert len(r["models"]) >= 2 and r["items"]


def test_providers_drift_apart_and_eng_sco_divergence_present():
    r = drift.run(models=None, n_samples=300)
    drifts = [it["mean_cross_model_drift"] for it in r["items"].values()]
    assert max(drifts) > 0.1, "expected cross-model drift among divergent providers"
    # at least one item carries a real England-vs-Scotland divergence number
    assert any(it["eng_vs_sco_tv"] is not None for it in r["items"].values())


def test_floor_probe_gets_a_per_model_verdict():
    r = drift.run(models=None, n_samples=300)
    floor = [it for it in r["items"].values() if it["class"] == "floor"]
    assert floor, "expected the AI due-process floor probe"
    for m in floor[0]["models"].values():
        assert "floor_held" in m and "protective_mass" in m
    # the efficiency-leaning provider should be the one most likely to cross the floor
    assert not all(m["floor_held"] for m in floor[0]["models"].values())
