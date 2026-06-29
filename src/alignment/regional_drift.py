"""Regional decision-drift against public-opinion targets.

This bridges the public-opinion extraction layer into the decision-drift frame: for each
comparable item, elicit a model distribution and score which regional public target it sits
closest to.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alignment import public_opinion as PO
from alignment import run_meta
from alignment.instrument import measure as M
from alignment.instrument import scorers as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"


def _targets(path: Path | None = None) -> dict:
    p = path or (PO.OUT / "targets.json")
    if p.exists():
        return json.loads(p.read_text())
    if path:
        raise FileNotFoundError(path)
    missing = PO.missing_source_files()
    if missing:
        raise FileNotFoundError(f"missing public-opinion source file: {missing[0]}")
    return PO.extract_targets()


def comparable_items(targets: dict | None = None) -> list[dict]:
    """Latest-year items with at least two regional distributions on the same scale."""
    t = targets or _targets()
    items = []
    for item_id, item in t["items"].items():
        by_year: dict[int, list[dict]] = {}
        for series in item["series"]:
            by_year.setdefault(int(series["year"]), []).append(series)
        latest_year = None
        latest_series = None
        for year in sorted(by_year, reverse=True):
            groups: dict[tuple[str, ...], list[dict]] = {}
            for series in by_year[year]:
                groups.setdefault(tuple(series["labels"]), []).append(series)
            candidates = [group for group in groups.values() if len(group) >= 2]
            if candidates:
                latest_year = year
                latest_series = max(candidates, key=len)
                break
        if latest_year is None or latest_series is None:
            continue
        labels = latest_series[0]["labels"]
        targets_by_polity = {
            series["polity"]: {
                "label": series["label"],
                "dataset_id": series["dataset_id"],
                "distribution": np.array(series["distribution"], dtype=float),
                "n_unweighted": series["n_unweighted"],
                "n_weighted": series["n_weighted"],
            }
            for series in latest_series
        }
        items.append({
            "id": item_id,
            "domain": item["domain"],
            "class": item["class"],
            "prompt_text": item["question"],
            "scale": {"labels": labels},
            "year": latest_year,
            "targets_by_polity": targets_by_polity,
        })
    return items


class RegionalSimModel:
    """Simulation provider that samples near one polity target, or their average."""

    def __init__(self, items: list[dict], mode: str, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.by_text = {it["prompt_text"]: it for it in items}
        self.mode = mode

    def __call__(self, prompt: str) -> str:
        item = next((it for text, it in self.by_text.items() if text in prompt), None)
        if item is None:
            return ""
        targets = item["targets_by_polity"]
        if self.mode in targets:
            dist = targets[self.mode]["distribution"]
        elif self.mode == "scotland":
            dist = targets["SCO"]["distribution"]
        elif self.mode == "england":
            dist = targets["ENG"]["distribution"]
        else:
            dist = sum(t["distribution"] for t in targets.values()) / len(targets)
        return str(int(self.rng.choice(len(dist), p=dist)) + 1)


def _providers(items: list[dict], models: list[str] | None):
    if models:
        out = []
        for model in models:
            elic, label = M.real_elicitor(model)
            out.append((label, elic, True))
        return out
    polities = sorted({p for item in items for p in item["targets_by_polity"]})
    out = []
    for i, polity in enumerate(polities, start=1):
        label = next(
            item["targets_by_polity"][polity]["label"]
            for item in items if polity in item["targets_by_polity"]
        )
        out.append((f"SIM {label}-leaning provider", RegionalSimModel(items, polity, seed=i), False))
    out.append(("SIM blended provider", RegionalSimModel(items, "blend", seed=99), False))
    return out


def run(models: list[str] | None = None, n_samples: int = 200,
        targets: dict | None = None, target_path: Path | None = None) -> dict:
    items = comparable_items(targets)
    providers = _providers(items, models)
    report = {
        "mode": "real_models" if models else "simulated",
        "models": [p[0] for p in providers],
        "source": (targets or {}).get("title", "public-opinion regional targets"),
        "items": {},
    }
    report["run"] = run_meta.run_block(
        target_file=target_path or (PO.OUT / "targets.json"),
        samples=n_samples, models=[p[0] for p in providers], schema_version=1,
        extra={"shuffle_options": models is not None, "simulated": models is None})
    for label, elicitor, debias in providers:
        dists = M.measure(elicitor, items, n_samples=n_samples, shuffle=debias)
        for it in items:
            dist = dists[it["id"]]
            rep_by_polity = {
                polity: S.representation_score(dist, target["distribution"])
                for polity, target in it["targets_by_polity"].items()
            }
            best_score = max(rep_by_polity.values())
            best_polities = [
                polity for polity, score in rep_by_polity.items()
                if abs(score - best_score) < 0.02
            ]
            if len(best_polities) != 1:
                closer = "tie"
            else:
                closer = it["targets_by_polity"][best_polities[0]]["label"]
            entry = report["items"].setdefault(it["id"], {
                "domain": it["domain"],
                "year": it["year"],
                "prompt": it["prompt_text"],
                "labels": it["scale"]["labels"],
                "targets": {
                    polity: {
                        "label": target["label"],
                        "dataset_id": target["dataset_id"],
                        "distribution": target["distribution"].round(4).tolist(),
                        "n_unweighted": target["n_unweighted"],
                        "n_weighted": target["n_weighted"],
                    }
                    for polity, target in it["targets_by_polity"].items()
                },
                "models": {},
            })
            entry["models"][label] = {
                "dist": dist.round(4).tolist(),
                "rep_by_polity": rep_by_polity,
                "closer_to": closer,
            }
            if "ENG" in rep_by_polity:
                entry["models"][label]["rep_vs_england"] = rep_by_polity["ENG"]
            if "SCO" in rep_by_polity:
                entry["models"][label]["rep_vs_scotland"] = rep_by_polity["SCO"]
    return report


def _fmt(report: dict) -> str:
    lines = [f"REGIONAL DECISION DRIFT · {report['source']} · {report['mode']}"]
    for item_id, item in report["items"].items():
        target_labels = {p: t["label"] for p, t in item["targets"].items()}
        lines.append(f"\n{item_id} ({item['year']}) · targets: {', '.join(target_labels.values())}")
        for label, model in item["models"].items():
            reps = " ".join(
                f"{target_labels[p]}={score:.2f}"
                for p, score in sorted(model["rep_by_polity"].items())
            )
            lines.append(f"  {label[:32]:32s} {reps} closer={model['closer_to']}")
    return "\n".join(lines)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Score model policy preferences vs regional public targets")
    parser.add_argument("--models", nargs="*", default=None,
                        help="model ids (MLX repo id or ollama/...); omit for simulated providers")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--targets", type=Path, default=None,
                        help="public-opinion targets JSON; defaults to out/public_opinion/targets.json")
    parser.add_argument("--out", type=Path, default=OUT / "regional_drift.json")
    args = parser.parse_args(argv)
    targets = _targets(args.targets)
    report = run(args.models, args.samples, targets,
                 target_path=args.targets or (PO.OUT / "targets.json"))
    print(_fmt(report))
    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(f"\nwrote {_display_path(out_path)}")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
