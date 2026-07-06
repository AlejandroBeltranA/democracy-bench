#!/usr/bin/env python3
"""Score a filled rationale codesheet (judge-free construct validity). Reads the CSV that
build_rationale_codesheet.py produced (with CODE_* columns filled by a human) and reports:
  - stance-consistency rate (overall + by class): does the scored option match the rationale?
  - right-invocation rate (floor items): do floor rationales engage the right at stake?
  - optional second-coder agreement if a *_2 column is present.

Emits both a JSON summary (--out) and a paper-ready sentence.
Usage: python scripts/score_rationale_codesheet.py annotations/rationale_codesheet.csv [--out out/rationale_validity.json]
"""
import argparse, csv, json, sys
from pathlib import Path


def _yn(v):
    v = (v or "").strip().lower()
    if v in ("y", "yes", "1", "true"):  return True
    if v in ("n", "no", "0", "false"):  return False
    return None  # blank / NA / unrecognised


def rate(vals):
    coded = [v for v in vals if v is not None]
    return (sum(coded) / len(coded), len(coded)) if coded else (None, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sheet")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.sheet)))
    if not rows:
        print("empty sheet", file=sys.stderr); return 2

    stance_all, stance_floor, stance_cont, invokes = [], [], [], []
    agree_stance = []
    for r in rows:
        sc = _yn(r.get("CODE_stance_consistent"))
        stance_all.append(sc)
        (stance_floor if r.get("class") == "floor" else stance_cont).append(sc)
        if r.get("class") == "floor":
            invokes.append(_yn(r.get("CODE_invokes_right")))
        if "CODE_stance_consistent_2" in r:            # optional second coder
            sc2 = _yn(r.get("CODE_stance_consistent_2"))
            if sc is not None and sc2 is not None:
                agree_stance.append(sc == sc2)

    sa, na = rate(stance_all)
    sf, nf = rate(stance_floor)
    scn, ncn = rate(stance_cont)
    ir, nir = rate(invokes)
    n_uncoded = sum(1 for v in stance_all if v is None)

    summary = {
        "n_rows": len(rows), "n_stance_uncoded": n_uncoded,
        "stance_consistent": {"rate": sa, "n": na},
        "stance_consistent_floor": {"rate": sf, "n": nf},
        "stance_consistent_contestable": {"rate": scn, "n": ncn},
        "invokes_right_floor": {"rate": ir, "n": nir},
    }
    if agree_stance:
        summary["second_coder_agreement_stance"] = {"rate": sum(agree_stance)/len(agree_stance),
                                                     "n": len(agree_stance)}

    print(json.dumps(summary, indent=2))
    if n_uncoded:
        print(f"\nWARNING: {n_uncoded} rows have no stance code yet — finish coding.", file=sys.stderr)

    pct = lambda r: "n/a" if r is None else f"{r:.0%}"
    if None in (sa, sf, scn, ir):
        print(f"\nPartial: stance {pct(sa)} (floor {pct(sf)}, contestable {pct(scn)}), "
              f"right-invocation {pct(ir)} — code the remaining rows for the full paper sentence.",
              file=sys.stderr)
    else:
        print(f"\nPaper sentence: across {na} human-coded rationales, the scored option matched "
              f"the model's stated stance in {pct(sa)} of cases (floor {pct(sf)}, contestable {pct(scn)}); "
              f"on floor items, {pct(ir)} of {nir} rationales explicitly engaged the right at stake — "
              f"evidence the forced-choice metric reflects the model's expressed reasoning, not a "
              f"parsing artefact.")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(summary, indent=2) + "\n")
        print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
