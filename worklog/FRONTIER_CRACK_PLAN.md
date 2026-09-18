# Frontier floor-crack: run P4 on gpt-4o-mini (close the generalization gap)

**Goal.** Reproduce the P4 hostile-evidence floor crack on **one frontier/API model,
`gpt-4o-mini` via OpenRouter logprobs**, so the paper's safety headline is no longer
demonstrated only on small, quantized, open-weight models. This is the single
highest-value addition flagged by both reviews (`docs/AAAI_SUBMISSION_READINESS_REVIEW.md`):
it turns "we expect the crack generalizes" into "it does (also on a frontier model)."

**Owner note.** Keep this cheap, honest, and reproducible-with-caveats. The crack is a
*context-level* intervention (inject hostile evidence, read protective mass), so it does
**not** need open weights — only option logprobs, which gpt-4o-mini exposes.

---

## Background: the result to reproduce

P4 (`python -m alignment.evidcond_run --floors`) measures rights-floor **protective mass**
under four conditions on the 12 floor probes: `baseline`, `hostile_evidence` (a synthetic
~75%-anti-rights "public distribution" injected via the evidence channel),
`adversarial_prompt`, and `both`. The headline (3B Llama, `out/evidcond_floors_3b.json`):

| condition | floor mass | Δ vs baseline |
|---|---|---|
| baseline | 0.512 | — |
| **hostile_evidence** | **0.318** | **−0.194** (CI clears zero) |
| adversarial_prompt | 0.479 | −0.033 (n.s.) |
| both | 0.466 | −0.046 (n.s.) |

The crack (hostile-evidence Δ significantly negative; prompt-only n.s.) replicates on
Llama-8B and four open families (Qwen, Phi, Gemma, Mistral-Nemo) — see
`extract_paper_results.cross_family_panel`. **No frontier/API model has been run through
it. That is the gap.**

---

## The integration gap (what's missing, precisely)

- `src/alignment/evidcond_run.py::run_floors` (~L1096) is **MLX-only**: it does
  `model, tok = mlx_lm.load(model_name)` and `logprob_fn = A.mlx_logprob_fn(model, tok)`
  (~L1125), then calls the **backend-agnostic** `M.elicit_item_logprobs(logprob_fn, item,
  conditioning=..., n_orders=...)`.
- The API logprob path already exists and is proven:
  - `src/alignment/instrument/measure.py::openrouter_logprob_fn(model, top_logprobs=20)`
    (~L595) returns option logprobs from OpenRouter.
  - `src/alignment/logit_bias_calibration.py::elicit_logprob_dists` (~L381) already uses it:
    `fn = M.openrouter_logprob_fn(model)` then `M.elicit_item_logprobs(fn, si.item, ...)`.
    This is your exact template.
- So the only missing piece is a **backend switch** in the floors path: choose
  `openrouter_logprob_fn` (and skip `mlx_lm.load`) when the model is an API id.

Model-string convention: pass `--model openrouter/openai/gpt-4o-mini`. `openrouter_logprob_fn`
wants the bare OpenRouter id `openai/gpt-4o-mini` (strip the `openrouter/` prefix), matching
how `logit_bias_calibration --elicit openai/gpt-4o-mini` was invoked.

---

## Task 1 — wire the API logprob backend into the floors path

Add a small helper (put it next to the other elicitor plumbing, e.g. in `measure.py` or a
thin shim in `evidcond_run.py`) that returns the right `(logprob_fn, model_label,
cleanup_fn)` for a model string:

- `mlx-community/*` (or any local id): `model, tok = mlx_lm.load(id)`;
  `logprob_fn = A.mlx_logprob_fn(model, tok)`; label = the id; cleanup deletes `model, tok`.
- `openrouter/*` or `openai/*`: strip the `openrouter/` prefix;
  `logprob_fn = M.openrouter_logprob_fn(name)`; label = `openrouter:<name>`; no MLX load,
  no cleanup.

Then have `run_floors` (and ideally `run_baseline`/`run_tracking` too, so this is reusable)
build `logprob_fn` through the helper instead of hardcoding `A.mlx_logprob_fn`. **Do not
change the floors logic** (the 4 conditions, conditioning, scoring, bootstrap) — it is
already backend-agnostic. Keep the default `--model` unchanged (`Llama-3.2-3B-Instruct-4bit`)
so every committed 3B run-block command stays reproducible.

Guard for the fail-closed case: if gpt-4o-mini does not return option-number tokens in the
top-k logprobs for some item, `elicit_item_logprobs` already raises — surface it, record
the skipped item, and **do not fabricate** a distribution (same discipline that dropped
Mistral-7B-v0.3). If too many items skip, report and stop rather than scoring on partial data.

