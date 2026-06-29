"""Print a clean per-model/per-mode summary from a (possibly in-progress) stress-test artifact.

Read-only. Works on a partial checkpoint (computes the aggregate model_summary on the fly if the
run hasn't finished) so a parallel demo-drafting session can pull live numbers as modes land.
Run: python scripts/summarize_stress.py [path]   (default out/policy_delegate_stress.json)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alignment import policy_delegate_stress as P  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[1] / "out" / "policy_delegate_stress.json"


def main(path: Path) -> None:
    report = json.loads(path.read_text())
    run = report.get("run", {})
    prog = report.get("progress")
    print(f"artifact: {path}")
    print(f"simulated: {report.get('simulated')} | models: {run.get('models')}")
    if report.get("simulated"):
        print("\n** this is still the SIMULATED placeholder — the real run hasn't checkpointed yet **")
    if prog:
        print(f"progress: mode {prog['modes_done']}/{prog['modes_total']} done "
              f"(last: {prog['last_mode']}) — PARTIAL")
    else:
        print("progress: complete (final artifact)")

    if not report.get("model_summary"):
        P._add_model_summary(report)   # compute from whatever modes are present

    print("\nper-model summary (nan = mode not run yet):")
    hdr = f"  {'model':40s} {'default':>8s} {'predict':>8s} {'deleg+':>8s} {'const+':>8s} {'floor↑':>8s} {'nudge':>7s}"
    print(hdr)
    for label, s in report["model_summary"].items():
        print(f"  {label[:40]:40s} "
              f"{s.get('default_representation', float('nan')):8.2f} "
              f"{s.get('public_prediction_accuracy', float('nan')):8.2f} "
              f"{s.get('delegate_compliance', float('nan')):+8.2f} "
              f"{s.get('constitutional_nudge', float('nan')):+8.2f} "
              f"{s.get('constitutional_floor_retention', float('nan')):+8.2f} "
              f"{str(s.get('nudge_label', '—')):>7s}")
    print("\ncols: default rep · public-prediction rep · delegate gain · constitutional nudge · "
          "floor retention · nudge label")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
