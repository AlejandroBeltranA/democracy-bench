#!/usr/bin/env python3
"""Headline figure: agreement with the British public, 2025 six-model panel vs 2026 ten-model
panel, grouped by lab origin.

Agreement is `1 - total variation` between a model's sampled answer distribution and the
weighted BSA marginal, averaged over the 50 contestable ENG items (default prompt mode, S=24,
options shuffled). Intervals are 95 % percentile bootstraps over items.

Reads:
  out/policy_delegate_stress.json          the 2025 panel (merged, mid-2025 model snapshots)
  out/rep_panel_2026/<model>.json          one driver output per 2026 model
Writes out/figures/alternates/representation_panel_2026.{png,pdf} and a JSON table beside it.

Usage:
    python scripts/make_representation_panel_figure.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "out" / "figures" / "alternates"
OLD = REPO / "out" / "policy_delegate_stress.json"
NEW_DIR = REPO / "out" / "rep_panel_2026"

INK, MUTED = "#222222", "#666666"
# Okabe-Ito, one hue per lab region; text stays in ink
REGION_COLOUR = {"US": "#0072B2", "China": "#D55E00", "Europe": "#009E73", "Canada": "#CC79A7"}

# (display label, lab region, 2025 key, 2026 key)
ROWS = [
    ("OpenAI",    "US",     "openrouter:openai/gpt-4o-mini",                    "openrouter:openai/gpt-5.6-sol"),
    ("OpenAI (gpt-4o-mini, 2026 rerun)", "US", None,                          "openrouter:openai/gpt-4o-mini"),
    ("Anthropic", "US",     "openrouter:anthropic/claude-3-haiku",              "openrouter:anthropic/claude-sonnet-5"),
    ("Anthropic (Haiku 4.5)", "US", None,                                     "openrouter:anthropic/claude-haiku-4.5"),
    ("Google",    "US",     "openrouter:google/gemini-2.5-flash",               "openrouter:google/gemini-3.1-flash-lite"),
    ("DeepSeek",  "China",  "openrouter:deepseek/deepseek-chat",                "openrouter:deepseek/deepseek-v4-pro"),
    ("Alibaba (Qwen3.5-397B)", "China", None,                                 "openrouter:qwen/qwen3.5-397b-a17b"),
    ("Z.ai (GLM-5.2)", "China", None,                                         "openrouter:z-ai/glm-5.2"),
    ("Mistral",   "Europe", "openrouter:mistralai/mistral-small-3.2-24b-instruct", "openrouter:mistralai/mistral-medium-3-5"),
    ("Cohere",    "Canada", "openrouter:cohere/command-r-08-2024",              "openrouter:cohere/command-a"),
]
SHORT_2025 = {"openrouter:openai/gpt-4o-mini": "gpt-4o-mini",
              "openrouter:anthropic/claude-3-haiku": "Claude 3 Haiku",
              "openrouter:google/gemini-2.5-flash": "Gemini 2.5 Flash",
              "openrouter:deepseek/deepseek-chat": "DeepSeek-chat",
              "openrouter:mistralai/mistral-small-3.2-24b-instruct": "Mistral Small 3.2",
              "openrouter:cohere/command-r-08-2024": "Command-R"}
SHORT_2026 = {"openrouter:openai/gpt-5.6-sol": "GPT-5.6 Sol",
              "openrouter:openai/gpt-4o-mini": "gpt-4o-mini",
              "openrouter:anthropic/claude-sonnet-5": "Claude Sonnet 5",
              "openrouter:anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
              "openrouter:google/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
              "openrouter:deepseek/deepseek-v4-pro": "DeepSeek-V4-Pro",
              "openrouter:qwen/qwen3.5-397b-a17b": "Qwen3.5-397B",
              "openrouter:z-ai/glm-5.2": "GLM-5.2",
              "openrouter:mistralai/mistral-medium-3-5": "Mistral Medium 3.5",
              "openrouter:cohere/command-a": "Command A"}


def item_reps(doc: dict, model_key: str) -> list[float]:
    """Per-item agreement (1 - TV) for the default mode over contestable items."""
    vals = []
    for item in doc["items"].values():
        if item.get("class") != "contestable":
            continue
        rec = item["modes"].get("default", {}).get("models", {}).get(model_key)
        if rec and isinstance(rec.get("rep_vs_public"), (int, float)):
            vals.append(float(rec["rep_vs_public"]))
    return vals


def boot_ci(vals: list[float], n: int = 4000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    k = len(vals)
    means = sorted(mean(rng.choice(vals) for _ in range(k)) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def load_2026() -> dict[str, dict]:
    docs = {}
    for path in sorted(NEW_DIR.glob("*.json")):
        doc = json.load(open(path))
        for key in doc["model_summary"]:
            docs[key] = doc
    return docs


def collect() -> list[dict]:
    old = json.load(open(OLD))
    new = load_2026()
    rows = []
    for label, region, k25, k26 in ROWS:
        row = {"label": label, "region": region}
        if k25 and k25 in old["model_summary"]:
            v = item_reps(old, k25)
            row["y2025"] = {"model": SHORT_2025[k25], "mean": mean(v), "ci": boot_ci(v), "n": len(v)}
        if k26 in new:
            v = item_reps(new[k26], k26)
            row["y2026"] = {"model": SHORT_2026[k26], "mean": mean(v), "ci": boot_ci(v), "n": len(v)}
        if "y2026" in row or "y2025" in row:
            rows.append(row)
    return rows


def plot(rows: list[dict]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#BBBBBB"})
    n = len(rows)
    fig, ax = plt.subplots(figsize=(10.2, 0.52 * n + 3.2), dpi=160)
    ys = list(range(n))[::-1]
    for y, r in zip(ys, rows):
        c = REGION_COLOUR[r["region"]]
        if "y2025" in r and "y2026" in r:
            ax.plot([r["y2025"]["mean"], r["y2026"]["mean"]], [y, y], color=c, lw=1.2, alpha=0.5, zorder=1)
        if "y2025" in r:
            m, (lo, hi) = r["y2025"]["mean"], r["y2025"]["ci"]
            ax.plot([lo, hi], [y + 0.16, y + 0.16], color=c, lw=1.0, alpha=0.5, zorder=2)
            ax.scatter([m], [y + 0.16], s=52, facecolor="white", edgecolor=c, linewidth=1.6, zorder=3)
            ax.text(hi + 0.012, y + 0.16, f"{r['y2025']['model']}  {m:.2f}", va="center", fontsize=8, color=MUTED)
        if "y2026" in r:
            m, (lo, hi) = r["y2026"]["mean"], r["y2026"]["ci"]
            yy = y - 0.16 if "y2025" in r else y
            ax.plot([lo, hi], [yy, yy], color=c, lw=1.6, zorder=2)
            ax.scatter([m], [yy], s=58, color=c, edgecolor="white", linewidth=1.2, zorder=3)
            ax.text(hi + 0.012, yy, f"{r['y2026']['model']}  {m:.2f}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels([r["label"] for r in rows], fontsize=9.5)
    for tick, r in zip(ax.get_yticklabels(), rows):
        tick.set_color(REGION_COLOUR[r["region"]])
    ax.set_xlim(0.35, 0.86)
    ax.set_xlabel("Agreement with the British public  (1 − total variation, mean over 50 contestable items)")
    ax.xaxis.grid(True, color="#E6E6E6", lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=INK,
                      markeredgewidth=1.4, markersize=7, label="mid-2025 panel (six models)"),
               Line2D([0], [0], marker="o", color="none", markerfacecolor=INK, markersize=7,
                      label="2026 panel (ten models), 95% bootstrap over items")]
    handles += [Line2D([0], [0], color=c, lw=3, label=f"{k} lab") for k, c in REGION_COLOUR.items()]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.12), fontsize=8,
              frameon=False, ncol=3, columnspacing=1.4)
    fig.text(0.02, 0.975, "How close is each model's default answer to the British public?",
             fontsize=13, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 0.935, "British Social Attitudes 2024 targets; forced choice, options shuffled, "
             "24 samples per item, no evidence in context, reasoning off.\n"
             "Gemini 3.5/3.8 Flash and GLM-5.3 are reasoning-mandatory and cannot take the "
             "forced choice; Gemini 3.1 Flash Lite stands in for Google.",
             fontsize=9.5, color=MUTED, va="top", linespacing=1.4)
    fig.subplots_adjust(left=0.26, right=0.985, top=0.84, bottom=0.2)
    return fig


def main():
    rows = collect()
    OUT.mkdir(parents=True, exist_ok=True)
    fig = plot(rows)
    fig.savefig(OUT / "representation_panel_2026.png", facecolor="white")
    fig.savefig(OUT / "representation_panel_2026.pdf", facecolor="white")
    (OUT / "representation_panel_2026.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        a = r.get("y2025"); b = r.get("y2026")
        print(f"{r['label']:28s} {r['region']:7s} "
              + (f"2025 {a['model']:18s} {a['mean']:.3f} [{a['ci'][0]:.3f},{a['ci'][1]:.3f}]  " if a else " " * 46)
              + (f"2026 {b['model']:18s} {b['mean']:.3f} [{b['ci'][0]:.3f},{b['ci'][1]:.3f}] n={b['n']}" if b else ""))
    print("wrote", OUT / "representation_panel_2026.png")


if __name__ == "__main__":
    main()
