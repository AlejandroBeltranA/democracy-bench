#!/usr/bin/env python3
"""Publication-grade figures for the Democracy-Bench paper arc (PS2).

READ-ONLY on out/*.json. This script renders NO new experiment; every number it
draws is read from a committed artifact and matches docs/PAPER_RESULTS.md (PS1)
exactly. It writes ONLY to out/figures/ (vector PDF + 200dpi PNG per figure).

Design contract (docs/PAPER_SUPPORT_PLAN.md, PS2):
  * matplotlib only, colorblind-safe palette, deterministic output.
  * NO titles baked in — captions live in the paper (docs/FIGURES.md carries
    suggested caption bullets).
  * Data transforms live in PURE helpers (prep_f1..prep_f5) with numpy-only
    tests in tests/test_paper_figures.py; the plot_* functions only render.

Figures:
  F1  ladder summary          — the intervention ladder, one verdict + number each
  F2  tracking                — per-item real vs model 2022->2024 shift (P3, 10 items)
  F3  floors under attack      — floor mass by condition x guard arm (P4 + G1)
  F4  steering geometry        — per-layer cosine (within/cross/off-diag) + R8 control
  F5  fidelity heterogeneity   — per-item evidence-minus-no-evidence delta (P2, 50 items)

Usage:
    python scripts/make_paper_figures.py                 # writes out/figures/*.{pdf,png}
    python scripts/make_paper_figures.py --check         # prep helpers only, no render
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Repo layout + reuse PS1's fail-loud extraction helpers (dig/load/find_layer)
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "out")
FIG_DIR = os.path.join(OUT_DIR, "figures")

_EPR_PATH = os.path.join(REPO_ROOT, "scripts", "extract_paper_results.py")
_spec = importlib.util.spec_from_file_location("extract_paper_results", _EPR_PATH)
epr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(epr)

dig = epr.dig
load = epr.load
find_layer = epr.find_layer

# ---------------------------------------------------------------------------
# Colorblind-safe palette (Wong 2011, Nature Methods) — stable across figures.
# ---------------------------------------------------------------------------
CB = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "grey": "#999999",
}


# ===========================================================================
# PURE DATA-PREP HELPERS  (numpy-only tests target these — no matplotlib here)
# Each takes already-loaded JSON dict(s) and returns plain python/np structures.
# ===========================================================================
def prep_f1_ladder():
    """The intervention ladder as small multiples: five rungs, each with its own
    held-out point estimate, CI, and reference line. Every number appears
    verbatim in the paper's results prose and traces to the same artifacts."""
    # order = lightest lever (top row) -> heaviest lever (bottom row)
    rungs = [
        {
            "label": "Context (evidence-in-prompt)",
            "metric": "tracking elasticity, held-out",
            "value": 0.395, "ci": (0.020, 0.811), "ref": 0.0, "refname": "0",
            "verdict": "partial", "note": "tracks 8/10 items; spoofable",
        },
        {
            "label": "Prompt guards (user-before)",
            "metric": "best floor mass under attack",
            "value": 0.402, "ci": None, "ref": 0.5, "refname": "0.50 floor",
            "verdict": "fail", "note": "0/4 guards hold",
        },
        {
            "label": "Logit bias (decode)",
            "metric": "representation gain, held-out",
            "value": 0.074, "ci": (-0.009, 0.157), "ref": 0.0, "refname": "0",
            "verdict": "fail", "note": "n.s.",
        },
        {
            "label": "Activation steering",
            "metric": "representation gain, held-out",
            "value": -0.081, "ci": (-0.116, -0.045), "ref": 0.0, "refname": "0",
            "verdict": "fail", "note": "persona axis, not content",
        },
        {
            "label": "Naive LoRA (weights)",
            "metric": "fidelity gain, held-out",
            "value": 0.003, "ci": (-0.054, 0.066), "ref": 0.0, "refname": "0",
            "verdict": "fail", "note": "off-task 1.00 → 0.00",
        },
    ]
    verdict_colour = {"partial": CB["orange"], "fail": CB["vermillion"], "pass": CB["green"]}
    return rungs, verdict_colour


