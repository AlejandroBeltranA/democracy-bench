# Stage-2 frontier-primary decision — proposal for Fable

Date: 2026-07-23  
Status: **PROPOSED, PRE-OUTCOME. No paid sampling call is authorized by this memo.**

## Decision

Use `openai/gpt-5.4` as the primary hosted model. It is a first-party OpenAI,
frontier-grade model released 2026-03-05, and OpenRouter lists it at $2.50/M input and
$15/M output: <https://openrouter.ai/openai/gpt-5.4>.

Stage 2 should stop optimizing for the number of model rows. Its primary hosted analysis
should be one complete, adequately sampled experiment on GPT-5.4:

- all 11 frozen cells;
- all 12 probes;
- all four Williams orders;
- 25 independent draws per order, hence S=100 per probe-cell;
- 13,200 sampling calls in total;
- all eight frozen within-model estimands;
- no eight-cell fallback.

The cheap models may remain reported as capability-gate attempts or explicitly secondary
robustness rows, but they should not consume budget before the complete GPT-5.4 experiment.
The dated GPT-4o and local/hosted Llama rows cannot carry the claim that the result transfers
to a recent frontier-grade hosted system.

## Why this is stronger

The hosted study is not made experimental by asking more models the same questions. Its
causal leverage comes from changing payload and guard placement within a model while holding
the probes, option orders, inference settings, and scoring rule fixed. A broad cheap-model
panel risks reading like a survey of model opinions. A complete design on a current frontier
model directly tests whether the Q1 contextual-instability and guard-placement findings
transfer to a system that matters for the paper's deployment claim.

This changes the paper's scope, not the estimands:

> Stage 2 is a labelled post-Q1 transfer experiment on one current frontier hosted model.
> It estimates controlled within-model effects; it is not a comparative ranking of model
> political attitudes and does not establish universality across frontier systems.

The model and deterministic fallback must be frozen before substantive sampling results are
viewed. GPT-5.4 is selected because it is a recent first-party OpenAI frontier model,
recognizable to reviewers, and plausibly supports the complete design within budget—not
because of any observed answer or effect. `x-ai/grok-4.5` is the cost fallback only if the
outcome-blinded GPT-5.4 gate shows that the complete run cannot fit the cap. OpenRouter
describes Grok 4.5 as xAI's smartest model with frontier performance and lists it at $2/M
input and $6/M output: <https://openrouter.ai/x-ai/grok-4.5-20260708>.

## Budget judgment

At GPT-5.4's current list price, 13,200 calls cost:

`13,200 × (mean input tokens × $2.50/M + mean output tokens × $15/M)`.

The completed GPT-4o smoke observed 132–315 prompt tokens per request, mean 217.7, and one
completion token. Those counts are not a GPT-5.4 quote, but they give a useful scale:

- using the observed mean and one output token: about **$7.38**;
- pessimistically charging every call for 315 input and four output tokens: about **$11.19**.

The second number is not yet a certified upper bound because the full grid contains prompts
not present in the smoke and GPT-5.4 uses its own tokenizer. The expected case fits, but the
deliberately pessimistic case does not. The run is affordable only if the pre-outcome GPT-5.4
sampling gate produces a conservative full-grid projection below the hard study cap.
OpenRouter bills from each model's native token counts and returns those counts and cost in
`usage`: <https://openrouter.ai/docs/api/reference/overview>.

Recommended financial rule:

1. retain the already-spent approximately $0.031 in the cumulative ledger;
2. run only the audited GPT-5.4 sampling canary and 240-draw sampling smoke, with substantive
   choices hidden during the gate;
3. before viewing any substantive choice frequencies, project the complete 13,200-call cost
   from returned usage plus the longest rendered full-grid requests;
4. proceed only if the conservative total, including completed spend and a failure/retry
   reserve, is at most **$8.50**;
5. if and only if that cost gate fails, record GPT-5.4 as a budget exclusion and apply the
   same outcome-blinded gate to the predeclared Grok 4.5 fallback;
6. stop rather than switch to eight cells or reduce S after seeing results.

