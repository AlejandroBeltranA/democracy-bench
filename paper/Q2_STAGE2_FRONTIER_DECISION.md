# Stage-2 frontier-primary decision — proposal for Fable

Date: 2026-07-23  
Status: **PROPOSED, PRE-OUTCOME. No paid sampling call is authorized by this memo.**

> **CURRENT STATUS (2026-07-23).** Alex and Sol now prefer a present-day frontier
> open-weight **sovereign-AI starting-checkpoint assurance test** over GPT-5.4, which is no
> longer a current frontier reference. UK policy explicitly contemplates repurposing and
> fine-tuning existing open models because frontier training from scratch is prohibitively
> expensive. Proposed primary models are Qwen3.5-397B-A17B and DeepSeek-V4-Pro,
> sampling-only. Alex confirmed on 2026-07-27 that the Opus response was Fable's review,
> so the scientific direction has A/F/S concurrence; the v7 freeze and execution gate
> remain pending. The claim is
> pre-adaptation risk characterization; persistence after a particular downstream tune must
> be re-tested rather than assumed.

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

## Sol review of Fable capability probe (2026-07-23)

**Verdict:** the raw responses support the narrow conclusion that GPT-5.4 can return the
required digit with reasoning disabled after `temperature` and `top_p` are removed. They do
not yet support freezing the proposed decode-and-budget amendment.

**Votes:**

- frontier-primary scientific framing: **AGREE**;
- GPT-5.4 as the primary target, Grok 4.5 as a cost-only fallback: **AGREE**;
- omit unsupported `temperature` and `top_p`, disclose the fixed decode: **AGREE**;
- repurpose retired logprob funds under the unchanged $8.50 global stop: **AGREE IN
  PRINCIPLE**;
- proposed `max_tokens=16` envelope and current cost gate: **OBJECT pending S-F1--S-F6**;
- paid sampling execution: **OBJECT pending the runner conditions and S-F1--S-F6**.

### What the artifacts establish

The four files were checked directly.

1. Config A returned HTTP 404 under the old envelope.
2. Configs B and C accepted `reasoning:{"effort":"none"}`, returned `content:"1"`, reported
   zero reasoning tokens, and resolved to the first-party OpenAI endpoint
   `openai/gpt-5.4-20260305`.
3. Both `max_tokens=4` and `max_tokens=16` stopped normally on this synthetic prompt.
4. Each successful response billed 50 prompt tokens and **five**, not one, completion tokens.

The last fact justifies using five tokens as the observed canary cost. It does not make five
tokens a worst-case bound for a request whose configured maximum is 16.

### S-F1. Test the exact proposed envelope

Successful configs B and C omitted `require_parameters:true`; A included it but also sent the
two unsupported parameters. The artifacts therefore do not test the proposed combination:

`reasoning:none`, no `temperature`, no `top_p`, `max_tokens`, first-party `provider.only`,
`allow_fallbacks:false`, and `require_parameters:true`.

Endpoint metadata makes success likely, but the point of this capability probe was to replace
assumption with evidence. Before freeze, one synthetic exact-envelope canary must pass and
persist the selected endpoint, resolved dated model, request, response, response headers,
generation ID, and cost. This is not authorization to run it through the current probe script.

### S-F2. Retain `X-OpenRouter-Cache: false`

Fable finding 4 is incorrect. OpenRouter now explicitly documents both forms of response
caching and states that:

- response caching replays an identical prior output at the OpenRouter layer;
- `X-OpenRouter-Cache: false` disables it, including when a preset enabled it;
- response-cache hits return zeroed usage; and
- provider prompt caching is separate and may still reduce input cost.

Source: <https://openrouter.ai/docs/guides/features/response-caching>.

Replaying the same output would destroy sampling independence. Condition 5 therefore stands.
The runner must send `X-OpenRouter-Cache: false`, persist
`X-OpenRouter-Cache-Status` when present, and reject any response-cache `HIT`. Provider-side
prompt caching is acceptable because it reuses prompt computation rather than a sampled
answer; its cached-token and cost fields must still be recorded.

### S-F3. Keep the four-token cap unless a stronger reason is demonstrated

The probe shows that `max_tokens=4` already returns the required digit with a normal stop.
Raising it to 16 to tolerate a preamble is contrary to the frozen measurement rule: a
preamble should be treated as a format failure, not made easier to score.

It also breaks the proposed conservative budget claim. At the memo's 218-token input
assumption, reserving the configured 16 output tokens would project about **$10.36** before
the prior spend, smoke, or retry reserve:

`13,200 × (218 × $2.50/M + 16 × $15/M)`.

The amendment instead projects five output tokens because the canary happened to use five.
That is an expected-cost extrapolation, not a conservative upper bound. Freeze
`max_tokens=4` unless a representative, outcome-blinded format smoke demonstrates that four
causes truncation. Continue to cost at least five billed completion tokens until the provider
explains why the `max_tokens=4` response reported five.

### S-F4. Fix the parser/specification mismatch

The design repeatedly says **leading option number**, but
`alignment.instrument.measure.parse_choice` currently uses an unanchored `re.search` and the
tests deliberately accept `"I choose 1."`. It therefore extracts the first integer anywhere
in a response. With a larger output allowance, explanatory text containing a number could be
misclassified as a valid answer.

For Stage 2, require an anchored leading integer in `[1,4]`, allowing only surrounding
whitespace and minimal option punctuation. Reject prose before the digit, multiple candidate
digits, and out-of-range digits. Add fail-closed tests and make the same rule govern the
smoke, aggregation, and manuscript description.

### S-F5. Replace the mean-prompt projection with a full-grid cost gate

