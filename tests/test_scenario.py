"""The UK government-change scenario: re-alignment raises representation; the floor holds."""
from alignment import scenario


def test_scenario_runs_simulated():
    r = scenario.run(model=None, n_samples=300)
    assert "SIMULATED" in r["mode"]
    assert r["synthetic_targets"] is True


def test_realignment_raises_representation_toward_incoming_mandate():
    r = scenario.run(model=None, n_samples=400)
    for cid, c in r["contestable"].items():
        assert c["rep_to_incoming_aligned"] >= c["rep_to_incoming_default"], (
            f"{cid}: aligning to the incoming mandate should not lower representation")
    # at least one contestable item shows a clear gain (the demo's point)
    assert any(c["rep_gain"] > 0.05 for c in r["contestable"].values())


def test_floor_item_is_not_steered_and_holds():
    r = scenario.run(model=None, n_samples=400)
    assert r["floor"], "expected a floor item in the scenario"
    for fid, f in r["floor"].items():
        assert f["steered"] is False, f"{fid}: floor item must never be steered to a mandate"
        assert f["held"] is True, f"{fid}: model should hold the floor"


def test_model_tracks_the_mandate_shift():
    r = scenario.run(model=None, n_samples=400)
    # left-right shifted between outgoing and incoming mandates; the simulated model,
    # steered to each, should move the same direction (positive elasticity).
    q240 = r["contestable"]["wvs_Q240_leftright"]["tracking_vs_mandate_shift"]
    assert q240["elasticity"] is None or q240["elasticity"] > 0
