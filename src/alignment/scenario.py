"""UK government-change scenario: re-align the model to a new mandate, hold the floor.

The live demo beat the project is built around. A new government (or new PM) arrives; its
program implies different stances on contestable policy items. We:

  1. MEASURE the model's default (neutral) distribution.
  2. RE-ALIGN contestable items toward the *incoming* mandate (tier-1 mandate persona).
  3. Show representation toward the incoming mandate RISE, and — comparing an outgoing-mandate
     framing to an incoming-mandate framing — show the model TRACKS the mandate shift.
  4. FLOOR: the floor item (a strong leader who bypasses parliament) is NEVER steered toward
     a mandate; we only check the model still HOLDS it. "We re-aligned policy to the new
     mandate, but we never moved the floor."

Like `loop.py`, this is a demo driver (not the Inspect scoring harness). With a local Ollama
model it elicits for real; otherwise it runs a clearly-labelled SIMULATED model. All scenario
targets are SYNTHETIC (see data/scenarios/uk_gov_change/PROVENANCE.md) until Gate 2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alignment.instrument import measure as M
from alignment.instrument import scorers as S
from alignment.loop import load_items, target_vec
from alignment.steer import tier1_prompt as T1

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "data" / "scenarios" / "uk_gov_change"
OUT = ROOT / "out"

INCOMING_LABEL = "the incoming UK government"
OUTGOING_LABEL = "the outgoing UK government"
INCOMING_YEAR, OUTGOING_YEAR = 2026, 2022


def load_mandate(name: str) -> dict:
    return json.loads((SCENARIO / name).read_text())


class ScenarioModel:
    """SIMULATED stand-in (no Ollama): centrist on contestable, protective on floor. When a
    mandate persona names the incoming/outgoing government it samples from a blend pulled
    `alpha` toward that mandate. Proves the wiring; the numbers are synthetic, not a model."""

    def __init__(self, items, mandate_in, mandate_out, alpha: float = 0.8, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.by_text = {it["prompt_text"]: it for it in items}
        self.mandate_in, self.mandate_out = mandate_in, mandate_out
        self.alpha = alpha
        self.defaults = {}
        for it in items:
            if it["class"] == "floor":
                d = np.array([0.04, 0.12, 0.34, 0.50])
                if it.get("floor_dir", 1) < 0:
                    d = d[::-1]
            else:
                d = np.array([0.20, 0.30, 0.30, 0.20])
            self.defaults[it["id"]] = d

    def __call__(self, prompt: str) -> str:
        item = next((it for txt, it in self.by_text.items() if txt in prompt), None)
        if item is None:
            return ""
        dist = self.defaults[item["id"]].copy()
        mandate = self.mandate_in if "incoming" in prompt else (
            self.mandate_out if "outgoing" in prompt else None)
        if mandate is not None:
            dist = (1 - self.alpha) * dist + self.alpha * target_vec(item, mandate)
        dist = dist / dist.sum()
        return str(int(self.rng.choice(len(dist), p=dist)) + 1)


def pick_elicitor(items, mandate_in, mandate_out, model: str | None):
    real = M.real_elicitor(model)
    if real:
        return real
    return ScenarioModel(items, mandate_in, mandate_out), "SIMULATED (no model — plumbing only)"


def run(model: str | None = None, n_samples: int = 200) -> dict:
    items = load_items()
    mandate_in, mandate_out = load_mandate("mandate_incoming.json"), load_mandate("mandate_outgoing.json")
    public = load_mandate("public_recent.json")

    contest = [it for it in items if it["class"] == "contestable"]
    floor = [it for it in items if it["class"] == "floor"]
    elicitor, mode = pick_elicitor(items, mandate_in, mandate_out, model)
    debias = "SIMULATED" not in mode   # option-order debiasing for real models only

    # contestable: default, then re-aligned to the incoming mandate; outgoing framing for tracking.
    default = M.measure(elicitor, contest, n_samples=n_samples, shuffle=debias)
    to_incoming = M.measure(elicitor, contest, n_samples=n_samples, shuffle=debias,
                            conditioning=T1.mandate_persona(INCOMING_LABEL, INCOMING_YEAR))
    to_outgoing = M.measure(elicitor, contest, n_samples=n_samples, shuffle=debias,
                            conditioning=T1.mandate_persona(OUTGOING_LABEL, OUTGOING_YEAR))

    report = {"scenario": "uk_gov_change", "mode": mode, "synthetic_targets": True,
              "contestable": {}, "floor": {}}
    for it in contest:
        m_in, m_out = target_vec(it, mandate_in), target_vec(it, mandate_out)
        rep_default = S.representation_score(default[it["id"]], m_in)
        rep_aligned = S.representation_score(to_incoming[it["id"]], m_in)
        # did the model move the way the mandate moved (outgoing -> incoming)?
        trk = S.tracking(to_outgoing[it["id"]], to_incoming[it["id"]], m_out, m_in)
        report["contestable"][it["id"]] = {
            "rep_to_incoming_default": rep_default, "rep_to_incoming_aligned": rep_aligned,
            "rep_gain": rep_aligned - rep_default, "tracking_vs_mandate_shift": trk,
            "rep_vs_public": S.representation_score(to_incoming[it["id"]], target_vec(it, public)),
        }

    # floor: NEVER steered toward a mandate — measure neutral, check it holds. The reference
    # is the PUBLIC (not a mandate): the model must be at least as rights-protective as the
    # population. A mandate is protective by construction, so it's the wrong yardstick here.
    floor_default = M.measure(elicitor, floor, n_samples=n_samples, shuffle=debias)
    for it in floor:
        fl = S.floor_violation(floor_default[it["id"]], it["floor_dir"], target_vec(it, public))
        report["floor"][it["id"]] = {"held": not fl["violation"], "steered": False,
                                     "reference": "public_recent", **fl}

    return report


def _fmt(r: dict) -> str:
    L = []
    if "SIMULATED" in r["mode"]:
        L += ["", "=" * 70,
              "  SIMULATED MODEL — no Ollama. Numbers are SYNTHETIC (plumbing only).",
              "  Scenario targets are SYNTHETIC too (Gate 2). Not a model result.",
              "=" * 70]
    L.append(f"\nUK GOVERNMENT-CHANGE SCENARIO  ·  model: {r['mode']}")
    L.append("re-align contestable policy to the incoming mandate; the floor must hold.\n")
    L.append("CONTESTABLE items — re-alignment toward the INCOMING mandate + mandate tracking:")
    for cid, c in r["contestable"].items():
        t = c["tracking_vs_mandate_shift"]
        el = "n/a" if t["elasticity"] is None else f"{t['elasticity']:+.2f}"
        L.append(f"  {cid:24s} rep {c['rep_to_incoming_default']:.2f} -> "
                 f"{c['rep_to_incoming_aligned']:.2f} (+{c['rep_gain']:.2f})   "
                 f"tracks mandate shift: elasticity={el} dir_match={t['direction_match']}")
    L.append("\nFLOOR item — NOT steered toward the mandate; must hold:")
    for fid, f in r["floor"].items():
        L.append(f"  {fid:24s} held={f['held']}  steered={f['steered']}  "
                 f"protective_gap={f['protective_gap']:+.2f}")
    return "\n".join(L)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="UK government-change re-alignment scenario")
    p.add_argument("--model", default=None, help="Ollama model; omit for the labelled simulation")
    p.add_argument("--samples", type=int, default=200)
    args = p.parse_args(argv)
    report = run(args.model, args.samples)
    print(_fmt(report))
    OUT.mkdir(exist_ok=True)
    out_path = OUT / "scenario_uk_gov_change.json"
    out_path.write_text(json.dumps(report, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(f"\nwrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
