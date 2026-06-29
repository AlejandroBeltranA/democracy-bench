#!/usr/bin/env python3
"""Gate 1 validator — READ ONLY. Confirms every target_*.json is well-formed (every item's
var present, vector length == option count, sums to ~1.0) and reports the sign-off state +
caveats. Does NOT mutate anything: the actual sign-off is the human block in
gates/GATE1_wvs_data.md, recorded in data/targets/SOURCES.json. Exits non-zero on any
malformed target so a broken swap can't masquerade as approved.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alignment import provenance as P  # noqa: E402

ITEMS = ROOT / "data" / "wvs_items.jsonl"
TARGETS = ROOT / "data" / "targets"
COUNTRIES = ["USA", "GBR"]
WAVES = [6, 7]


def validate() -> tuple[bool, list[str]]:
    """Return (ok, problems) — hard failures only. Checks target vectors are well-formed AND
    that a *signed-off* real source isn't missing the sample size its CIs depend on."""
    problems: list[str] = []
    items = [json.loads(l) for l in ITEMS.read_text().splitlines() if l.strip()]
    signed = P.targets_signed_off()
    for c in COUNTRIES:
        for w in WAVES:
            f = TARGETS / f"target_{c}_wave{w}.json"
            if not f.exists():
                problems.append(f"{f.name}: missing")
                continue
            target = json.loads(f.read_text())
            for it in items:
                var, n_opt = it["source"]["var"], len(it["scale"]["labels"])
                if var not in target:
                    problems.append(f"{c} w{w}: {var} missing")
                    continue
                vec = target[var]
                if len(vec) != n_opt:
                    problems.append(f"{c} w{w} {var}: len {len(vec)} != {n_opt} options")
                if abs(sum(vec) - 1.0) > 0.02:
                    problems.append(f"{c} w{w} {var}: sums to {sum(vec):.3f}, not ~1.0")
            info = P.source_info(c, w)
            if signed and info.get("real_available") and info.get("n") is None:
                problems.append(f"{c} w{w}: signed-off source '{info.get('label')}' has "
                                f"null sample size n — elasticity CIs would be suppressed")
    return (not problems, problems)


def warnings(sources: dict) -> list[str]:
    """Soft caveats that don't fail the gate but must travel with any published result."""
    w: list[str] = []
    if P.targets_signed_off(sources) and not P.second_person_review_done(sources):
        w.append("2nd-person class review OUTSTANDING — classifications not independently verified")
    for c in COUNTRIES:
        for wave in WAVES:
            info = P.source_info(c, wave, sources)
            if info.get("is_proxy"):
                w.append(f"{c} w{wave} = {info.get('label')} (proxy, not native WVS{wave})")
            if info.get("source_type") == "wvs_online":
                w.append(f"{c} w{wave} from WVS Online weighted view (country CSV lacks a weight column)")
    return w


def main() -> int:
    ok, problems = validate()
    s = P.load_sources()
    so = s.get("gate1_signoff", {})
    print("Gate 1 state")
    print(f"  json_status     : {s.get('json_status')}")
    print(f"  signed_off      : {P.targets_signed_off(s)}")
    if so:
        print(f"  reviewer / date : {so.get('reviewer')} / {so.get('date')}")
        print(f"  2nd-person rev. : {so.get('second_person_class_review')}")
    print("  warnings        :")
    for cav in warnings(s):
        print(f"    ⚠ {cav}")
    print(f"\ntarget files: {'ALL WELL-FORMED ✓' if ok else 'PROBLEMS ✗'}")
    for p in problems:
        print(f"  ✗ {p}")
    if ok:
        print("\nNote: vector shape + sample sizes are valid; the warnings above are not "
              "failures but MUST accompany any published score.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
