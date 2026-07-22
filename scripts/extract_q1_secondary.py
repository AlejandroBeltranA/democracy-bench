"""Fail-loud derived-results extractor for Q1 SECONDARY numbers (R-W7).

The Q1 headline estimands live inside the immutable run artifacts
(out/q1_channel_{3b,8b}.json); this script derives the SECONDARY numbers the manuscript
quotes but which are not named headline estimands there:

  - the placebo effect per model (placebo::no_guard - baseline::no_guard, paired per
    probe, frozen percentile bootstrap B=2000 seed=0);
  - the 3B surveillance-exclusion sensitivity (data / instruction / channel-contrast /
    system-recovery means recomputed over the 11 remaining probes).

Fail-loud rules: the two source artifacts are verified against pinned sha256 hashes
before anything is read (a mismatch raises, never a warning); every probe id must be
present in every cell used; the script REFUSES to overwrite an existing output. The
sources are never modified. Output: out/q1_secondary_extract.json, the only file the
paper may quote these numbers from.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alignment import run_meta                          # noqa: E402
from alignment.instrument.scorers import bootstrap_mean_ci   # noqa: E402

B, SEED = 2000, 0
EXCLUDED_PROBE = "pol_surveillance"                     # 3B coverage-anomaly probe

PINNED = {
    "out/q1_channel_3b.json":
        "bfa5f8f95b1c927b0361bf771a36fb2fbdf938c148421c18e4af5573b081c341",
    "out/q1_channel_8b.json":
        "bd6d4582774a1c305db9d9e0c5161bed1373585dba6698094c441cc8bedb6791",
}


def load_verified(rel: str) -> dict:
    p = ROOT / rel
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if digest != PINNED[rel]:
        raise RuntimeError(
            f"source hash mismatch for {rel}: got {digest}, pinned {PINNED[rel]}; "
            f"refusing to derive numbers from an unverified artifact")
    return json.loads(p.read_text())


def cell_mass(artifact: dict, cell_id: str) -> dict:
    rows = artifact["cells"][cell_id]
    return {r["id"]: float(r["protective_mass"]) for r in rows}


def paired_effect(artifact: dict, cell: str, ref: str, exclude: str | None = None) -> dict:
    a, b = cell_mass(artifact, cell), cell_mass(artifact, ref)
    if set(a) != set(b):
        raise RuntimeError(f"probe-id mismatch between {cell} and {ref}: pairing broken")
    ids = sorted(i for i in a if i != exclude)
    if exclude is not None and len(ids) != len(a) - 1:
        raise RuntimeError(f"exclusion probe {exclude!r} not found in {cell}")
    return bootstrap_mean_ci([a[i] - b[i] for i in ids], B=B, seed=SEED)


def main() -> None:
    out_path = ROOT / "out" / "q1_secondary_extract.json"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite existing artifact {out_path} "
                         f"(hard rule: new path per run)")
    art = {sz: load_verified(f"out/q1_channel_{sz}.json") for sz in ("3b", "8b")}

    placebo = {sz: paired_effect(art[sz], "placebo::no_guard", "baseline::no_guard")
               for sz in ("3b", "8b")}

    a3 = art["3b"]
    excl = {
        "excluded_probe": EXCLUDED_PROBE,
        "data_effect": paired_effect(a3, "data_only::no_guard", "baseline::no_guard",
                                     exclude=EXCLUDED_PROBE),
        "instruction_effect": paired_effect(a3, "instruction_only::no_guard",
                                            "baseline::no_guard", exclude=EXCLUDED_PROBE),
        "system_recovery": paired_effect(a3, "data_only::system_guard",
                                         "data_only::no_guard", exclude=EXCLUDED_PROBE),
    }
    # channel contrast under exclusion: per-probe (data - instruction) differences
    d, i, b0 = (cell_mass(a3, c) for c in
                ("data_only::no_guard", "instruction_only::no_guard", "baseline::no_guard"))
    ids = sorted(x for x in d if x != EXCLUDED_PROBE)
    excl["channel_contrast"] = bootstrap_mean_ci(
        [(d[x] - b0[x]) - (i[x] - b0[x]) for x in ids], B=B, seed=SEED)

    report = {
        "run": run_meta.run_block(
            command="python scripts/extract_q1_secondary.py",
            models=[art[sz]["run"]["models"][0] for sz in ("3b", "8b")],
            schema_version=1,
            extra={"kind": "q1_secondary_extract", "sources": dict(PINNED),
                   "n_bootstrap": B, "seed": SEED}),
        "placebo_effect": placebo,
        "surveillance_exclusion_3b": excl,
        "caveats": [
            "Derived secondary numbers only; Q1 headline estimands live in the immutable "
            "run artifacts and are NOT restated here.",
            "Sources verified by pinned sha256 before reading; this artifact is the only "
            "permitted source for the manuscript's placebo and exclusion-sensitivity "
            "numbers.",
        ],
    }
    out_path.write_text(json.dumps(report, indent=1))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
