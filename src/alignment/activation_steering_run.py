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
from alignment.instrument import scorers as S
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


def _summarize_holdout_layer(ho: dict, floor_min: float, B: int, seed: int) -> dict:
    """Turn one layer's raw held-out sweep (per-fold, per-alpha per-item reps) into per-alpha pooled
    gains vs the alpha=0 baseline, each with a bootstrap-over-items 95% CI, plus pooled floor mass.
    The R1 gate lives here: an alpha `survives` iff its held-out gain CI clears zero AND the pooled
    floor mass still holds (>= floor_min)."""
    by_alpha = {row["alpha"]: row for row in ho["per_alpha"]}
    if 0.0 not in by_alpha:
        raise ValueError("holdout sweep needs alpha=0 as the per-item baseline")
    base_reps = by_alpha[0.0]["held_out_reps"]

    alphas_out = []
    for row in ho["per_alpha"]:
        gains = A.held_out_gains(base_reps, row["held_out_reps"])
        gain = S.bootstrap_mean_ci(gains, B=B, seed=seed)
        floor = S.bootstrap_mean_ci(row["floor_masses"], B=B, seed=seed)
        clears_zero = bool(gain["ci"] is not None and gain["ci"][0] > 0.0)
        floor_holds = bool(floor["mean"] is None or floor["mean"] >= floor_min)
        alphas_out.append({
            "alpha": row["alpha"],
            "held_out_gain": gain,        # {mean, ci, n} over held-out items
            "floor_mass": floor,          # {mean, ci, n} over folds x floor probes
            "n_contestable_ok": row["n_contestable_ok"], "n_contestable_broke": row["n_contestable_broke"],
            "n_floor_ok": row["n_floor_ok"], "n_floor_broke": row["n_floor_broke"],
            "gain_ci_clears_zero": clears_zero,
            "floor_holds": floor_holds,
            "survives": bool(clears_zero and floor_holds and row["alpha"] != 0.0),
        })
    survivors = [a for a in alphas_out if a["survives"]]
    best = max(survivors, key=lambda a: a["held_out_gain"]["mean"], default=None)
    return {"folds": ho["folds"], "k": ho["k"], "n_orders": ho["n_orders"],
            "per_alpha": alphas_out,
            "best_surviving_alpha": (best["alpha"] if best else None),
            "survives": bool(survivors)}


def run_holdout(model_name: str, layers: list[int], alphas: list[float], k: int = 4,
                n_options: int = 4, n_orders: int = 4, seed: int = 0, primary: str = "ENG",
                floor_min: float = 0.5, boot: int = 2000) -> dict:
    """R1 driver: k-fold held-out direction capture at each layer. Direction captured on train
    contestable items, representation scored on held-out test items only; floors always evaluated,
    never captured on. Reports per-(layer, alpha) held-out gain CI and whether it clears zero."""
    alphas = [0.0] + [float(a) for a in alphas if float(a) != 0.0]   # baseline first, deduped
    model, tok = A.load_model(model_name)
    n_layers = len(model.model.layers)

    contest = [si for si in PDS.contestable_items(PDS.load_targets(), primary)
               if si.public is not None and len(si.item["scale"]["labels"]) == n_options]
    floors = [si for si in PDS.floor_items()
              if len(si.item["scale"]["labels"]) == n_options]
    if len(contest) < k:
        raise ValueError(f"need >= k={k} contestable {n_options}-option items, found {len(contest)}")

    per_layer = []
    for li in layers:
        tap, restore = A.install_tap(model, li)
        try:
            ho = A.holdout_dose_response(model, tok, tap, contest, floors, alphas,
                                         k=k, n_orders=n_orders, seed=seed,
                                         country=A.PERSONA_COUNTRY, year=A.PERSONA_YEAR)
        finally:
            restore()
        summ = _summarize_holdout_layer(ho, floor_min, boot, seed)
        per_layer.append({"layer": li, **summ})
        for a in summ["per_alpha"]:
            if a["alpha"] == 0.0:
                continue
            g, f = a["held_out_gain"], a["floor_mass"]
            ci = g["ci"]
            print(f"layer {li:>2} a={a['alpha']:>4g}: held-out gain "
                  f"{g['mean']:+.3f} CI[{ci[0]:+.3f},{ci[1]:+.3f}] "
                  f"floor={f['mean']:.3f}  {'SURVIVES' if a['survives'] else '-'}")

    survives = any(pl["survives"] for pl in per_layer)
    return {
        "run": run_meta.run_block(
            command="python -m alignment.activation_steering_run --holdout",
            models=[model_name], schema_version=1,
            extra={"kind": "activation_steering_holdout", "n_layers": n_layers,
                   "layers": layers, "alphas": alphas, "k_folds": k, "n_orders": n_orders,
                   "seed": seed, "n_options": n_options, "primary": primary,
                   "floor_min": floor_min, "n_bootstrap": boot,
                   "n_contestable": len(contest), "n_floor": len(floors),
                   "persona": f"{A.PERSONA_COUNTRY} {A.PERSONA_YEAR}"}),
        "per_layer": per_layer,
        "survives": survives,
        "gate": ("R1 SURVIVES: held-out gain CI clears zero at a floor-safe alpha somewhere"
                 if survives else
                 "R1 KILLED: no layer/alpha has a held-out gain CI clearing zero with floors held"),
    }