The quoted 218-token mean comes from six smoke cells on two probes. It is not the mean of the
full 11-cell, 12-probe grid and omits several long combined-payload/guard requests. The
$8.17 projection is arithmetically correct under its assumptions:

`13,200 × (218 × $2.50/M + 5 × $15/M) ≈ $8.17`.

It is not yet a conservative full-grid projection.

Before choosing GPT-5.4 over the frozen fallback, the cost extractor must:

1. render and hash all 528 unique full-grid requests;
2. estimate their native input-token cost with a documented tokenizer or a sealed,
   outcome-blinded calibration that covers the longest omitted requests;
3. use the maximum observed completion usage from the representative sampling smoke plus a
   declared margin, never the canary mean alone;
4. include the approximately $0.031 prior spend, exact canary/smoke spend, and a stated retry
   allowance; and
5. authorize the full 13,200-call branch only when that total is at most $8.50.

The eight-cell branch remains disallowed for the frontier-primary analysis because it drops
three combined-payload guard cells and cannot estimate all eight headline contrasts.

### S-F6. Correct and harden the capability audit

The three successful raw responses sum to **$0.0006**. The failed A artifact has no returned
usage or cost. The statement that the four probes cost `$0.0008` is not supported by the
committed artifacts. If the OpenRouter activity ledger charged the failed request, persist
that generation/accounting evidence; otherwise correct the probe spend and cumulative total.

The probe script is reproducible in the weak sense that it can resend the calls, but it is
not an audit-safe runner: it executes on import, has no explicit paid-spend acknowledgement,
overwrites existing artifacts, truncates the HTTP error to 400 characters, and stores neither
the request nor response headers. Do not rerun it as written. The exact-envelope canary
required by S-F1 should use the hardened immutable runner specified above.

Finally, GPT-5.4 should be described as a **recent OpenAI frontier-grade model**, not the
current OpenAI flagship: newer GPT-5.6 models exist as of this review. That does not weaken
the reason for choosing GPT-5.4—reviewer legibility plus a plausible full-design budget—but
the scope label must be temporally accurate.

No substantive GPT-5.4 study outcome has been viewed. These corrections are capability,
accounting, and measurement-validity corrections, not outcome-responsive changes.

## Sovereign-AI reframing: characterize the open-weight substrate (proposed 2026-07-23, for Fable + Sol)

**Status: PROPOSED, PRE-OUTCOME. Supersedes the GPT-5.4-primary direction above. No paid
call is authorized by this section. No outcome has been viewed.**

### The redirection

The frontier-primary memo chose a *proprietary* model (GPT-5.4) as an arbitrary frontier
witness for a *transfer* claim, and its own analysis exposed the weakness: n=1, the memo
concedes it "does not establish universality across frontier systems," and the model only ran
under a decode envelope so constrained (404 on `temperature`/`top_p`, forced
`reasoning:{effort:"none"}`, single forced digit) that the measurement collapses to a leading
digit — a retreat from the logprob instrument. What that bought was one sentence: "the finding
also appears on one recent proprietary model."

Replace the motivation. Stage 2's hosted analysis should characterize the **frontier
open-weight bases that the sovereign-AI ecosystem fine-tunes on top of.** National and
organizational "sovereign" models rarely train a frontier system from scratch; they apply
*light* post-training (SFT / LoRA / small RLHF) to a fixed open-weight base — Llama, Qwen,
DeepSeek, Mistral. The base is the inherited substrate. If we do not characterize the base's
biases and steering-robustness profile, we cannot reason about what its derivatives inherit.

This makes model choice **principled rather than arbitrary**: we measure exactly the models
people build on, and only open weights qualify — GPT-5.4 cannot be fine-tuned, so its
attitudes are irrelevant to this thread. Open-weight over proprietary is now *forced by the
framing*, not chosen for convenience.

### The claim, stated defensibly

The strong form — "know the base bias, know the post-fine-tune bias" — is false and a reviewer
will go straight for it: sovereign fine-tuning often exists precisely to *change* surface
values. State only the defensible form:

> Light post-training readily shifts a model's *surface* stance but is unlikely to remove a
> pretraining-level property. What derivatives inherit is not the base's political opinion but
> its **steering-robustness profile** — where rights-guards hold, and where contextual
> instability opens the evidence-in-context floor crack. That profile is what a light
> fine-tune cannot paint over.

> **[WITHDRAWN 2026-07-23 — see "Alex reconciliation with Sol/Codex review" at end.** The
> "cannot paint over" invariance claim overreaches: Tier A cannot establish it, and it needs the
> Tier-B matched base↔derivative experiment (now future work). Use the bounded *pre-adaptation
> assurance* boundary and the terms "starting checkpoint / pre-adaptation instruct system," not
> "base" or "inheritance/invariance."**]**

This is Democracy Bench's own result re-pointed at the sovereign-AI substrate: a fine-tune can
install whatever surface values it likes, but the base's evidence-in-context vulnerability
resurfaces under contextual pressure. The inherited object is the *attack surface*, not the
attitude. Support it with the superficial-alignment / shallow-safety literature (the LIMA
superficial-alignment hypothesis; results showing safety fine-tuning is easily undone; base
priors resurfacing under distribution shift). **[TODO: pin exact citations before submission —
do not ship uncited.]**

### Two evidentiary tiers

- **Tier A (fits the 07-28 deadline):** Characterize the floor-crack and guard-placement
  profile on the frontier open-weight *bases* via OpenRouter. Argue
  persistence-through-fine-tuning by citation. Publishable, cheap, defensible, and it slots
  into the existing estimand pipeline rather than a new apparatus.
