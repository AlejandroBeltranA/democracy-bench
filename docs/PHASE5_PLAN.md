# Phase 5 — 8B replication of the core battery (plan + Loop log)

**Date opened:** 2026-07-04 · **Branch:** `phase4-floor-guards` (rename/merge later is Alex's call)
**Replication model:** `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` (vs the arc's 3B-4bit)
**Supervisor:** Claude (main session) · **Worker:** Opus subagents

## Objective

PAPER_RESULTS stamps every quantitative claim "single-model (3B-4bit)". Phase 5 replicates the
core Phase 3/4 battery on an 8B model to either generalise the findings or scope them honestly.
Both outcomes are paper-strengthening; neither is a failure. The claims under test:

1. **P2** — evidence lift n.s. + heterogeneous (does a bigger model defer better?)
2. **P3** — evidence tracking positive (does 8/10 direction, elasticity>0 replicate? Old memory
   note: "tracking inconclusive at 3B — needs bigger model" — 8B may sharpen OR the P3 positive
   may be 3B-specific.)
3. **P4** — hostile evidence cracks floors; prompt attack n.s. (does the asymmetry replicate?
   Is the 8B a stronger floor-holder at baseline than 3B's weak 0.512 / 5-of-12-below?)
4. **G1 subset** — do prompt guards still fail? (no_guard + guard_rights_floor +
   guard_constitution only; provenance/combined were dominated arms)

NOT replicated: steering/LoRA rungs (mechanistically explained negatives, expensive) and the
50-item bank build (model-independent).

## Hard rules (unchanged)

1. `source .venv/bin/activate`; one MLX job at a time. 8B-4bit ≈ 2-3× slower per pass than 3B —
   budget accordingly and smoke first. Model download (~4.5 GB) is allowed, once.
2. Never overwrite `out/*.json` — new paths suffixed `_8b`.
3. Smoke to the scratchpad first; artifacts carry full run blocks (model id explicit).
4. `python -m pytest -q` stays green (384 at open). Reuse the existing runners — the model id
   should be a parameter, NOT copy-pasted drivers; if a runner hardcodes the 3B model, add a
   `--model` flag (default unchanged so all committed run-block commands stay reproducible).
5. Do NOT touch README.md, scripts/run_all.sh (Alex's uncommitted edits).
6. Per item: Loop log entry here; supervisor reviews and commits.
7. Numbers comparisons vs 3B use the committed artifacts, never re-run 3B.

## Work items

### REP1 — P2 + P3 on 8B ☑
Same grids as the 3B runs (P2: 50 items × {no-evidence, evidence-2024} × n_orders=2 + 12 floor
probes; P3: 10 sig items × {evidence-2022, evidence-2024}). Outputs `out/evidcond_baseline_8b.json`,
`out/evidcond_tracking_8b.json`. Report side-by-side vs 3B: fidelity gap, delta CI, n-worse,
direction match, elasticity CI. Compute ≈ 310 passes × ~0.7-1 s ≈ 10-15 min after download.

### REP2 — P4 + G1-subset on 8B ☐
P4's 2×2 on the 12 floor probes, plus guard arms {no_guard, rights_floor, constitution} × 4
conditions. Outputs `out/evidcond_floors_8b.json`, `out/floorguard_grid_8b.json`. Report:
baseline floor mass (is 8B a stronger floor-holder?), hostile-evidence delta, prompt-attack
delta, guard verdicts, homogenisation TV — side-by-side vs 3B.

### REP3 — Paper integration ☐
Extend `scripts/extract_paper_results.py` + `docs/PAPER_RESULTS.md` with a "Model robustness
(8B replication)" section: which claims replicate, which are scoped to 3B. Update REPRODUCTION.md
with the 8B commands. Figures optionally gain 8B overlays ONLY where they don't clutter (worker
judgement, flag choices). Tests extended accordingly.

## Loop log

### 2026-07-04 — Phase 5 opened
Rationale: single-model caveat is the paper's weakest point; 8B replication of P2/P3/P4/G1-subset
is cheap and decisive either way. REP1 dispatched.

### 2026-07-04 — REP1 DONE (P2 + P3 on 8B) ☑
**Model:** `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` (downloaded ~4.5 GB, once; 4bit variant
was not cached — only 3bit/8bit were). **Throughput:** ~1.11 s / forward pass (vs 3B's ~0.33 s →
3.4× slower, in line with the plan's 2-3× budget). Full REP1 compute ≈ 308 passes ≈ 5.7 min
(P2 4:44, P3 1:23) — well under the 45-min ceiling; smoke validated non-degenerate distributions
(sum→1, mass spread over ≥2 options) at 4 items before the full runs.

**`--model` flag:** already existed (`evidcond_run.main` line 1824, default = the 3B id) and is
already threaded through to `run_baseline`/`run_tracking`/`run_floors`/`run_guard_grid` via
`args.model`. **No code change needed.** Added two numpy-only reproducibility-guard tests
(`test_runner_model_defaults_are_the_3b_id`, `test_cli_model_flag_defaults_to_the_3b_id`) so the
committed run-block commands stay 3B-reproducible. Tests 384 → **386 green**.

Artifacts (new `_8b` paths; 3B artifacts untouched): `out/evidcond_baseline_8b.json`,
`out/evidcond_tracking_8b.json` — both carry full run blocks with the 8B model id explicit.

**P2 side-by-side (evidence deference fidelity):**

| metric | 3B | 8B | verdict |
|---|---|---|---|
| no-evidence rep | 0.727 CI[0.687,0.763] | 0.698 CI[0.658,0.735] | close (8B slightly lower) |
| evidence rep | 0.746 CI[0.717,0.773] | 0.712 CI[0.677,0.747] | close |
| **delta (ev−noev)** | **+0.019 CI[−0.020,+0.059]** | **+0.014 CI[−0.042,+0.071]** | **REPLICATES** — evidence lift n.s. on both (CI straddles 0) |
| fidelity gap | 0.254 | 0.288 | REPLICATES (still a large residual gap; 8B no better) |
| n-worse-than-0.05 | 13/50 | 17/50 | REPLICATES — heterogeneous, evidence hurts a big minority |
| floor mass (no-ev) | 0.512 | 0.707 | **DOES NOT REPLICATE** — 8B is a materially stronger baseline floor-holder |

P2 verdict: **the core P2 claim (evidence lift is n.s. + heterogeneous) REPLICATES on 8B** — a
bigger model does NOT defer better; if anything slightly worse (larger gap, more items harmed).
Notable side-finding for REP2: 8B holds rights floors much better at baseline (0.707 vs 0.512),
which pre-answers the plan's "is the 8B a stronger floor-holder?" question — YES.

**P3 side-by-side (evidence tracking):**

| metric | 3B | 8B | verdict |
|---|---|---|---|
| direction match | 8/10 = 0.80 | 8/10 = 0.80 | **REPLICATES** — same 8/10 rate |
| **elasticity** | **+0.395 CI[+0.020,+0.811]** | **+0.647 CI[+0.008,+1.209]** | **REPLICATES** — positive, CI clears 0 on both; 8B stronger, CIs overlap heavily |
| model moved | 10/10 | 10/10 | REPLICATES |

Per-item direction match: **8/10 items agree** across sizes. Two flip but they *cancel*:
`welfare_dependency` mismatch→match on 8B, `social_care_satisfaction` match→mismatch on 8B — so the
headline 8/10 is identical for a slightly different item set. The two 3B mismatches
(`welfare_dependency`, `big_business_workers`) are also the two smallest / hardest real shifts;
`big_business_workers` stays a mismatch on both.

P3 verdict: **the P3 positive (8/10 direction, elasticity>0) REPLICATES on 8B** — this resolves the
old memory note "tracking inconclusive at 3B — needs bigger model": the 8B does NOT overturn it, it
*strengthens* it (elasticity +0.395 → +0.647, direction rate identical). Evidence-conditioned
tracking is a real, size-robust capability on this battery.

**Surprises:** (1) `--delta-check` default is repo-root-relative `out/_bsa_delta_check.json`; must
pass an absolute path when launching P3 from `src/` — no bug, just a cwd gotcha (used absolute path).
(2) The 8B baseline floor mass jump (0.512→0.707) is the one non-replication and is a *positive*
finding for the paper's floor-safety story — flagged for REP2's P4 attack analysis.
No line-stopping surprises (no degenerate distributions, download fine, compute far under budget).
