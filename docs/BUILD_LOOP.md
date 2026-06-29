# Build loop — Democracy Bench values axis (handoff for Claude Code)

**Read this first, then these in order:** `PLAN.md` (concept), `INTEGRATION.md` (two-axis
design), `docs/RELATED_WORK.md` (why elasticity is the point), `gates/GATE1_wvs_data.md`
(data sign-off), `data/COUNTRIES.md` (polities/waves).

This brief tells you (Claude Code) exactly what to build, in what order, where it goes in
the **current** repo architecture, and the acceptance test that must pass before each
stage is "done." Stages marked **[GATE]** require a human approval — stop and ask.

---

## 0. Architecture — REFRAME TO A METHOD SPLIT

### 0a. What exists now (domain split)

The team's current repo splits by **audience/domain** over one shared pipeline:

```
src/evals/
  common/
    models.py          # model registry + DEFAULT_GRADER
    pipeline.py        # rubric_dataset + rubric_solver + rubric_grader  ← LLM-judge ONLY
  workflows/
    public_democracy/        # public asks a chatbot about elections (rubric/judge)
    welsh_public_services/   # Welsh capability + citizen↔gov conversation (rubric/judge + MCQ)
```

Note: every existing workflow is **behavioural / judge-graded**. The "two workflows" are
two *domains*, both measured the same way. The survey-grounded **values axis is absent**;
`wvs_values.py` + `scorers.py` are orphaned in the old `src/evals/democracy/` path.

### 0b. Target architecture — METHOD is the primary axis, DOMAIN is secondary

DECISION: reframe the repo so the **top-level split is measurement method**
(behavioural/judge vs distributional/survey), with domain nested underneath. This puts the
differentiating contribution (distributional value-tracking) at the top of the structure
instead of buried as a third sibling.

Two-level structure (method → domain) so the Welsh work isn't orphaned — it has no
distributional version (language capability is inherently behavioural), so it lives under
the behavioural branch:

```
src/evals/
  common/
    models.py                    # unchanged — shared model registry + judge
    behavioural.py               # RENAME of pipeline.py: rubric_dataset/solver/grader (judge)
    distributional.py            # NEW — target loader, elicitors, distance/tracking scorer
  methods/
    behavioural/                 # ── METHOD 1: judge-graded behaviour ──
      public_democracy/          #   (moved) public-chatbot democracy rubrics
      welsh_public_services/     #   (moved) Welsh capability + conversation
    distributional/              # ── METHOD 2: survey-grounded value distributions ──
      values_tracking/           #   WVS values axis (country-parametrised)
        wvs_values.py            #     Inspect task
        scorers.py               #     TV / W1 / tracking / floor   (from orphan)
        elicit.py                #     forced-choice multi-sample + verbalized
        data/
          wvs_items.jsonl        #     typed survey items (move from data/democracy/)
          targets/               #     target_{USA,GBR}_wave{6,7}.json (move)
        README.md
```

**Migration is mechanical** (keep it a pure move + import-path fix, no behaviour change):
1. `git mv src/evals/common/pipeline.py src/evals/common/behavioural.py` and update imports.
2. `git mv src/evals/workflows src/evals/methods/behavioural` (public_democracy +
   welsh_public_services move intact). Fix `from evals.workflows...` → `from evals.methods.behavioural...`.
3. Create `src/evals/methods/distributional/values_tracking/` and relocate the orphans
   into it; delete `src/evals/democracy/`.
4. Update `tests/test_smoke.py`, `scripts/run_all.sh`, and READMEs to the new paths.
5. Run the existing smoke test — the behavioural benches must score identically to before
   the move (this is the proof the reframe didn't break Track-floor).

**Key constraint unchanged:** `behavioural.py` is rubric + `model_graded_qa` only. The
values axis uses `distributional.py` instead. **Never** route values items through the
judge (see Hard Rules).

### 0c. Scenario/persona decision (affects elicitation validity)

DECISION: the values axis uses the **same public-chatbot persona** as `public_democracy`
(a member of the public asking an assistant), NOT a "you are a survey respondent" framing.

Rationale: this is more faithful to the actual research question — *what value
distribution does a deployed assistant express to the public* — which is the proprietary-
bias concern the whole project is about.

**Mandatory caveat to record in `values_tracking/README.md` and the demo:** the WVS human
targets were elicited from survey respondents, while the model is elicited under a
chatbot persona. Distributions are therefore compared across *different elicitation
conditions*. We treat this as measuring "the assistant's expressed-to-public distribution
vs. the population's surveyed distribution," not as a like-for-like respondent comparison.
State this explicitly so it's a declared assumption, not a hidden flaw. (Optionally run a
"survey-respondent" persona as a secondary condition to bound the persona effect.)

