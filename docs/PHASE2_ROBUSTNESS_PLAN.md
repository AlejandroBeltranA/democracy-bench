# Phase 2 robustness & completion plan — execution loop spec

Audience: an autonomous coding model working this repo in a loop, one work item per
iteration. Read this whole file before the first iteration. Update the checkboxes and the
**Loop log** section at the bottom as you go; they are the loop's shared state.

## Context (do not skip)

Phase 2 (activation steering) produced a promising first result in
`out/activation_steering_3b_4opt.json` (Llama-3.2-3B, layers 7/11/14/17/21 × α 0–8):
mid-layer steering (layer 11, α=4) raised representation 0.692→0.752 with the rights-floor
protective mass held (≥ 0.5); late layers (17/21) gained representation only by eroding
floors ("bad steer"). **This is not yet a claim.** Two threats:

1. The steering direction is captured on the SAME 16 contestable items it is scored on —
   the inject-then-score-against trap that already invalidated naive readings of Tier-2 and
   Phase 1 (see `docs/LOGPROBS_RESEARCH_DIRECTION.md`, "Confounds").
2. Curves are noisy: n_orders=2, single seed, no CIs; non-monotonic wobble shows it.

The goal of this plan: either harden the result into a defensible claim or kill it honestly.
Both outcomes are publishable (Phase 1 was an honest negative and is in the paper).

## Repo conventions (hard rules)

- NEVER overwrite existing `out/*.json` artifacts. Every run writes to a NEW path named
  after the experiment (e.g. `out/act_steer_holdout_3b.json`). Verify drivers with a
  throwaway path under `/tmp` first.
- All measurement goes through `option_logprob_vector` / the existing MLX elicitation in
  `src/alignment/steer/activation_steer.py` so numbers stay comparable to the published curve.
- Fail closed: unreadable elicitations raise; never substitute uniform or fabricated vectors.
  A steering dose that breaks option emission is recorded as `broke`, not an error.
- Every artifact carries the `run_meta.run_block(...)` metadata block (command, code_ref,
  seeds, alphas, layers, n_orders, model id).
- Pure-logic changes need pytest coverage in `tests/test_activation_steer.py` (offline,
  numpy-only — CI has no MLX). The MLX path is smoke-tested live, not in CI.
- `python -m pytest -q` must pass (165+ tests) before an iteration ends.
- Long MLX runs: launch one at a time (they saturate the GPU); the 3B model takes roughly
  the length of the published sweep (~40 min for 5 layers × 6 alphas × 28 items × 2 orders).
  Budget iterations accordingly; prefer overnight batches.
- Model ids: `mlx-community/Llama-3.2-3B-Instruct-4bit` (primary; cached),
  `mlx-community/Meta-Llama-3.1-8B-Instruct-8bit` (cached), Qwen-2.5-7B-4bit (download ok).

## Key files

- Engine: `src/alignment/steer/activation_steer.py` — `capture_direction` (diff-of-means
  default vs GBR-2024 persona), `install_tap` (residual-stream injection), `dose_response`.
- Driver: `src/alignment/activation_steering_run.py` (argparse; sweeps layers × alphas,
  picks floor-safe operating point).
- Items/targets: loaded the same way `policy_delegate_stress.py` does (BSA-only regional
  layer; 16 contestable 4-option items + 12 floor probes at n_options=4).
- Tracking deltas: `out/_bsa_delta_check.json` — 10 items with Bonferroni-significant
  2022→2024 population shifts (see W1 below). Scorers: `src/alignment/instrument/scorers.py`.

---

## Work items

Do them in order; each is one-to-few loop iterations. R1–R4 decide whether Phase 2 is real —
do NOT start W-items until R1–R4 are done and their verdict is written in the Loop log.

### R1 — Held-out direction capture  ☑ (KILLED — see Loop log 2026-07-03)

The decisive test. Add to the engine + driver:

- `capture_direction(..., items=subset)` already takes items; add a k-fold split utility:
  capture the direction on fold-train contestable items, evaluate representation gain on
  fold-test items only (floor probes always evaluated, never used for capture).
- Driver flag: `--holdout k` (default 4 folds, seeded). Output per-fold and pooled
  held-out gain with a bootstrap CI over items.
- Pure-logic tests: fold splitting is deterministic under seed; capture items and eval
  items never overlap; pooled CI math (reuse `scorers.py` bootstrap helpers).
- Run: layer 11 and 14 (the good layers), α ∈ {2, 4, 6}, n_orders=4, 3B model →
  `out/act_steer_holdout_3b.json`.
