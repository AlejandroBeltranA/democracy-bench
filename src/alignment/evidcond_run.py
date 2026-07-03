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

from alignment import drift
from alignment import policy_delegate_stress as PDS
from alignment.instrument import measure as M
from alignment.instrument import scorers as S
from alignment.steer import tier2_preference as T2

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


# ---- P2 pure aggregation helpers (no MLX; numpy-only, CI-testable) --------------------

def representation(model_dist, target_dist) -> float:
    """Headline representation (1 - TV) of a model distribution against a public target — the
    same metric family (`scorers.representation_score`) the rest of the project scores on. Both
    vectors are normalised to their option set, so 3-/4-/5-option items share one call."""
    return float(S.representation_score(
        normalise_distribution(model_dist), normalise_distribution(target_dist)))


def fidelity_gap(evidence_representation: float) -> float:
    """How far short of the PROVIDED evidence the model lands: `1 - representation` under the
    evidence-conditioned prompt. 0 = the model reproduced the injected distribution exactly;
    →1 = it ignored the evidence entirely. This is the P2 headline the LoRA rung is sized against."""
    return float(1.0 - evidence_representation)


def condition_summary(reps, seed: int = 0) -> dict:
    """Aggregate a list of per-item representation scores into {mean, ci, n} via the project's
    nonparametric bootstrap-over-items (`bootstrap_mean_ci`) — the right CI when the units are
    ITEMS. Kept separate from the delta so both conditions report the identical shape."""
    return S.bootstrap_mean_ci(reps, seed=seed)


def delta_summary(no_ev_reps, ev_reps, seed: int = 0) -> dict:
    """Paired per-item delta (evidence − no-evidence) representation with a bootstrap-over-items
    CI. Pairing is item-wise (same item under both conditions), so the two lists must be aligned
    and equal length — the CI then answers 'does evidence move representation, over items?'."""
    a = np.asarray(list(no_ev_reps), dtype=float)
    b = np.asarray(list(ev_reps), dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"paired delta needs aligned lists, got {a.shape} vs {b.shape}")
    return S.bootstrap_mean_ci(b - a, seed=seed)


def group_condition_summaries(rows: list, key: str, seed: int = 0) -> dict:
    """Slice per-item rows by a grouping key (e.g. 'n_options' or 'domain') and return, per group,
    the mean±CI representation under each condition plus the paired delta. `rows` are dicts each
    carrying `key`, `representation_no_evidence`, `representation_evidence`. Powers the P2
    by-option-count and by-domain sub-analyses off one aggregation path."""
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out: dict = {}
    for g in sorted(groups, key=lambda x: (isinstance(x, str), x)):
        grp = groups[g]
        no_ev = [r["representation_no_evidence"] for r in grp]
        ev = [r["representation_evidence"] for r in grp]
        out[str(g)] = {
            "n_items": len(grp),
            "no_evidence": condition_summary(no_ev, seed=seed),
            "evidence": condition_summary(ev, seed=seed),
            "delta": delta_summary(no_ev, ev, seed=seed),
            "fidelity_gap": fidelity_gap(condition_summary(ev, seed=seed)["mean"])
            if grp else None,
        }
    return out


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


# ---- P2 baseline deference-fidelity runner (MLX; not imported by CI) ------------------

def evidence_conditioning(si) -> str:
    """The evidence-conditioned prompt prefix for a contestable item: the Tier-2 phrasing
    (`steer.tier2_preference.preference`) stating the item's real England public distribution,
    keyed off the target's own label/year. Reused verbatim so Phase 3 stays comparable to the
    prior tiers — the ONLY change is that the injected distribution is scored against later."""
    return T2.preference(si.target_meta["label"], si.target_meta["year"], si.item, si.public)


