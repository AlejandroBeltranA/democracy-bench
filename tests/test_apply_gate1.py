"""The read-only Gate 1 validator confirms every target file is well-formed."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("apply_gate1", ROOT / "scripts" / "apply_gate1.py")
ag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ag)


def test_all_targets_well_formed():
    ok, problems = ag.validate()
    assert ok, f"malformed targets: {problems}"


def test_validate_returns_problem_list_shape():
    ok, problems = ag.validate()
    assert isinstance(problems, list)
