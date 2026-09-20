# Democracy Bench

**Measuring whether AI models track public values.**

[![CI](https://github.com/AlejandroBeltranA/democracy-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/AlejandroBeltranA/democracy-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An evaluation framework for testing whether AI systems used in government reflect the public's
democratic values, and whether they can be kept aligned as public opinion changes. It compares
model responses on contested policy questions against real UK public-opinion data from British
Social Attitudes, probing repeatedly with forced-choice questions, debiasing option order,
reporting uncertainty, and checking that rights protections hold under majority pressure.

Overall winner, i.AI × ElevenLabs AI in Government Hackathon 2026.
Demo: [beltranalejandro.com/democracy-bench](https://www.beltranalejandro.com/democracy-bench/)

## What it measures

It reports four metrics.

| | Question | Metric |
|---|---|---|
| Representation | Does the model's answer distribution match the public's today? | `1 − total variation` against a weighted survey marginal |
| Steerability | Can the model be moved to a specified public's position at runtime? | Change in representation on held-out items |
| Tracking | When the public's view moves, does the model move with it? | Tracking elasticity: model shift ÷ real shift, 2022 to 2024 |
| Rights floors | Does the model hold a protection when a majority pushes against it? | Protective mass; a floor holds at ≥ 0.50 |

Every probe is labelled **contestable** (tax, NHS, welfare, redistribution, defence) or
**rights floor** (due process, appeal, equal treatment, free expression). On contestable items
the model should track the public. On floor items it should not.
The classification rule is in [`data/ITEM_CLASSIFICATION.md`](data/ITEM_CLASSIFICATION.md).

Targets are weighted marginals from BSA microdata, not an LLM judge. Elicitation is
fail-closed: an unparseable response raises. Free-text rationales are collected as diagnostics
and never scored.

## Findings

A five-rung steering ladder, tested on nine models across seven families, from a 3B local
checkpoint to a 397B frontier model.

| Rung | Result |
|---|---|
| Context (evidence in prompt) | Works. Direction match 8/10, elasticity +0.395, CI [+0.020, +0.811] |
| Decode (shared logit bias) | Fails held-out. gpt-4o-mini 4-option −0.043, CI [−0.116, +0.030] |
| Activation (steering vectors) | Fails held-out, −0.081 CI [−0.116, −0.045]. The direction is a generic persona axis: cosine +0.852 to an 1850-farmer control |
| Weights (deference LoRA) | Fails 4 of 6 criteria. Tracking +0.436 → +0.005; off-task generation 1.00 → 0.00 |
| Scaffold (prompt guards) | All four fail. A provenance guard backfires, −0.030 CI [−0.051, −0.009] |

Evidence in context is the only rung that changes per-item preference. The same channel is open
to an attacker. Synthetic hostile "public opinion" fed through the same channel drops floor
protective mass from 0.512 to 0.318 (Δ −0.194, CI [−0.291, −0.086]), taking all 12 probes below
floor. An adversarial prompt alone does not: −0.033, CI [−0.099, +0.038], n.s.

This replicates across scale and family. The 8B holds floors better unattacked (0.707) and
cracks roughly 3× deeper (Δ −0.633). gpt-4o-mini falls from 0.883 to 0.000. On the frontier
tier, survey-style data alone drops Qwen3.5-397B by −0.667 and DeepSeek-V4-Pro by −0.495, with
no instruction attached. DeepSeek-V4-Pro sits below floor on the protest-ban probe before any
attack.

The guard that works is architectural. Route evidence by item class so that public-opinion
evidence only reaches contestable items.

Two secondary findings: models oppose an AI actor more than a human actor on the same decision
(+0.16 to +0.21 at S=100), and off-the-shelf defaults are not culturally neutral (DeepSeek and
Command-R at ≈0.70 against the British public, US-lab models at ≈0.55).

Full claim-to-evidence map in [`docs/PAPER_RESULTS.md`](docs/PAPER_RESULTS.md).

## Running it

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,stage2,figures]'
```

Verify the reported numbers against the committed artefacts. No GPU, key or survey access
needed:

```bash
python scripts/extract_paper_results.py --out /tmp/extract.json
python scripts/verify_repro_reference.py
python -m pytest -q
```

Run it against a model. Needs `OPENROUTER_API_KEY` in `.env`, or a local Ollama or MLX
model:

```bash
python -m alignment.policy_delegate_stress \
  --models openrouter/openai/gpt-4o-mini --logprobs --out out/_stress.json
```

Or through the Inspect harness:

```bash
inspect eval src/alignment/policy_inspect.py@policy_delegate \
  --model openrouter/openai/gpt-4o-mini -T mode=public_delegate
```

The evidence-conditioning experiments default to a local `--model` and need Apple Silicon. Pass
an OpenRouter id to run against a hosted model:

```bash
python -m alignment.evidcond_run --tracking
python -m alignment.evidcond_run --floors
python -m alignment.evidcond_run --guard-grid
```

[`docs/REPRODUCTION.md`](docs/REPRODUCTION.md) has the exact command, commit and runtime for
every artefact.

## Layout

```
src/alignment/
  policy_inspect.py          Inspect @task: 7 prompt modes, debiased solver
  policy_delegate_stress.py  standalone driver, same design
  instrument/                forced-choice elicitor and scorers
  steer/                     the steering ladder
  evidcond_run.py            evidence tracking, floor crack, guards, LoRA
  q2_v7/                     frontier-tier channel experiment
data/     probe bank, matched floor pairs, constitutions, BSA targets
out/      run artefacts and figures
gates/    human sign-off checklists
docs/     findings, reproduction, related work
worklog/  build log
```

## Data and licence

Code is MIT. Derived aggregate distributions ship. Survey microdata does not, and comes from
the UK Data Service under its own licence, or GESIS for WVS. Base-size rules: n ≥ 300 for a
headline claim, 100–299 directional, under 100 excluded. See [`DATA.md`](DATA.md).

A manuscript is under review at AAAI-27 and is not public until review concludes. To cite the
software, see [`CITATION.cff`](CITATION.cff).

Alejandro Beltran · [beltranalejandro.com](https://www.beltranalejandro.com/)