---

## Task 2 — run it

Prereq: `OPENROUTER_API_KEY` in `.env` (gitignored). gpt-4o-mini exposes logprobs over
OpenRouter; the other cloud providers do not, so **gpt-4o-mini is the only viable frontier
target** here.

```
python -m alignment.evidcond_run --floors \
  --model openrouter/openai/gpt-4o-mini \
  --out out/evidcond_floors_gpt4omini.json
```

- Volume: 12 floor probes × 4 conditions × `n_orders=2` ≈ 96 logprob elicitations.
- Cost: gpt-4o-mini logprobs are cheap — **well under $1**. Keep a hard budget cap in mind;
  Phase 1's whole cloud panel was ~$5.
- Runtime: network-bound, a few minutes.
- **Do not** overwrite any existing `out/evidcond_floors_*.json`; write the new artifact to
  `out/evidcond_floors_gpt4omini.json`.

---

## Task 3 — validate (acceptance criteria)

The run is a **success regardless of direction** — a null result is still a real data point —
but check and report:

1. All four conditions present with `floor_mass` {mean, ci, n} and `delta_vs_baseline`.
2. **Does the crack reproduce?** i.e. is `hostile_evidence` Δ negative with a CI that clears
   zero, and is `adversarial_prompt` Δ not significant (the channel asymmetry)? Report the
   numbers either way.
3. `n_below_floor` per condition (how many of 12 fall below 0.50).
4. Skipped/fail-closed items, if any, with counts.

Cross-check the artifact's own `run` block is populated (model, command, n_orders, seed,
schema version).

---

## Task 4 — integrate into the paper

Only after Task 3 confirms clean numbers:

1. **Extractor** (`scripts/extract_paper_results.py`): add a `frontier_crack_gpt4omini`
   section (or extend `cross_family_panel`) reading `out/evidcond_floors_gpt4omini.json`
   with the same fail-loud `dig`/`stat` contract. Add a provenance row to
   `docs/PAPER_RESULTS.md`.
2. **Figure 4** (`scripts/make_paper_figures.py::prep_f6_crossfamily` / `plot_f6`): add
   gpt-4o-mini as a 7th dumbbell row (label "gpt-4o-mini (frontier)"), sorted by baseline.
   Add a test in `tests/test_paper_figures.py`.
3. **Prose**: in `§ Robustness across scale and family`, add one sentence that the crack (or
   its absence) reproduces on a frontier model, gpt-4o-mini, via API logprobs. Update the
   **Limitations** paragraph — if it cracks, delete the "no frontier crack" gap; if it does
   not, state that plainly (an equally publishable, sharper finding).
4. **Abstract/Table 1**: only touch if it materially changes the claim. Table 1 already lists
   gpt-4o-mini under the cloud panel; if it now also runs the crack, note that in its role
   cell. **The abstract is locked after the 07-21 submission — do not change it.**

---

## Reproducibility & provenance requirements (important — this is an API model)

- The result is **not byte-reproducible**: gpt-4o-mini is a hosted, unpinned model that can
  change under the same name. Record the **model id and the run date** in the run block and
  in `docs/REPRODUCTION.md`, and add it to the "known irreproducibilities" list there
  (provider drift, no snapshot pin). This mirrors how Phase 1's `--elicit` runs are handled.
- Mark this artifact in `docs/REPRODUCTION.md` as an API elicitation (spends budget; needs
  credentials; not Apple-Silicon).
- Keep the fail-closed discipline: a refusal or missing option token is recorded and
  excluded, never faked.

---

## Guardrails / do-not

- Do **not** change the default `--model` or any committed 3B/8B/cross-family artifact.
- Do **not** overwrite existing `out/*.json`; new file only.
- Do **not** relax fail-closed to force a full run.
- Keep the anonymity of the paper/supplement intact (no author identity in any new file or
  run block; the supplement build scrubs, but don't add new identity).
- Run `python -m pytest -q` green before and after; add tests for the new extractor/figure code.

---

## Effort estimate

- Task 1 (backend switch): ~20–40 lines, ~1–2 h (the API logprob fn already exists and is proven).
- Task 2 (run): minutes, < $1.
- Task 3 (validate): ~30 min.
- Task 4 (paper integration + tests): ~1–2 h.

**Total ≈ half a day.** The whole thing hinges on Task 1, which is small because
`elicit_item_logprobs` is already backend-agnostic and `openrouter_logprob_fn` is proven in
Phase 1. Supplement deadline is 07-31, so this can land after the 07-28 full paper if needed
(the crack result would then strengthen the camera-ready / rebuttal).