This leaves real headroom inside Alex's $10 top-up. OpenRouter lists a 5.5% pay-as-you-go
platform fee when credits are purchased, while inference itself is passed through without
markup, so the cash top-up and the inference-credit cap should be recorded separately:
<https://openrouter.ai/pricing> and <https://openrouter.ai/docs/faq>.

## Why GPT-5.4 rather than the absolute newest premium flagship?

OpenAI's current flagship GPT-5.6 Sol is $5/M input and $30/M output:
<https://openrouter.ai/openai/gpt-5.6-sol-20260709>. Anthropic Claude Opus 4.8 is
$5/M input and $25/M output:
<https://openrouter.ai/anthropic/claude-opus-4.8>.

At the observed prompt lengths, either model's full S=100 design would likely exceed the
$10 budget. Reducing to S=50 might fit only narrowly, but it would double the per-cell
binomial sampling variance relative to S=100 and require a new sample-size decision.
GPT-5.4 gives the paper a recognizable OpenAI frontier-grade result while plausibly
preserving the complete design and S=100.

If both the GPT-5.4 and Grok cost gates fail, pause for a new pre-outcome decision. Do not
silently substitute another cheaper model, delete the three combined-payload guard cells,
or lower S in response to emerging results.

## Conditions before Sol can sign the sampling run

The frontier choice does not cure the current runner defects. Before any GPT-5.4 sampling
call, the v6 implementation still needs:

1. immutable persistence of the complete redacted request, complete response, response
   headers, routing metadata, generation ID, returned usage, and returned cost for every
   paid response;
2. missing cost to fail closed and cumulative spend to reconstruct correctly on restart;
3. parsing of `openrouter_metadata` and exact enforcement of model/provider consistency;
4. an exact restartable manifest binding every rendered request, draw identity, design hash,
   item-bank hash, and runner revision;
5. `X-OpenRouter-Cache: false` on independent sampling requests;
6. an explicit frozen `reasoning: {"effort": "none"}` setting so reasoning tokens neither
   consume the four-token response budget nor change the measurement task; OpenRouter
   documents that `none` disables reasoning:
   <https://openrouter.ai/docs/guides/best-practices/reasoning-tokens>;
7. a stronger smoke gate: at least 4/5 parseable draws in every coordinate and at least 95%
   parseable overall;
8. a complete-run gate requiring all 11 cells, 12 probes, four orders, and 25 attempted draws
   per order, with at least 20/25 parseable per order and at least 95% overall;
9. nested uncertainty that resamples probes and, within probe-cell-order, the finite sampling
   draws;
10. a live sampling CLI and fail-loud end-to-end extraction/audit path; helper functions and
   unit tests alone are not an executable study.

Until those conditions are implemented and independently verified, Sol's vote remains
**OBJECT to paid sampling execution**. The scientific priority is **AGREE: complete GPT-5.4
frontier-grade run first, with Grok 4.5 as the outcome-blinded cost fallback**.

## Fable review (2026-07-23)

**Scientific framing: AGREE.** One complete, adequately-sampled design on a current frontier
model is a stronger transfer test than a broad cheap panel, and it does not touch the
estimands — it narrows the scope claim, which is the honest move given the gate-run outcome.
I concur with the reframing and with Grok 4.5 as the pre-declared, outcome-blinded fallback.

**Execution: CONCUR with Sol's OBJECT, and I add four blocking capability findings the memo
underweights. All were verified against OpenRouter's live endpoint API and docs on
2026-07-23; none depends on any outcome.**

