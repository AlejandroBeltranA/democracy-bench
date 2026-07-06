#!/usr/bin/env python3
"""Build a human-coding codesheet from the collected rationales (judge-free construct
validity). Draws a deterministic stratified sample from out/_rationale_panel.json — all
floor items (weighted, for the 'invokes the right' code) plus a contestable slice (for the
stance-consistency code) — and writes a CSV with the prompt, options, the model's scored
answer, the rationale text, and EMPTY code columns for a human to fill.

Two codes (both readable off the text, no LLM judge):
  CODE_stance_consistent : does the rationale's stated stance match the scored option? (y/n)
  CODE_invokes_right     : (floor items only) does the rationale engage the right at stake? (y/n)

Reproduce: python scripts/build_rationale_codesheet.py --out annotations/rationale_codesheet.csv
Score after coding: python scripts/score_rationale_codesheet.py annotations/rationale_codesheet.csv
"""
import argparse, csv, json, random
from pathlib import Path

SEED = 20260706
PER_ITEM_MODELS = 6          # one sample per (item, model)
N_CONTESTABLE_ITEMS = 13     # contestable items to sample (floor: all 12)


def short_model(m):
    return m.split("/")[-1].split(":")[-1]


def collect(panel):
    """Yield one representative (deterministic) parsed sample per (item, model)."""
    rng = random.Random(SEED)
    items = panel["items"]
    floor_ids = [i for i, it in items.items() if it.get("class") == "floor"]
    cont_ids = [i for i, it in items.items() if it.get("class") == "contestable"]
    cont_ids = sorted(cont_ids)
    rng.shuffle(cont_ids)
    chosen_items = sorted(floor_ids) + cont_ids[:N_CONTESTABLE_ITEMS]

    rows = []
    for iid in chosen_items:
        it = items[iid]
        labels = it.get("labels") or []
        opt_str = " | ".join(f"{k}: {lab}" for k, lab in enumerate(labels))
        for model, mm in it["modes"]["default"]["models"].items():
            samples = [s for s in mm["diagnostics"]["samples"]
                       if s.get("canonical") is not None and (s.get("reason") or "").strip()]
            if not samples:
                continue
            s = samples[rng.randrange(len(samples))]     # deterministic pick
            idx = s["canonical"]
            rows.append({
                "item_id": iid,
                "class": it.get("class"),
                "domain": it.get("domain"),
                "model": short_model(model),
                "prompt": it.get("prompt", ""),
                "options": opt_str,
                "answer_idx": idx,
                "answer_label": labels[idx] if 0 <= idx < len(labels) else f"?{idx}",
                "rationale": (s.get("reason") or "").strip().replace("\n", " "),
            })
    rng.shuffle(rows)                                    # blind the coder to item order
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", default="out/_rationale_panel.json")
    ap.add_argument("--out", default="annotations/rationale_codesheet.csv")
    args = ap.parse_args()

    panel = json.load(open(args.panel))
    rows = collect(panel)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    fields = ["row_id", "item_id", "class", "domain", "model", "prompt", "options",
              "answer_idx", "answer_label", "rationale",
              "CODE_stance_consistent", "CODE_invokes_right", "CODE_notes"]
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(rows):
            r = dict(r)
            r["row_id"] = f"r{i:03d}"
            r["CODE_stance_consistent"] = ""
            r["CODE_invokes_right"] = "" if r["class"] == "floor" else "NA"
            r["CODE_notes"] = ""
            w.writerow(r)

    n_floor = sum(1 for r in rows if r["class"] == "floor")
    print(f"wrote {args.out}: {len(rows)} rationales "
          f"({n_floor} floor / {len(rows)-n_floor} contestable), seed {SEED}")
    print("Code CODE_stance_consistent (y/n) for every row; CODE_invokes_right (y/n) for floor rows.")


if __name__ == "__main__":
    main()
