"""Merge per-model stress-test artifacts into one combined report.

When the panel is run as separate per-model jobs (for parallel speed), each writes its own
artifact. This stitches them back into a single report at out/policy_delegate_stress.json,
recomputing cross-model drift per item-mode and the aggregate model_summary. Partial-safe: run it
any time, on whatever the per-model checkpoints currently hold (modes a model hasn't reached show
as nan in the summary). Read-only on the inputs.

Run: python scripts/merge_stress.py [in1.json in2.json ...] [--out path]
"""
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alignment import policy_delegate_stress as P  # noqa: E402
from alignment.instrument import scorers as S  # noqa: E402

DEFAULT_INPUTS = [ROOT / "out" / f"_stress_{m}.json" for m in ("gpt", "claude", "deepseek")]
DEFAULT_OUT = ROOT / "out" / "policy_delegate_stress.json"


def main(inputs, out_path):
    reports = [json.loads(p.read_text()) for p in inputs if p.exists()]
    if not reports:
        print("no per-model artifacts found yet:", [str(p) for p in inputs])
        return
    base = json.loads(json.dumps(reports[0]))   # deep copy
    labels = []
    for r in reports:
        for m in r["run"].get("models", []):
            if m not in labels:
                labels.append(m)
    # union every model's cells into the base
    for r in reports[1:]:
        for iid, item in r["items"].items():
            bitem = base["items"].setdefault(iid, json.loads(json.dumps(item)))
            for mode, me in item["modes"].items():
                bmode = bitem["modes"].setdefault(mode, {"models": {}})
                bmode["models"].update(me["models"])
    # recompute cross-model drift per item-mode from the merged model set
    for item in base["items"].values():
        for me in item["modes"].values():
            dists = [np.array(c["dist"], dtype=float) for c in me["models"].values() if "dist" in c]
            pairs = [S.total_variation(a, b) for a, b in combinations(dists, 2)]
            me["mean_cross_model_drift"] = float(np.mean(pairs)) if pairs else 0.0
    base["run"]["models"] = labels
    base["run"]["merged_from"] = [p.name for p in inputs if p.exists()]
    base["simulated"] = False
    base.pop("progress", None)
    base["model_summary"] = {}   # _add_model_summary fills this in place
    P._add_model_summary(base)
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(base, indent=2,
                        default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    modes_per = {r["run"]["models"][0]: (r.get("progress", {}) or {}).get("modes_done", "done")
                 for r in reports}
    print(f"merged {len(reports)} model(s) -> {out_path.relative_to(ROOT)}")
    print("models:", labels)
    print("modes completed per model:", modes_per)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    out = DEFAULT_OUT
    if "--out" in args:
        i = args.index("--out"); out = Path(args[i + 1]).resolve(); del args[i:i + 2]
    inputs = [Path(a) for a in args] if args else DEFAULT_INPUTS
    main(inputs, out)
