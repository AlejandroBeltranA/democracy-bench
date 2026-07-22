"""Tests for the Q1 secondary extractor (R-W7): source identity, pairing, signs, and the
rounded values the manuscript quotes."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "extract_q1_secondary", ROOT / "scripts" / "extract_q1_secondary.py")
X = importlib.util.module_from_spec(spec)
spec.loader.exec_module(X)


def test_source_identity_enforced(tmp_path, monkeypatch):
    """A tampered source must raise, not warn."""
    rel = "out/q1_channel_3b.json"
    src = json.loads((ROOT / rel).read_text())
    src["tampered"] = True
    bad = tmp_path / "q1_channel_3b.json"
    bad.write_text(json.dumps(src))
    monkeypatch.setitem(X.PINNED, str(Path("out") / "tampered.json"), "0" * 64)
    monkeypatch.setattr(X, "ROOT", tmp_path)
    monkeypatch.setitem(X.PINNED, rel, X.PINNED[rel])
    (tmp_path / "out").mkdir()
    (tmp_path / rel).write_text(json.dumps(src))
    with pytest.raises(RuntimeError, match="hash mismatch"):
        X.load_verified(rel)


def test_sources_verify_and_pairing_holds():
    art = {sz: X.load_verified(f"out/q1_channel_{sz}.json") for sz in ("3b", "8b")}
    for sz in ("3b", "8b"):
        a = X.cell_mass(art[sz], "placebo::no_guard")
        b = X.cell_mass(art[sz], "baseline::no_guard")
        assert set(a) == set(b) and len(a) == 12


def test_placebo_effects_signs_and_quoted_values():
    art = {sz: X.load_verified(f"out/q1_channel_{sz}.json") for sz in ("3b", "8b")}
    r3 = X.paired_effect(art["3b"], "placebo::no_guard", "baseline::no_guard")
    r8 = X.paired_effect(art["8b"], "placebo::no_guard", "baseline::no_guard")
    # signs: harmful on both, CIs wholly below zero
    for r in (r3, r8):
        assert r["mean"] < 0 and r["ci"][1] < 0 and r["n"] == 12
    # the rounded values the draft quotes
    assert round(r3["mean"], 3) == -0.143
    assert [round(x, 3) for x in r3["ci"]] == [-0.217, -0.073]
    assert round(r8["mean"], 3) == -0.112
    assert [round(x, 3) for x in r8["ci"]] == [-0.187, -0.033]


def test_surveillance_exclusion_quoted_values():
    a3 = X.load_verified("out/q1_channel_3b.json")
    data = X.paired_effect(a3, "data_only::no_guard", "baseline::no_guard",
                           exclude=X.EXCLUDED_PROBE)
    instr = X.paired_effect(a3, "instruction_only::no_guard", "baseline::no_guard",
                            exclude=X.EXCLUDED_PROBE)
    sysrec = X.paired_effect(a3, "data_only::system_guard", "data_only::no_guard",
                             exclude=X.EXCLUDED_PROBE)
    assert data["n"] == instr["n"] == sysrec["n"] == 11
    # the rounded values quoted in the draft (Sol's sensitivity check)
    assert round(data["mean"], 3) == -0.150
    assert round(instr["mean"], 3) == -0.552
    assert round(sysrec["mean"], 3) == 0.010
    d, i, b0 = (X.cell_mass(a3, c) for c in
                ("data_only::no_guard", "instruction_only::no_guard", "baseline::no_guard"))
    ids = sorted(x for x in d if x != X.EXCLUDED_PROBE)
    contrast = sum((d[x] - b0[x]) - (i[x] - b0[x]) for x in ids) / len(ids)
    assert round(contrast, 3) == 0.402


def test_missing_exclusion_probe_raises():
    a3 = X.load_verified("out/q1_channel_3b.json")
    with pytest.raises(RuntimeError, match="not found"):
        X.paired_effect(a3, "data_only::no_guard", "baseline::no_guard",
                        exclude="not_a_probe")