def run_baseline(model_name: str = "mlx-community/Llama-3.2-3B-Instruct-4bit",
                 n_orders: int = 2, seed: int = 0, primary: str = "ENG",
                 items: list | None = None, floors: list | None = None,
                 boot: int = 2000) -> dict:
    """P2: baseline deference fidelity. For every contestable item elicit the option distribution
    under two conditions — (a) no-evidence (default prompt) and (b) evidence-conditioned (the
    item's real 2024 England distribution injected via Tier-2 phrasing) — and score representation
    against the SAME public target under both. Aggregates over items with `bootstrap_mean_ci`:
    mean representation per condition, the paired delta, and the fidelity gap (1 − evidence
    representation). Floors run under both conditions with NO synthetic hostile evidence (P4 owns
    that); condition (b) for a floor injects the floor's OWN no-evidence distribution as benign
    evidence, so we test that the evidence-conditioning MECHANISM does not by itself move floor mass.
    """
    from alignment.steer import activation_steer as A  # MLX-touching; imported lazily

    bank = load_phase3(primary)
    contest = bank["contestable"] if items is None else items
    floor_items = bank["floors"] if floors is None else floors

    model, tok = A.load_model(model_name)
    logprob_fn = A.mlx_logprob_fn(model, tok)

    def elicit(item, conditioning):
        return M.elicit_item_logprobs(logprob_fn, item, conditioning=conditioning,
                                      n_orders=n_orders, seed=seed)

    # ---- contestable items: no-evidence vs evidence-conditioned ----
    item_rows = []
    for si in contest:
        item = si.item
        d_no = np.asarray(elicit(item, None), dtype=float)
        d_ev = np.asarray(elicit(item, evidence_conditioning(si)), dtype=float)
        rep_no = representation(d_no, si.public)
        rep_ev = representation(d_ev, si.public)
        item_rows.append({
            "id": item["id"],
            "domain": item.get("domain"),
            "n_options": n_options(item),
            "public": [round(float(x), 4) for x in normalise_distribution(si.public)],
            "dist_no_evidence": [round(float(x), 4) for x in d_no],
            "dist_evidence": [round(float(x), 4) for x in d_ev],
            "representation_no_evidence": rep_no,
            "representation_evidence": rep_ev,
            "delta": rep_ev - rep_no,
        })

    no_reps = [r["representation_no_evidence"] for r in item_rows]
    ev_reps = [r["representation_evidence"] for r in item_rows]
    ev_summary = condition_summary(ev_reps, seed=seed)
    headline = {
        "no_evidence": condition_summary(no_reps, seed=seed),
        "evidence": ev_summary,
        "delta": delta_summary(no_reps, ev_reps, seed=seed),
        "fidelity_gap": fidelity_gap(ev_summary["mean"]),
    }

    # ---- floors: own-probe elicitation, NO synthetic hostile evidence (P4 owns that) ----
    # Per the P2 spec, condition (b) for a floor is the floor item's OWN elicitation with no
    # injected distribution — we are checking that turning on the contestable evidence-conditioning
    # machinery leaves the (un-targeted) rights floors exactly where they were. Because the floor
    # prompt is identical in both conditions and the logprob read is deterministic, the two floor
    # distributions coincide by construction; a nonzero delta would signal the machinery leaking
    # into floor scoring. (Hostile-evidence floor stress is P4's job, not P2's.)
    floor_rows = []
    for si in floor_items:
        item = si.item
        fdir = int(item["floor_dir"])
        d_no = np.asarray(elicit(item, None), dtype=float)
        d_ev = np.asarray(elicit(item, None), dtype=float)   # same benign prompt: no evidence injected
        floor_rows.append({
            "id": item["id"],
            "domain": item.get("domain"),
            "floor_dir": fdir,
            "dist_no_evidence": [round(float(x), 4) for x in d_no],
            "dist_evidence": [round(float(x), 4) for x in d_ev],
            "protective_mass_no_evidence": drift.protective_mass(d_no, fdir),
            "protective_mass_evidence": drift.protective_mass(d_ev, fdir),
        })
    floor_no = [r["protective_mass_no_evidence"] for r in floor_rows]
    floor_ev = [r["protective_mass_evidence"] for r in floor_rows]
    floor_summary = {
        "no_evidence": condition_summary(floor_no, seed=seed),
        "evidence": condition_summary(floor_ev, seed=seed),
        "delta": delta_summary(floor_no, floor_ev, seed=seed),
    }

    report = {
        "run": PDS_run_block(model_name, primary, n_orders, seed, boot,
                             len(contest), len(floor_items)),
        "headline": headline,
        "by_option_count": group_condition_summaries(item_rows, "n_options", seed=seed),
        "by_domain": group_condition_summaries(item_rows, "domain", seed=seed),
        "floors": floor_summary,
        "items": item_rows,
        "floor_items": floor_rows,
    }
    return report


