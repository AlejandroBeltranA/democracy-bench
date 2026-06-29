"""The demo loop: MEASURE -> STEER -> RE-MEASURE -> TRACK, one entrypoint.

Runs the full arc on one model and one polity:

  1. MEASURE  the model's *self* distribution (unconditioned)         -> default rep is LOW
  2. STEER    with a tier-1 persona toward the polity (contestable)
  3. RE-MEASURE                                                       -> steered rep RISES
  4. TRACK    steer toward an earlier wave and a later wave, compare the model's movement
              to the population's movement                            -> tracking elasticity
  +  FLOOR    floor items are NOT steered toward the majority; we report whether the model
              holds the rights-protective floor.

If a local Ollama server is running, it elicits from that real model. Otherwise it runs a
clearly-labelled SIMULATED model so the plumbing can be verified end-to-end — those numbers
are synthetic and printed under a loud banner. The population targets are Gate-1-approved
real WVS/EVS marginals (with the proxy + 2nd-person-review caveats provenance surfaces); a
SIMULATED model means the model distributions — not the targets — are a stand-in.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# Allow `python src/alignment/loop.py` to find the `alignment` package (src/ on path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alignment import provenance as P
from alignment.instrument import measure as M
from alignment.instrument import scorers as S
from alignment.steer import tier1_prompt as T1

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"

# Persona years per polity-wave. GBR W6 is the EVS2018 proxy (GB absent from WVS6), so its
# year is 2018, and the pair is reported as 'EVS2018_proxy -> WVS2022' (see SOURCES.json).
YEARS = {("GBR", 6): 2018, ("GBR", 7): 2022, ("USA", 6): 2011, ("USA", 7): 2017}


# ---- data loading --------------------------------------------------------------------

def load_items() -> list[dict]:
    return [json.loads(l) for l in (DATA / "wvs_items.jsonl").read_text().splitlines() if l.strip()]


def load_target(country: str, wave: int) -> dict:
    return json.loads((DATA / "targets" / f"target_{country}_wave{wave}.json").read_text())


def target_vec(item: dict, target: dict) -> np.ndarray:
    return np.array(target[item["source"]["var"]], dtype=float)


# ---- the simulated model (plumbing only, clearly labelled) ---------------------------

class SimulatedModel:
    """A deterministic stand-in for a real LLM, used ONLY when no Ollama server is present.

    Unconditioned it answers from a fixed centrist prior (a 'frozen' model that is off from
    any polity -> low default representation). When a persona naming a year is present it
    samples from a blend pulled `alpha` of the way toward that wave's target (steering
    'works'). This proves the loop wiring; it is NOT a model and its numbers are synthetic.
    """

    def __init__(self, items, targets_by_wave, alpha: float = 0.75, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.by_text = {it["prompt_text"]: it for it in items}
        # Illustrative priors (NOT measured): contestable items get a centrist default;
        # floor items lean protective, reflecting that aligned models reliably reject
        # anti-democratic options (e.g. a strong leader who bypasses parliament). The real
        # run replaces all of this with an actual model's elicited answers.
        self.defaults = {}
        for it in items:
            if it["class"] == "floor":
                d = np.array([0.04, 0.12, 0.34, 0.50])              # protective = high index
                if it.get("floor_dir", 1) < 0:
                    d = d[::-1]                                      # ...or low index
            else:
                d = np.array([0.20, 0.30, 0.30, 0.20])              # centrist
            self.defaults[it["id"]] = d
        self.targets_by_wave = targets_by_wave
        self.alpha = alpha

    def __call__(self, prompt: str) -> str:
        item = next((it for txt, it in self.by_text.items() if txt in prompt), None)
        if item is None:
            return ""  # unparseable item -> measure() will fail closed, as it should
        dist = self.defaults[item["id"]].copy()
        for (country, wave), year in YEARS.items():
            if wave in self.targets_by_wave and str(year) in prompt:
                tgt = target_vec(item, self.targets_by_wave[wave])
                dist = (1 - self.alpha) * dist + self.alpha * tgt
                break
        dist = dist / dist.sum()
        return str(int(self.rng.choice(len(dist), p=dist)) + 1)


def pick_elicitor(items, targets_by_wave, model: str | None):
    """Return (elicitor, mode_label). Real backend (Ollama/MLX) if a model is named, else
    the labelled simulation."""
    real = M.real_elicitor(model)
    if real:
        return real
    return SimulatedModel(items, targets_by_wave), "SIMULATED (no model — plumbing only)"


# ---- the loop ------------------------------------------------------------------------

def run(country: str = "GBR", wave_a: int = 6, wave_b: int = 7,
        model: str | None = None, n_samples: int = 32) -> dict:
    items = load_items()
    targets = {wave_a: load_target(country, wave_a), wave_b: load_target(country, wave_b)}
    year_a, year_b = YEARS[(country, wave_a)], YEARS[(country, wave_b)]

    floor_items = [it for it in items if it["class"] == "floor"]
    contest_items = [it for it in items if it["class"] == "contestable"]

    elicitor, mode = pick_elicitor(items, targets, model)
    debias = "SIMULATED" not in mode   # option-order debiasing for real models only

    # 1. MEASURE default (unconditioned) — the frozen-model gap, vs the later wave.
    default = M.measure(elicitor, contest_items, n_samples=n_samples, shuffle=debias)
    # 2-3. STEER tier1 toward the polity at each wave, RE-MEASURE.
    steered_a = M.measure(elicitor, contest_items, n_samples=n_samples, shuffle=debias,
                          conditioning=T1.persona(country, year_a))
    steered_b = M.measure(elicitor, contest_items, n_samples=n_samples, shuffle=debias,
                          conditioning=T1.persona(country, year_b))

    report = {"country": country, "waves": [wave_a, wave_b], "mode": mode,
              "synthetic_targets": P.targets_are_synthetic(),
              "caveats": P.baseline_caveats(country, [wave_a, wave_b]),
              "source_a": P.source_info(country, wave_a),
              "source_b": P.source_info(country, wave_b),
              "contestable": {}, "floor": {}}

    for it in contest_items:
        ta, tb = target_vec(it, targets[wave_a]), target_vec(it, targets[wave_b])
        rep_default = S.representation_score(default[it["id"]], tb)
        rep_steered = S.representation_score(steered_b[it["id"]], tb)
        trk = S.tracking(steered_a[it["id"]], steered_b[it["id"]], ta, tb,
                         n_model=n_samples,
                         n_target_t=report["source_a"].get("n"),
                         n_target_t1=report["source_b"].get("n"))
        report["contestable"][it["id"]] = {
            "rep_default": rep_default, "rep_steered": rep_steered,
            "rep_gain": rep_steered - rep_default, "tracking": trk,
            "labels": it["scale"]["labels"], "prompt": it["prompt_text"],
            "dist": {"target": tb.tolist(),
                     "default": default[it["id"]].tolist(),
                     "steered": steered_b[it["id"]].tolist()},
        }

    # FLOOR: not steered toward the majority — just check the model holds the floor.
    floor_default = M.measure(elicitor, floor_items, n_samples=n_samples, shuffle=debias)
    for it in floor_items:
        tb = target_vec(it, targets[wave_b])
        fl = S.floor_violation(floor_default[it["id"]], it["floor_dir"], tb)
        report["floor"][it["id"]] = {
            "held": not fl["violation"], **fl,
            "labels": it["scale"]["labels"], "prompt": it["prompt_text"],
            "dist": {"target": tb.tolist(), "default": floor_default[it["id"]].tolist()},
        }

    return report


def _fmt(report: dict) -> str:
    lines = []
    if "SIMULATED" in report["mode"]:
        lines += ["", "=" * 70,
                  "  SIMULATED MODEL — no Ollama. The distributions below come from a",
                  "  simulated model, NOT a real LLM. (Target provenance: see caveats.)",
                  "=" * 70]
    lines.append(f"\nPolity {report['country']} waves {report['waves']}  ·  model: {report['mode']}")
    sa, sb = report["source_a"]["label"], report["source_b"]["label"]
    lines.append(f"baseline: wave {report['waves'][0]}={sa}  ·  wave {report['waves'][1]}={sb}")
    for c in report["caveats"]:
        lines.append(f"  ⚠ {c}")
    lines.append("")
    lines.append("CONTESTABLE items (representation gain + tracking):")
    for cid, r in report["contestable"].items():
        t = r["tracking"]
        if t["elasticity"] is None:
            el = "n/a (no pop shift)"
        else:
            ci = t.get("elasticity_ci")
            el = f"{t['elasticity']:+.2f}" + (f" 95%CI[{ci[0]:+.2f},{ci[1]:+.2f}]" if ci else " CI n/a")
        sig = t.get("population_delta_significant")
        flag = "  ⚠pop Δ not significant" if sig is False else ""
        lines.append(
            f"  {cid:24s} rep {r['rep_default']:.2f}->{r['rep_steered']:.2f} "
            f"(+{r['rep_gain']:.2f})  elasticity={el} dir={t['direction_match']}{flag}")
    lines.append("\nFLOOR items (not steered; must hold the rights floor):")
    for fid, r in report["floor"].items():
        lines.append(f"  {fid:24s} held={r['held']}  protective_gap={r['protective_gap']:+.2f}")
    return "\n".join(lines)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Democracy Bench measure->steer->track loop")
    p.add_argument("--country", default="GBR")
    p.add_argument("--wave-a", type=int, default=6)
    p.add_argument("--wave-b", type=int, default=7)
    p.add_argument("--model", default=None, help="Ollama model name; omit for the simulation")
    p.add_argument("--samples", type=int, default=32)
    args = p.parse_args(argv)

    report = run(args.country, args.wave_a, args.wave_b, args.model, args.samples)
    print(_fmt(report))
    OUT.mkdir(exist_ok=True)
    out_path = OUT / f"loop_{args.country}_w{args.wave_a}{args.wave_b}.json"
    out_path.write_text(json.dumps(report, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(f"\nwrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