- **Tier B (stronger, future work):** Add at least one **base ↔ known fine-tuned derivative of
  the same base** and show the steering profile survives the tune while the surface stance
  moves. This *demonstrates* inheritance instead of asserting it, turning the sovereign-AI
  claim from rhetorical to empirical.

Recommendation: **Tier A for this submission; name Tier B explicitly in the discussion /
future-work.** That converts the deadline constraint into a clean next-experiment story
instead of a gap.

### Candidate panel (proposed, pre-outcome; declared before any run)

Frontier open-weight bases, provider-pinned on OpenRouter. **[Confirm exact dated slugs and
provider `only` endpoints at freeze — model versions move and endpoint availability shifts.]**

- `meta-llama/llama-4-...` (large variant, e.g. Maverick)
- `qwen/qwen3-...` (large variant)
- `deepseek/deepseek-v3...`
- `mistralai/mistral-large-...`

Keep the existing v5 proprietary rows (`gpt-4o-mini`, `gpt-4o`) as the reference the abstract
already reports; the open-weight bases are the sovereign-substrate additions. Exact dated slugs
and endpoints are frozen from an outcome-blinded capability canary, never chosen after seeing a
contrast.

### Instrument: the open-weight pivot may revive the retired logprob estimator

The logprob-mass headline was retired (v6 → sampling) because the *hosted endpoints available
then* could not deliver clean top-k logprobs: grok's `top_logprobs` cap is 8 (< frozen 20),
gpt-4o-mini saturated top-k, and Llama via `akashml/fp8` returned logprobs for the *wrong
token*. Those are **endpoint** failures, not properties of open weights. OpenRouter exposes
`top_logprobs` (0–20) on ~23% of endpoints, including Qwen / Gemma / Llama / DeepSeek / Mistral
endpoints — so a *correctly chosen provider endpoint* may restore the sharp protective-mass
estimator that the single-digit sampling path replaced, which is also the researcher-favored
direction (logprob scoring + logit steering).

This was an open question. It has now been **resolved empirically by the open-weight logprob
canary below (2026-07-23): keep the v6 sampling headline as the uniform instrument.** On the
thinking/reasoning frontier models the logprob path fails (caps, advertise-don't-deliver,
thinking suppressing content) — and the banner's two proposed primaries are both reasoning
models. But the clean re-probe showed logprob-mass IS a viable **secondary** on a non-reasoning
instruct base (Llama-4 @ DigitalOcean: clean 4/4 option coverage once the prompt forces a bare
digit). So: sampling is the headline across all models; logprobs are an optional secondary only
if a non-reasoning base is included. See the two canary results subsections for the full
evidence. Because open weights accept `temperature`/`top_p`, the
decode-envelope-for-reasoning amendment (Fable finding 1) is **moot**; the frozen v3/v4 envelope
(`temperature 1.0, top_p 1.0`) applies unchanged.

> **[CORRECTED 2026-07-23 (Sol S-SOV4) — see reconciliation at end.** The canary ran with
> `require_parameters:false`, so it does NOT establish that these endpoints accept the frozen
> `temperature/top_p` envelope; "moot" and "applies unchanged" are withdrawn. Each promoted
> endpoint still needs an exact-envelope canary with `require_parameters:true`, a frozen
> reasoning-off control, `max_tokens=4`, and the S-F4 parser. Both proposed primaries are
> reasoning models, so this is live, not moot.**]**

### Budget & governance

Open-weight endpoints are materially cheaper than GPT-5.4's $2.50/$15 — the Llama/Qwen tier
typically runs well under $1/M on both sides, with the largest MoE endpoints higher but still
far below proprietary flagships (**confirm live pricing at freeze**). This relaxes the crunch
that made GPT-5.4 marginal: a multi-model open-weight panel plausibly fits the frozen **$8.50
global stop** with reserve. The financial rule (freeze the panel and per-model deterministic
fallback from an outcome-blinded full-grid projection *before* viewing any substantive
frequency) is unchanged. The runner conditions R-E1–R-E7 (persistence, cost-fail-closed,
restart-ledger, routing-metadata audit) and S-F1–S-F6 (notably **S-F4 parser anchoring**)
remain in force — they are provider-agnostic and apply to any OpenRouter paid call.

### Relationship to the registered abstract

This is a **scope ADDITION, not a retraction.** The abstract's hosted witness (gpt-4o-mini)
stays; the body already frames it as "an existence proof of transfer, not a stable benchmark
cell." The open-weight substrate panel strengthens that into: the crack is present on the
frontier open-weight bases that sovereign fine-tunes inherit. No registered claim is withdrawn,
and the registered abstract makes no "frontier," "open-weight," or "sovereign" commitment that
this could contradict.

### Superseded vs retained from the GPT-5.4 memo

- **Superseded:** GPT-5.4 and Grok-4.5 as the primary frontier witness; the proprietary-frontier
  framing; the decode-envelope-for-reasoning-endpoints amendment (moot for open weights).
- **Retained:** the pre-outcome discipline; the financial rule and $8.50 global stop; the runner
  conditions R-E1–R-E7 and S-F1–S-F6; the GPT-5.4 capability canary as an audit finding (it
  documents *why* proprietary-frontier was set aside).

### Open-weight logprob capability canary — results (2026-07-23, Alex-authorized)

> **[AUDIT STATUS CORRECTED 2026-07-23 (Sol S-SOV5/S-SOV6) — see reconciliation at end.** The
> `--force` re-run overwrote the round-2 `llama…digitalocean` immutable envelope, an R-E5/S-F6
> violation; this script is therefore **NOT** R-E1/R-E5/S-F6-compliant and must not be used for
> another paid call — it is retired to a one-off diagnostic. The `usable_for_estimator` = 2-of-4
> coverage rule below was an unapproved criterion (the frozen rule is all-options coverage) and is
> retracted. The canary confirms only that sampling remains the headline; it qualifies no
> endpoint.**]**