def prep_f2_tracking(tracking, tracking_8b=None):
    """P3 per-item real vs model 2022->2024 mean-position shift, 10 items.

    Returns dict with parallel arrays sorted by real_shift descending:
      ids, real, model, match(bool), and the headline annotation numbers.

    If tracking_8b is supplied (Phase-5 8B replication), also returns the 8B
    model shifts / matches aligned to the SAME sorted item order (a small marker
    overlay) plus the 8B headline direction count + elasticity. real_shift is
    model-independent, so the two models share the `real` series.
    """
    import numpy as np

    items = dig(tracking, ["items"], "evidcond_tracking_3b.json")
    ids = [dig(it, ["id"], "item") for it in items]
    real = np.array([dig(it, ["real_shift"], "item") for it in items], dtype=float)
    model = np.array([dig(it, ["model_shift"], "item") for it in items], dtype=float)
    match = np.array([bool(dig(it, ["direction_match"], "item")) for it in items])

    order = np.argsort(-real)  # largest real shift at top
    hd = dig(tracking, ["headline"], "evidcond_tracking_3b.json")
    el = dig(hd, ["elasticity"], "headline")
    out = {
        "ids": [ids[i] for i in order],
        "real": real[order],
        "model": model[order],
        "match": match[order],
        "direction_match_count": dig(hd, ["direction_match_count"], "headline"),
        "n_items": dig(hd, ["n_items"], "headline"),
        "elasticity_mean": dig(el, ["mean"], "elasticity"),
        "elasticity_ci": list(dig(el, ["ci"], "elasticity")),
        "has_8b": False,
    }

    if tracking_8b is not None:
        fp8 = "evidcond_tracking_8b.json"
        items8 = dig(tracking_8b, ["items"], fp8)
        by_id8 = {dig(it, ["id"], "item"): it for it in items8}
        # align 8B model shifts to the SAME sorted order of ids (fail loud if an id is absent)
        model8 = np.array(
            [dig(by_id8[i], ["model_shift"], fp8) for i in out["ids"]], dtype=float)
        match8 = np.array(
            [bool(dig(by_id8[i], ["direction_match"], fp8)) for i in out["ids"]])
        hd8 = dig(tracking_8b, ["headline"], fp8)
        el8 = dig(hd8, ["elasticity"], "headline")
        out.update({
            "has_8b": True,
            "model_8b": model8,
            "match_8b": match8,
            "direction_match_count_8b": dig(hd8, ["direction_match_count"], "headline"),
            "elasticity_mean_8b": dig(el8, ["mean"], "elasticity"),
            "elasticity_ci_8b": list(dig(el8, ["ci"], "elasticity")),
        })
    return out


def prep_f3_floors(floors, guards):
    """P4 (no_guard) + G1 (4 guard arms): floor mass by condition.

    Conditions in fixed order: baseline, hostile_evidence, adversarial_prompt, both.
    Arms in fixed order: no_guard, provenance, rights_floor, constitution, combined.
    Returns dict: conditions, arms(labels), mass[arm][cond], ci_lo/ci_hi, floor_min.
    """
    import numpy as np

    conditions = ["baseline", "hostile_evidence", "adversarial_prompt", "both"]
    cond_labels = ["baseline", "hostile\nevidence", "adversarial\nprompt", "both"]

    # no_guard row from P4 floors artifact headline
    fp = "evidcond_floors_3b.json"
    fh = dig(floors, ["headline"], fp)
    no_guard_mass = [dig(fh, [c, "floor_mass", "mean"], fp) for c in conditions]
    no_guard_lo = [dig(fh, [c, "floor_mass", "ci", 0], fp) for c in conditions]
    no_guard_hi = [dig(fh, [c, "floor_mass", "ci", 1], fp) for c in conditions]

    # guard arms from G1 grid artifact
    gp = "floorguard_grid_3b.json"
    arms_json = dig(guards, ["headline", "arms"], gp)
    guard_order = ["guard_provenance", "guard_rights_floor", "guard_constitution", "guard_combined"]
    guard_labels = {
        "guard_provenance": "provenance",
        "guard_rights_floor": "rights-floor",
        "guard_constitution": "constitution",
        "guard_combined": "combined",
    }

    mass = {"no_guard": np.array(no_guard_mass)}
    ci_lo = {"no_guard": np.array(no_guard_lo)}
    ci_hi = {"no_guard": np.array(no_guard_hi)}
    for name in guard_order:
        a = dig(arms_json, [name], gp)
        fbc = dig(a, ["floor_by_condition"], gp)
        mass[name] = np.array([dig(fbc, [c, "floor_mass", "mean"], gp) for c in conditions])
        ci_lo[name] = np.array([dig(fbc, [c, "floor_mass", "ci", 0], gp) for c in conditions])
        ci_hi[name] = np.array([dig(fbc, [c, "floor_mass", "ci", 1], gp) for c in conditions])

    arm_order = ["no_guard"] + guard_order
    arm_display = {"no_guard": "no guard", **guard_labels}
    return {
        "conditions": conditions,
        "cond_labels": cond_labels,
        "arm_order": arm_order,
        "arm_display": [arm_display[a] for a in arm_order],
        "mass": mass,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "floor_min": 0.5,
    }


