# Phase 2 (activation steering) — handoff

**Date:** 2026-07-03 · **Branch:** `phase2-activation-steering` · **Model:** `mlx-community/Llama-3.2-3B-Instruct-4bit`

## TL;DR — verdict

Phase 2 activation steering is a **comprehensive, publication-ready NEGATIVE with a geometric
mechanism.** A diff-of-means "public-agreement direction" injected into the residual stream does
**not** move this model toward the UK public in a way that generalises across items, at any layer,
with the rights-floor held. The original promising result (`out/activation_steering_3b_4opt.json`,
layer 11 α=4, 0.692→0.752) was the **inject-then-score-against-the-same-16-items confound** — it
vanishes under held-out capture and under error bars.

The negative is characterised from **seven independent angles** (R1–R4, W3, R7, R8), all committed as
small JSON artifacts in `out/`. This is the honest-negative mirror of Phase 1 (which was also a
negative and is in the paper). The decisive test (R1) and the mechanism (W3) both landed, satisfying
the plan's stop condition. The human stopped the loop here to write the paper section; W1/W4/W5 are
left for a future agent (plan below).

## What the mechanism IS (the one thing to remember)

W3 geometry (`docs/PHASE2_GEOMETRY_NOTE.md`) found the per-item steering arrows are **strongly
aligned at every layer** (mean off-diagonal cosine 0.56–0.82) — there IS one dominant direction. But
because each arrow is a `(persona − default)` shift and it is ~0.8 shared across 16 items with
*different* public targets, that direction is a **generic persona/style axis** ("sound like a
surveyed member of the public"), **not** per-item public content. R8 nailed this from a second angle:
a totally irrelevant persona (an 1850 subsistence farmer) yields a direction **0.852 cosine-parallel**
to the real UK-2024 one. So the axis steering injects is persona-generic; the ~15% persona-specific
residual is exactly the item-memorising, non-generalising slice R1 killed. This also re-explains
Phase 1: a global logit-bias on the *output* is the same move as a shared shift in the *stream* — one
direction cannot fit all items.

---

## What was done, iteration by iteration

Each item: pure-logic code + tests (`python -m pytest -q` kept green, 165→212), a smoke-test on a tiny
grid to `/tmp`, then the real run to a **new** `out/*.json` path, then a Loop-log entry + commit. All
per the plan's per-iteration protocol.

| Item | Verdict | Key numbers | Artifact |
|---|---|---|---|
| **R1** held-out capture | **KILLED** (decisive) | held-out gain CIs fail at L11/L14; α2 significantly negative; floors also fail out-of-sample | `out/act_steer_holdout_3b.json` |
| **R2** random-direction control | real but **item-local** | captured dir beats matched-norm random only at L11 α4 (in-sample); α2/α6 within noise | `out/act_steer_randctrl_3b.json` |
| **R3** negative dose | **not a concept axis** | no antisymmetry; inverted polarity at |α|=1,2; baseline sits in a perturbation *valley* (best point α=−2) | `out/act_steer_negalpha_3b.json` |
| **R4** error bars (headline grid) | **contradiction found + resolved** | L11 headline evaporates (α4 gain −0.001 CI[−0.044,+0.042]); in-sample signal moved to L17/21 | `out/act_steer_ci_3b.json` |
| R4 follow-up | held-out fails at L17/21 too | no cell's CI clears zero at 17/21 either → negative airtight across all 4 candidate layers | `out/act_steer_holdout_late_3b.json` |
| **W3** arrow geometry | **mechanism found** | arrows aligned everywhere (cos 0.56–0.82); persona-generic, not public-content; depth adds domain fracture | `out/act_steer_geometry_3b.json` + `docs/PHASE2_GEOMETRY_NOTE.md` |
| **R7** off-task coherence | steering has a real **capability cost** | off-task acc α0/2=1.00, α4=0.70, α6=0.20, α8=0.00; arithmetic corrupts first | `out/act_steer_offtask_3b.json` |
| **R8** wrong-persona control | axis is **85% persona-generic** | cos(real, 1850-farmer control)=+0.852; effects indistinguishable at α2 | `out/act_steer_personactrl_3b.json` |

**R5, R6, W2 were SKIPPED** — all gated on "only if R1 survived", and R1 killed the result.

### Where it succeeded / where it "failed"

- **Succeeded** (as engineering + science): every planned R-item ran cleanly, the confound was
  isolated (R1), the mechanism was explained (W3), and two independent confirmations (R7, R8) held.
  The full test suite passes (212). The result is a coherent, well-evidenced negative — a success in
  the plan's own terms ("harden into a defensible claim **or kill it honestly**"). One live surprise
  (R4's contradiction) was caught by the protocol, flagged, and resolved with a targeted follow-up
  rather than papered over.
- **"Failed"** (the scientific claim, by design): activation steering does **not** work as an
  alignment lever for per-item public representation on this model. That is the finding, not a bug.

---

## Code added (all committed)

**Engine — `src/alignment/steer/activation_steer.py`** (pure helpers are numpy-only / CI-testable;
`capture_*`, `dose_response*`, `holdout_dose_response`, `generate_under_tap` touch MLX and are
smoke-tested live, not in CI):
- pure: `kfold_test_indices`, `held_out_gains`, `random_direction`, `cosine_matrix`,
  `within_cross_domain_cosine`, `cosine_to_mean`
- mlx: `capture_item_directions`, `dose_response_items`, `holdout_dose_response`,
  `generate_under_tap`, and a `persona_text` override added to `capture_direction`

**Driver — `src/alignment/activation_steering_run.py`**:
- runners: `run_holdout` (R1), `run_randctrl` (R2), `run_negdose` (R3), `run_ci` (R4),
  `run_geometry` (W3), `run_offtask` (R7), `run_personactrl` (R8)
- pure helpers: `_summarize_holdout_layer`, `_curve_gain`, `_randctrl_comparison`,
  `antisymmetry_report`, `summarize_ci_layer`, `_ci_verdict`, `off_task_match`, `OFF_TASK_PROBES`,
  `CONTROL_PERSONA`
- CLI flags: `--holdout k`, `--direction random --seeds …`, `--negdose`, `--ci`, `--geometry`,
  `--offtask`, `--persona-control [text]`

**Scorers — `src/alignment/instrument/scorers.py`**: `bootstrap_mean_ci` (nonparametric
bootstrap-over-observations CI; the item/seed-level CI the R-battery leans on).

**Tests — `tests/test_activation_steer.py`**: 11 → 42 → 56 tests (47 new). Cover fold splitting,
held-out gains, bootstrap CI, holdout/CI verdicts, random-direction norm-matching, curve gain,
random-control comparison, antisymmetry, cosine geometry, off-task exact-match, control-persona
sanity. **Full suite: 212 passed.**

## CLI reference (to reproduce or extend)

```bash
source .venv/bin/activate    # MLX works here; ~0.33 s / forward pass on this machine
# R1 held-out (decisive):
python -m alignment.activation_steering_run --holdout 4 --layers 11 14 --alphas 2 4 6 --n-orders 4 --out out/act_steer_holdout_3b.json
# R2 random control:
python -m alignment.activation_steering_run --direction random --layers 11 --alphas 2 4 6 --seeds 0 1 2 --n-orders 2 --out out/act_steer_randctrl_3b.json
# R3 negative dose:
python -m alignment.activation_steering_run --negdose --layers 11 --alphas -4 -2 -1 0 1 2 4 --n-orders 2 --out out/act_steer_negalpha_3b.json
# R4 CIs on the headline grid (~57 min):
python -m alignment.activation_steering_run --ci --layers 7 11 14 17 21 --alphas 0 1 2 4 6 8 --seeds 0 1 2 --n-orders 4 --out out/act_steer_ci_3b.json
# W3 geometry (~2 min):
python -m alignment.activation_steering_run --geometry --layers 7 11 14 17 21 --out out/act_steer_geometry_3b.json
# R7 off-task coherence:
python -m alignment.activation_steering_run --offtask --layers 11 --alphas 0 2 4 6 8 --out out/act_steer_offtask_3b.json
# R8 wrong-persona control:
python -m alignment.activation_steering_run --persona-control --layers 11 --alphas 0 2 4 6 --n-orders 2 --out out/act_steer_personactrl_3b.json
```

---

## Remaining work — plan for the next agent

Read this handoff and `docs/PHASE2_ROBUSTNESS_PLAN.md` (the Loop log at the bottom is the shared
state) before starting. Hard rules still apply: never overwrite `out/*.json` (new path per run);
smoke to `/tmp` first; keep `pytest -q` green; pure logic gets numpy-only tests; every artifact
carries a `run_meta.run_block`.

### W1 — Steering implements tracking (the flagship) — RECOMMENDED next, but expected to FAIL

**Question the paper cares about most:** does moving the arrow from a *2022* persona to a *2024*
persona move the model along the **real** 2022→2024 public shift? This tests steering against the
project's core "governments change" tracking axis, not just static representation.

**Data is ready:** `out/_bsa_delta_check.json` → `summary.sig_2022_2024_bonferroni` lists the **10**
Bonferroni-significant items (`nhs_satisfaction`, `ae_satisfaction`, `dentist_satisfaction`,
`gp_satisfaction`, `social_care_satisfaction`, `redistribution`, `welfare_dependency`,
`benefit_cheat_poverty_reason`, `defence_spending`, `big_business_workers`). Each item in
`items[]` has `distributions` keyed `{"2022","2023","2024"}`, a `harmonised_labels` bool (all 10 sig
items are `True`; the 6 in `summary.not_harmonised` are already excluded), and `pairs` with the
`2022->2024` `delta` / `mean_position_shift` / significance.

**Method (mostly reuses existing code):**
1. Build two persona strings, "median England respondent in 2022" and "…in 2024" (persona-year
   variants). **Reuse the `persona_text=` override already added to `capture_direction`** (R8 added
   it). Capture `direction_2022` and `direction_2024` at layer 11 (and maybe 7/14 for robustness).
2. **Cheap kill-check first (do this before the full build):** report `cosine(direction_2022,
   direction_2024)`. Given R8 (cos 0.852 for an 1850-farmer!), these two near-identical personas will
   almost certainly give cosine ≈ 1.0. If so, `steered@2022 ≈ steered@2024` ⇒ `model_delta ≈ 0` ⇒
   tracking elasticity ≈ 0 **by construction** — a one-run demonstration that steering cannot
   implement tracking. That single number may be the whole flagship result.
3. Full build (if the cosine leaves any room): for each of the 10 items compute
   `steered_distribution` under `direction_2022` and under `direction_2024`
   (`activation_steer.steered_distribution`), then feed to **`scorers.tracking(model_t=steered@2022,
   model_t1=steered@2024, target_t=dist2022, target_t1=dist2024, …)`** — it already returns
   direction-match + elasticity with CIs. Headline metric = tracking elasticity under steering.
4. Floors: measure the floor probes under **both** arrows; floors must hold.
5. Output `out/act_steer_tracking_3b.json` with a `run_block`. New `run_tracking` driver + `--tracking`
   flag; pure-logic tests for any new aggregation (the tracking math itself is already tested in
   `scorers`). Caveat to bake in: harmonised-label items only (already the case for the 10).
**Expected outcome:** FAIL (elasticity ≈ 0, direction-match ≈ chance) — because the arrows are
persona-generic (step 2) and R1 showed no item-specific transfer. Frame it as the flagship negative.

### W4 — Steering under adversarial pressure — OPTIONAL, low priority (mostly moot)

Combine the layer-11 tap with the `constitution_plus_adversarial_majority` pressure prompt from
`policy_delegate_stress.py` on the floor probes: does mid-layer steering stay floor-safe when the
*prompt* pushes majoritarian? **Mostly moot for a negative** — there is no good operating point to
defend, and R4/R7 already show floors crack and capability degrades under dose. Only worth it if the
paper wants a "steering + hostile prompt" stress figure. Output `out/act_steer_pressure_3b.json`.

### W5 — LoRA rung — STRETCH, requires human sign-off before any compute

LoRA-fine-tune (mlx-lm supports it) toward the public targets on train items; evaluate held-out
representation, floor mass, and persistence under the W4 pressure prompts vs the runtime tap.
Completes the context→decode→activation→**weights** ladder. Big job. The plan explicitly says:
**propose a design in the Loop log and wait for human sign-off before burning compute.** Do not start
this autonomously.

### R5 / R6 / W2 — SKIPPED, keep skipped

Gated on "only if R1 survived." R1 killed the result. Do not run unless a future finding revives the
positive claim (nothing here suggests it will).

---

## Environment & gotchas

- **venv:** `source .venv/bin/activate`. MLX is available there (Apple Silicon); CI is numpy-only, so
  keep model-touching code out of the CI test path (smoke-test it live instead).
- **Throughput:** ~0.33 s / forward pass (3B-4bit). Budget: R4-style full grid (5 layers × 6 α × 3
  seeds × 4 orders) ≈ 57 min. Held-out (2 layers, k=4) ≈ 15–20 min. Geometry / off-task / persona ≈
  2–4 min. Launch one MLX run at a time (GPU saturates).
- **Never overwrite `out/*.json`.** Every run writes a new experiment-named path. The original
  point-estimate artifact `out/activation_steering_3b_4opt.json` is the *superseded* published curve —
  left intact; R4's `out/act_steer_ci_3b.json` supersedes it without touching it.
- **Untouched pre-existing changes:** at session start `README.md`, `scripts/run_all.sh`,
  `out/_bsa_delta_check.json`, and `out/activation_steering_3b_4opt.json` had uncommitted edits I did
  **not** make and did **not** commit. Left as-is for the human. `_bsa_delta_check.json` is a W1 input.
- **Commits:** 8 commits on `phase2-activation-steering` (one per work item + the R4 follow-up), from
  `204a830` (R1) to `a37a4e3` (R8). Each artifact is small JSON (< 10 KB) and committed with its code.