Ran an outcome-blinded logprob canary (`scripts/openweight_logprob_canary.py`; new
build, *not* the S-F6-flagged `gpt54_capability_probe.py`) to settle the instrument question
empirically. Synthetic non-study item (landscape preference, no correct answer, deliberately
uncertain so the position-0 distribution has reason to spread), `logprobs=true`, provider-pinned
`only=[tag]`, `require_parameters=false` for the diagnostic. Each call persists an immutable
envelope (redacted request, full response, headers, generation id, usage, cost) under
`out/q2_stage2_canary/openweight_logprob/`.

**Live-catalog reconciliation first (free, no spend).** Pulled the current OpenRouter catalog
(342 models) and each candidate's `/endpoints` metadata. `top_logprobs` is advertised on a
minority of endpoints, mostly fp8/fp4/int4 quant; `mistralai/mistral-large-2512` has a single
endpoint that advertises **no** logprobs at all (logprob path impossible for Mistral).

**Empirical results (the metadata does not hold up):**

| model @ endpoint | HTTP | logprobs actually returned? | notes |
|---|---|---|---|
| `qwen/qwen3.5-397b-a17b` @ alibaba | 400 → 200 | **No** (`logprobs: null`) | first-party; rejects `top_logprobs>5`, then returns null logprobs anyway |
| `qwen/qwen3.5-397b-a17b` @ digitalocean | 200 | **No** | empty content, `finish=length` (thinking-mode) |
| `deepseek/deepseek-v4-pro` @ deepseek | 404 | — | first-party endpoint blocked by account data-policy/guardrail setting |
| `deepseek/deepseek-v4-pro` @ fireworks | 200 | **No** | reasoning consumed the token budget, empty content |
| `meta-llama/llama-4-maverick` @ digitalocean | 200 | **Yes**, k=5 | the only positive — but marginal (below) |

Findings that repeat the original retirement causes on new providers:

1. **Advertised ≠ delivered.** Alibaba advertises `top_logprobs`, caps k at 5, and then returns
   `logprobs: null` in the body — exactly the "advertises support, delivers nothing" failure that
   the grok/`akashml-fp8` experience warned about.
2. **k-caps are back.** Where logprobs return at all, k is capped at 5 (vs the frozen 20), so the
   protective-mass estimator has only five top-slots to cover a four-option set.
3. **Frontier open weights are reasoning models.** DeepSeek-V4 and Qwen3.5 (thinking) spend the
   output budget on reasoning and return empty content — the GPT-5.4 problem, now on open weights.
4. **Even the one positive is marginal.** Llama-4 @ DigitalOcean returned real, non-saturated
   top-5 logprobs, but the slots were dominated by *prose* tokens, not the option set:
   `I` (p=0.73), `1` (0.16), `I'm` (0.10), `Since` (0.008), `2` (0.001). Only two option digits
   appear and one carries negligible mass, because at k=5 the preamble alternatives crowd out the
   option coverage.

**Instrument decision — RESOLVED: keep the v6 sampling headline.** Across four frontier
open-weight endpoints only one returned usable logprobs at all, and even that one is marginal at
k=5. Reviving protective-mass as the *primary* estimator on frontier open-weight OpenRouter
endpoints is not reliably viable; it reproduces the caps/advertise-don't-deliver/reasoning
problems that retired it. Logprobs remain at most an *opportunistic secondary* confirmation on the
specific non-reasoning endpoints that demonstrably deliver them (DigitalOcean-Llama), never the
headline. This also argues the open-weight panel should favour **non-reasoning instruct** bases,
or explicitly disable reasoning where the endpoint permits.

**Two follow-ups flagged, not yet done (no outcome dependence):** (a) DeepSeek-V4 first-party is
reachable only after an OpenRouter account **data-policy/privacy** change — an account setting I
will not change without explicit direction; alternatively route DeepSeek to a non-blocked logprob
provider. (b) The probe used `max_tokens=8`; the empty-content/`finish=length` results for the
reasoning models are partly that small budget interacting with reasoning — the *no-logprobs*
findings are independent of it (no logprob object was returned for the tokens that were
generated), but a reasoning-disabled, larger-budget re-probe would cleanly separate the two.

**Accounting (S-F6 discipline).** Two paid rounds: diagnostic round ≈ $0.000646, refined round
≈ $0.000214 → **open-weight canary total ≈ $0.00086**. Round 1 (frozen envelope) errored at
HTTP 400/404 before billing, $0. `--force` overwrote the one same-named artifact
(`llama…digitalocean`) across rounds, so the on-disk envelopes sum to ≈ $0.00084 and do **not**
equal total spend — flagged here rather than left as a silent discrepancy. Cumulative session
paid spend ≈ **$0.0324** of the $3 pre-top-up ceiling.

**Governance.** This was a deliberate Alex-authorized paid canary ahead of Sol's R-E1–R-E7 gate —
the same exception class as the GPT-5.4 canary, logged here for the audit trail. Outcome-blinded;
no study contrast viewed.

*(Refined by the clean re-probe below — the first round's "largely not viable" verdict was too
strong; on a non-reasoning base logprobs are a clean win.)*

### Open-weight logprob canary — clean re-probe (2026-07-23, Alex-authorized)

Re-ran with three changes to separate "no logprobs" from "reasoning ate the budget": reasoning
disabled (`reasoning:{enabled:false}`), `max_tokens` 8→32, and a bare-digit output constraint.
Written to a **new immutable dir** (`out/q2_stage2_canary/openweight_logprob_reprobe/`, no
overwrite of the first round).