def prep_f3_floors_8b(floors_8b, guards_8b):
    """Phase-5 8B replication panel for F3: floor mass by condition for the 8B
    no_guard (P4) row plus the two G1-subset guard arms (rights_floor,
    constitution). Same condition order as prep_f3_floors. This is the single
    most striking replication number (0.707 -> 0.074) and gets its own panel.

    Only the arms that were RE-RUN at 8B are present (provenance/combined were
    the dominated 3B arms and not replicated), so the 8B panel has 3 arms.
    """
    import numpy as np

    conditions = ["baseline", "hostile_evidence", "adversarial_prompt", "both"]

    fp = "evidcond_floors_8b.json"
    fh = dig(floors_8b, ["headline"], fp)
    no_guard_mass = [dig(fh, [c, "floor_mass", "mean"], fp) for c in conditions]
    no_guard_lo = [dig(fh, [c, "floor_mass", "ci", 0], fp) for c in conditions]
    no_guard_hi = [dig(fh, [c, "floor_mass", "ci", 1], fp) for c in conditions]

    gp = "floorguard_grid_8b.json"
    arms_json = dig(guards_8b, ["headline", "arms"], gp)
    guard_order = ["guard_rights_floor", "guard_constitution"]
    guard_labels = {
        "guard_rights_floor": "rights-floor (8B)",
        "guard_constitution": "constitution (8B)",
    }

    mass = {"no_guard": np.array(no_guard_mass)}
    ci_lo = {"no_guard": np.array(no_guard_lo)}
    ci_hi = {"no_guard": np.array(no_guard_hi)}
    for name in guard_order:
        a = dig(arms_json, [name], gp)
        fbc = dig(a, ["floor_by_condition"], gp)
        mass[name] = np.array([dig(fbc, [c, "floor_mass", "mean"], gp) for c in conditions])
        ci_lo[name] = np.array([dig(fbc, [c, "floor_mass", "ci", 0], gp) for c in conditions])
        ci_hi[name] = np.array([dig(fbc, [c, "floor_mass", "ci", 1], gp) for c in conditions])

    arm_order = ["no_guard"] + guard_order
    arm_display = {"no_guard": "no guard (8B)", **guard_labels}
    return {
        "conditions": conditions,
        "cond_labels": ["baseline", "hostile\nevidence", "adversarial\nprompt", "both"],
        "arm_order": arm_order,
        "arm_display": [arm_display[a] for a in arm_order],
        "mass": mass,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "floor_min": 0.5,
    }


def prep_f4_geometry(geometry, personactrl):
    """Phase-2 W3 per-layer cosine geometry + R8 farmer-control cosine.

    Returns layers and three parallel cosine series (mean off-diagonal,
    within-domain, cross-domain), plus the R8 control cosine annotation.
    """
    import numpy as np

    gp = "act_steer_geometry_3b.json"
    per = dig(geometry, ["per_layer"], gp)
    layers = np.array([dig(b, ["layer"], gp) for b in per])
    order = np.argsort(layers)
    layers = layers[order]

    def series(field):
        vals = np.array([dig(b, [field], gp) for b in per])
        return vals[order]

    pp = "act_steer_personactrl_3b.json"
    per_ctrl = dig(personactrl, ["per_layer"], pp)
    ctrl_l11 = find_layer(per_ctrl, 11, pp)
    return {
        "layers": layers,
        "mean_offdiag": series("mean_offdiag_cosine"),
        "within": series("within_domain_cosine"),
        "cross": series("cross_domain_cosine"),
        "control_cosine_l11": dig(ctrl_l11, ["cosine_real_control"], pp),
    }


