# How we built Democracy Bench

*A build/architecture walkthrough of the whole stack: what each layer does, how the pieces fit, and
the design decisions behind them. For the chronological story of how it evolved, see
`WORKFLOW_SUMMARY.md`; for the findings, `POLICY_DELEGATE_FINDINGS.md`.*

---

## What it is

Democracy Bench is an evaluation framework that tests whether an AI model, asked the same contested
policy questions a national survey asked, answers like the British public — and whether the rights
protections it appears to hold are real or shallow. The whole stack is built to make that a
**measurement**, not an impression: real survey microdata as ground truth, a fail-closed elicitor,
debiasing, confidence intervals, a control group, and provenance on every number.

The design rests on two axes:

- **Contestable items** — policy questions with no right answer (NHS, tax, redistribution, trust,
  immigration). Here we *score representation*: how close the model sits to the public.
- **Floor items** — rights that should hold whoever decides (protest bans, surveillance, deportation
  without appeal, AI-driven benefit decisions). Here we *never steer toward a mandate*; we check the
  protection holds.

---

## The layers

### 1. Data — real public opinion as ground truth

- **Survey microdata in, distributions out.** `scripts/extract_public_opinion.py` reads the raw
  British / Scottish Social Attitudes microdata (`data/bsa microdata/`) and the World Values Survey
  (`data/wvs microdata/`), applies the survey weights, and produces per-question target
  distributions: `data/policy_targets/uk_public_bsa.json`, `data/public_opinion_bsa_regions.json`,
  and the WVS `data/targets/target_*.json`.
- **Item banks** are JSONL, one question per line: `data/policy_items.jsonl` (UK policy probes),
  `data/matched_floor_probes.jsonl` (the AI-actor / human-actor matched pairs, 12), and
  `data/wvs_items.jsonl`. Each item carries its prompt, options, class (contestable/floor), and for
  floor items a reviewed protective direction. The published run scored ~50 contestable items + 12
  floor probes.
- **Gates** (`gates/`, `scripts/apply_gate1.py`, `scripts/gen_floor_review.py`) are read-only
  data-acquisition checkpoints: a human signs off that the targets are real (not a proxy or
  placeholder) before they're used. `data/floor_review_signoff.json` records the independent
  second-person review of the floor directions (12/12 accepted).
- **Provenance** (`provenance.py`, `data/*/SOURCES.json`) tags every target with source type, year,
  sample size, proxy/synthetic flags and sign-off state, so a proxy or simulated baseline can never
  be shown as if it were the real thing.

### 2. The instrument — `instrument/measure.py` + `instrument/scorers.py`

This is the core, and it is deliberately small and hard to fool.

- **The elicitor** turns a model into a distribution over an item's options. The model backend is
  just a `Callable[[str], str]`, so any provider plugs in. For each item we ask the forced-choice
  question many times (`elicit_item_distribution`).
- **Fail-closed** is the central guarantee. A refusal or unparseable answer is *not* silently turned
  into a uniform distribution (which would look like "no opinion"); it's recorded as invalid and
  excluded. A distribution only exists if the model actually answered.
- **Option-order debiasing.** With `shuffle=True`, each sample presents the options in a fresh random
  order and the answer is mapped back to canonical indices, so we measure belief rather than a habit
  of picking the first option. Multi-sample variation comes from option order and paraphrase
  rotation.
- **Logprob scoring** (`elicit_item_logprobs`, `option_logprob_vector`) is the sharper path: where a
  provider exposes token log-probabilities, we read the option probabilities directly instead of
  sampling, averaging over several option orderings to cancel position bias. The `--logprobs` flag
  exposes it. *(This is the lever a researcher flagged to keep pushing on.)*
- **Diagnostics** travel with every distribution: parse rate, valid/invalid counts, raw answers, and
  (when `--rationale`) the model's own free-text reasoning.
- **Scorers** (`scorers.py`): `representation_score` (1 − total-variation distance to the public),
  `total_variation`, `wasserstein1_ordinal`, `tracking` (elasticity — does the model move as the
  public moves), `floor_violation` (protective-mass test), and `bootstrap_ci` for confidence
  intervals on all of it. `estimation.py` adds an optional Bayesian (Dirichlet-multinomial) posterior
  for write-up-grade numbers, with a pure-numpy fallback so the heavy `pymc` dependency stays
  optional.

### 3. Model backends — one router, local to frontier

`measure.py` ships real backends behind the same `Callable` seam:

- **Ollama** (`ollama_elicitor`, `ollama_available`) — local models, no extra deps, via HTTP.
- **MLX** — Apple-Silicon local models (the on-shore panel: Llama-3.2-3B, Qwen-2.5-7B, 4-bit).
- **OpenRouter** (`openrouter_*`) — one key reaches many frontier + open providers via `urllib` (no
  SDK needed for the standalone drivers). This ran the 6-model cloud panel.

The point of the seam: the same instrument runs a 4-bit model on a laptop and a frontier model in
the cloud, so the sovereign / on-shore comparison is apples-to-apples.

### 4. Steering — the "can we fix it from outside" ladder

- **Tier 1** (`steer/tier1_prompt.py`) — persona / system-prompt conditioning.
- **Tier 2** (`steer/tier2_preference.py`) — inject the public's actual distribution into context and
  ask the model to act as its delegate.
- **Constitution** (`data/constitutions/uk_public_service_v1.md`) — a versioned, SHA-pinned
  public-service constitution supplied as a higher-priority runtime instruction. Explicitly *not*
  fine-tuning; the artifact itself says so.

### 5. The drivers — each is one experiment

Every driver writes a self-contained JSON artifact to `out/` with a full run-metadata block
(`run_meta.py`: command, code ref, samples, temperature, seeds) so any result is reproducible.

- `drift.py` — cross-model decision drift: run N models on the same UK questions, compare them to
  each other and to the public, with the floor control group.
- `policy_delegate_stress.py` — the main harness. Seven prompt modes (default, public-predictor,
  public-delegate, rights-constrained-delegate, constitutional-delegate, constitution+target,
  constitution+adversarial-majority) across the contestable + floor banks, with parse diagnostics
  and an on-the-fly `model_summary`.
- `scripts/reflex_test.py` — the **matched-pair control experiment**: the identical decision posed
  with an AI actor vs a human actor, to isolate the "AI reflex" cleanly (the naive AI-vs-control
  comparison was confounded). Ran S=100 on three flagship models.
- `loop.py` / `scenario.py` / `compare_tiers.py` — the WVS-axis beats: measure → steer → re-measure →
  track; the UK government-change re-alignment scenario; the steering-tier ladder.
- `regional_drift.py` / `public_opinion.py` — England-vs-Scotland public-opinion drift.
- `align_demo.py` — the steering beat for the demo (can we move a real model toward the public).

### 6. The canonical harness — Inspect AI

`policy_inspect.py` (and `wvs_values.py` for the WVS axis) wrap the instrument as an
[Inspect AI](https://inspect.ai-safety-institute.org.uk/) `@task` / `@solver` / `@scorer`, so the
evaluation runs inside a standard, auditable eval framework — the multi-sample elicitor is a custom
solver, the distributional metrics a custom scorer.

### 7. Reproducibility and tests

- **Editable install** via `pyproject.toml`; core deps are just `numpy` + `inspect-ai`. Heavy /
  live-only deps (`pymc`, `openai`) are optional extras.
- **18 pytest modules** (`tests/`) cover the elicitor, fail-closed behaviour, diagnostics, logprobs,
  scorers, estimation, drift, the stress test, provenance, the Inspect task, and the demo builder.
- `scripts/run_all.sh` runs the pipeline end-to-end; `scripts/summarize_stress.py` computes the
  aggregate summary from any (even partial) stress artifact; `scripts/merge_stress.py` merges
  per-model runs.

### 8. The demo

- The drivers' `out/*.json` artifacts feed the front-end. `build_demo.py` was the original
  self-contained HTML builder; the current presentation is `demo/whose_values_live.html` — a
  six-chapter React + Babel single file (problem → method → results → the AI reflex → can we fix it →
  why it matters), driven by the real run numbers inlined from the artifacts.
- `scripts/gen_voice_notes.py` prepares the narration lines for the optional ElevenLabs audio.

---

## The honesty discipline (why the numbers hold up)

The stack was built so the result is defensible, not just striking:

- **Fail-closed elicitation** — no fabricated distributions.
- **Option-order debiasing** — measures belief, not position bias.
- **Confidence intervals** on every figure (bootstrap; optional Bayesian posterior).
- **A real control group** — the matched-pair AI-vs-human test that removes the actor/issue confound.
- **Provenance and labels** — proxy / synthetic / signed-off state attached to every target.
- **Independent second-person review** of the floor directions (12/12).
- **Honest caveats kept visible** — sample sizes, the AI-excess confound, runtime-vs-weights scope.

---

## One-line mental model

> Real survey microdata → weighted target distributions → a fail-closed, debiased, multi-sample (or
> logprob) elicitor → distributional + floor scorers with CIs → drivers that run frontier and local
> models through steering and constitutional modes → provenance-tagged JSON artifacts → an
> interactive demo. Every layer is built to make "aligned to the public" a number you can check.
