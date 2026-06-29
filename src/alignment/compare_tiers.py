"""Compare steering tiers: default (frozen) vs Tier 1 (persona label) vs Tier 2 (inject the
actual distribution). The money-slide comparison — representation should climb left to right.

Demo driver like loop.py: real Ollama if --model is given and a server is up, else a clearly
labelled SIMULATED model. Targets are Gate-1-approved real WVS marginals (see provenance).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alignment import provenance as P
from alignment.instrument import measure as M
from alignment.instrument import scorers as S
from alignment.loop import YEARS, load_items, load_target, target_vec
from alignment.steer import tier1_prompt as T1
from alignment.steer import tier2_preference as T2

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"


class TierSimModel:
    """SIMULATED model that responds more strongly to a richer alignment signal: it blends
    its centrist prior toward the target by `a1` under a Tier-1 persona and by the larger
    `a2` under Tier-2 preference injection (a model follows an explicit distribution better
    than a label). Detects tier by stable marker phrases. Numbers are synthetic."""

    def __init__(self, items, target, a1: float = 0.45, a2: float = 0.92, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.by_text = {it["prompt_text"]: it for it in items}
        self.target = target
        self.a1, self.a2 = a1, a2
        self.defaults = {it["id"]: np.array([0.20, 0.30, 0.30, 0.20]) for it in items}

    def __call__(self, prompt: str) -> str:
        item = next((it for txt, it in self.by_text.items() if txt in prompt), None)
        if item is None:
            return ""
        dist = self.defaults[item["id"]].copy()
        tgt = target_vec(item, self.target)
        if "were distributed approximately" in prompt:      # Tier 2
            dist = (1 - self.a2) * dist + self.a2 * tgt
        elif "median adult" in prompt:                       # Tier 1
            dist = (1 - self.a1) * dist + self.a1 * tgt
        dist = dist / dist.sum()
        return str(int(self.rng.choice(len(dist), p=dist)) + 1)


def pick_elicitor(items, target, model):
    real = M.real_elicitor(model)
    if real:
        return real
    return TierSimModel(items, target), "SIMULATED (no model — plumbing only)"


def run(country: str = "GBR", wave: int = 7, model: str | None = None, n_samples: int = 300) -> dict:
    items = [it for it in load_items() if it["class"] == "contestable"]
    target = load_target(country, wave)
    year = YEARS[(country, wave)]
    elicitor, mode = pick_elicitor(load_items(), target, model)
    debias = "SIMULATED" not in mode   # option-order debiasing for real models only

    default = M.measure(elicitor, items, n_samples=n_samples, shuffle=debias)
    tier1 = M.measure(elicitor, items, n_samples=n_samples, shuffle=debias,
                      conditioning=T1.persona(country, year))

    report = {"country": country, "wave": wave, "mode": mode,
              "synthetic_targets": P.targets_are_synthetic(),
              "caveats": P.baseline_caveats(country, [wave]), "items": {}}
    for it in items:
        tgt = target_vec(it, target)
        cond2 = T2.preference(country, year, it, tgt)
        d2 = M.elicit_item_distribution(elicitor, it, n_samples=n_samples, conditioning=cond2,
                                        shuffle=debias)
        report["items"][it["id"]] = {
            "rep_default": S.representation_score(default[it["id"]], tgt),
            "rep_tier1": S.representation_score(tier1[it["id"]], tgt),
            "rep_tier2": S.representation_score(d2, tgt),
        }
    return report


def _fmt(r: dict) -> str:
    L = []
    if "SIMULATED" in r["mode"]:
        L += ["", "=" * 66, "  SIMULATED MODEL — SYNTHETIC numbers, plumbing only.", "=" * 66]
    L.append(f"\nSTEERING TIERS  ·  {r['country']} wave {r['wave']}  ·  model: {r['mode']}")
    L.append("representation should climb: default < Tier 1 (label) < Tier 2 (injected dist)\n")
    L.append(f"  {'item':24s} {'default':>8s} {'tier1':>8s} {'tier2':>8s}")
    for cid, c in r["items"].items():
        L.append(f"  {cid:24s} {c['rep_default']:8.2f} {c['rep_tier1']:8.2f} {c['rep_tier2']:8.2f}")
    return "\n".join(L)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Compare default / Tier 1 / Tier 2 steering")
    p.add_argument("--country", default="GBR")
    p.add_argument("--wave", type=int, default=7)
    p.add_argument("--model", default=None)
    p.add_argument("--samples", type=int, default=300)
    args = p.parse_args(argv)
    r = run(args.country, args.wave, args.model, args.samples)
    print(_fmt(r))
    OUT.mkdir(exist_ok=True)
    out_path = OUT / f"compare_tiers_{args.country}_w{args.wave}.json"
    out_path.write_text(json.dumps(r, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(f"\nwrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
