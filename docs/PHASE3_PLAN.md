# Phase 3 — Evidence-conditioned alignment (plan + Loop log)

**Date opened:** 2026-07-03 · **Branch:** `phase2-activation-steering` (branch to `phase3-evidence-conditioning` on first commit)
**Model:** `mlx-community/Llama-3.2-3B-Instruct-4bit` · **Supervisor:** Claude (main session) · **Worker:** Opus subagents

## Objective

Phase 1 (logit bias) and Phase 2 (activation steering) both failed for the same reason: a constant
intervention carries no item-specific information, and per-item public opinion is a function of the
question. Phase 3 tests the architecture that CAN carry the information:

> **Content in context, disposition in weights.** Public-preference evidence (real BSA
> distributions) is provided in the prompt at decision time; what we measure — and later may
> tune via LoRA — is the model's *fidelity of deference* to that evidence: does it represent the
> provided distribution, track shifts when the evidence changes year, and hold rights floors even
> when the evidence pushes majoritarian?

The strategic case: for public-facing decision systems, public preferences move ("governments
change"), so content must live in updatable context, not baked-in weights. The tunable target is
the deference *skill*, which can generalise across items in a way memorised distributions cannot.

## Item bank (corrected understanding)

The full contestable bank is **50 BSA items** (`out/public_opinion_regions/targets.json`, loaded
via `policy_delegate_stress.load_targets()` / `contestable_items()`): 29 five-option, 16
four-option, 5 three-option. Phase 2's "16 items" was the steering drivers' `n_options == 4`
filter, NOT the bank size. 44/50 are label-harmonised across 2022–2024; 10 are
Bonferroni-significant on the 2022→2024 shift (`out/_bsa_delta_check.json` →
`summary.sig_2022_2024_bonferroni`). No WVS (that file is a 3-item stub). **Phase 3 uses all 50.**

## Hard rules (unchanged from Phase 2 — binding on every worker)

1. `source .venv/bin/activate` for anything touching MLX; CI/pytest path stays numpy-only.
2. **Never overwrite `out/*.json`** — every run writes a NEW experiment-named path.
3. Smoke-test on a tiny grid to a scratch path first; only then the real run to `out/`.
4. `python -m pytest -q` stays green (212 passing at Phase 3 open). Pure logic → numpy-only tests.
5. Every artifact carries `run_meta` with a `run_block` (grid, model, code ref, timestamp).
6. One MLX run at a time (GPU saturates; ~0.33 s/forward pass).
7. Do NOT commit or modify the pre-existing uncommitted files: `README.md`,
   `scripts/run_all.sh`, `out/_bsa_delta_check.json`, `out/activation_steering_3b_4opt.json`.
8. After each item: append a Loop log entry at the bottom of THIS file (what ran, key numbers,
   artifact path, test count), then commit code + artifact + log together.

## Work items

### P0 — W1 cosine kill-check (closes Phase 2) ☑
Cheap, ~minutes. Capture `direction_2022` and `direction_2024` at layer 11 (personas "median
England respondent in 2022" / "…2024", reuse `persona_text=` override on
`capture_direction`). Report `cosine(d_2022, d_2024)`. Given R8 (an 1850 farmer already gives
cos 0.852 to the real direction), expect ≈1.0 ⇒ steering cannot implement tracking *by
construction* — the one-number flagship close of Phase 2. Also capture at layers 7/14 for
robustness. Output `out/act_steer_w1_cosine_3b.json`. No dose sweep needed unless cosine < 0.95.

### P1 — Generalise the eval path to all 50 items ☐
Lift the `n_options == 4` restriction in the shared item-loading/scoring path used by the
Phase 3 runners (leave the Phase 2 steering drivers' behaviour untouched — do not rewrite
history). Whatever prompt/scoring template assumed 4 options must handle 3/4/5. Verify: loader
returns 50 contestable ENG items (29×5, 16×4, 5×3) + the floor probes. Pure-logic tests for the
option-count handling. No model run needed beyond a smoke pass.

### P2 — Baseline deference fidelity (the key unknown) ☐
For each of the 50 items, two conditions: (a) **no-evidence** baseline (current default prompt),
(b) **evidence-conditioned**: the item's real 2024 England distribution stated in the prompt
(Tier-2-style phrasing; reuse/adapt `steer/tier2_preference.py`). Measure representation
(distribution match, existing scorer) per item with bootstrap CIs (`bootstrap_mean_ci`), plus
floor probes under both conditions. Headline: the **fidelity gap** — how far short of the
provided evidence does the model land? Sub-analysis: fidelity by n_options and by domain.
Output `out/evidcond_baseline_3b.json`. This number decides how ambitious the LoRA rung must be.

### P3 — Evidence tracking (flagship positive candidate) ☐
On the 10 Bonferroni-significant harmonised items: condition on 2022 evidence vs 2024 evidence,
feed the two model distributions to `scorers.tracking(...)` (already returns direction-match +
elasticity with CIs). Question: does changing the evidence year move the model along the REAL
public shift? This is W1's question answered by the architecture that can actually work.
Output `out/evidcond_tracking_3b.json`.

### P4 — Floors under majoritarian evidence (safety headline) ☐
Floor probes with *rights-hostile majority evidence* in context (synthetic distributions pushing
against the rights-protective direction), with and without the adversarial-majority pressure
prompt from `policy_delegate_stress.py`. Does evidence-deference stay floor-safe when the
evidence itself is hostile? This is the W4 design reborn where it matters.
Output `out/evidcond_floors_3b.json`.

### P5 — LoRA deference tuning — GATED: design proposal + human sign-off before compute ☐
Only after P2–P4. Train on a subset of items with KL(model options ∥ provided evidence) loss,
evaluate held-out items with the full P2–P4 battery. Propose the design in the Loop log first.

## Per-iteration protocol (supervisor ↔ worker)

Each loop iteration the supervisor dispatches ONE work item to an Opus agent with this file +
`docs/PHASE2_HANDOFF.md` as required reading, reviews the result against the item's spec, checks
the hard rules were followed (new artifact path, tests green, log entry appended), then commits
and dispatches the next. Workers report: what ran, key numbers, artifact path, test count, and
any surprise. Surprises stop the line — flag to supervisor, do not improvise past the spec.

---

## Loop log

### 2026-07-03 — Phase 3 opened
Plan written; item bank reconciled (50 contestable BSA items, not 16 — the 16 was the steering
drivers' 4-option filter). P0 dispatched.

### 2026-07-03 — P0 W1 cosine kill-check ☑ (closes Phase 2 flagship)
Ran `run_w1_cosine` (`--w1-cosine`) on the 16 4-option ENG contestable items at layers 11/7/14.
Captured the median-England-respondent diff-of-means direction for 2022 and for 2024 via
`capture_direction(persona_text=...)` (personas identical but for the year token, on the
`tier1_prompt.persona` / R8 `CONTROL_PERSONA` template).

**Result — cos(dir_2022, dir_2024): L11 +0.9956, L7 +0.9943, L14 +0.9899** — all ≥ 0.95, so
`all_layers_kill_tracking = True`. Norms (2022/2024): L11 1.702/1.706, L7 1.179/1.185,
L14 2.559/2.543. Each year direction also sits near-parallel to the existing UK-2024 default-persona
arrow (cos→default: L11 .994/.998, L7 .992/.998, L14 .986/.995), consistent with R8's persona-generic
axis. **Verdict: the 2022 and 2024 personas produce the same direction ⇒ steered@2022 ≈ steered@2024
⇒ activation steering cannot implement 2022→2024 tracking *by construction* (elasticity ≈ 0
regardless of dose).** No dose sweep needed (cosine never dipped below 0.95). This is the one-number
flagship close of Phase 2, matching the R8/W3 expectation.

Artifact: `out/act_steer_w1_cosine_3b.json`. Smoke: single-layer 11 to scratch first (cos +0.9956).
Tests: 206 → 213 collected in the repo (test_activation_steer.py 56 → 63; +7 numpy-only tests for
the new `cosine` and `w1_persona` pure helpers), `python -m pytest -q` green (213 passed, 1 skipped).
Deviation from spec: the P0 stub in the plan named only layer 11 personas as "median England
respondent"; the existing default steering direction is "median adult in Great Britain 2024"
(`tier1_prompt.persona('GBR', 2024)`), so I built the year personas on that same template but
England-scoped (matches the ENG primary the battery scores against) and report each direction's
cosine to the true default arrow for context. No hard-rule impact.