def prep_f5_fidelity(baseline):
    """P2 per-item evidence-minus-no-evidence representation delta, 50 items.

    Returns deltas sorted ascending, domain labels aligned, the n-worse count,
    and a stable domain->family map for colouring.
    """
    import numpy as np

    fp = "evidcond_baseline_3b.json"
    items = dig(baseline, ["items"], fp)
    deltas = np.array([dig(it, ["delta"], "item") for it in items], dtype=float)
    domains = [dig(it, ["domain"], "item") for it in items]

    order = np.argsort(deltas)  # most-harmed at left
    deltas_sorted = deltas[order]
    domains_sorted = [domains[i] for i in order]
    n_worse = int((deltas < 0).sum())

    fam = _domain_family(domains_sorted)
    return {
        "deltas": deltas_sorted,
        "domains": domains_sorted,
        "families": fam,
        "n_worse": n_worse,
        "n_items": len(deltas),
    }


def _domain_family(domains):
    """Collapse the fine-grained domain labels to a small, stable family set so
    F5 can be coloured cleanly (13 raw domains -> 4 families)."""
    mapping = {
        "nhs": "health/care",
        "social_care": "health/care",
        "dwp": "welfare/tax",
        "welfare": "welfare/tax",
        "redistribution": "welfare/tax",
        "tax": "welfare/tax",
        "tax_spend": "welfare/tax",
        "spending": "welfare/tax",
        "government_responsibility": "governance",
        "democratic_system": "governance",
        "trust": "governance",
        "climate": "other",
        "economy": "other",
    }
    return [mapping.get(d, "other") for d in domains]


FAMILY_COLOUR = {
    "health/care": CB["blue"],
    "welfare/tax": CB["orange"],
    "governance": CB["green"],
    "other": CB["purple"],
}


