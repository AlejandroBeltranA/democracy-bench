"""Phase 3 driver: evidence-conditioned alignment (item-loading + scoring path).

Phase 1 (logit bias) and Phase 2 (activation steering) both failed for one reason: a *constant*
intervention carries no item-specific information. Phase 3 tests the architecture that CAN carry
it — **content in context, disposition in weights**: the item's real public-preference evidence
is stated in the prompt at decision time, and what we measure is the model's *fidelity of
deference* to that evidence (P2), whether it tracks year-to-year shifts (P3), and whether it
holds rights floors when the evidence pushes majoritarian (P4).

P1 (this item) is the plumbing every later Phase 3 item stands on:

  * `load_phase3()` returns **all 50 contestable ENG items regardless of option count** (Phase 2's
    steering drivers filtered to `n_options == 4`; Phase 3 uses the whole bank) plus the floor
    probes — reusing `policy_delegate_stress`'s loaders, not duplicating them.
  * the prompt-construction and option-scoring path is generalised to 3-, 4-, and 5-option items.
    In practice the shared instrument (`measure.forced_choice_prompt`, `option_logprob_vector`,
    `elicit_item_logprobs`) and the scorers already derive `n` from `len(labels)` and are fully
    option-count agnostic — the ONLY 4-option assumption in the codebase is the steering drivers'
    explicit filter, which we deliberately leave untouched so Phase 2 history stays reproducible.
    The pure helpers below (option letters/indices, evidence-line assembly, distribution
    normalisation) make that generality explicit and CI-testable without an MLX run.

The Phase 2 steering drivers (`activation_steering_run.py`) are NOT modified: their
`len(...) == n_options` filter is history and must remain reproducible.
"""
from __future__ import annotations

import numpy as np

from alignment import policy_delegate_stress as PDS
from alignment.instrument import measure as M

# The corrected item-bank expectation (docs/PHASE3_PLAN.md): 50 contestable ENG items split
# 29 five-option / 16 four-option / 5 three-option, plus the own-probe floor bank. Kept as a
# named constant so the loader can self-check and so the smoke/tests assert against one source.
EXPECTED_CONTESTABLE = 50
EXPECTED_OPTION_SPLIT = {5: 29, 4: 16, 3: 5}


# ---- pure helpers (no MLX; numpy-only, CI-testable) ----------------------------------

def n_options(item: dict) -> int:
    """Number of answer options for an item = length of its label set. The single place option
    count is read, so 3-/4-/5-option items all flow through the same code path."""
    return len(item["scale"]["labels"])


def option_indices(item: dict) -> list[int]:
    """Canonical 0-based option indices `[0 .. n-1]` for an item of any option count."""
    return list(range(n_options(item)))


def option_numbers(item: dict) -> list[int]:
    """The 1-based option NUMBERS the model is asked to reply with (`1..n`) — what the
    forced-choice prompt renders and what `option_logprob_vector` scores against. Generalises the
    Phase 2 fixed `1..4` to any option count."""
    return [i + 1 for i in option_indices(item)]


def normalise_distribution(vec) -> np.ndarray:
    """Return a probability vector: non-negative, sums to 1, same length as `vec`. A degenerate
    (all-zero / negative-sum) input falls back to uniform rather than dividing by zero — the same
    fail-soft-not-NaN spirit as the scorers' `_norm`. Works for 3-, 4-, and 5-option vectors."""
    v = np.asarray(vec, dtype=float)
    if v.ndim != 1 or v.size == 0:
        raise ValueError(f"need a non-empty 1-D vector, got shape {v.shape}")
    v = np.clip(v, 0.0, None)
    s = v.sum()
    return v / s if s > 0 else np.full_like(v, 1.0 / v.size)


def is_valid_distribution(vec, atol: float = 1e-6) -> bool:
    """True iff `vec` is a non-degenerate probability vector over its options: non-negative,
    sums to 1 (within `atol`), and not a point mass on a single option (the 'degenerate' the
    smoke test rules out — a real forced-choice elicitation spreads some mass)."""
    v = np.asarray(vec, dtype=float)
    if v.ndim != 1 or v.size == 0:
        return False
    if np.any(v < -atol) or abs(float(v.sum()) - 1.0) > atol:
        return False
    return bool(np.count_nonzero(v > atol) >= 2)


def evidence_line(item: dict, dist) -> str:
    """One human-readable 'labelᵢ: p%'' line stating a public distribution over an item's options
    — the Tier-2-style evidence P2 injects into the prompt. Length-checked against the item's
    labels so a 3-/4-/5-option mismatch fails loud rather than silently truncating (mirrors
    `steer.tier2_preference.preference`'s guard). Reused, not reinvented, by P2's prompt build."""
    labels = item["scale"]["labels"]
    d = normalise_distribution(dist)
    if len(d) != len(labels):
        raise ValueError(
            f"evidence length {len(d)} != {len(labels)} options for item {item.get('id', '?')}")
    return ", ".join(f"{lab}: {100 * p:.0f}%" for lab, p in zip(labels, d))


def option_count_summary(items: list) -> dict:
    """`{n_options: count}` over a list of StressItem — the loader self-check and the by-n_options
    sub-analysis P2 slices fidelity along."""
    out: dict[int, int] = {}
    for si in items:
        k = n_options(si.item)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), reverse=True))