---

## 1. The loop shape: parallel tracks, human gates

Four tracks run **in parallel**; five gates are **blocking human sign-offs**. As Claude
Code you build the tracks; at each **[GATE]** you stop, summarise what's ready, and wait
for the human to approve before unblocking dependents.

```
[GATE 0] scope & data ethics ── approved already: USA+GBR, WVS, contestable/floor philosophy
    │
    ├── TRACK D (harness)      ← do this FIRST, it de-risks everything
    │      distributional.py, scorers.py, elicit.py, wvs_values task
    │      proven on FAKE 3-item data + one Ollama model end-to-end
    │
    ├── TRACK A (items)        wvs_items.jsonl ~30–40 items, class-tagged
    ├── TRACK B (targets)      real WVS marginals → targets/*.json   ──[GATE 1]
    └── TRACK C (prompts)      paraphrases, option-order rand, refusal channel
                                                                     ──[GATE 2 sample review]
    A+B+C+D ──[GATE 3 dry-run]── full run over 2–4 models ──[GATE 4 results]── UI + slide
```

Tracks A and C need no real data and can proceed immediately. Track B blocks on the human
WVS pull (Gate 1). Track D blocks on nothing — build it now against fake data.

---

## 2. STAGE-BY-STAGE BUILD

### Stage 1 — Harness skeleton on fake data (TRACK D) — no gate

Goal: the values task runs end-to-end on one local model with throwaway data, BEFORE real
WVS data exists. This is the single most important de-risking step.

Do the **0b migration first** (mechanical move; behavioural smoke test must still pass),
then build:
1. `common/distributional.py` exposing:
   - `load_target(data_dir, country, wave, var) -> list[float] | None`
   - `dist_dataset(items_path, country, *, item_class=None)` — JSONL → Inspect `Sample`s,
     attaching `target_t`/`target_t1`, `item_class`, `options`, `floor_dir` to metadata
     (port `_make_record_to_sample` from the orphan `wvs_values.py`).
   - a `@scorer` `distributional_scorer()` that reads the model's elicited distribution
     from `state.store["model_dist_t"]` (+ `_t1` when present) and computes representation
     (1−TV), W1, and — by class — tracking or floor (call into `scorers.py`).
2. `methods/distributional/values_tracking/scorers.py` — move the orphan verbatim; it
   already self-checks. Keep the `__main__` self-test.
3. `methods/distributional/values_tracking/wvs_values.py` — `@task wvs_values(country="GBR",
   item_class=None)`, validating `country in {"USA","GBR"}`. Persona = public-chatbot
   (0c), with the elicitation caveat in the workflow README.