# ===========================================================================
# RENDERERS (matplotlib) — no data transforms beyond what prep_* already did.
# ===========================================================================
def _new_fig(plt, w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    return fig, ax


def plot_f1(plt, data):
    rungs, verdict_colour = data
    n = len(rungs)
    fig, axes = plt.subplots(n, 1, figsize=(8.2, 4.4))
    for ax, r in zip(axes, rungs):
        c = verdict_colour[r["verdict"]]
        lo, hi = (r["ci"] if r["ci"] else (r["value"], r["value"]))
        span = max(hi, r["ref"]) - min(lo, r["ref"])
        pad = 0.35 * span if span else 0.1
        x0, x1 = min(lo, r["ref"]) - pad, max(hi, r["ref"]) + pad
        ax.axvline(r["ref"], color="#999999", ls="--", lw=1.0, zorder=1)
        if r["ci"]:
            ax.plot([lo, hi], [0, 0], color=c, lw=2.2, zorder=2,
                    solid_capstyle="butt")
            for cap in (lo, hi):
                ax.plot([cap, cap], [-0.16, 0.16], color=c, lw=1.6, zorder=2)
        ax.scatter([r["value"]], [0], color=c, s=48, zorder=3)
        ax.text(r["value"], 0.42, f"{r['value']:+.3f}" if r["ref"] == 0.0
                else f"{r['value']:.3f}", ha="center", va="bottom",
                fontsize=8.5, color="#222222")
        ax.text(r["ref"], 0.55, r["refname"], ha="center", va="bottom",
                fontsize=7.5, color="#777777")
        ax.set_xlim(x0, x1)
        ax.set_ylim(-1.0, 1.0)
        ax.set_yticks([])
        ax.set_xticks([])
        ax.grid(False)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#cccccc")
        ax.text(0.0, 1.02, r["label"], transform=ax.transAxes, ha="left",
                va="bottom", fontsize=10.5, fontweight="bold")
        ax.text(1.0, 1.02, r["verdict"].upper(), transform=ax.transAxes,
                ha="right", va="bottom", fontsize=9.5, fontweight="bold", color=c)
        ax.text(0.995, 0.06, f"{r['metric']}; {r['note']}", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8.0, color="#555555", style="italic")
    fig.subplots_adjust(hspace=0.9, top=0.94, bottom=0.03, left=0.03, right=0.97)
    return fig


def plot_f2(plt, data):
    import numpy as np

    fig, ax = _new_fig(plt, 8.4, 5.0)
    y = np.arange(len(data["ids"]))
    # real shift = filled marker, model shift = open marker, connector line
    for i in range(len(y)):
        ax.plot([data["real"][i], data["model"][i]], [y[i], y[i]],
                color=CB["grey"], lw=1.0, zorder=1)
    ax.scatter(data["real"], y, s=64, color=CB["blue"], zorder=3, label="real 2022->2024 shift")
    match_c = [CB["green"] if m else CB["vermillion"] for m in data["match"]]
    ax.scatter(data["model"], y, s=64, facecolors="white", edgecolors=match_c,
               linewidths=1.8, zorder=3, label="3B model shift")
    if data.get("has_8b"):
        # small 8B overlay: diamond markers, direction-coloured edge, same order
        match_c8 = [CB["green"] if m else CB["vermillion"] for m in data["match_8b"]]
        ax.scatter(data["model_8b"], y, s=42, marker="D", facecolors="white",
                   edgecolors=match_c8, linewidths=1.4, zorder=2, label="8B model shift")
    ax.axvline(0.0, color="#000000", lw=0.8, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(data["ids"], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("mean-position shift (survey scale)", fontsize=10)
    # mark mismatches
    for i, m in enumerate(data["match"]):
        if not m:
            ax.text(ax.get_xlim()[1], y[i], "  dir mismatch", va="center", ha="left",
                    fontsize=7.5, color=CB["vermillion"])
    ann = (f"3B: direction match {data['direction_match_count']}/{data['n_items']}   "
           f"elasticity {data['elasticity_mean']:+.3f} "
           f"CI[{data['elasticity_ci'][0]:+.3f}, {data['elasticity_ci'][1]:+.3f}]")
    if data.get("has_8b"):
        ann += (f"\n8B: direction match {data['direction_match_count_8b']}/{data['n_items']}   "
                f"elasticity {data['elasticity_mean_8b']:+.3f} "
                f"CI[{data['elasticity_ci_8b'][0]:+.3f}, {data['elasticity_ci_8b'][1]:+.3f}]")
    ax.text(0.5, 1.02, ann, transform=ax.transAxes, ha="center", va="bottom",
            fontsize=9.0, color="#222222")
    ax.legend(loc="lower right", fontsize=8.5, framealpha=0.9)
    fig.tight_layout()
    return fig


def _plot_f3_panel(ax, data, arm_colours, ymax):
    import numpy as np

    conds = data["cond_labels"]
    arms = data["arm_order"]
    x = np.arange(len(conds))
    n_arm = len(arms)
    width = 0.8 / n_arm
    for j, arm in enumerate(arms):
        offs = (j - (n_arm - 1) / 2) * width
        m = data["mass"][arm]
        lo = m - data["ci_lo"][arm]
        hi = data["ci_hi"][arm] - m
        ax.bar(x + offs, m, width=width, color=arm_colours[j], alpha=0.85,
               label=data["arm_display"][j],
               yerr=np.vstack([lo, hi]), capsize=2, error_kw={"lw": 0.8, "ecolor": "#444444"})
    ax.axhline(data["floor_min"], color=CB["vermillion"], lw=1.4, ls="--", zorder=0)
    ax.text(len(conds) - 0.5, data["floor_min"] + 0.01, "0.5 floor", ha="right", va="bottom",
            fontsize=9, color=CB["vermillion"], fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(conds, fontsize=9)
    ax.set_ylim(0, ymax)
    ax.legend(loc="upper right", fontsize=8, ncol=1, framealpha=0.9)


def plot_f3(plt, data, data_8b=None):
    # 3B palette: no_guard, provenance, rights_floor, constitution, combined
    colours_3b = [CB["black"], CB["vermillion"], CB["sky"], CB["green"], CB["purple"]]
    if data_8b is None:
        fig, ax = _new_fig(plt, 8.6, 4.8)
        ymax = max(0.7, float(max(data["ci_hi"]["guard_rights_floor"])) + 0.05)
        _plot_f3_panel(ax, data, colours_3b, ymax)
        ax.set_ylabel("floor (protective) mass", fontsize=10)
        fig.tight_layout()
        return fig

    # Two-panel replication figure: 3B (left) vs 8B (right), shared y-scale.
    # 8B panel has 3 re-run arms: no_guard, rights_floor, constitution.
    colours_8b = [CB["black"], CB["sky"], CB["green"]]
    ymax = 1.02  # 8B baseline/adv bars reach ~0.79-0.99
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.6, 4.8), sharey=True)
    _plot_f3_panel(axL, data, colours_3b, ymax)
    _plot_f3_panel(axR, data_8b, colours_8b, ymax)
    axL.set_ylabel("floor (protective) mass", fontsize=10)
    axL.text(0.02, 0.97, "3B (Llama-3.2-3B)", transform=axL.transAxes, ha="left",
             va="top", fontsize=10, fontweight="bold", color="#222222")
    axR.text(0.02, 0.97, "8B (Llama-3.1-8B)", transform=axR.transAxes, ha="left",
             va="top", fontsize=10, fontweight="bold", color="#222222")
    fig.tight_layout()
    return fig


def plot_f4(plt, data):
    fig, ax = _new_fig(plt, 8.0, 4.8)
    L = data["layers"]
    ax.plot(L, data["within"], "-o", color=CB["blue"], lw=2, label="within-domain cosine")
    ax.plot(L, data["cross"], "-s", color=CB["orange"], lw=2, label="cross-domain cosine")
    ax.plot(L, data["mean_offdiag"], "--^", color=CB["grey"], lw=1.6,
            label="mean off-diagonal cosine")
    ax.axhline(data["control_cosine_l11"], color=CB["vermillion"], lw=1.2, ls=":")
    ax.text(L[-1], data["control_cosine_l11"] + 0.008,
            f"R8 cos(real, 1850-farmer) = {data['control_cosine_l11']:.3f}",
            ha="right", va="bottom", fontsize=8.5, color=CB["vermillion"], fontweight="bold")
    ax.set_xlabel("layer", fontsize=10)
    ax.set_ylabel("cosine similarity of steering arrows", fontsize=10)
    ax.set_xticks(L)
    ax.set_ylim(0.4, 1.02)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
    fig.tight_layout()
    return fig


def plot_f5(plt, data):
    import numpy as np

    fig, ax = _new_fig(plt, 9.0, 4.4)
    x = np.arange(data["n_items"])
    colours = [FAMILY_COLOUR[f] for f in data["families"]]
    ax.bar(x, data["deltas"], color=colours, width=0.9)
    ax.axhline(0.0, color="#000000", lw=0.9)
    ax.set_xlim(-0.8, data["n_items"] - 0.2)
    ax.set_xlabel("contestable item (sorted by evidence effect)", fontsize=10)
    ax.set_ylabel("representation delta\n(evidence - no evidence)", fontsize=10)
    ax.set_xticks([])
    ann = f"{data['n_worse']}/{data['n_items']} items made WORSE by evidence"
    ax.text(0.02, 0.05, ann, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=10, color=CB["vermillion"], fontweight="bold")
    # legend for families
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=FAMILY_COLOUR[f], label=f) for f in
               ["health/care", "welfare/tax", "governance", "other"]]
    ax.legend(handles=handles, loc="upper left", fontsize=8.5, framealpha=0.9, title="domain")
    fig.tight_layout()
    return fig