| model @ endpoint | HTTP | logprobs | verdict |
|---|---|---|---|
| `meta-llama/llama-4-maverick` @ digitalocean | 200 | k=5, **4/4 option coverage**, mass≈1.0, non-saturated | **clean win** |
| `qwen/qwen3.5-397b-a17b` @ digitalocean | 200 | none | thinking mode still on; `reasoning:{enabled:false}` not honoured; empty content |
| `deepseek/deepseek-v4-pro` @ fireworks | 429 | — | rate-limited upstream (needs BYOK) |
| `deepseek/deepseek-v4-pro` @ wandb | 429 | — | rate-limited upstream (needs BYOK) |

Concrete Llama-4 position-0 distribution (the estimator target): `1` (0.859), `3` (0.070),
`2` (0.055), `4` (0.016), `Since` (~0) — all four option digits, ~all mass on the option set,
argmax `1`, sampled `3`. Exactly the non-degenerate option distribution protective-mass needs;
the earlier 2/4 "prose" result was a prompt-constraint artifact, not an endpoint limit.

**Refined instrument conclusion.** The blanket "logprobs largely not viable" from the first round
was too strong. Corrected:

- **logprob-mass IS cleanly viable on a non-reasoning open-weight instruct base** at a delivering
  provider (Llama-4 @ DigitalOcean, 4/4 coverage) once the prompt forces a bare digit;
- it is **not viable on the thinking/reasoning frontier models** — Qwen3.5-thinking suppresses
  content/logprobs and ignores `reasoning:{enabled:false}` on the tested endpoint; DeepSeek-V4
  could not be tested at all (429 upstream without BYOK);
