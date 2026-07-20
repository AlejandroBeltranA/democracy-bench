"""Numpy-only tests for the pure parsing/matching helpers of
scripts/verify_repro_reference.py (PS3). No model runs; no file I/O in these
tests beyond importing the module."""
import importlib.util
import os

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, os.pardir, "scripts", "verify_repro_reference.py")
_spec = importlib.util.spec_from_file_location("verify_repro_reference", _SCRIPT)
vrr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vrr)


# ---- parse_fenced_commands -------------------------------------------------

def test_parse_picks_only_single_line_python_and_mlx():
    md = (
        "text\n\n"
        "```\nsource .venv/bin/activate      # env, not a command\n```\n\n"
        "```\npython -m alignment.evidcond_run --baseline\n```\n\n"
        "```\nmlx_lm.lora --model X --train\n```\n\n"
        "```\nbase model:\n  Phase 1 · Phase 2   (multi-line diagram)\n```\n"
    )
    cmds = vrr.parse_fenced_commands(md)
    assert cmds == [
        "python -m alignment.evidcond_run --baseline",
        "mlx_lm.lora --model X --train",
    ]


def test_parse_preserves_order():
    md = "```\npython a\n```\n```\npython b\n```\n```\npython c\n```\n"
    assert vrr.parse_fenced_commands(md) == ["python a", "python b", "python c"]


def test_parse_ignores_non_command_fences():
    md = "```\njson blob {}\n```\n```\nls out/\n```\n"
    assert vrr.parse_fenced_commands(md) == []


# ---- normalise_command -----------------------------------------------------

def test_normalise_collapses_whitespace():
    assert (vrr.normalise_command("python  -m  x    --flag")
            == "python -m x --flag")
    assert (vrr.normalise_command("python -m x\n  --flag y")
            == "python -m x --flag y")


# ---- match_commands --------------------------------------------------------

def test_match_all_ok():
    expected = [("a", "art_a.json", "python a"), ("b", None, "python b")]
    matches, errors = vrr.match_commands(["python a", "python b"], expected)
    assert errors == []
    assert matches == [
        ("a", "art_a.json", "python a", True),
        ("b", None, "python b", False),
    ]


def test_match_detects_wrong_command():
    expected = [("a", "art_a.json", "python a")]
    _matches, errors = vrr.match_commands(["python WRONG"], expected)
    assert len(errors) == 1 and "mismatch" in errors[0]


def test_match_detects_count_mismatch():
    expected = [("a", None, "python a"), ("b", None, "python b")]
    _m, errors = vrr.match_commands(["python a"], expected)
    assert any("COUNT mismatch" in e for e in errors)


def test_match_is_order_sensitive():
    expected = [("a", None, "python a"), ("b", None, "python b")]
    _m, errors = vrr.match_commands(["python b", "python a"], expected)
    assert len(errors) == 2


def test_match_ignores_wrapping_whitespace():
    expected = [("a", None, "python -m x --flag")]
    _m, errors = vrr.match_commands(["python -m x    --flag"], expected)
    assert errors == []


# ---- compare_to_runblock ---------------------------------------------------

def test_compare_runblock_match():
    ok, why = vrr.compare_to_runblock("python a", {"command": "python  a"})
    assert ok and why is None


def test_compare_runblock_mismatch():
    ok, why = vrr.compare_to_runblock("python a", {"command": "python b"})
    assert not ok and "python b" in why


def test_compare_runblock_missing_command():
    ok, why = vrr.compare_to_runblock("python a", {})
    assert not ok and "no 'command'" in why


# ---- EXPECTED table sanity (pure structural checks) ------------------------

def test_expected_table_shape_and_verified_count():
    labels = [row[0] for row in vrr.EXPECTED]
    assert len(labels) == len(set(labels)), "duplicate labels in EXPECTED"
    verified = np.array([row[1] is not None for row in vrr.EXPECTED])
    asserted = ~verified
    # 19 run-block-verified (15 arc + 4 Phase-5 8B replication), 7 asserted-by-doc
    # (3 phase1 + superseded + train + extractor + figures).
    assert int(verified.sum()) == 19
    assert int(asserted.sum()) == 7
    assert verified.sum() + asserted.sum() == len(vrr.EXPECTED)


def test_expected_table_covers_the_four_8b_replication_artifacts():
    arts = {row[1] for row in vrr.EXPECTED}
    for a in ("evidcond_baseline_8b.json", "evidcond_tracking_8b.json",
              "evidcond_floors_8b.json", "floorguard_grid_8b.json"):
        assert a in arts, f"8B artifact {a} not covered by the verifier"


def test_expected_commands_are_command_shaped():
    for _lbl, _art, cmd in vrr.EXPECTED:
        assert cmd.startswith("python ") or cmd.startswith("mlx_lm")