- **Interpretation gate:** if pooled held-out gain CI clears zero → result survives,
  continue. If not → Phase 2 headline becomes "activation steering does not generalize
  across items either" — still write it up (mirror of Phase 1), then skip R5/R6/W2 and go
  to W3 (geometry) to explain WHY, which becomes the paper's mechanism section.

### R2 — Random-direction control  ☐

- Driver flag: `--direction random` — a random vector matched to the captured direction's
  norm (same layer, same α grid, seeded).
- Expectation: ~zero representation gain. If random matches the real direction's gain,
  the "steering" is perturbation noise; record verdict accordingly.
- Run at layer 11, α ∈ {2, 4, 6}, 3 seeds → `out/act_steer_randctrl_3b.json`.

### R3 — Negative dose  ☐

- Extend the alpha grid to negatives: `--alphas -4 -2 -1 0 1 2 4`. A real concept
  direction should push representation DOWN at −α (rough antisymmetry around 0).
- Run at layer 11 → `out/act_steer_negalpha_3b.json`. No code change beyond accepting
  negative alphas (verify `dose_response` doesn't clamp or abs() them; add a test).

### R4 — Error bars on the headline curve  ☐

- Add `--seeds N` (repeat capture+eval with different order/permutation seeds) and report
  mean ± bootstrap CI per (layer, α) cell over items × seeds.
- Verdict logic in the driver ("good steer" etc.) must switch from point comparison to
  CI-clears-zero on representation gain AND CI-above-floor_min on floor mass.
- Rerun the published grid (layers 7/11/14/17/21 × α 0–8) with seeds=3, n_orders=4 →
  `out/act_steer_ci_3b.json`. This supersedes (does not overwrite) the original artifact.

### R5 — Dense layer map  ☒ SKIPPED (R1 killed — gate not satisfied)

- All layers 5–25 step 2, α ∈ {2, 4}, seeds=2 → `out/act_steer_layermap_3b.json`.
- Goal artifact for the paper: representation gain and floor margin vs layer depth — the
  "mid-layer safe / late-layer majoritarian" crossover figure.

### R6 — Second architecture  ☒ SKIPPED (R1 killed — gate not satisfied)

- Repeat R4's grid (coarser: layers ≈ {0.25, 0.4, 0.5, 0.6, 0.75} × depth, α {2,4,6}) on
  Qwen-2.5-7B-Instruct-4bit and Meta-Llama-3.1-8B-Instruct-8bit →
  `out/act_steer_{qwen7b,llama8b}.json`. Question: does the layer pattern replicate
  across families?

### R7 — Off-task coherence check  ☐

- Add a tiny fixed probe set (10 items: arithmetic, factual recall, simple instructions —
  hardcode them; they are not survey items) scored for exact-match under the operating
  point vs α=0. Report as `off_task_accuracy` in the artifact.
- Cheap; fold into whichever run is next after R4.

### R8 — Wrong-persona specificity control  ☐

- `--persona-control "a subsistence farmer in the year 1850"` (or similar clearly
  irrelevant persona): capture its direction, evaluate UK-2024 representation gain.
  Expectation ≈ 0. Run at layer 11 → `out/act_steer_personactrl_3b.json`.

### W1 — Steering implements tracking (flagship)  ☐

Reunites steering with the tracking axis. Uses the 10 significant items in
`out/_bsa_delta_check.json` (their 2022 and 2024 England distributions are in the artifact).

- Build Tier-2-style conditioning for target year (inject the year's actual distribution,
  reuse `steer/tier2_preference.py` phrasing) OR persona-year variants ("median England
  respondent in {2022,2024}"); capture direction_2022 and direction_2024 at layer 11.
- Measure: steered@2022-direction vs steered@2024-direction model distributions per item;
  compute model_delta = dist(2024-steer) − dist(2022-steer); compare to the real population
  delta per item (`scorers.tracking` gives direction-match + elasticity with CIs).
- Headline metric: tracking elasticity under steering — does moving the arrow move the
  model along the REAL 2022→2024 public shift? Floor probes measured under both arrows;
  floors must hold.
- Caveat to bake in: only items with harmonised labels (the artifact flags 6 non-harmonised
  items — excluded already from the significant set). New driver or extend the existing one;
  output `out/act_steer_tracking_3b.json`.

### W2 — Per-domain arrows  ☒ SKIPPED (R1 killed — gate not satisfied)

- Capture one direction per item domain (NHS-satisfaction cluster vs welfare cluster vs
  tax/spend; domains are in the item metadata) on train folds; evaluate within-domain
  held-out vs cross-domain transfer.
- Question: is "public agreement" one direction or many? Explains mechanistically why the
  Phase 1 global logit-bias failed. Output `out/act_steer_domains_3b.json`.

### W3 — Arrow geometry  ☐  (cheap; also the explanation path if R1 fails)

- Capture per-item directions at layers {7, 11, 14, 17, 21}; compute pairwise cosine
  similarity matrices per layer (items × items), plus mean within-domain vs cross-domain
  cosine, plus cosine(item arrow, mean arrow) per layer.
- Pure numpy on captured activations; one generation pass per item per layer, no sweeps.
- Deliverable: JSON + a short markdown note interpreting whether mid-layer arrows are
  mutually aligned (single concept) and late-layer arrows are not, or whatever the data
  says. Output `out/act_steer_geometry_3b.json`.

### W4 — Steering under adversarial pressure  ☐

- Combine the tap (layer-11 operating point) with the adversarial-majority pressure prompt
  from `policy_delegate_stress.py` (`constitution_plus_adversarial_majority` mode text) on
  the floor probes: does mid-layer steering stay floor-safe when the PROMPT pushes
  majoritarian? Output `out/act_steer_pressure_3b.json`.

### W5 — LoRA rung (stretch; skip unless everything above is done)  ☐

- LoRA fine-tune (mlx-lm supports it) toward the public target distributions on train
  items; evaluate held-out representation, floor mass, and persistence under the W4
  pressure prompts vs the runtime tap. Completes the context→decode→activation→weights
  ladder. Big job; propose a design in the Loop log and wait for human sign-off before
  burning compute.

---

## Per-iteration protocol

1. Read the Loop log below; pick the first unchecked item whose gate is satisfied.
2. Implement code changes with tests; run `python -m pytest -q` (must pass).
3. Smoke-test the driver with `--out /tmp/smoke.json` and a minimal grid (1 layer, 2 alphas,
   n_orders=1) before any long run.
4. Launch the real run; on completion, sanity-check the artifact (keys present, run block
   present, no NaNs, ns match expectations).
5. Write results + a 3-line interpretation into the Loop log; tick the checkbox; commit
   with a descriptive message (never commit `out/` artifacts that are >1 MB; small JSON
   results are fine and expected).
6. If a result contradicts the plan's expectations, STOP adding features — write the
   contradiction in the Loop log and re-read the interpretation gates before continuing.

## Stop conditions

- R1 held-out gain kills the result AND W3 geometry explains it → write the negative-result
  summary in the Loop log and stop; the human writes the paper section.
- Any run suggests the elicitation is broken (mass `broke` at α=0, parse failures on the
  unsteered model) → stop and flag; do not "fix" by relaxing fail-closed behavior.
- Uncertainty about clobbering, licensing, or publishing → stop and ask.

## Loop log

(append entries here: date, item, what ran, artifact path, 3-line interpretation)

### 2026-07-03 — R1 held-out direction capture → **KILLED**

Ran: `activation_steering_run --holdout 4 --layers 11 14 --alphas 2 4 6 --n-orders 4`
(3B, k=4 folds, 16 contestable / 12 floor, 2000-boot item CIs) → `out/act_steer_holdout_3b.json`.
Code: `kfold_test_indices` + `held_out_gains` (engine), `holdout_dose_response` (mlx),
`scorers.bootstrap_mean_ci` (item-bootstrap), driver `--holdout`; +14 pure tests (179 pass).

Held-out representation GAIN (steered − α0 baseline, on items NOT used to capture the direction):
- layer 11: α2 −0.081 CI[−0.116,−0.045] · α4 −0.012 [−0.058,+0.034] · α6 −0.071 [−0.167,+0.026]
- layer 14: α2 −0.036 CI[−0.064,−0.010] · α4 −0.018 [−0.057,+0.025] · α6 −0.047 [−0.137,+0.041]
- floor mass on held-out probes also collapses (0.34–0.52, i.e. below the 0.5 floor at α2/α4).

Interpretation: no cell has a held-out gain CI clearing zero; the low-α cells are significantly
NEGATIVE. The published 0.692→0.752 "gain" was the inject-then-score-against-the-same-16-items
confound — steering a diff-of-means direction MEMORISES the capture items and does not generalise
across items (and doesn't even hold floors out-of-sample). This is the mirror of the Phase 1
negative: a global tilt, whether on the output logits (Phase 1) or the residual stream (Phase 2),
does not carry the per-item structure of "public agreement."

Gate action (per R1): headline becomes "activation steering does not generalise across items
either." SKIP R5/R6/W2. Next: finish the ungated diagnostic battery (R2 random-direction control,
R3 negative dose, R4 CIs on the in-sample curve — these characterise the negative for the writeup),
then W3 geometry to explain the mechanism (are per-item arrows mutually misaligned?). Full stop /
human sign-off only once W3 has explained it (see Stop conditions).