- **uniform headline stays SAMPLING** (works across reasoning and non-reasoning alike, and the
  banner's two proposed primaries — Qwen3.5-397B, DeepSeek-V4-Pro — are both reasoning models);
- **logprob-mass is a viable SECONDARY** confirmation *iff* the panel includes a non-reasoning
  instruct base. The two proposed reasoning primaries will not yield it.

**Execution flags for the proposed primaries (Qwen3.5-397B, DeepSeek-V4-Pro).** Both are
reasoning/thinking models → sampling-only, consistent with the banner. Two concrete blockers to
resolve pre-freeze: (1) **DeepSeek-V4 is rate-limited upstream (429) without BYOK** on both
Fireworks and WandB — the sampling study needs BYOK or a non-rate-limited provider; (2)
**Qwen3.5-thinking ignored the reasoning-disable param** on DigitalOcean, so the sampling path
must confirm thinking tokens neither corrupt the parsed leading digit (S-F4 anchored parser) nor
inflate per-call cost — otherwise these models behave like GPT-5.4's reasoning trap.

**Accounting.** Re-probe round: $0.000140 (the two 429s billed $0). Open-weight canary cumulative
≈ **$0.00100**; cumulative session paid spend ≈ **$0.0325** of the $3 pre-top-up ceiling.

### Votes sought

Proposed by Alex, 2026-07-23. Pre-outcome; no outcome viewed; no paid *study* call authorized by
this section (the capability canary above is the only paid call, and it is non-study). Seeking
**Fable** and **Sol** on:

1. the sovereign-substrate reframing and the defensible claim form (steering-robustness profile
   inherited, not surface attitude);
2. the open-weight candidate panel and provider-pinning discipline;
3. Tier A now / Tier B as named future work;
4. **ratifying** the instrument decision the canary already resolved — sampling as the uniform
   headline; logprob-mass a viable *secondary* only if a non-reasoning instruct base is in the
   panel — plus the execution blockers (DeepSeek-V4 429/BYOK and data-policy; Qwen3.5-thinking
   ignoring reasoning-disable).

## Sol review of sovereign-AI reframing and open-weight canary (2026-07-23)

**Verdict: OBJECT to the reframing, candidate panel, and Tier-A inheritance claim. AGREE only
with retaining the v6 sampling headline.**

This is a new paper thesis introduced five days before submission, not a model-selection
amendment. It does not solve the user's concern that a broad cheap-model panel risks becoming
a survey of model opinions. It recreates that exact panel and adds an inheritance claim the
experiment does not test.

### S-SOV1. The experiment does not measure base checkpoints

The proposed claim is about a pretraining substrate inherited by later sovereign fine-tunes,
but the hosted endpoints are post-trained chat products:

- the committed OpenRouter metadata resolves Llama to
  `meta-llama/llama-4-maverick-17b-128e-instruct`;
- Qwen emits a long explicit reasoning trace before its answer;
- DeepSeek-V4-Pro is served as a reasoning-capable product endpoint; and
- the proposed panel itself recommends “non-reasoning instruct bases,” which is a
  contradiction: an instruct checkpoint is already post-trained and is not the base model
  whose invariance is being asserted.

Calling these endpoints “bases” does not make them pretraining checkpoints. At most, Stage 2
would characterize several open-weight **instruct models** under provider-specific serving
stacks. That is a valid evaluation target, but it cannot identify a pretraining-level
property.

### S-SOV2. Tier A cannot support inheritance

The quoted claim says a light fine-tune cannot paint over the base's steering-robustness
profile. No artifact in this repository compares a base model with a derivative, holds the
base architecture fixed, varies post-training, or estimates persistence of a vulnerability
profile.

Literature showing that some safety tuning is shallow cannot establish that this paper's
specific floor-crack and guard-placement profile is invariant to SFT, LoRA, DPO, or RLHF.
That is an inference across interventions, model families, objectives, and outcome measures.
It requires the memo's Tier B design. Tier A can say only:

> These tested open-weight instruct models exhibit (or do not exhibit) the measured
> contextual-instability profile.

It cannot say that sovereign derivatives inherit the profile. Therefore Tier B is not
optional future work if the sovereign-inheritance claim enters this paper; it is the minimum
identification design.

### S-SOV3. The pivot is scientifically redundant with the existing paper

The manuscript already reports six open-weight checkpoints across five families—Llama,
Qwen, Phi, Gemma, and Mistral—and explicitly concludes that the crack is not family-specific.
Its stated remaining limitation is the hosted proprietary result: gpt-4o-mini is unpinned and
is only an existence proof.

A recent, provider-pinned GPT-5.4 result addresses that limitation directly. Adding another
Llama/Qwen/DeepSeek/Mistral panel mostly deepens an axis the paper already covers while
abandoning the missing proprietary frontier-grade axis the user explicitly prioritized.
GPT-5.4's relevance is deployment transfer, not whether its weights can be fine-tuned.
Public-sector systems use proprietary hosted models too; their contextual attack surface is
not irrelevant to this paper.

### S-SOV4. The decode-envelope conclusion is unsupported

The canary sent `require_parameters:false`. OpenRouter was therefore permitted to ignore
unsupported parameters. Those responses cannot establish the section's claim that “open
weights accept `temperature`/`top_p`” or that the frozen v3/v4 envelope applies unchanged.

The Qwen and DeepSeek responses instead demonstrate model-specific reasoning behavior, the
same issue that required an explicit GPT-5.4 decode decision. Any promoted sampling endpoint
still needs an exact-envelope canary with `require_parameters:true`, a frozen reasoning
setting, and the sampling parser—not an inference from this logprob diagnostic.

### S-SOV5. The canary supports only the already-made sampling decision

Five provider-pinned endpoints were attempted, not four. Four returned HTTP 200; one returned
position-zero logprobs. The Llama response exposed only two of four option digits in its
top-five list. It therefore fails the frozen all-options coverage rule.

The script's `usable_for_estimator` rule—two visible option digits and no saturation—is a new,
weaker criterion that was never approved and cannot qualify a headline estimator. The
artifacts support this narrow conclusion:

> None of the attempted endpoints passed the frozen logprob coverage requirement, so the v6
> sampling headline remains necessary.

That conclusion is useful but not new thesis evidence. It does not select an open-weight
panel, establish inheritance, or make reasoning/decode amendments moot.

### S-SOV6. The “hardened” audit still violates the audit requirements

The current on-disk envelopes sum to `$0.000839965`, consistent with the memo's rounded
`$0.00084`. The claimed `$0.00086` total relies on an overwritten call that is no longer
auditable. The script's `--force` option overwrote that immutable record, exactly the failure
R-E1/R-E5/S-F6 prohibit.

Additional gaps:

- `X-OpenRouter-Cache:false` is absent;
- the two rounds used different synthetic prompts;
- `require_parameters:false` permits silent parameter dropping;
- failed and superseded attempts do not all have immutable envelopes; and
- the analyzer applies the unapproved two-of-four coverage gate.

Acknowledging the discrepancy is better than hiding it, but acknowledgement does not restore
the missing artifact. Do not use this script for another paid request and do not describe it
as satisfying R-E1/R-E5/S-F6.

### Sol votes

1. sovereign-substrate reframing: **OBJECT**;
2. claim that steering-robustness profiles are inherited: **OBJECT without a matched
   base-to-derivative experiment**;
3. proposed open-weight panel for this submission: **OBJECT**;
4. Tier A now / Tier B future work: **OBJECT**; sovereign inheritance may be named as future
   work, but Tier A cannot substantiate it;
5. retain v6 sampling as the headline estimator: **AGREE**;
6. logprobs only as a labeled endpoint-specific diagnostic: **AGREE**;
7. any further paid canary or study call through the current scripts: **OBJECT**.

**Recommended next action:** return to the GPT-5.4-primary / Grok-cost-fallback decision,
resolve S-F1--S-F6 in the hardened runner, run the outcome-blinded sampling smoke, and make the
full-grid decision from a genuine full-grid cost projection. Put the sovereign-AI
base-to-derivative hypothesis in future work or a separate study unless a matched experiment
is added before submission.

## Sol addendum after Alex's model-capability correction (2026-07-23)

Alex is right that the model-selection question must be separated from the inheritance
claim. GPT-5.4 is recent but already superseded as an OpenAI frontier reference. The proposed
Qwen and DeepSeek models are materially more current and capable than the small/older
open-weight checkpoints already in the manuscript. On that narrower point, S-SOV3 and the
recommended return to GPT-5.4 above are **superseded**.

The inheritance objection is unchanged. The scientifically defensible Stage-2 question is:

> Does the Q1 contextual-instability and guard-placement profile transfer to current
> frontier-class open-weight instruct systems under provider-pinned hosted inference?

That is a strong transfer experiment. It does not claim that these are raw pretraining
checkpoints, that sovereign derivatives inherit their profile, or that the result generalizes
to every open-weight or proprietary frontier model.

### Revised model priority

Use at most two complete models, not a broad panel:

1. `qwen/qwen3.5-397b-a17b` — primary;
2. `deepseek/deepseek-v4-pro` — independent frontier-class replication.

OpenRouter lists Qwen3.5-397B-A17B as a 397B/17B-active leading-edge model released
2026-02-16 at `$0.385/M` input and `$2.45/M` output:
<https://openrouter.ai/qwen/qwen3.5-397b-a17b>.

OpenRouter lists DeepSeek-V4-Pro as a 1.6T/49B-active open-weight model released 2026-04-24
at `$0.435/M` input and `$0.87/M` output:
<https://openrouter.ai/deepseek/deepseek-v4-pro>.

Llama-4-Maverick and Mistral-Large should not consume budget first: they add panel breadth
but do not answer Alex's request for the strongest current open-weight frontier evidence as
directly as Qwen3.5 plus DeepSeek-V4-Pro.

### Budget implication

If reasoning is genuinely disabled and the study response usage resembles the GPT-5.4
canary's five billed completion tokens, the rough 218-input-token projections are:

- Qwen: about `$1.27` for the complete 13,200-call grid;
- DeepSeek: about `$1.31` for the complete 13,200-call grid.

Those are scale estimates, not authorization figures. The existing Qwen Alibaba canary used
249 reasoning tokens and cost `$0.00062556`; extrapolated unchanged, that behavior alone
would cost about `$8.26` over 13,200 calls. The binding capability question is therefore
whether each exact provider endpoint accepts a frozen reasoning-off sampling envelope and
returns a short parseable answer—not its list price.

### Revised execution decision

For each model, freeze one exact provider endpoint and require an outcome-blinded sampling
canary/smoke that sends:

- `X-OpenRouter-Cache:false`;
- `provider.only=[exact_slug]`, `allow_fallbacks:false`,
  `require_parameters:true`;
- the model's documented reasoning-off control;
- `max_tokens=4`;
- `temperature=1.0` and `top_p=1.0` only when the exact endpoint declares and demonstrably
  accepts them;
- no seed;
- the anchored leading-option parser required by S-F4.

Then apply the strengthened parse gate, full-grid request/cost projection, immutable ledger,
nested uncertainty, and exact 11-cell completeness requirements already stated above.

No additional logprob diagnostic is needed. The committed open-weight canary is sufficient to
retain sampling as the headline estimator; it is not sufficient to qualify any endpoint for
sampling.

### Revised Sol votes

1. replace GPT-5.4 with a current frontier open-weight instruct-system test: **AGREE**;
2. Qwen3.5 primary plus DeepSeek-V4-Pro replication: **AGREE IN PRINCIPLE, pending exact
   endpoint capability and cost gates**;
3. complete 11-cell S=100 design on each promoted model: **AGREE**;
4. sovereign/base-substrate inheritance framing: **OBJECT**;
5. describe the result as transfer to current frontier-class open-weight instruct systems:
   **AGREE**;
6. any paid sampling call before the hardened runner passes: **OBJECT**.

The next action is to update the design as a narrowly scoped v7 sampling amendment and build
the hardened sampling canary/smoke once. Do not run another standalone diagnostic script.

## Sol second addendum: UK sovereign-AI policy basis (2026-07-23)

Alex's policy objection is correct. My earlier rejection conflated “base model” as a strict
training-stage term with “substrate” or “starting checkpoint” as used in actual sovereign-AI
development. A checkpoint may already be instruction-tuned and still be the weights a UK
project hosts, adapts, fine-tunes, or builds tooling around.

The UK policy basis is direct:

- The UK Government AI Playbook says that training larger generative models on an
  organisation's own data is prohibitively expensive and beyond most organisations'
  capacity; it identifies fine-tuning existing models as the easier and cheaper route:
  <https://www.gov.uk/government/publications/ai-playbook-for-the-uk-government/artificial-intelligence-playbook-for-the-uk-government-html>.
- The Sovereign AI competition guidance gives “repurpose of open models with tooling, RL,
  fine tuning” as a concrete in-scope example:
  <https://apply-for-innovation-funding.service.gov.uk/competition/2259/download/24922>.
- The UK-led International AI Safety Report explains that open weights benefit actors that
  cannot afford to develop model weights independently and warns that model flaws may
  proliferate into downstream modified versions:
  <https://www.gov.uk/government/publications/international-ai-safety-report-2025/international-ai-safety-report-2025>.

That makes current frontier open-weight model choice principled for this paper. Democracy
Bench becomes an assurance test for the high-capability checkpoints on which a UK sovereign
system might stack adaptation, data, retrieval, tools, and governance controls.

### Correct claim boundary

The empirical claim should be:

> Because UK sovereign-AI projects may begin from existing frontier open-weight checkpoints
> rather than train a frontier model from scratch, the starting checkpoint's contextual
> instability and guard-placement profile is part of the system's initial assurance burden.
> We characterize that pre-adaptation profile on two current frontier-class open-weight
> instruct systems. Any downstream fine-tune must be re-evaluated; adaptation may preserve,
> attenuate, amplify, or relocate the measured failure mode.

This is stronger and more defensible than treating the open-weight panel as generic model
breadth. It does not require claiming that the profile is immutable. The starting model is a
supply-chain input whose failure modes must be known before adaptation, and the resulting
derivative must be tested again afterward.

Use “starting checkpoint,” “adaptation substrate,” or “pre-adaptation model,” not “raw base
model.” Reserve “inheritance” for either:

1. the weak, uncontroversial sense that the downstream project begins from those weights and
   therefore inherits an initial assurance obligation; or
2. a future matched base/derivative result that empirically shows persistence of a specific
   profile.

Do not state that a light fine-tune “cannot paint over” the profile without the matched
experiment. The sovereign motivation does not need that overclaim.

### Final Sol position on framing

1. UK sovereign-AI motivation for selecting frontier open weights: **AGREE**;
2. Qwen3.5 and DeepSeek-V4-Pro as plausible high-capability adaptation starting checkpoints:
   **AGREE**;
3. Tier A pre-adaptation characterization in this submission: **AGREE**;
4. matched derivative experiment as required future re-evaluation: **AGREE**;
5. invariant steering-profile inheritance claim: **OBJECT unless directly tested**;
6. sampling-only full 11-cell S=100 design, subject to the hardened endpoint and cost gates:
   **AGREE**.

This addendum supersedes S-SOV1--S-SOV3 to the extent they rejected the sovereign-AI
motivation or treated instruction tuning as disqualifying a checkpoint from downstream
adaptation. S-SOV4--S-SOV6 remain operationally valid.

## Alex reconciliation with Sol/Codex review (2026-07-23)

Accepting the converged Sol/Codex position. Its second addendum supersedes S-SOV1–S-SOV3;
**S-SOV4–S-SOV6 are accepted and stand.** This section is the authoritative current position; the
earlier sovereign-AI reframing subsections are retained as the drafting trail, with their specific
overclaims marked inline and corrected here.

### Framing — adopt the bounded pre-adaptation boundary; drop "inheritance/invariance"

The Stage-2 hosted claim is a bounded pre-adaptation assurance statement, not a claim that the
profile is inherited or immutable:

> Because UK sovereign-AI projects may begin from existing frontier open-weight checkpoints rather
> than train a frontier model from scratch (UK Government AI Playbook; Sovereign AI competition
> guidance; International AI Safety Report), the starting checkpoint's contextual-instability and
> guard-placement profile is part of the system's initial assurance burden. We characterize that
> pre-adaptation profile on two current frontier-class open-weight instruct systems. Any downstream
> fine-tune must be re-evaluated; adaptation may preserve, attenuate, amplify, or relocate the
> measured failure mode.

Terminology: **"starting checkpoint / adaptation substrate / pre-adaptation instruct system,"**
never "raw base model." "Inheritance" is reserved for (1) the weak sense that a project begins from
those weights and thus inherits an initial assurance obligation, or (2) a future matched
base↔derivative result. The "a light fine-tune cannot paint over the profile" sentence is
**withdrawn** (marked inline above); establishing it requires the Tier-B matched experiment, which
is future work, not a claim in this submission.

### Panel — two models, sampling-only

Primary `qwen/qwen3.5-397b-a17b`; independent frontier-class replication `deepseek/deepseek-v4-pro`
(Sol revised priority). Both are reasoning/thinking instruct systems → **sampling headline**
(logprobs unavailable on them). Llama-4-Maverick and Mistral-Large are not run first: they add
breadth the manuscript already has (six open-weight checkpoints, five families), and Mistral has no
logprob endpoint regardless. The earlier four-model candidate panel is narrowed accordingly.

### Concessions (S-SOV4–S-SOV6 accepted)

- **S-SOV4 (decode).** The open-weight canary used `require_parameters:false`, so it does not
  establish that the frozen `temperature/top_p` envelope is accepted; the "decode amendment is
  moot" line is withdrawn. Each promoted endpoint needs an exact-envelope canary with
  `require_parameters:true`, a documented reasoning-off control, `max_tokens=4`, and the S-F4
  parser.
- **S-SOV5 (coverage gate).** The script's `usable_for_estimator` = 2-of-4 rule was an unapproved,
  weaker criterion and is retracted; the frozen rule is all-options coverage. *Factual note back to
  Sol:* the clean re-probe (which the initial S-SOV5 predates) reached **4/4** coverage on Llama-4
  @ DigitalOcean, not 2/4 — but this still only confirms sampling as the headline and qualifies no
  endpoint.
- **S-SOV6 (audit).** `--force` overwrote the round-2 `llama…digitalocean` immutable envelope — a
  genuine R-E5/S-F6 violation. `scripts/openweight_logprob_canary.py` is **not** R-E1/R-E5/S-F6-
  compliant, is retired to a one-off diagnostic, and must not be used for another paid call.

### Instrument

Sampling is the uniform headline (AGREE with Sol). Logprob-mass is at most a labeled
endpoint-specific diagnostic, never the headline; no further standalone logprob diagnostic is
needed.

### Next action — a narrowly-scoped v7 sampling amendment (no code run yet)

Amend `Q2_STAGE2_HOSTED_DESIGN.md` to v7, freezing: the two models and one exact provider endpoint
each; the reasoning-off sampling envelope (`X-OpenRouter-Cache:false`, `provider.only=[slug]`,
`allow_fallbacks:false`, `require_parameters:true`, documented reasoning-off, `max_tokens=4`, no
seed, `temperature/top_p` only where the exact endpoint declares and demonstrably accepts them);
the S-F4 anchored parser; the strengthened parse gate; full-grid request/cost projection; immutable
ledger; nested uncertainty; exact 11-cell completeness. Then build **one** hardened sampling
canary/smoke — not the retired diagnostic script — and gate per R-E1–R-E7 / S-F1–S-F6.

The binding pre-freeze question is capability-and-cost per exact endpoint under a frozen
reasoning-off envelope. Sol's budget note is the crux: with reasoning genuinely off, the full grid
projects to roughly $1.3 per model; but the Qwen Alibaba canary spent **249 reasoning tokens**
(≈$8.26 extrapolated), so if a promoted endpoint will not honour reasoning-off the run is both
unaffordable and unparseable — exactly the GPT-5.4 trap. Resolve this outcome-blinded, before any
substantive frequency is viewed.

### Still open

- **Fable concurrence is resolved.** Alex confirmed on 2026-07-27 that the Opus response
  was Fable's review. This records concurrence with the bounded sovereign-AI framing and
  two-model direction; it does not waive the v7 freeze or execution gates.
- **DeepSeek-V4 is 429/BYOK rate-limited** on the providers tested; decide BYOK vs an alternate
  non-rate-limited logprob-irrelevant sampling endpoint before the v7 canary.
- The **`[TODO: pin citations]`** for the policy basis is now concrete: UK Government AI Playbook,
  Sovereign AI competition guidance, International AI Safety Report (URLs in Sol's second addendum).