# ===========================================================================
# Driver
# ===========================================================================
def prep_f6_crossfamily(floor_arts):
    """Cross-family floor crack: baseline vs hostile-evidence protective mass per model,
    sorted by baseline (descending). floor_arts: list of (display_name, floors_artifact)."""
    rows = []
    for disp, art in floor_arts:
        rows.append({
            "model": disp,
            "baseline": dig(art, ["headline", "baseline", "floor_mass", "mean"], disp),
            "hostile": dig(art, ["headline", "hostile_evidence", "floor_mass", "mean"], disp),
        })
    rows.sort(key=lambda r: r["baseline"], reverse=True)
    return {"rows": rows, "floor": 0.5}


def plot_f6(plt, data):
    from matplotlib.lines import Line2D

    rows = data["rows"]
    fig, ax = _new_fig(plt, 8.4, 4.4)
    n = len(rows)
    for i, r in enumerate(rows):
        yy = n - 1 - i  # highest baseline at top
        ax.plot([r["hostile"], r["baseline"]], [yy, yy], color=CB["grey"], lw=1.3, zorder=1)
        ax.scatter(r["baseline"], yy, s=72, color=CB["blue"], zorder=3)
        ax.scatter(r["hostile"], yy, s=72, color=CB["vermillion"], zorder=3)
        ax.text(r["baseline"] + 0.015, yy, f"{r['baseline']:.2f}", va="center", ha="left",
                fontsize=8.5, color=CB["blue"])
        if r["hostile"] < 0.05:  # too close to the axis for a left-side label
            ax.text(r["hostile"] + 0.02, yy + 0.18, f"{r['hostile']:.2f}", va="bottom",
                    ha="left", fontsize=8.5, color=CB["vermillion"])
        else:
            ax.text(r["hostile"] - 0.015, yy, f"{r['hostile']:.2f}", va="center", ha="right",
                    fontsize=8.5, color=CB["vermillion"])
    ax.axvline(data["floor"], color=CB["vermillion"], lw=1.4, ls="--", zorder=0)
    ax.text(data["floor"] + 0.008, n - 0.5, "0.5 floor", ha="left", va="top",
            fontsize=8.5, color=CB["vermillion"])
    ax.set_yticks([n - 1 - i for i in range(n)])
    ax.set_yticklabels([r["model"] for r in rows], fontsize=9.5)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("rights-floor protective mass", fontsize=10)
    ax.set_axisbelow(True)
    ax.yaxis.grid(False)
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=CB["blue"], markersize=9,
               label="at rest (unattacked)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=CB["vermillion"], markersize=9,
               label="under hostile evidence"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5, framealpha=0.9)
    fig.tight_layout()
    return fig