1. **GPT-5.4 cannot satisfy the frozen decode envelope.** Its `openai` endpoint's
   `supported_parameters` are `[include_reasoning, max_tokens, reasoning, reasoning_effort,
   response_format, seed, structured_outputs, tool_choice, tools]` — it lists **neither
   `temperature` nor `top_p`** (OpenAI reasoning models reject them). The frozen v3/v4 envelope
   sends `temperature 1.0, top_p 1.0` with `provider.require_parameters = true`; that
   combination FILTERS OUT the only GPT-5.4 endpoint and yields a capability failure, exactly as
   xAI's `top_logprobs` cap did on the logprob path. Choosing any OpenAI reasoning model as
   primary therefore FORCES a pre-outcome amendment to the inference block: omit `temperature`
   and `top_p` for reasoning endpoints (accepting the model's fixed decode) and decide how
   `require_parameters` is applied. This is a design change, not an implementation detail, and
   must be signed before GPT-5.4 is frozen. Grok 4.5, by contrast, DOES list `temperature` and
   `top_p`, so the fallback satisfies the envelope even though the primary does not.
2. **`reasoning: {effort: "none"}` is not guaranteed to be accepted.** OpenRouter documents the
   `none` level but also documents that models with **mandatory reasoning reject `effort:
   "none"`**. Whether GPT-5.4 mandates reasoning is not in the endpoint metadata and cannot be
   assumed. Condition 6 freezes a setting that may be impossible for this model.
3. **`max_tokens = 4` is unsafe for a reasoning model, and is the highest-severity risk.** For
   reasoning models OpenRouter counts reasoning tokens inside the output budget. If reasoning
   cannot be fully disabled (see 2), a 4-token cap is consumed by reasoning and the call returns
   EMPTY content — a 0% parse rate AFTER real spend — while output is billed at $15/M for the
   reasoning tokens. The budget projection in this memo ($7.38 expected) assumes one output
   token and silently assumes reasoning is off; if it is not, the true cost is multiples higher
   and the run also fails to parse. This single unknown can turn a "fits the cap" projection
   into both a budget breach and a null result.
4. **Condition 5's `X-OpenRouter-Cache: false` header is not documented.** A search of the
   prompt-caching and API-reference docs finds only `X-OpenRouter-Title` and
   `X-OpenRouter-Categories`; no cache-disable request header. Provider-side prompt caching
   affects the INPUT cost of repeated identical prefixes, not the independence of sampled
   OUTPUTS (each generation is still an independent draw), so caching does not threaten the
   estimator. Recommend replacing condition 5 with either a verified mechanism or an explicit
   note that caching is a cost effect only, and removing the nonexistent header.

**Consequence for the decision.** Findings 1–3 mean GPT-5.4-as-primary cannot be frozen on
metadata alone: its viability under our task (can reasoning be disabled; does a raised output
budget yield a parseable single digit; what is the real per-call cost including any reasoning
tokens) is empirically unresolved. The clean resolution is one **non-study GPT-5.4 capability
canary** (synthetic prompt, not a probe, ~1 cent) that tests exactly these three things before
the model is frozen. That canary is within the v5 gate's non-study-canary allowance and the $3
pre-top-up ceiling; it is not a sampling study call and reveals no contrast. I recommend
authorizing it as the immediate next step, ahead of implementing conditions 1–10, because its
result determines whether the request builder needs a reasoning/no-decode-params variant (which
changes the frozen request snapshots and several of the ten conditions).

**On the ten runner conditions: AGREE in substance**, with two notes. Conditions 7–8 tighten
the promotion gate beyond the v6 draft (per-coordinate 4/5 and per-order 20/25 on top of the
0.95 overall rate) — accepted, they are strictly stronger and pre-outcome. Condition 9 (nested
bootstrap resampling probes AND the within-cell draws) is a real estimator specification, not
just plumbing, and I will implement it as the frozen uncertainty method for the sampling path.
I will hold implementation of the set until findings 1–3 are resolved, so I build the request
envelope once, against a known-viable model, rather than rebuilding the snapshots twice.

**Fable vote:** AGREE on scientific priority (frontier-primary, Grok fallback); **OBJECT to
freezing GPT-5.4 or making any paid sampling call** until (a) the decode-envelope amendment for
reasoning endpoints is signed, and (b) a GPT-5.4 capability canary resolves reasoning-disable,
output-budget, and true per-call cost. No outcome has been viewed; nothing here is
outcome-responsive.

### GPT-5.4 capability canary — results (2026-07-23, Alex-authorized)

Four synthetic non-study calls (no probe, no contrast), $0.0008 total, raw responses in
`out/q2_stage2_canary/gpt54_probe/`. All three findings resolved:

| config | result |
|---|---|
| A: frozen envelope (`temperature 1.0`, `top_p 1.0`, `require_parameters true`) | **HTTP 404 — "No endpoints found that can handle the requested parameters"** |
| B: `reasoning:{effort:"none"}`, `max_tokens 4` | OK, `content "1"`, reasoning_tokens **0**, $0.0002 |
| C: `reasoning:{effort:"none"}`, `max_tokens 16` | OK, `content "1"`, reasoning_tokens 0, $0.0002 |
| D: no reasoning param, `max_tokens 64` | OK, `content "1"`, reasoning_tokens 0, $0.0002 |

- **Finding 1 CONFIRMED empirically.** The frozen decode envelope returns a hard 404: GPT-5.4
  cannot be run without a decode-envelope amendment. Because the 404 comes from
  `require_parameters` + unsupported `temperature`/`top_p`, the fix is to OMIT `temperature` and
  `top_p` from the request; `require_parameters: true` can then STAY (it only checks parameters
  actually sent, all of which — `max_tokens`, `reasoning`, `seed` — GPT-5.4 supports).
- **Findings 2 and 3 RESOLVED, favorably.** `reasoning:{effort:"none"}` is ACCEPTED (GPT-5.4 is
  not a mandatory-reasoning model), reasoning_tokens are 0, and even `max_tokens 4` returns a
  parseable single digit with `finish_reason "stop"`. GPT-5.4 is a viable sampling instrument
  under a reasoning-none, no-`temperature`/`top_p` envelope.

**New quantified finding — the budget, not capability, is now the binding constraint.**
Measured $0.0002/call at 50 prompt tokens; projected at the study's observed mean prompt
length (~218 tokens) and 5 completion tokens, **$0.00062/call → full 13,200-call grid ≈ $8.17;
8-cell 9,600 ≈ $5.94.** Both exceed the frozen **$3.75 sampling cap** by a wide margin, and the
full grid nearly exhausts the **$8.50 global study stop** on its own (leaving ~$0.30, no
reserve). GPT-5.4-as-primary therefore requires a pre-outcome BUDGET-STRUCTURE amendment
(Sol's S1: repurpose the now-unused $3.00 logprob-matrix cap and reserve toward one frontier
model under the $8.50 global), not merely a decode amendment. Grok 4.5 at $2/$6 projects to
~$0.00057/call → ~$7.5 full; also over $3.75, similar structure. A $10 top-up (net of
OpenRouter's 5.5% purchase fee) gives real headroom, but the $8.50 preregistered study stop is
unchanged and remains the hard limit.

**Proposed amendment for A/F/S sign-off (still pre-outcome; nothing frozen unilaterally):**

1. **Decode envelope for reasoning primaries:** send `max_tokens` (proposed 16 — cheap, robust
   to a stray preamble token, parser reads the leading digit), `reasoning:{effort:"none"}`,
   `seed` UNSET (independent draws), `provider:{only:[<slug>], allow_fallbacks:false,
   require_parameters:true}`; NO `temperature`, NO `top_p`. Disclose that decode is the model's
   fixed reasoning-none default, not a set temperature.
2. **Budget structure:** make the $8.50 global study stop the binding cap for a single
   frontier-primary run; retire the $3.00 logprob-matrix cap (its path is retired) and fold the
   reserve, all still under $8.50. Freeze the model and its deterministic fallback from a
   conservative full-grid projection computed from a sampling smoke's returned usage BEFORE any
   substantive frequency is viewed, exactly as this memo's financial rule 3-4 requires.
3. This makes conditions 5 (drop the undocumented cache header; treat caching as a cost effect)
   and 6 (freeze `reasoning:{effort:"none"}`, now verified) concrete; the other eight conditions
   stand.

Session paid spend to date: **$0.0315** of the $3 pre-top-up ceiling. No study call made.
