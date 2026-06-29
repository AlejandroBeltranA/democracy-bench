"""Every output artifact carries a run-metadata block (NEXT_EXPERIMENT_DESIGN "Required Run
Metadata" + success criterion "every artifact has run metadata")."""
from alignment import align_demo, drift, regional_drift, run_meta


def test_run_block_has_core_fields():
    block = run_meta.run_block(command="x y", samples=100, models=["m"], schema_version=2)
    for key in ("generated_at", "command", "code_ref", "schema_version"):
        assert key in block
    assert block["command"] == "x y"
    assert block["samples_requested"] == 100
    assert block["models"] == ["m"]
    assert block["schema_version"] == 2


def test_code_ref_is_a_string():
    assert isinstance(run_meta.code_ref(), str)
    assert run_meta.code_ref()  # non-empty (a sha or the no-git marker)


def test_display_path_is_repo_relative_for_repo_paths():
    p = run_meta.display_path(run_meta.ROOT / "data" / "policy_items.jsonl")
    assert p == "data/policy_items.jsonl"


def test_drift_report_carries_run_block():
    report = drift.run(models=None, n_samples=8)
    run = report["run"]
    assert run["simulated"] is True
    assert run["samples_requested"] == 8
    assert "target_file" in run and "item_file" in run
    assert run["shuffle_options"] is False


def test_regional_drift_report_carries_run_block():
    report = regional_drift.run(models=None, n_samples=8)
    run = report["run"]
    assert run["simulated"] is True
    assert run["samples_requested"] == 8
    assert "target_file" in run


def test_align_demo_report_carries_run_block():
    report = align_demo.run(model=None, n_samples=8)
    run = report["run"]
    assert run["simulated"] is True
    assert run["floor_steered"] is False
    assert run["samples_requested"] == 8