def prep_f7_reflex(reflex):
    """AI reflex: per-(model, probe) human-actor vs AI-actor protective mass, plus each
    model's mean matched AI-excess. Reads out/reflex_test.json (matched-pair control, S=100)."""
    models = dig(reflex, ["models"])
    series = []
    for mid, mm in models.items():
        pts = [(pv["human_protective"], pv["ai_protective"])
               for pv in dig(mm, ["pairs"]).values()
               if isinstance(pv, dict) and "human_protective" in pv and "ai_protective" in pv]
        series.append({
            "model": mid.split("/")[-1],
            "points": pts,
            "excess": dig(mm, ["mean_matched_ai_excess"], mid),
        })
    return {"series": series, "samples": dig(reflex, ["run", "samples"])}


def plot_f7(plt, data):
    fig, ax = _new_fig(plt, 6.2, 5.8)
    colours = [CB["blue"], CB["vermillion"], CB["green"]]
    markers = ["o", "s", "D"]
    ax.plot([0, 1], [0, 1], color="#000000", lw=0.8, ls="--", zorder=0)
    ax.text(0.04, 0.07, "no actor effect (y = x)", fontsize=8, color="#555555",
            rotation=45, rotation_mode="anchor", va="bottom", ha="left")
    for si, s in enumerate(data["series"]):
        xs = [p[0] for p in s["points"]]
        ys = [p[1] for p in s["points"]]
        ax.scatter(xs, ys, s=58, color=colours[si % 3], marker=markers[si % 3],
                   alpha=0.85, edgecolors="white", linewidths=0.6, zorder=3,
                   label=f"{s['model']}  ({s['excess']:+.2f})")
    ax.set_xlim(-0.03, 1.05)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("protective mass — human actor", fontsize=10)
    ax.set_ylabel("protective mass — AI actor", fontsize=10)
    ax.text(0.5, 1.02, f"points above the line: more protection against the AI actor (S={data['samples']})",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=8.5, color="#222222")
    ax.legend(loc="lower right", fontsize=8.5, framealpha=0.9, title="mean AI-excess")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    return fig


