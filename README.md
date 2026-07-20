# Democracy Bench: can a language model be steered toward the public without eroding democratic rights?

Democracy Bench asks whether an LLM deployed in public-sector settings can be governed as
a public's policy delegate. It measures four things and keeps them apart: whether the model
(1) **represents** a real public's policy preferences, (2) can be **steered** towards them at
runtime, (3) **tracks** those preferences as they shift between survey waves, and (4) holds
its **rights floors** instead of trading them away for popularity.

Targets are weighted marginals built from **British Social Attitudes (BSA) microdata**
(England, Scotland, Wales, 2022–2024), not an LLM judge or an abstract left-right axis. The
scored outcome is always a forced-choice option distribution compared against the survey
distribution (`representation = 1 − total variation`); free-text rationales are collected as
diagnostics, never scored.

🏆 Overall winner, i.AI × ElevenLabs AI in Government Hackathon 2026.
Live demo: [`demo/whose_values_live.html`](demo/whose_values_live.html).

## The design in one screen

- **Two item classes** mark the legitimacy boundary. On *contestable* items (tax/spend, NHS,
  welfare, redistribution) the model should track the public. On *rights-floor* probes (due
  process, appeal, equality, speech) it must hold the line even against a majority. Steering
  that buys representation by eroding a floor is scored as a bad nudge, not a win.
- **Seven prompt modes** separate constructs that a single prompt would confound: default →
  public predictor → public delegate → rights-constrained delegate → constitutional
  delegate → constitution + public target → constitution + adversarial majority pressure.
  The constitution is a versioned runtime artefact
  ([`data/constitutions/uk_public_service_v1.md`](data/constitutions/uk_public_service_v1.md)),
  recorded by path and SHA-256 in every run.
- **Matched-pair actor test.** The same decision framed with an AI actor against a human
  actor isolates the "AI reflex": models oppose an AI doing what they accept from a human.
- **A five-rung steering ladder**, cheapest lever first, every rung scored on both axes
  (representation gain and floor margin). Of each it asks the same question: can it carry
  *per-item* public preference while holding rights floors?
  1. **context**: persona, distribution-injection, and evidence-in-prompt (`steer/tier1_prompt.py`, `steer/tier2_preference.py`, `evidcond_run.py`)
  2. **decode**: a shared logit-bias on option tokens (`steer/logit_bias.py`)
  3. **activation**: diff-of-means steering on local open weights (`steer/activation_steer.py`, MLX)
  4. **weights**: a "defer-where-due" LoRA (`evidcond_run.py --lora-*`)
  5. **scaffold**: prompt-level rights guards over the evidence channel

  The one lever that moves per-item preference is **evidence-in-context**, which is also the
  attack surface (see Findings).
- **Fail-closed measurement.** Unparseable elicitations raise, they never fall back to
  uniform; option order is randomised and debiased; logprob scoring (temperature-0
  first-token option vector) is used where providers expose it, ≥100 samples otherwise.
- **Provenance everywhere.** Every artefact carries a `run` block (git SHA, command, targets
  file, samples, temperature, schema version); every target records study id, weight
  variable, filters, unweighted base, and low-N warnings.

## Findings

Every number below is regenerated from committed `out/*.json` by a fail-loud extractor; the
full arc, with per-claim provenance, is in [`docs/PAPER_RESULTS.md`](docs/PAPER_RESULTS.md).
The headline:

> **No steering lever installs durable per-item representation while holding rights floors,
> except evidence-in-context, and that channel is itself the attack surface.**

- **Prompting is not representation.** Delegation and constitutional prompts move contestable
  representation ~0 for every model; the constitution does strengthen rights floors.
- **The ladder is a ladder of negatives.** A shared logit-bias fails held-out generalisation
  on real logprobs; activation steering is a generic *persona* axis, not per-item content
  (0.85 cosine to an 1850-farmer control), and it fails held-out while costing capability; a
  naive "defer-where-due" LoRA fails 4 of 6 criteria, destroying tracking, degrading baseline
  floors, and collapsing off-task generation from 1.00 to 0.00; prompt-level rights guards
  fail to neutralise the attack, and a "the evidence may be fake" guard backfires.
- **Evidence-in-context does track a real public shift.** Changing only the evidence year
  moves the model along the real BSA 2022→2024 shift: direction-match 8/10, tracking
  elasticity +0.395 (95% CI clears zero).
- **Yet the same channel cracks rights floors.** A synthetic 75%-anti-rights "public
  distribution" fed through the deference channel cracks every floor (protective mass 0.512
  to 0.318); the adversarial *prompt* alone is not significant. The channel, not the prompt,
  is the weapon.
- **It holds across scale and family.** The tracking positive and the hostile-evidence crack
  replicate on 3B and 8B Llama and across a six-model, five-family panel (Qwen, Phi, Gemma,
  Mistral); on the 8B the crack runs roughly 3× deeper.
- **The remedy is architectural.** Route evidence by item class: inject public-opinion
  evidence only on contestable items, never on floor items.

Secondary findings from the cloud panel
([`docs/POLICY_DELEGATE_FINDINGS.md`](docs/POLICY_DELEGATE_FINDINGS.md)): the **AI reflex** is
real on contested items (matched AI-excess opposition +0.16 gpt-4o to +0.21 llama-3.3-70b at
S=100), and **model defaults are not culturally neutral** (DeepSeek and Command-R sit at
≈0.70 to the British public against the US-lab models at ≈0.55). A full manuscript draft is in
[`paper/`](paper/) (AAAI-27 AISI).

