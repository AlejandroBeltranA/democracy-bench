"""Load the real UK public-opinion targets produced by scripts/extract_public_opinion.py
(out/public_opinion/targets.json) into the item + target shape the instrument expects.

This is the bridge to the sibling BSA/SSA microdata pipeline: England (BSA, filtered by GOR)
and Scotland (SSA) distributions, by year. It turns each survey item into a forced-choice
item (question + option labels) and exposes the human target distribution per (polity, year),
so `measure`/`scorers`/`drift` can score real models against real British public opinion —
with England and Scotland kept as SEPARATE polities (an informative comparison, not one
harmonised survey).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = ROOT / "out" / "public_opinion" / "targets.json"


def available(path: Path = DEFAULT_TARGETS) -> bool:
    return path.exists()


def load(path: Path = DEFAULT_TARGETS):
    """Return (items, targets, meta).

    items   : [{id, class, domain, prompt_text, scale:{labels}, source}]
    targets : {(polity, year): {item_id: distribution}}
    meta    : {status, note, generated_at, polity_years: sorted[(polity,year)]}
    """
    blob = json.loads(Path(path).read_text())
    items, targets = [], {}
    for key, it in blob["items"].items():
        series = it["series"]
        labels = series[0]["labels"]            # same question => same option set across series
        items.append({
            "id": key, "class": it["class"], "domain": it["domain"],
            "prompt_text": it["question"],
            "scale": {"labels": labels, "type": f"cat{len(labels)}"},
            "source": {"dataset": series[0]["programme"], "variable": series[0]["variable"]},
        })
        for s in series:
            if len(s["labels"]) != len(labels):
                raise ValueError(f"{key}: series {s['dataset_id']} has a different option set")
            targets.setdefault((s["polity"], s["year"]), {})[key] = s["distribution"]
    meta = {
        "status": blob.get("status"), "note": blob.get("note"),
        "generated_at": blob.get("generated_at"),
        "polity_years": sorted(targets.keys()),
    }
    return items, targets, meta


def items_for(items, target_map):
    """Items that have a distribution in a given (polity, year) target dict."""
    return [it for it in items if it["id"] in target_map]


if __name__ == "__main__":
    items, targets, meta = load()
    print("status:", meta["status"])
    print("polity-years:", meta["polity_years"])
    print(f"{len(items)} items:")
    for it in items:
        ny = sorted(py for py, tm in targets.items() if it["id"] in tm)
        print(f"  {it['id']:24s} class={it['class']:14s} opts={len(it['scale']['labels'])}  in={ny}")