def _curve_gain(curve: list[dict]) -> dict:
    """Per-alpha representation gain vs the alpha=0 row of the same curve ({alpha: gain}); alphas whose
    representation broke (None) are omitted. Also returns the alpha=0 baseline representation."""
    base_row = min(curve, key=lambda r: abs(r["alpha"]))
    base = base_row["representation"]
    gains = {r["alpha"]: (r["representation"] - base)
             for r in curve if r["representation"] is not None and base is not None}
    return {"baseline": base, "gains": gains}


def _randctrl_comparison(real_curve: list[dict], random_curves: list[list[dict]]) -> list[dict]:
    """Per-alpha: real representation gain vs the spread of matched-norm random-direction gains (over
    seeds). `real_exceeds_random` flags alphas where the captured direction beats EVERY random draw —
    the only cells where the direction plausibly carries structure a random perturbation does not."""
    real = _curve_gain(real_curve)
    rand = [_curve_gain(c) for c in random_curves]
    out = []
    for a in sorted(real["gains"]):
        if a == min(real["gains"], key=abs):     # skip the alpha=0 baseline row (gain 0 by construction)
            pass
        rg = [c["gains"][a] for c in rand if a in c["gains"]]
        row = {
            "alpha": a,
            "real_rep_gain": real["gains"][a],
            "random_rep_gain_mean": float(np.mean(rg)) if rg else None,
            "random_rep_gain_min": float(np.min(rg)) if rg else None,
            "random_rep_gain_max": float(np.max(rg)) if rg else None,
            "n_random_ok": len(rg),
            "real_exceeds_random": bool(rg and real["gains"][a] > max(rg)),
        }
        out.append(row)
    return out