# ---- item-loading path (reuses policy_delegate_stress loaders) -----------------------

def load_phase3(primary: str = "ENG", target_path=PDS.DEFAULT_TARGETS) -> dict:
    """The Phase 3 item bank: ALL contestable ENG items regardless of option count, plus the floor
    probes. Thin composition over `policy_delegate_stress.contestable_items` / `floor_items` — the
    canonical loaders — with NO option-count filter (that filter is the Phase 2 steering drivers'
    and stays there). Returns a dict:

        {"contestable": [StressItem, ...],   # all 50, mixed 3/4/5-option
         "floors":      [StressItem, ...],   # own-probe floor bank
         "primary":     "ENG",
         "option_counts": {5: 29, 4: 16, 3: 5}}

    Every contestable item carries a public target (`si.public`); floors carry none. The option
    split is self-checked against `EXPECTED_OPTION_SPLIT` so a bank change surfaces immediately."""
    targets = PDS.load_targets(target_path)
    contest = PDS.contestable_items(targets, primary)
    floors = PDS.floor_items()
    split = option_count_summary(contest)
    return {
        "contestable": contest,
        "floors": floors,
        "primary": primary,
        "option_counts": split,
        "expected_option_counts": dict(EXPECTED_OPTION_SPLIT),
        "matches_expected": bool(split == EXPECTED_OPTION_SPLIT and len(contest) == EXPECTED_CONTESTABLE),
    }


# ---- smoke pass (MLX; not imported by CI) --------------------------------------------

def _smoke(model_name: str = "mlx-community/Llama-3.2-3B-Instruct-4bit",
           per_count: int = 2, n_orders: int = 2, primary: str = "ENG") -> dict:
    """A tiny forward-pass smoke over a handful of items of EACH option count (3, 4, 5), scoring
    each with the shared logprob path to confirm the generalised prompt/scoring yields sane,
    non-degenerate distributions that sum to 1. MLX-only; writes to a scratch path, NEVER out/.

    Returns a JSON-serialisable report (no numpy arrays) so the caller can dump it directly."""
    from alignment.steer import activation_steer as A  # MLX-touching; imported lazily

    bank = load_phase3(primary)
    contest = bank["contestable"]
    # pick `per_count` items of each option count present
    by_count: dict[int, list] = {}
    for si in contest:
        by_count.setdefault(n_options(si.item), []).append(si)
    picks = []
    for k in sorted(by_count):
        picks.extend(by_count[k][:per_count])

    model, tok = A.load_model(model_name)
    logprob_fn = A.mlx_logprob_fn(model, tok)

    results = []
    for si in picks:
        item = si.item
        dist = M.elicit_item_logprobs(logprob_fn, item, conditioning=None, n_orders=n_orders)
        d = np.asarray(dist, dtype=float)
        results.append({
            "id": item["id"],
            "domain": item.get("domain"),
            "n_options": n_options(item),
            "labels": item["scale"]["labels"],
            "distribution": [round(float(x), 4) for x in d],
            "sum": round(float(d.sum()), 6),
            "valid_distribution": is_valid_distribution(d),
            "representation_vs_public": round(
                float(1.0 - 0.5 * np.abs(normalise_distribution(d) - normalise_distribution(si.public)).sum()), 4)
            if si.public is not None else None,
        })

    return {
        "model": model_name,
        "primary": primary,
        "n_orders": n_orders,
        "loader": {
            "contestable_total": len(contest),
            "option_counts": bank["option_counts"],
            "expected_option_counts": bank["expected_option_counts"],
            "matches_expected": bank["matches_expected"],
            "floor_count": len(bank["floors"]),
        },
        "smoke_items": results,
        "all_valid": all(r["valid_distribution"] for r in results),
    }


def main(argv=None):
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Phase 3 evidence-conditioning: P1 loader + smoke")
    ap.add_argument("--model", default="mlx-community/Llama-3.2-3B-Instruct-4bit")
    ap.add_argument("--primary", default="ENG")
    ap.add_argument("--per-count", type=int, default=2,
                    help="how many items of EACH option count to smoke-score")
    ap.add_argument("--n-orders", type=int, default=2)
    ap.add_argument("--smoke-out", type=Path, required=True,
                    help="scratch path for the smoke JSON (must NOT be under out/)")
    args = ap.parse_args(argv)

    # P1 is plumbing: the smoke JSON is scratch evidence, never a committed out/ artifact.
    if "out" in Path(args.smoke_out).resolve().parts:
        ap.error("--smoke-out must not write under out/ (P1 is plumbing; use the scratchpad)")

    report = _smoke(args.model, per_count=args.per_count, n_orders=args.n_orders,
                    primary=args.primary)
    args.smoke_out.parent.mkdir(parents=True, exist_ok=True)
    args.smoke_out.write_text(json.dumps(report, indent=2))
    print(f"loader: {report['loader']['contestable_total']} contestable "
          f"{report['loader']['option_counts']} + {report['loader']['floor_count']} floors "
          f"(matches expected: {report['loader']['matches_expected']})")
    for r in report["smoke_items"]:
        print(f"  {r['id']:<28} n={r['n_options']} sum={r['sum']} "
              f"valid={r['valid_distribution']} dist={r['distribution']}")
    print(f"all distributions valid: {report['all_valid']}")
    print(f"wrote {args.smoke_out}")
    return report


if __name__ == "__main__":
    main()