def PDS_run_block(model_name, primary, n_orders, seed, boot, n_contest, n_floor) -> dict:
    """The P2 run block, matching activation_steering_run.py's convention (generated_at, command,
    code_ref via run_meta, model, grid echo, kind)."""
    from alignment import run_meta
    return run_meta.run_block(
        command="python -m alignment.evidcond_run --baseline",
        models=[model_name], schema_version=1,
        extra={
            "kind": "evidcond_baseline",
            "primary": primary,
            "n_orders": n_orders,
            "seed": seed,
            "n_bootstrap": boot,
            "n_contestable": n_contest,
            "n_floor": n_floor,
            "evidence_phrasing": "steer.tier2_preference.preference (Tier-2)",
            "scorer": "scorers.representation_score (1 - TV)",
        })


def main(argv=None):
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Phase 3 evidence-conditioning: P1 loader/smoke + P2 baseline")
    ap.add_argument("--model", default="mlx-community/Llama-3.2-3B-Instruct-4bit")
    ap.add_argument("--primary", default="ENG")
    ap.add_argument("--per-count", type=int, default=2,
                    help="how many items of EACH option count to smoke-score (P1 smoke / P2 smoke)")
    ap.add_argument("--n-orders", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-bootstrap", type=int, default=2000)
    ap.add_argument("--baseline", action="store_true",
                    help="P2: run the baseline deference-fidelity battery (no-evidence vs "
                         "evidence-conditioned) over all contestable items + floors")
    ap.add_argument("--out", type=Path,
                    help="P2 real run: committed artifact path (must be under out/)")
    ap.add_argument("--smoke-out", type=Path,
                    help="scratch path for a smoke JSON (must NOT be under out/)")
    args = ap.parse_args(argv)

    if not args.baseline:
        # P1 plumbing smoke (default): loader + non-degenerate distribution check.
        if args.smoke_out is None:
            ap.error("P1 smoke needs --smoke-out (scratch path)")
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

    # ---- P2 baseline ----
    smoke = args.smoke_out is not None
    if smoke == bool(args.out):
        ap.error("give exactly one of --smoke-out (scratch smoke) or --out (real run)")
    dest = args.smoke_out if smoke else args.out
    if smoke and "out" in Path(dest).resolve().parts:
        ap.error("--smoke-out must not write under out/ (use the scratchpad)")
    if not smoke and "out" not in Path(dest).resolve().parts:
        ap.error("--out must write under out/")
    if not smoke and Path(dest).exists():
        ap.error(f"refusing to overwrite existing artifact {dest} (hard rule: new path per run)")

    bank = load_phase3(args.primary)
    items, floors = bank["contestable"], bank["floors"]
    if smoke:
        # a tiny grid spanning option counts + a couple of floors
        by_count: dict[int, list] = {}
        for si in items:
            by_count.setdefault(n_options(si.item), []).append(si)
        picks = []
        for k in sorted(by_count):
            picks.extend(by_count[k][:max(1, args.per_count // 2 or 1)])
        items = picks[:4] if len(picks) >= 4 else picks
        floors = floors[:2]

    report = run_baseline(args.model, n_orders=args.n_orders, seed=args.seed,
                          primary=args.primary, items=items, floors=floors,
                          boot=args.n_bootstrap)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(report, indent=2))

    h = report["headline"]
    print(f"[P2 baseline{' SMOKE' if smoke else ''}] {len(report['items'])} contestable, "
          f"{len(report['floor_items'])} floors")
    print(f"  no-evidence rep:  {h['no_evidence']['mean']:.3f} "
          f"CI[{h['no_evidence']['ci'][0]:.3f},{h['no_evidence']['ci'][1]:.3f}]")
    print(f"  evidence    rep:  {h['evidence']['mean']:.3f} "
          f"CI[{h['evidence']['ci'][0]:.3f},{h['evidence']['ci'][1]:.3f}]")
    print(f"  fidelity gap:     {h['fidelity_gap']:.3f}")
    print(f"  delta (ev-noev):  {h['delta']['mean']:+.3f} "
          f"CI[{h['delta']['ci'][0]:+.3f},{h['delta']['ci'][1]:+.3f}]")
    fl = report["floors"]
    print(f"  floor mass:  no-ev {fl['no_evidence']['mean']:.3f}  "
          f"ev {fl['evidence']['mean']:.3f}  "
          f"delta {fl['delta']['mean']:+.3f} "
          f"CI[{fl['delta']['ci'][0]:+.3f},{fl['delta']['ci'][1]:+.3f}]")
    if smoke:
        worse = [r["id"] for r in report["items"] if r["delta"] < 0]
        print(f"  smoke items where evidence made it WORSE: {worse or 'none'}")
    print(f"wrote {dest}")
    return report


if __name__ == "__main__":
    main()
