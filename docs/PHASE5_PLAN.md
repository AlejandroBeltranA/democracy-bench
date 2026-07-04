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

### REP1 — P2 + P3 on 8B ☐
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