def run_randctrl(model_name: str, layers: list[int], alphas: list[float], seeds: list[int],
                 n_options: int = 4, n_orders: int = 2, primary: str = "ENG",
                 floor_min: float = 0.5) -> dict:
    """R2 driver: matched-norm random-direction control. At each layer, capture the real diff-of-means
    direction and run its (in-sample) dose-response, then for each seed inject a random vector of the
    SAME norm and run the same sweep. If random moves representation as much as the captured direction,
    the effect is perturbation noise. Complements R1: R1 showed no generalization, R2 asks whether the
    in-sample bump was even direction-specific."""
    alphas = [0.0] + [float(a) for a in alphas if float(a) != 0.0]
    model, tok = A.load_model(model_name)
    n_layers = len(model.model.layers)

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
            norm = float(np.linalg.norm(vec))
            real_curve = A.dose_response(model, tok, tap, contest, floors, vec, alphas,
                                         n_orders=n_orders, seed=0)
            random_curves = []
            for s in seeds:
                rvec = A.random_direction(vec.shape[0], norm, seed=s)
                random_curves.append(A.dose_response(model, tok, tap, contest, floors, rvec, alphas,
                                                     n_orders=n_orders, seed=0))
        finally:
            restore()
        comp = _randctrl_comparison(real_curve, random_curves)
        beats = any(r["real_exceeds_random"] for r in comp)
        verdict = ("in-sample structure: captured direction beats every random draw at some alpha "
                   "(but R1 shows it does not generalize across items)" if beats else
                   "perturbation noise: a matched-norm random vector moves representation as much as "
                   "the captured direction")
        per_layer.append({
            "layer": li, "direction_norm": norm, "random_seeds": list(seeds),
            "real_curve": real_curve, "random_curves": random_curves,
            "comparison": comp, "verdict": verdict,
        })
        for r in comp:
            if r["alpha"] == 0.0:
                continue
            print(f"layer {li:>2} a={r['alpha']:>4g}: real gain {r['real_rep_gain']:+.3f} vs "
                  f"random [{r['random_rep_gain_min']:+.3f},{r['random_rep_gain_max']:+.3f}]"
                  f"  {'REAL>RANDOM' if r['real_exceeds_random'] else 'within noise'}")

    any_structure = any("structure" in pl["verdict"] for pl in per_layer)
    return {
        "run": run_meta.run_block(
            command="python -m alignment.activation_steering_run --direction random",
            models=[model_name], schema_version=1,
            extra={"kind": "activation_steering_randctrl", "n_layers": n_layers,
                   "layers": layers, "alphas": alphas, "seeds": list(seeds), "n_orders": n_orders,
                   "n_options": n_options, "primary": primary, "floor_min": floor_min,
                   "n_contestable": len(contest), "n_floor": len(floors),
                   "persona": f"{A.PERSONA_COUNTRY} {A.PERSONA_YEAR}"}),
        "per_layer": per_layer,
        "any_in_sample_structure": any_structure,
        "verdict": ("R2: captured direction beats matched-norm random somewhere in-sample"
                    if any_structure else
                    "R2: steering effect is indistinguishable from matched-norm random perturbation"),
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
    ap.add_argument("--holdout", type=int, default=0,
                    help="if >0, run R1 k-fold held-out capture with this many folds instead of the sweep")
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap resamples for held-out gain CIs")
    ap.add_argument("--direction", choices=["captured", "random"], default="captured",
                    help="'random' runs the R2 matched-norm random-direction control")
    ap.add_argument("--seeds", type=int, nargs="*", default=[0, 1, 2],
                    help="random-vector seeds for --direction random")
    ap.add_argument("--out", type=Path, default=OUT / "activation_steering.json")
    args = ap.parse_args(argv)

    if args.direction == "random":
        if args.layers is None:
            ap.error("--direction random requires explicit --layers (e.g. --layers 11)")
        result = run_randctrl(args.model, args.layers, args.alphas, args.seeds,
                              n_options=args.n_options, n_orders=args.n_orders,
                              primary=args.primary, floor_min=args.floor_min)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))
        print("\n" + result["verdict"])
        print(f"wrote {args.out}")
        return result

    if args.holdout:
        if args.layers is None:
            ap.error("--holdout requires explicit --layers (e.g. --layers 11 14)")
        result = run_holdout(args.model, args.layers, args.alphas, k=args.holdout,
                             n_options=args.n_options, n_orders=args.n_orders, seed=args.seed,
                             primary=args.primary, floor_min=args.floor_min, boot=args.boot)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))
        print("\n" + result["gate"])
        print(f"wrote {args.out}")
        return result

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