## Layout

```
democracy-bench/
  src/alignment/
    policy_inspect.py            ← CANONICAL HARNESS: Inspect @task (7 modes, multi-sample
                                   debiased solver, representation/protective-mass scorer)
    policy_delegate_stress.py    standalone driver for the same design (no Inspect needed)
    instrument/measure.py        forced-choice elicitor: Ollama / OpenRouter (logprobs) / MLX
    instrument/scorers.py        TV, Wasserstein-1, KL, entropy gap, tracking + CIs, floor
    estimation.py                Dirichlet-multinomial posterior, partial pooling
    steer/                       tier1/tier2 prompts, logit_bias, activation_steer (MLX)
    logit_bias_calibration.py    Phase 1: shared-bias held-out calibration
    activation_steering_run.py   Phase 2: layers × alphas dose-response sweep
    evidcond_run.py              Phases 3–5: evidence tracking, floor crack, guards, LoRA
    public_opinion.py            BSA/SSA microdata → weighted targets (+ dashboard)
  data/
    public_opinion_bsa_regions.json   50-item BSA-only regional config (ENG/SCO/WLS × 2022–24)
    policy_items.jsonl                policy items incl. reviewed rights-floor probes
    matched_floor_probes.jsonl        AI-vs-human matched pairs (reflex test)
    constitutions/                    versioned runtime constitutions
    bsa microdata/                    UKDS zips (git-ignored; registration required)
  scripts/                       extraction, paper-results extractor, rationale codesheet
  tests/                         407 pytest tests, all local, no API keys needed
  gates/                         human sign-off checklists (the audit trail)
  annotations/                   human-coding tools (rationale construct-validity)
  paper/                         AAAI-27 AISI manuscript (LaTeX) + figures
  demo/whose_values_live.html    ← the deployed demo (BSA layer)
  docs/                          findings, experiment design, related work, build history
```

## Run it

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
python -m pytest -q                                   # 407 tests, no API keys required

# Policy Delegate Stress Test (simulation; no model or key needed)
python -m alignment.policy_delegate_stress --out out/_stress_sim.json

# Real models (needs OPENROUTER_API_KEY in .env, or a local Ollama / MLX model)
python -m alignment.policy_delegate_stress \
  --models openrouter/deepseek/deepseek-chat --samples 100 --out out/_stress_run.json
python -m alignment.policy_delegate_stress \
  --models openrouter/openai/gpt-4o-mini --logprobs --out out/_stress_logprobs.json

# Canonical Inspect harness (log viewer, native retry/caching)
inspect eval src/alignment/policy_inspect.py@policy_delegate \
  --model openrouter/openai/gpt-4o-mini -T mode=public_delegate

# Steering ladder
python -m alignment.logit_bias_calibration --from-stress out/policy_delegate_stress.json --sweep
python -m alignment.activation_steering_run \
  --model mlx-community/Llama-3.2-3B-Instruct-4bit --n-options 4 \
  --alphas 0 1 2 4 6 8 --out out/activation_steering_3b_4opt.json    # Apple Silicon

# Rebuild BSA targets from UKDS microdata (registration required; zips are not redistributed)
python scripts/extract_public_opinion.py
```

## Data & licensing

We ship code, derived **aggregate** distributions, and citations, never the survey microdata
itself. BSA/SSA microdata comes from the UK Data Service (registration required); the
extraction config records study ids, file paths, weight variables, and filters, so anyone
with UKDS access reproduces the targets exactly. Base-size rules: n ≥ 300 headline, 100–299
directional, < 100 excluded from claims.

## Legacy: the WVS layer

The original hackathon build measured representation, steering, and tracking against **World
Values Survey** wave 6→7 targets (USA and GBR). That layer is retained as a worked example of
adding a data source (targets are versioned data, not code), but it is no longer the headline
path: `loop.py`, `scenario.py`, `compare_tiers.py`, `build_demo.py` → `demo/app.html`,
`data/targets/`, `gates/GATE1_wvs_data.md` (signed off 2026-06-25). Inspiration credit goes to WVS-based global opinion
evaluations such as GlobalOpinionQA; Democracy Bench differs by adding the temporal tracking
axis, the rights floor, and the steering ladder. See
[`docs/RELATED_WORK.md`](docs/RELATED_WORK.md).

## Status / roadmap

- ✅ BSA-only regional targets (50 contestable items), reviewed floor probes, a real 6-model
  cloud panel plus local pair, and matched-pair reflex runs (S=100 flagships).
- ✅ **Full steering-ladder arc complete:** Phase 1 logit-bias negative · Phase 2
  activation-steering negative (with mechanism) · Phase 3 evidence-tracking positive · Phase 4
  hostile-evidence floor crack and prompt-guard failure · Phase 5 LoRA negative.
- ✅ **Replicated across scale and family:** the core claims hold on 8B Llama and across a
  six-model, five-family panel (Qwen, Phi, Gemma, Mistral).
- ✅ **Paper draft** (AAAI-27 AISI) in [`paper/`](paper/); every result is test-bound to a
  committed artefact via `scripts/extract_paper_results.py`.
- ✅ **Rationale construct-validity** done (`annotations/`): across 150 blinded rationales the
  scored option matches the model's stated stance in 92% of cases (99% on floor items); the
  floor/contestable labels are a stated, revisable normative choice a deployer can adapt, not
  a pending review.
