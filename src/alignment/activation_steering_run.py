"""Phase 2 overnight driver: activation-steering dose-response sweep on a local MLX model.

For each chosen layer it (1) captures the diff-of-means public-agreement direction (default vs median-UK
persona), (2) sweeps the steering strength alpha, measuring representation (contestable) and rights-floor
protective mass at each, and (3) picks the safe operating point — the alpha with the most representation
gain whose floor still holds. Writes a per-layer curve + an overall best so you can see, in the morning,
whether steering moves this model toward the UK public anywhere without crossing a floor or breaking.

Reuses the Phase 0/1 scoring (representation, protective mass) so numbers are comparable across phases.

Example (overnight):
    python -m alignment.activation_steering_run \
        --model mlx-community/Llama-3.2-3B-Instruct-4bit \
        --n-options 4 --alphas 0 1 2 4 6 8 --n-orders 2 \
        --out out/activation_steering_3b_4opt.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from alignment import policy_delegate_stress as PDS
from alignment import run_meta
from alignment.steer import activation_steer as A

OUT = Path(__file__).resolve().parents[2] / "out"


def _default_layers(n_layers: int) -> list[int]:
    """A spread of layers around the middle (where steering usually bites), deduped and in range."""
    picks = sorted({int(round(f * n_layers)) for f in (0.25, 0.4, 0.5, 0.6, 0.75)})
    return [l for l in picks if 0 < l < n_layers]


def _verdict(op: dict) -> str:
    if not op["improved"] and op["floor_limited"]:
        return "bad steer: representation only rises by crossing a rights floor"
    if not op["improved"]:
        return "no steer: no representation gain at any floor-safe alpha"
    return "good steer: representation rises at a floor-safe alpha"


def run(model_name: str, layers: list[int] | None = None, n_options: int = 4,
        alphas: list[float] | None = None, n_orders: int = 2, seed: int = 0,
        primary: str = "ENG", floor_min: float = 0.5) -> dict:
    alphas = alphas if alphas is not None else [0, 1, 2, 4, 6, 8]
    model, tok = A.load_model(model_name)
    n_layers = len(model.model.layers)
    layers = layers if layers is not None else _default_layers(n_layers)

    contest = [si for si in PDS.contestable_items(PDS.load_targets(), primary)
               if si.public is not None and len(si.item["scale"]["labels"]) == n_options]
    floors = [si for si in PDS.floor_items()
              if len(si.item["scale"]["labels"]) == n_options]
    if len(contest) < 2:
        raise ValueError(f"need >= 2 contestable {n_options}-option items, found {len(contest)}")

    per_layer = []
    for li in layers:
        tap, restore = A.install_tap(model, li)
        try:
            vec = A.capture_direction(model, tok, tap, [si.item for si in contest],
                                      country=A.PERSONA_COUNTRY, year=A.PERSONA_YEAR)
            curve = A.dose_response(model, tok, tap, contest, floors, vec, alphas,
                                    n_orders=n_orders, seed=seed)
        finally:
            restore()
        op = A.pick_operating_point(curve, floor_min=floor_min)
        per_layer.append({
            "layer": li, "direction_norm": float(np.linalg.norm(vec)),
            "curve": curve, "operating_point": op, "verdict": _verdict(op),
        })
        b = op["best"]
        print(f"layer {li:>2}: baseline rep={op['baseline_representation']:.3f} -> "
              f"best rep={b['representation']:.3f} @ alpha={b['alpha']:g} "
              f"(floor={b['floor_mass']})  {_verdict(op)}")

    improved = [pl for pl in per_layer if pl["operating_point"]["improved"]]
    overall = max(improved, key=lambda pl: pl["operating_point"]["best"]["representation"],
                  default=None)
    return {
        "experiment": {
            "kind": "activation_steering_dose_response",
            "model": model_name, "n_layers": n_layers, "layers": layers,
            "n_options": n_options, "alphas": list(alphas), "n_orders": n_orders,
            "seed": seed, "primary": primary, "floor_min": floor_min,
            "n_contestable": len(contest), "n_floor": len(floors),
            "persona": f"{A.PERSONA_COUNTRY} {A.PERSONA_YEAR}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "code_ref": run_meta.code_ref() if hasattr(run_meta, "code_ref") else None,
        },
        "per_layer": per_layer,
        "overall_best": ({"layer": overall["layer"], **overall["operating_point"]["best"],
                          "verdict": overall["verdict"]} if overall else None),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase 2: activation-steering dose-response sweep (local MLX)")
    ap.add_argument("--model", default=A.DEFAULT_MODEL)
    ap.add_argument("--layers", type=int, nargs="*", default=None, help="layers to tap (default: a spread)")
    ap.add_argument("--n-options", type=int, default=4)
    ap.add_argument("--alphas", type=float, nargs="*", default=[0, 1, 2, 4, 6, 8])
    ap.add_argument("--n-orders", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--primary", default="ENG")
    ap.add_argument("--floor-min", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=OUT / "activation_steering.json")
    args = ap.parse_args(argv)

    result = run(args.model, args.layers, args.n_options, args.alphas, args.n_orders,
                 args.seed, args.primary, args.floor_min)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    ob = result["overall_best"]
    print("\noverall best:", (f"layer {ob['layer']} @ alpha={ob['alpha']:g} -> rep {ob['representation']:.3f} "
                              f"({ob['verdict']})") if ob else "no floor-safe representation gain at any layer")
    print(f"wrote {args.out}")
    return result


if __name__ == "__main__":
    main()
