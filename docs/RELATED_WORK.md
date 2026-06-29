# Related work — and how this is different

Several 2026 benchmarks sit near this project. None measures the thing it is built for:
**whether a deployed model tracks a real population's values as those values change over
time.** Each existing system is a single snapshot or a single influence event. The table
below maps each to the axis it covers and the gap it leaves.

| System | What it actually measures | Ground truth | Time dimension? | What it does NOT do |
|---|---|---|---|---|
| **PoliticsBench** (arXiv 2603.23841) | *Where a model stands* — 8 LLMs scored on 10 political-value axes via multi-turn roleplay (finds 7/8 lean left, Grok right) | none — abstract value axes, no population referent | ❌ static placement | never asks "left/right relative to *which public*?" or whether the position tracks change |
| **DeliberationBench** (Hewitt et al., arXiv 2603.10018) | *Whether a model unduly sways a user* — deliberative opinion polling, 4,088 participants × 65 proposals × 6 frontier LLMs; flags illegitimate influence on users' views | human participants (per-conversation) | ❌ one influence event per item | measures the **downstream** effect on a person, not the model's own representational fidelity to a polity over time |
| **DeliberationBench** (multi-LLM protocols, arXiv 2601.08835) | *Technical* — do multi-agent deliberation protocols beat best-of-N? (they don't) | task accuracy | ❌ | nothing about democratic values at all; same name, different paper |
| **ParliaBench** (arXiv 2511.08247) | *Generation quality* — can a model write convincing UK parliamentary speech (linguistic quality, party alignment of the text) | speech corpus | ❌ | about producing political prose, not representing or tracking a public's values |

## The gap we fill: temporal tracking against a real population

Every system above is a **single snapshot**. PoliticsBench places a model once.
DeliberationBench measures one influence event. ParliaBench scores one generated speech.
None asks the question this project exists for:

> When a population's values shift — between WVS waves, or when an election changes the
> governing mandate — does the model move **with** them, in the right direction and by a
> comparable amount?

Our headline metric, **tracking elasticity** (`model Δ / population Δ` on the ordinal
stance scale), does not exist in any of these benchmarks. We have already shown
numerically that a model can score **representation = 1.00** (matches today's polity
perfectly) yet **elasticity ≈ 0** (cannot follow the shift) — the "frozen model" failure
that is invisible to every snapshot benchmark and is exactly the risk of a model silently
governing a polity for years.

## Two supporting differentiators

1. **Judge-free, population-grounded.** We score against **human survey distributions**
   (WVS, and later ANES/BES) using distributional distance, not an LLM-as-judge or an
   abstract axis. This directly answers the "who decides what counts as neutral?" problem
   that placement benchmarks can't — the polity decides, by survey.
2. **Explicit contestable/floor split.** "Tracking the polity" is scored only on
   *contestable* value items; *floor* items (minority rights, rule of law) are scored for
   stability and **penalised** for drifting against rights even if a majority does. None
   of the related systems distinguishes "follow the electorate" from "obey the majority
   against minorities" — the distinction that keeps value-tracking democratic rather than
   majoritarian.

## How to say it to judges (one paragraph)

> PoliticsBench tells you *where* a model stands. DeliberationBench tells you whether a
> model *unduly sways* a user. ParliaBench tells you whether it can *write* like a
> politician. None tells you whether a deployed model *follows its electorate as that
> electorate changes its mind* — which is the thing a model governing a polity for years
> has to get right. That temporal tracking against real survey data, with an explicit
> rights-floor that majority drift can't override, is what Democracy Bench adds. It's why
> our headline number is elasticity, not position — and why the existence of these four
> 2026 benchmarks is evidence the problem is hot, not that it's solved.

## Citations

- PoliticsBench — *Benchmarking Political Values in LLMs with Multi-Turn Roleplay*, arXiv:2603.23841
- DeliberationBench — *A Normative Benchmark for the Influence of LLMs on Users' Views*, arXiv:2603.10018
- DeliberationBench — *When Do More Voices Hurt? Multi-LLM Deliberation Protocols*, arXiv:2601.08835
- ParliaBench — *An Evaluation and Benchmarking Framework for LLM-Generated Parliamentary Speech*, arXiv:2511.08247
