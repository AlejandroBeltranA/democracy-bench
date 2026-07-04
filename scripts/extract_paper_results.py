#!/usr/bin/env python3
"""Extract every headline number the Democracy-Bench paper arc needs from the
committed out/*.json artifacts.

This is PURE EXTRACTION. It runs no models. It fails loudly (nonzero exit,
named missing key) if an expected key is absent from an artifact — a silent
default here would put a wrong number in a paper table, the worst possible bug
in the paper-support track (docs/PAPER_SUPPORT_PLAN.md, PS1).

Usage:
    python scripts/extract_paper_results.py                 # JSON to stdout
    python scripts/extract_paper_results.py --out out/paper_results_extract.json

The output is a single JSON object, one top-level key per claim in the arc.
Every number carries the artifact path and the JSON key-path it came from.
docs/PAPER_RESULTS.md is the human-readable claim->evidence map built on top of
this; every number in that doc is meant to be traceable back to this extractor.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "out")


class MissingKey(KeyError):
    """Raised when an artifact is missing a key the paper arc depends on."""


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_paper_extract.py — numpy only)
# ---------------------------------------------------------------------------
def dig(obj, path, artifact="<obj>"):
    """Follow a key-path (list of str/int) into a nested dict/list.

    Fails loudly with the full path and artifact name if any step is absent —
    never returns a silent default.
    """
    cur = obj
    trail = []
    for key in path:
        trail.append(key)
        if isinstance(key, int):
            if not isinstance(cur, list):
                raise MissingKey(
                    f"{artifact}: expected list at {trail[:-1]!r} to index {key}, "
                    f"got {type(cur).__name__}"
                )
            if key >= len(cur) or key < -len(cur):
                raise MissingKey(
                    f"{artifact}: index {key} out of range at path {trail!r} "
                    f"(len {len(cur)})"
                )
            cur = cur[key]
        else:
            if not isinstance(cur, dict):
                raise MissingKey(
                    f"{artifact}: expected dict at {trail[:-1]!r} to read {key!r}, "
                    f"got {type(cur).__name__}"
                )
            if key not in cur:
                raise MissingKey(
                    f"{artifact}: missing key {key!r} at path {trail!r}"
                )
            cur = cur[key]
    return cur


def stat(obj, path, artifact="<obj>"):
    """Extract a {mean, ci: [lo, hi], n} stat block as a flat, rounded dict.

    Fails loudly if mean/ci are absent. n is optional (defaults to None with an
    explicit marker, never silently 0).
    """
    block = dig(obj, path, artifact)
    if not isinstance(block, dict):
        raise MissingKey(f"{artifact}: expected stat dict at {path!r}, got {type(block).__name__}")
    if "mean" not in block:
        raise MissingKey(f"{artifact}: stat block at {path!r} missing 'mean'")
    if "ci" not in block:
        raise MissingKey(f"{artifact}: stat block at {path!r} missing 'ci'")
    ci = block["ci"]
    if not (isinstance(ci, list) and len(ci) == 2):
        raise MissingKey(f"{artifact}: stat block at {path!r} 'ci' is not [lo, hi]: {ci!r}")
    return {
        "mean": block["mean"],
        "ci_lo": ci[0],
        "ci_hi": ci[1],
        "n": block.get("n"),
        "ci_clears_zero": _ci_clears_zero(block["mean"], ci),
    }


def _ci_clears_zero(mean, ci):
    """A CI 'clears zero' (is significant) if BOTH bounds lie on the same side of 0."""
    lo, hi = ci
    if lo > 0 and hi > 0:
        return True
    if lo < 0 and hi < 0:
        return True
    return False


def find_layer(per_layer, layer, artifact="<obj>"):
    """Return the per-layer block whose 'layer' == layer. Fails loudly if absent."""
    for block in per_layer:
        if block.get("layer") == layer:
            return block
    have = [b.get("layer") for b in per_layer]
    raise MissingKey(f"{artifact}: no per_layer block for layer {layer} (have {have})")


def find_alpha(per_alpha, alpha, artifact="<obj>"):
    """Return the per-alpha block whose 'alpha' == alpha. Fails loudly if absent."""
    for block in per_alpha:
        if block.get("alpha") == alpha:
            return block
    have = [b.get("alpha") for b in per_alpha]
    raise MissingKey(f"{artifact}: no per_alpha block for alpha {alpha} (have {have})")


def curve_point(curve, alpha, field, artifact="<obj>"):
    """Read a scalar field at a given alpha from a [{alpha, <field>...}] curve."""
    blk = find_alpha(curve, float(alpha), artifact)
    if field not in blk:
        raise MissingKey(f"{artifact}: curve point alpha={alpha} missing {field!r}")
    return blk[field]


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def load(name):
    """Load an out/ artifact by basename; fail loudly if the file is absent."""
    path = os.path.join(OUT_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"expected artifact not found: {path}")
    with open(path) as fh:
        return json.load(fh), os.path.join("out", name)


# ---------------------------------------------------------------------------
# Per-claim extractors. Each returns {source, keys, numbers, caveats}.
# ---------------------------------------------------------------------------
def extract_phase1_logit_bias():
    """Phase 1 — logit-bias negative. A single global logit bias does not
    generalise to held-out items. Real-logprobs artifacts on gpt-4o-mini +
    the multi-model sampled sweep."""
    lp4, p4 = load("logit_bias_calibration_logprobs_gpt4omini_4opt.json")
    lp5, p5 = load("logit_bias_calibration_logprobs_gpt4omini_5opt.json")
    sweep, ps = load("logit_bias_calibration.json")

    def _lp(obj, art):
        gain = dig(obj, ["held_out_gain"], art)
        ci = dig(obj, ["held_out_gain_ci"], art)
        return {
            "held_out_gain": gain,
            "ci_lo": ci[0],
            "ci_hi": ci[1],
            "significant_positive": dig(obj, ["held_out_gain_significant_positive"], art),
            "n_items": dig(obj, ["n_items"], art),
            "ci_clears_zero": _ci_clears_zero(gain, ci),
        }

    # The one sampled-data cell that LOOKED positive (gpt-4o-mini, 5-option),
    # which the logprobs re-run collapses to n.s. — a documented discrepancy.
    sweep5 = dig(sweep, ["by_option_length", "5_option", "results"], ps)
    gpt_5opt_sampled = None
    for r in sweep5:
        if r.get("model") == "openrouter:openai/gpt-4o-mini":
            gpt_5opt_sampled = {
                "held_out_gain": r["held_out_gain"],
                "ci_lo": r["held_out_gain_ci"][0],
                "ci_hi": r["held_out_gain_ci"][1],
                "significant_positive": r["held_out_gain_significant_positive"],
                "n_items": r["n_items"],
            }
    if gpt_5opt_sampled is None:
        raise MissingKey(f"{ps}: gpt-4o-mini not found in 5_option sampled results")

    return {
        "claim": "Phase 1: a global logit bias does not generalise to held-out items (negative).",
        "sources": [p4, p5, ps],
        "keys": [
            "held_out_gain / held_out_gain_ci / held_out_gain_significant_positive (logprobs artifacts)",
            "by_option_length.5_option.results[gpt-4o-mini] (sampled sweep)",
        ],
        "numbers": {
            "gpt4omini_logprobs_4opt": _lp(lp4, p4),
            "gpt4omini_logprobs_5opt": _lp(lp5, p5),
            "gpt4omini_5opt_sampled_LOOKED_positive": gpt_5opt_sampled,
        },
        "caveats": [
            dig(sweep, ["experiment", "caveat"], ps),
            "logit_bias_calibration.json is the SAMPLED S=24 published run (source_simulated=false but not a --logprobs elicitation). The *_logprobs_* artifacts are the real option-logprob re-runs.",
        ],
    }


def extract_phase2_steering():
    """Phase 2 — activation steering negative from multiple angles + mechanism."""
    orig, po = load("activation_steering_3b_4opt.json")
    holdout, ph = load("act_steer_holdout_3b.json")
    late, pl = load("act_steer_holdout_late_3b.json")
    ci, pci = load("act_steer_ci_3b.json")
    rand, pr = load("act_steer_randctrl_3b.json")
    neg, pn = load("act_steer_negalpha_3b.json")
    geo, pg = load("act_steer_geometry_3b.json")
    off, pf = load("act_steer_offtask_3b.json")
    per, pp = load("act_steer_personactrl_3b.json")
    w1, pw = load("act_steer_w1_cosine_3b.json")

    # Superseded original headline: L11 alpha0 -> alpha4 in-sample representation.
    orig_l11 = find_layer(dig(orig, ["per_layer"], po), 11, po)["curve"]
    orig_rep_a0 = curve_point(orig_l11, 0, "representation", po)
    orig_rep_a4 = curve_point(orig_l11, 4, "representation", po)
    best = dig(orig, ["overall_best"], po)

    # R1 held-out kill: L11 alpha2 held-out gain (significantly negative).
    ho_l11 = find_layer(dig(holdout, ["per_layer"], ph), 11, ph)
    ho_l11_a2 = find_alpha(ho_l11["per_alpha"], 2.0, ph)

    # R4 CI: L11 alpha4 headline evaporates.
    ci_l11 = find_layer(dig(ci, ["per_layer"], pci), 11, pci)
    ci_l11_a4 = find_alpha(ci_l11["per_alpha"], 4.0, pci)

    # W3 geometry: mean off-diagonal cosine at L11 and at L21 (0.56-0.82 band),
    # plus within/cross domain fracture at L21.
    geo_l11 = find_layer(dig(geo, ["per_layer"], pg), 11, pg)
    geo_l21 = find_layer(dig(geo, ["per_layer"], pg), 21, pg)

    # R7 off-task capability cost.
    off_l11 = find_layer(dig(off, ["per_layer"], pf), 11, pf)
    off_acc = {str(int(a["alpha"])): a["off_task_accuracy"] for a in off_l11["per_alpha"]}

    # R8 wrong-persona control.
    per_l11 = find_layer(dig(per, ["per_layer"], pp), 11, pp)

    # P0 / W1 kill-check cosine.
    w1_l11 = find_layer(dig(w1, ["per_layer"], pw), 11, pw)

    return {
        "claim": "Phase 2: activation steering does NOT implement per-item public representation (negative), with a persona-generic-axis mechanism.",
        "sources": [po, ph, pl, pci, pr, pn, pg, pf, pp, pw],
        "keys": [
            "activation_steering_3b_4opt: per_layer[L11].curve (superseded in-sample headline)",
            "act_steer_holdout_3b: survives, gate, per_layer[L11].per_alpha[a2].held_out_gain",
            "act_steer_holdout_late_3b: survives, gate",
            "act_steer_ci_3b: per_layer[L11].per_alpha[a4].gain, good_steer_layers",
            "act_steer_randctrl_3b: verdict, any_in_sample_structure",
            "act_steer_negalpha_3b: any_antisymmetric",
            "act_steer_geometry_3b: per_layer[L].mean_offdiag_cosine / within_domain_cosine / cross_domain_cosine",
            "act_steer_offtask_3b: per_layer[L11].per_alpha[*].off_task_accuracy",
            "act_steer_personactrl_3b: per_layer[L11].cosine_real_control",
            "act_steer_w1_cosine_3b: all_layers_kill_tracking, per_layer[L].cosine_2022_2024",
        ],
        "numbers": {
            "superseded_original": {
                "layer": 11,
                "representation_alpha0": orig_rep_a0,
                "representation_alpha4": orig_rep_a4,
                "overall_best_layer": best["layer"],
                "overall_best_alpha": best["alpha"],
                "overall_best_representation": best["representation"],
                "note": "SUPERSEDED: in-sample inject-then-score-same-16-items confound; killed by R1/R4.",
            },
            "R1_holdout": {
                "survives": dig(holdout, ["survives"], ph),
                "gate": dig(holdout, ["gate"], ph),
                "L11_alpha2_held_out_gain": stat(ho_l11_a2, ["held_out_gain"], ph),
                "L11_alpha2_floor_mass": stat(ho_l11_a2, ["floor_mass"], ph),
            },
            "R1_holdout_late_layers": {
                "layers": dig(late, ["run", "layers"], pl),
                "survives": dig(late, ["survives"], pl),
                "gate": dig(late, ["gate"], pl),
            },
            "R4_ci": {
                "good_steer_layers": dig(ci, ["good_steer_layers"], pci),
                "verdict": dig(ci, ["verdict"], pci),
                "L11_alpha4_gain": stat(ci_l11_a4, ["gain"], pci),
                "L11_alpha4_floor_mass": stat(ci_l11_a4, ["floor_mass"], pci),
                "L11_alpha4_floor_ci_above_min": dig(ci_l11_a4, ["floor_ci_above_min"], pci),
            },
            "R2_randctrl": {
                "verdict": dig(rand, ["verdict"], pr),
                "any_in_sample_structure": dig(rand, ["any_in_sample_structure"], pr),
            },
            "R3_negdose": {
                "any_antisymmetric": dig(neg, ["any_antisymmetric"], pn),
            },
            "W3_geometry": {
                "L11_mean_offdiag_cosine": dig(geo_l11, ["mean_offdiag_cosine"], pg),
                "L21_mean_offdiag_cosine": dig(geo_l21, ["mean_offdiag_cosine"], pg),
                "L11_within_domain_cosine": dig(geo_l11, ["within_domain_cosine"], pg),
                "L11_cross_domain_cosine": dig(geo_l11, ["cross_domain_cosine"], pg),
                "L21_within_domain_cosine": dig(geo_l21, ["within_domain_cosine"], pg),
                "L21_cross_domain_cosine": dig(geo_l21, ["cross_domain_cosine"], pg),
            },
            "R7_offtask": {
                "baseline_accuracy": dig(off_l11, ["baseline_accuracy"], pf),
                "off_task_accuracy_by_alpha": off_acc,
            },
            "R8_personactrl": {
                "cosine_real_control": dig(per_l11, ["cosine_real_control"], pp),
                "real_direction_norm": dig(per_l11, ["real_direction_norm"], pp),
                "control_direction_norm": dig(per_l11, ["control_direction_norm"], pp),
            },
            "P0_W1_cosine_killcheck": {
                "all_layers_kill_tracking": dig(w1, ["all_layers_kill_tracking"], pw),
                "verdict": dig(w1, ["verdict"], pw),
                "L11_cosine_2022_2024": dig(w1_l11, ["cosine_2022_2024"], pw),
                "L7_cosine_2022_2024": dig(find_layer(w1["per_layer"], 7, pw), ["cosine_2022_2024"], pw),
                "L14_cosine_2022_2024": dig(find_layer(w1["per_layer"], 14, pw), ["cosine_2022_2024"], pw),
            },
        },
        "caveats": [
            "Single model: mlx-community/Llama-3.2-3B-Instruct-4bit (3B, 4-bit).",
            "16 four-option contestable ENG items (the steering drivers' n_options==4 filter), 12 floor probes.",
            "R8 control persona = 'a subsistence farmer in the year 1850'; cos to the real UK-2024 direction = 0.852 => axis is persona-generic.",
        ],
    }


def extract_p2_fidelity():
    """P2 — baseline deference fidelity gap + heterogeneity."""
    d, p = load("evidcond_baseline_3b.json")
    hd = dig(d, ["headline"], p)
    items = dig(d, ["items"], p)
    n_worse = sum(1 for it in items if it.get("delta", 0.0) < 0.0)
    boc = dig(d, ["by_option_count"], p)
    return {
        "claim": "P2: untuned evidence-conditioning is a weak, heterogeneous lift — 25% fidelity gap, 24/50 items get WORSE.",
        "sources": [p],
        "keys": ["headline.{no_evidence,evidence,delta,fidelity_gap}", "items[].delta", "by_option_count.{3,4,5}"],
        "numbers": {
            "no_evidence_rep": stat(hd, ["no_evidence"], p),
            "evidence_rep": stat(hd, ["evidence"], p),
            "delta": stat(hd, ["delta"], p),
            "fidelity_gap": dig(hd, ["fidelity_gap"], p),
            "n_items": len(items),
            "n_items_worse_with_evidence": n_worse,
            "by_option_count": {
                k: {"delta": stat(boc[k], ["delta"], p), "fidelity_gap": dig(boc[k], ["fidelity_gap"], p), "n_items": dig(boc[k], ["n_items"], p)}
                for k in ("3", "4", "5")
            },
            "floors_no_evidence": stat(dig(d, ["floors"], p), ["no_evidence"], p),
            "floors_delta": stat(dig(d, ["floors"], p), ["delta"], p),
        },
        "caveats": [
            "50 contestable ENG items (29 five-opt, 16 four-opt, 5 three-opt); n_orders=2; untuned 3B-4bit.",
            "Floor condition (b) is the floor's OWN elicitation (no synthetic hostile evidence — that is P4); delta 0 by construction.",
        ],
    }


def extract_p3_tracking():
    """P3 — evidence tracking positive (the flagship)."""
    d, p = load("evidcond_tracking_3b.json")
    hd = dig(d, ["headline"], p)
    return {
        "claim": "P3: evidence-in-context tracks the REAL 2022->2024 public shift (flagship positive) — direction 8/10, elasticity +0.395.",
        "sources": [p],
        "keys": ["headline.{direction_match_count,direction_match_rate,elasticity,n_model_moved,n_trackable}"],
        "numbers": {
            "n_items": dig(hd, ["n_items"], p),
            "n_trackable": dig(hd, ["n_trackable"], p),
            "direction_match_count": dig(hd, ["direction_match_count"], p),
            "direction_match_rate": dig(hd, ["direction_match_rate"], p),
            "elasticity": stat(hd, ["elasticity"], p),
            "n_model_moved": dig(hd, ["n_model_moved"], p),
        },
        "caveats": dig(d, ["caveats"], p),
    }


def extract_p4_floors():
    """P4 — hostile-evidence floor crack (safety headline)."""
    d, p = load("evidcond_floors_3b.json")
    hd = dig(d, ["headline"], p)

    def _cond(name):
        c = dig(hd, [name], p)
        return {
            "floor_mass": stat(c, ["floor_mass"], p),
            "delta_vs_baseline": stat(c, ["delta_vs_baseline"], p),
            "n_below_floor": dig(c, ["n_below_floor"], p),
            "floor_min": dig(c, ["floor_min"], p),
        }

    return {
        "claim": "P4: SYNTHETIC hostile evidence alone cracks EVERY floor (0.512->0.318, 12/12 below 0.5); the adversarial prompt alone is n.s.",
        "sources": [p],
        "keys": ["headline.{baseline,hostile_evidence,adversarial_prompt,both}.{floor_mass,delta_vs_baseline,n_below_floor}"],
        "numbers": {
            "baseline": _cond("baseline"),
            "hostile_evidence": _cond("hostile_evidence"),
            "adversarial_prompt": _cond("adversarial_prompt"),
            "both": _cond("both"),
        },
        "caveats": dig(d, ["caveats"], p),
    }


def extract_p5_lora():
    """P5a/P5b — LoRA deference negative."""
    des, pd = load("lora_deference_design.json")
    d, p = load("evidcond_lora_eval_3b.json")

    fid = dig(d, ["fidelity_heldout"], p)
    trk = dig(d, ["tracking_heldout"], p)
    fl = dig(d, ["floors"], p)
    off = dig(d, ["offtask"], p)
    mem = dig(d, ["memorisation_guard"], p)
    hom = dig(d, ["homogenisation"], p)

    return {
        "claim": "P5: naive 'deference-where-due' LoRA FAILS (4/6 criteria) — kills tracking, degrades baseline floors, homogenises answers, and collapses off-task generation.",
        "sources": [pd, p],
        "keys": [
            "fidelity_heldout.{evidence.delta,n_worse_by_0.05}",
            "tracking_heldout.{untuned,tuned}.{direction_match_count,elasticity}",
            "floors.{delta_baseline,delta_hostile_evidence}",
            "offtask.{untuned_accuracy,tuned_accuracy}",
            "memorisation_guard.{train_no_evidence.delta,heldout_no_evidence.delta}",
            "homogenisation.{mean_pairwise_tv_untuned,mean_pairwise_tv_tuned}",
        ],
        "numbers": {
            "split": {
                "n_train": len(dig(des, ["split", "train"], pd)),
                "n_heldout": len(dig(des, ["split", "heldout"], pd)),
                "sig_heldout": dig(des, ["split", "sig_in_heldout"], pd),
                "n_sig_heldout": dig(des, ["split", "n_sig_heldout"], pd),
            },
            "fidelity_heldout_delta": stat(dig(fid, ["evidence"], p), ["delta"], p),
            "fidelity_heldout_n_worse_by_0.05": dig(fid, ["n_worse_by_0.05"], p),
            "tracking_untuned_direction_count": dig(trk, ["untuned", "direction_match_count"], p),
            "tracking_untuned_elasticity": stat(dig(trk, ["untuned"], p), ["elasticity"], p),
            "tracking_tuned_direction_count": dig(trk, ["tuned", "direction_match_count"], p),
            "tracking_tuned_elasticity": stat(dig(trk, ["tuned"], p), ["elasticity"], p),
            "floors_baseline_cross_delta": stat(dig(fl, ["delta_baseline"], p), ["delta"], p),
            "floors_hostile_cross_delta": stat(dig(fl, ["delta_hostile_evidence"], p), ["delta"], p),
            "offtask_untuned_accuracy": dig(off, ["untuned_accuracy"], p),
            "offtask_tuned_accuracy": dig(off, ["tuned_accuracy"], p),
            "memorisation_train_delta": stat(dig(mem, ["train_no_evidence"], p), ["delta"], p),
            "memorisation_heldout_delta": stat(dig(mem, ["heldout_no_evidence"], p), ["delta"], p),
            "homogenisation_tv_untuned": dig(hom, ["mean_pairwise_tv_untuned"], p),
            "homogenisation_tv_tuned": dig(hom, ["mean_pairwise_tv_tuned"], p),
        },
        "caveats": dig(d, ["caveats"], p),
    }


def extract_g1_guards():
    """G1 — prompt-level floor guards all fail; provenance backfires."""
    d, p = load("floorguard_grid_3b.json")
    arms = dig(d, ["headline", "arms"], p)
    ref = dig(d, ["headline", "no_guard_reference"], p)

    out = {}
    for name in ("no_guard", "guard_provenance", "guard_rights_floor", "guard_constitution", "guard_combined"):
        a = dig(arms, [name], p)
        fbc = dig(a, ["floor_by_condition"], p)
        entry = {
            "hostile_floor_mass": stat(dig(fbc, ["hostile_evidence"], p), ["floor_mass"], p),
            "baseline_floor_mass": stat(dig(fbc, ["baseline"], p), ["floor_mass"], p),
            "hostile_below_floor": dig(fbc, ["hostile_evidence", "n_below_floor"], p),
            "hostile_mean_pairwise_tv": dig(a, ["hostile_mean_pairwise_tv"], p),
        }
        if name != "no_guard":
            entry["hostile_delta_vs_no_guard"] = stat(a, ["hostile_evidence_delta_vs_no_guard"], p)
            entry["baseline_delta_vs_no_guard"] = stat(a, ["baseline_delta_vs_no_guard"], p)
            entry["baseline_degraded"] = dig(a, ["baseline_degraded"], p)
            entry["verdict"] = dig(a, ["verdict"], p)
        out[name] = entry

    return {
        "claim": "G1: all four prompt-level guards FAIL; guard_provenance BACKFIRES (lowers hostile floor mass and degrades baseline); guard_constitution recovers only partially and homogenises.",
        "sources": [p],
        "keys": [
            "replication_check.{no_guard_baseline_floor_mass,no_guard_hostile_floor_mass}",
            "headline.arms[*].{hostile_floor_mass,baseline_floor_mass,hostile_below_floor,hostile_mean_pairwise_tv,*_delta_vs_no_guard,baseline_degraded,verdict}",
        ],
        "numbers": {
            "replication_check": dig(d, ["replication_check"], p),
            "no_guard_reference": {
                "baseline_floor_mass": stat(ref, ["baseline_floor_mass"], p),
                "hostile_evidence_floor_mass": stat(ref, ["hostile_evidence_floor_mass"], p),
                "hostile_below_floor": dig(ref, ["hostile_below_floor"], p),
                "hostile_mean_pairwise_tv": dig(ref, ["hostile_mean_pairwise_tv"], p),
            },
            "arms": out,
        },
        "caveats": dig(d, ["caveats"], p),
    }


def extract_model_robustness_8b():
    """Phase 5 — 8B replication of the core P2/P3/P4/G1-subset battery.

    Reads the four `_8b` artifacts (Meta-Llama-3.1-8B-Instruct-4bit) with the
    SAME fail-loud contract as the 3B extractors above. This section carries
    ONLY the 8B numbers; the side-by-side vs 3B lives in docs/PAPER_RESULTS.md
    (which reads both this section and the 3B sections). Verdicts per claim:
      - P2 fidelity: evidence lift n.s. on both -> REPLICATES; 8B is a stronger
        baseline floor-holder (0.707 vs 0.512) -> that ONE sub-number does not.
      - P3 tracking: 8/10 direction + elasticity CI clears zero -> REPLICATES.
      - P4 floors: hostile-evidence crack REPLICATES (deeper, ~3x); prompt-attack
        channel asymmetry REPLICATES (sharper).
      - G1 guards: both prompt guards still FAIL on both sizes -> REPLICATES;
        8B recovery is genuine per-probe (TV RISES, not homogenised) yet insufficient.
    """
    base, pb = load("evidcond_baseline_8b.json")
    trk, pt = load("evidcond_tracking_8b.json")
    fl, pf = load("evidcond_floors_8b.json")
    gg, pg = load("floorguard_grid_8b.json")

    # --- P2 fidelity (8B) ---
    bhd = dig(base, ["headline"], pb)
    bitems = dig(base, ["items"], pb)
    b_n_worse = sum(1 for it in bitems if it.get("delta", 0.0) < 0.0)

    # --- P4 floors (8B) ---
    fhd = dig(fl, ["headline"], pf)

    def _cond(name):
        c = dig(fhd, [name], pf)
        return {
            "floor_mass": stat(c, ["floor_mass"], pf),
            "delta_vs_baseline": stat(c, ["delta_vs_baseline"], pf),
            "n_below_floor": dig(c, ["n_below_floor"], pf),
            "floor_min": dig(c, ["floor_min"], pf),
        }

    # --- G1 guard subset (8B: no_guard, guard_rights_floor, guard_constitution) ---
    arms = dig(gg, ["headline", "arms"], pg)
    guard_out = {}
    for name in ("no_guard", "guard_rights_floor", "guard_constitution"):
        a = dig(arms, [name], pg)
        fbc = dig(a, ["floor_by_condition"], pg)
        entry = {
            "hostile_floor_mass": stat(dig(fbc, ["hostile_evidence"], pg), ["floor_mass"], pg),
            "baseline_floor_mass": stat(dig(fbc, ["baseline"], pg), ["floor_mass"], pg),
            "hostile_below_floor": dig(fbc, ["hostile_evidence", "n_below_floor"], pg),
            "hostile_mean_pairwise_tv": dig(a, ["hostile_mean_pairwise_tv"], pg),
        }
        if name != "no_guard":
            entry["hostile_delta_vs_no_guard"] = stat(a, ["hostile_evidence_delta_vs_no_guard"], pg)
            entry["baseline_delta_vs_no_guard"] = stat(a, ["baseline_delta_vs_no_guard"], pg)
            entry["baseline_degraded"] = dig(a, ["baseline_degraded"], pg)
            entry["verdict"] = dig(a, ["verdict"], pg)
        guard_out[name] = entry

    return {
        "claim": "Phase 5 (8B replication): P2 lift n.s. + P3 8/10 tracking + P4 hostile-evidence crack + G1 prompt-guard failure ALL REPLICATE on Meta-Llama-3.1-8B-Instruct-4bit; the ONE non-replication is 8B being a much stronger BASELINE floor-holder (0.707 vs 3B 0.512), yet it cracks ~3x deeper under hostile evidence.",
        "model_under_test": "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit (8B, 4-bit)",
        "sources": [pb, pt, pf, pg],
        "keys": [
            "evidcond_baseline_8b: headline.{no_evidence,evidence,delta,fidelity_gap}, items[].delta, floors.no_evidence",
            "evidcond_tracking_8b: headline.{direction_match_count,direction_match_rate,elasticity,n_model_moved}",
            "evidcond_floors_8b: headline.{baseline,hostile_evidence,adversarial_prompt,both}.{floor_mass,delta_vs_baseline,n_below_floor}",
            "floorguard_grid_8b: replication_check, headline.arms[{no_guard,guard_rights_floor,guard_constitution}].{floor_by_condition,*_delta_vs_no_guard,baseline_degraded,verdict}",
        ],
        "numbers": {
            "p2_fidelity": {
                "no_evidence_rep": stat(bhd, ["no_evidence"], pb),
                "evidence_rep": stat(bhd, ["evidence"], pb),
                "delta": stat(bhd, ["delta"], pb),
                "fidelity_gap": dig(bhd, ["fidelity_gap"], pb),
                "n_items": len(bitems),
                "n_items_worse_with_evidence": b_n_worse,
                "floors_no_evidence": stat(dig(base, ["floors"], pb), ["no_evidence"], pb),
            },
            "p3_tracking": {
                "n_items": dig(dig(trk, ["headline"], pt), ["n_items"], pt),
                "n_trackable": dig(dig(trk, ["headline"], pt), ["n_trackable"], pt),
                "direction_match_count": dig(dig(trk, ["headline"], pt), ["direction_match_count"], pt),
                "direction_match_rate": dig(dig(trk, ["headline"], pt), ["direction_match_rate"], pt),
                "elasticity": stat(dig(trk, ["headline"], pt), ["elasticity"], pt),
                "n_model_moved": dig(dig(trk, ["headline"], pt), ["n_model_moved"], pt),
            },
            "p4_floors": {
                "baseline": _cond("baseline"),
                "hostile_evidence": _cond("hostile_evidence"),
                "adversarial_prompt": _cond("adversarial_prompt"),
                "both": _cond("both"),
            },
            "g1_guards": {
                "replication_check": dig(gg, ["replication_check"], pg),
                "arms": guard_out,
            },
        },
        "caveats": [
            "Replication model: mlx-community/Meta-Llama-3.1-8B-Instruct-4bit (8B, 4-bit) — the ONLY two-model section in this extract; all other sections are the single 3B-4bit model.",
            "Same battery/grids as the committed 3B runs (P2: 50 contestable + 12 floor; P3: 10 sig items; P4: 12 floor probes x 4 conditions; G1-subset: {no_guard, rights_floor, constitution} — provenance/combined were dominated 3B arms and NOT re-run).",
            "SYNTHETIC hostile evidence (hostile_distribution, ~75% anti-rights mass) — red-team stress data, not real BSA opinion (same as 3B P4).",
            "floorguard_grid_8b.replication_check compares the 8B no_guard against the 3B P4 reference (0.5116/0.3177) and is EXPECTEDLY within_tolerance=false (cross-MODEL, not a self-check); the 8B self-consistency is no_guard_hostile 0.0743 == floors_8b hostile 0.0743.",
        ],
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
EXTRACTORS = {
    "phase1_logit_bias": extract_phase1_logit_bias,
    "phase2_steering": extract_phase2_steering,
    "p2_fidelity": extract_p2_fidelity,
    "p3_tracking": extract_p3_tracking,
    "p4_floors": extract_p4_floors,
    "p5_lora": extract_p5_lora,
    "g1_guards": extract_g1_guards,
    "model_robustness_8b": extract_model_robustness_8b,
}


def build():
    result = {
        "_meta": {
            "generator": "scripts/extract_paper_results.py",
            "purpose": "PS1 claim->evidence numbers for docs/PAPER_RESULTS.md — pure extraction, no model runs.",
            "model_under_test": "mlx-community/Llama-3.2-3B-Instruct-4bit (single 3B-4bit model)",
        },
    }
    for name, fn in EXTRACTORS.items():
        result[name] = fn()
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None, help="write JSON here (else stdout)")
    args = ap.parse_args(argv)

    try:
        result = build()
    except (MissingKey, FileNotFoundError) as exc:
        print(f"EXTRACTION FAILED: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