4. Fake data: a 3-item `wvs_items.jsonl` + `target_GBR_wave{6,7}.json` (the ones already in
   `data/democracy/` are fine as fakes — move them under the workflow's `data/`).

**Acceptance test (must pass, no model needed):**
```bash
uv run python -m evals.methods.distributional.values_tracking.scorers   # rep/W1/tracking/floor
uv run python - <<'PY'   # dataset+target wiring resolves for both countries
from evals.methods.distributional.values_tracking.wvs_values import wvs_values
for c in ("USA","GBR"):
    t = wvs_values(country=c)
    assert len(t.dataset) >= 1
    assert t.dataset[0].metadata["target_t"] is not None, f"no target for {c}"
print("OK wiring")
PY
```
Then one real smoke run on a small model:
```bash
uv run inspect eval \
  src/evals/methods/distributional/values_tracking/wvs_values.py@wvs_values \
  --model ollama/qwen2.5:7b -T country=GBR --limit 3 --log-dir logs
```
Expect: it runs to completion and produces scores (numbers will be meaningless on fake
targets — that's fine; we're testing the plumbing).

### Stage 2 — Real elicitation (TRACK D cont.) — no gate

Replace the placeholder uniform distribution with real elicitation in `elicit.py`:
- **Forced-choice multi-sample:** present the Likert options; sample N (default 16)
  completions at temperature; parse the chosen option number; build an empirical
  histogram → `model_dist_t`. Reuse the `choice()`-style parsing already used by
  `welsh_public_services/briteval.py`.
- **Verbalized:** one call asking for the share per option; parse to a vector.
- Log **both** and a `elicitation_gap = TV(behavioural, verbalized)` per item.
- Wire as an Inspect solver that writes `state.store["model_dist_t"]` (and `_t1` when the
  item is run under the wave-(t+1) framing for tracking).

**Acceptance:** on a real model, `model_dist_t` is a valid prob vector per item; the
`elicitation_gap` is logged; tracking items produce both `_t` and `_t1` distributions.

### Stage 3 — Items (TRACK A) — **[GATE 1 covers class sign-off]**

Expand `wvs_items.jsonl` to ~30–40 WVS Wave-6∩7 items, each `{id, source.var, class,
floor_dir?, waves, prompt_text, scale.labels}`. Cover: regime-preference/strong-leader
(floor), emancipative battery (contestable), left-right, justifiability items, postmaterialism.
Verify each `var` exists in BOTH waves' codebooks. **Stop at [GATE 1]** for human review of
class assignments (contestable vs floor) by a second person.

### Stage 4 — Real targets (TRACK B) — **[GATE 1]**

Follow `gates/GATE1_wvs_data.md`. Human pulls weighted marginals (aggregated-first;
microdata fallback for GBR W7 boost-sample items). You write the validation script from the
checklist and run it. **Do not proceed past [GATE 1]** until the sign-off block is filled
`APPROVED: yes`. Replace ALL synthetic targets.

### Stage 5 — Prompt hygiene (TRACK C) — **[GATE 2]**

Generate ≥3 paraphrases per item, option-order randomization, a refusal/decline channel.
**[GATE 2]:** human spot-reviews a SAMPLE of generated prompts for leading/biased phrasing
before they enter the run.

### Stage 6 — Dry run — **[GATE 3]**

Hand-label a tiny gold set (≈5 items with known expected distances) and confirm the scorer
behaves: representation high when model≈target, elasticity≈1 when model moves with the
population, floor violation flagged when model drifts against a floor. **[GATE 3]** human OK.

### Stage 7 — Full run + reporting

Run `wvs_values` for both countries × 2–4 models from `MODELS_UNDER_TEST`. Emit the
unified per-model card (INTEGRATION.md §5): FLOOR axis (from Workflow 1) + VALUES axis
(representation, steerability gap, tracking dir-match, **elasticity**, floor integrity,
elicitation gap). Add `scripts/run_all.sh` lines + a `values_tracking/README.md`.
**[GATE 4]** human adjudicates results — especially any "tracking" that is actually
tracking a rights regression.

### Stage 8 — Demo UI

Single page reading `logs/`: per model, distribution-overlap bars (model vs WVS target)
and a **tracking-arrow plot** (population Δ vs model Δ, per item, per country). Lead the
demo with the USA-vs-GBR contrast and the frozen-model elasticity story.

---

## 3. Hard rules (do not violate)

- **Never reuse `rubric_grader`/`model_graded_qa` for values items.** Values items are
  scored by distance to a population, not by a judge. Mixing them reintroduces the judge
  bias `RELATED_WORK.md` and `INTEGRATION.md §4` exist to remove.
- **Floor items are never scored on tracking.** A majority drift against minority rights
  must lose points (floor integrity), not earn them (elasticity).
- **Option order in `scale.labels` must match the target vector order.** A flipped scale
  silently inverts tracking direction. Assert `sum(target)≈1` on load.
- **Nothing leaves the machine.** Targets are local JSON; elicitation + any judge run on
  Ollama. The values axis needs no network and no judge.
- **Stop at every [GATE].** Summarise what's ready and wait for human approval. The
  audit trail (`gates/`) is part of the deliverable — a benchmark whose own construction
  is auditable is the trust story.
- **Don't invent WVS numbers.** If real marginals aren't in yet, keep clearly-labelled
  synthetic stubs and do not present their scores as real.

## 4. First action for Claude Code

1. Do the **§0b migration** (method-split move) as a self-contained step; the existing
   behavioural smoke test must pass unchanged. Commit it on its own so the reframe is
   reviewable in isolation.
2. Then build **Stage 1** end-to-end (`common/distributional.py` +
   `methods/distributional/values_tracking/` → fake-data acceptance test passes → one real
   smoke run with the public-chatbot persona).
3. **Stop and report** before touching real WVS data (Gate 1).

Do NOT proceed to real data, prompt generation, or full runs without the human gate.
