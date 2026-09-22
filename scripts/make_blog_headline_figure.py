#!/usr/bin/env python3
"""Blog headline figure: the data-channel floor crack across nine models, 3B to 397B.

One dumbbell per model, ordered by scale. Filled dot = rights-floor protective mass
at rest; arrowhead = under survey-style hostile evidence with no instruction attached.
Hollow dot = the two frontier models with the class-routing system guard in place.

Reads only committed artefacts:
  out/evidcond_floors_<tag>.json                    (local panel + gpt-4o-mini, logprobs)
  out/q2_stage2_v7_run_panel/extract_<slug>.json    (frontier, sampling S=100)
Writes out/figures/alternates/headline_scale_ladder.{png,pdf}.

Usage:
    python scripts/make_blog_headline_figure.py
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "out" / "figures" / "alternates"
FLOOR = 0.5

# Okabe-Ito, matching make_paper_figures.py
BLUE = "#0072B2"
VERM = "#D55E00"
GREEN = "#009E73"
GREY = "#999999"
INK = "#222222"
MUTED = "#666666"

# (label, scale label, source kind, path key)
MODELS = [
    ("Llama-3.2", "3B", "local", "3b"),
    ("Phi-4-mini", "3.8B", "local", "phi4mini"),
    ("Qwen-2.5", "7B", "local", "qwen7b"),
    ("Llama-3.1", "8B", "local", "8b"),
    ("Gemma-2", "9B", "local", "gemma9b"),
    ("Mistral-Nemo", "12B", "local", "mistralnemo"),
    ("gpt-4o-mini", "API", "local", "gpt4omini"),
    ("GLM-5.2\n(Panel B)", "MoE", "frontier_b", "z-ai__glm-5.2"),
    ("DeepSeek\nV4-Pro", "frontier", "frontier", "deepseek__deepseek-v4-pro"),
    ("Qwen3.5\n397B-A17B", "MoE", "frontier", "qwen__qwen3.5-397b-a17b"),
]
FRONTIER_DIRS = {"frontier": "q2_stage2_v7_run_panel", "frontier_b": "q2_stage2_panel_b_run",
                 "frontier_b2": "q2_stage2_panel_b2_run"}


def load_rows():
    rows = []
    for label, scale, kind, key in MODELS:
        if kind == "local":
            d = json.load(open(REPO / "out" / f"evidcond_floors_{key}.json"))
            h = d["headline"]
            rows.append({
                "label": label, "scale": scale,
                "rest": h["baseline"]["floor_mass"]["mean"],
                "attacked": h["hostile_evidence"]["floor_mass"]["mean"],
                "below": h["hostile_evidence"]["n_below_floor"],
                "guarded": None,
            })
        else:
            d = json.load(open(REPO / "out" / FRONTIER_DIRS[kind] / f"extract_{key}.json"))
            pm = d["protective_mass"]

            def m(cell):
                return mean(v for v in pm[cell].values() if isinstance(v, (int, float)))

            rows.append({
                "label": label, "scale": scale,
                "rest": m("baseline::no_guard"),
                "attacked": m("data_only::no_guard"),
                "below": sum(v < FLOOR for v in pm["data_only::no_guard"].values()),
                "guarded": m("data_only::system_guard"),
            })
    return rows


def plot(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#BBBBBB", "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": MUTED,
    })
    fig, ax = plt.subplots(figsize=(11.5, 5.8), dpi=160)
    n = len(rows)
    xs = list(range(n))

    ax.axhspan(0, FLOOR, color="#F5F5F5", zorder=0)
    ax.axhline(FLOOR, color=INK, lw=1.0, ls=(0, (4, 3)), zorder=1)
    ax.text(n - 0.55, FLOOR + 0.015, "0.50 rights floor", ha="right", va="bottom",
            fontsize=9, color=INK)

    for x, r in zip(xs, rows):
        ax.annotate("", xy=(x, r["attacked"]), xytext=(x, r["rest"]),
                    arrowprops=dict(arrowstyle="-|>", color=VERM, lw=2.0,
                                    shrinkA=5, shrinkB=0, mutation_scale=14), zorder=3)
        ax.scatter([x], [r["rest"]], s=70, color=BLUE, zorder=4,
                   edgecolor="white", linewidth=1.5)
        ax.text(x + 0.12, r["rest"], f"{r['rest']:.2f}", ha="left", va="center",
                fontsize=8.5, color=BLUE)
        ax.text(x + 0.12, r["attacked"] + (0.03 if r["attacked"] < 0.12 else -0.02),
                f"{r['attacked']:.2f}", ha="left", va="center", fontsize=8.5, color=VERM)
        if r["guarded"] is not None:
            ax.scatter([x], [r["guarded"]], s=80, facecolor="white", edgecolor=GREEN,
                       linewidth=2.0, zorder=5)
            ax.text(x - 0.12, r["guarded"], f"{r['guarded']:.2f}", ha="right",
                    va="center", fontsize=8.5, color=GREEN)

    ax.set_xticks(xs)
    ax.set_xticklabels([f"{r['label']}\n{r['scale']}" for r in rows], fontsize=9)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(-0.03, 1.03)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel("Rights-floor protective mass (mean over 12 probes)")
    ax.yaxis.grid(True, color="#E6E6E6", lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)

    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=BLUE, markersize=8,
               label="At rest (no evidence in context)"),
        Line2D([0], [0], color=VERM, lw=2.0,
               label="Under survey-style hostile 'public opinion', no instruction attached"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
               markeredgecolor=GREEN, markeredgewidth=2, markersize=8,
               label="Same attack, evidence routed by item class (frontier only)"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.16),
              ncol=2, fontsize=8.5, frameon=False, columnspacing=2.0, handletextpad=0.6)
    fig.text(0.07, 0.955, "Bigger models don't hold rights floors better. The channel is the problem.",
             fontsize=13, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.07, 0.905,
             "Ten models, eight families, 3B to 397B. Every one drops when opinion data enters the "
             "context.\nRouting that data away from rights items restores the floor.",
             fontsize=9.5, color=MUTED, ha="left", va="top", linespacing=1.4)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.82, bottom=0.25)
    return fig


def main():
    rows = load_rows()
    OUT.mkdir(parents=True, exist_ok=True)
    fig = plot(rows)
    fig.savefig(OUT / "headline_scale_ladder.png", facecolor="white")
    fig.savefig(OUT / "headline_scale_ladder.pdf", facecolor="white")
    for r in rows:
        print(f"{r['label']:16s} {r['scale']:9s} rest={r['rest']:.3f} "
              f"attacked={r['attacked']:.3f} below={r['below']}/12"
              + (f" guarded={r['guarded']:.3f}" if r["guarded"] is not None else ""))
    print("wrote", OUT / "headline_scale_ladder.png")


if __name__ == "__main__":
    main()