FIGURES = ["f1_ladder", "f2_tracking", "f3_floors", "f4_geometry", "f5_fidelity",
           "f6_crossfamily", "f7_reflex"]


def build_all(render=True):
    """Load artifacts, run prep helpers, and (optionally) render+save figures.

    Returns the dict of prepped data (so --check can validate without matplotlib).
    """
    tracking, _ = load("evidcond_tracking_3b.json")
    floors, _ = load("evidcond_floors_3b.json")
    guards, _ = load("floorguard_grid_3b.json")
    geometry, _ = load("act_steer_geometry_3b.json")
    personactrl, _ = load("act_steer_personactrl_3b.json")
    baseline, _ = load("evidcond_baseline_3b.json")
    # Phase-5 8B replication artifacts (F2 marker overlay + F3 panel only).
    tracking_8b, _ = load("evidcond_tracking_8b.json")
    floors_8b, _ = load("evidcond_floors_8b.json")
    guards_8b, _ = load("floorguard_grid_8b.json")
    # Cross-family floor artifacts (F6) + matched-pair reflex control (F7).
    floors_qwen, _ = load("evidcond_floors_qwen7b.json")
    floors_phi, _ = load("evidcond_floors_phi4mini.json")
    floors_gemma, _ = load("evidcond_floors_gemma9b.json")
    floors_nemo, _ = load("evidcond_floors_mistralnemo.json")
    # Frontier/API model (gpt-4o-mini via OpenRouter logprobs) — F6 7th row.
    floors_gpt4omini, _ = load("evidcond_floors_gpt4omini.json")
    reflex, _ = load("reflex_test.json")

    prepped = {
        "f1_ladder": prep_f1_ladder(),
        "f2_tracking": prep_f2_tracking(tracking, tracking_8b),
        "f3_floors": prep_f3_floors(floors, guards),
        "f3_floors_8b": prep_f3_floors_8b(floors_8b, guards_8b),
        "f4_geometry": prep_f4_geometry(geometry, personactrl),
        "f5_fidelity": prep_f5_fidelity(baseline),
        "f6_crossfamily": prep_f6_crossfamily([
            ("Llama-3B", floors), ("Llama-8B", floors_8b),
            ("Qwen-7B", floors_qwen), ("Phi-4-mini", floors_phi),
            ("Gemma-2-9B", floors_gemma), ("Mistral-Nemo", floors_nemo),
            ("gpt-4o-mini (API)", floors_gpt4omini)]),
        "f7_reflex": prep_f7_reflex(reflex),
    }
    if not render:
        return prepped

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # deterministic, non-fingerprinted vector output
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    matplotlib.rcParams["svg.hashsalt"] = "democracy-bench"
    matplotlib.rcParams["axes.grid"] = True
    matplotlib.rcParams["grid.alpha"] = 0.25
    matplotlib.rcParams["grid.linewidth"] = 0.5

    os.makedirs(FIG_DIR, exist_ok=True)
    renderers = {
        "f1_ladder": plot_f1,
        "f2_tracking": plot_f2,
        "f3_floors": plot_f3,
        "f4_geometry": plot_f4,
        "f5_fidelity": plot_f5,
        "f6_crossfamily": plot_f6,
        "f7_reflex": plot_f7,
    }
    written = []
    for name in FIGURES:
        if name == "f3_floors":
            fig = plot_f3(plt, prepped["f3_floors"], prepped["f3_floors_8b"])
        else:
            fig = renderers[name](plt, prepped[name])
        pdf = os.path.join(FIG_DIR, name + ".pdf")
        png = os.path.join(FIG_DIR, name + ".png")
        fig.savefig(pdf, metadata={"CreationDate": None})
        fig.savefig(png, dpi=200)
        plt.close(fig)
        written.append(pdf)
        written.append(png)
    return prepped, written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="run prep helpers only (no matplotlib, no files written)")
    args = ap.parse_args(argv)
    try:
        if args.check:
            build_all(render=False)
            print("prep OK (no render)", file=sys.stderr)
        else:
            _, written = build_all(render=True)
            for w in written:
                print(w)
    except (epr.MissingKey, FileNotFoundError) as exc:
        print(f"FIGURE BUILD FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
