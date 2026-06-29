#!/usr/bin/env python3
"""Build England-vs-Scotland public-opinion targets from BSA/SSA UKDA ZIPs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alignment import public_opinion as PO  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract BSA/SSA weighted public-opinion targets")
    parser.add_argument("--config", type=Path, default=PO.CONFIG)
    parser.add_argument("--out-dir", type=Path, default=PO.OUT)
    args = parser.parse_args(argv)

    cfg = PO.load_config(args.config)
    missing = PO.missing_source_files(cfg)
    if missing:
        print("Missing raw UKDA ZIP files:")
        for path in missing:
            print(f"  - {path.relative_to(PO.ROOT)}")
        return 2

    inventory = PO.build_dataset_inventory(cfg)
    problems = [
        (ds_id, ds["missing_configured_vars"])
        for ds_id, ds in inventory["datasets"].items()
        if ds["missing_configured_vars"]
    ]
    if problems:
        print("Configured variables missing from source data:")
        for ds_id, vars_ in problems:
            print(f"  - {ds_id}: {', '.join(vars_)}")
        return 1

    targets = PO.extract_targets(cfg)
    paths = PO.write_outputs(targets, inventory, args.out_dir)
    print("wrote:")
    for name, path in paths.items():
        print(f"  {name:9s} {_display_path(path)}")
    for item_id, item in targets["items"].items():
        comps = item["comparisons"]
        if comps:
            latest_year = max(c["year"] for c in comps)
            latest = [c for c in comps if c["year"] == latest_year]
            bits = [
                f"{c.get('pair', c['left'] + '/' + c['right'])} TV={c['total_variation']:.3f}"
                for c in latest
            ]
            print(f"{item_id}: {latest_year} " + " · ".join(bits))
    return 0


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PO.ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
