# Stage-2 Panel B — frontier extension, proposal

Date: 2026-09-22
Status: **FROZEN 2026-09-22, PRE-OUTCOME.** Alex's decision, verbatim: "do glm on the fp8
endpoint plus sol, $11 stop". Amendment AMD-PB-01 signed below. No substantive frequency
has been viewed for either model.

## Why

The frozen v7 panel is two open-weight models (Qwen3.5-397B-A17B, DeepSeek-V4-Pro). Two
rows carry the frontier transfer claim. A blog post and a reviewer will both ask whether
the crack and the routing-guard recovery hold on other current frontier systems. Panel B
adds rows under the same frozen design: 11 cells × 12 probes × 4 Williams orders × 25
draws = 13,200 sampling calls per model, all eight within-model estimands, no reduced
design.

Panel B is a labelled extension. It does not reopen v7 estimands, cells, probes, orders,
or scoring. The v7 rows stay primary; Panel B rows are reported as replication rows.

## What the frozen wire format requires

Every study draw is sent with `require_parameters: true`, `temperature: 1.0`,
`top_p: 1.0`, `reasoning.effort: "none"`, `max_tokens: 4`, single pinned provider, no
fallback. Promotion needs a C2 full-grid cost projection from a pinned, hash-verified
official tokenizer read from committed local files.

Live OpenRouter endpoint listing, 2026-09-22:

| Model | temp / top_p declared | Public tokenizer | Fits frozen gate as-is |
|---|---|---|---|
| z-ai/glm-5.3 | yes | yes (zai-org/GLM-5.3) | **yes** |
| moonshotai/kimi-k3 | yes on third-party endpoints, **no** on Moonshot and Alibaba first-party | yes (moonshotai/Kimi-K3) | yes, third-party endpoint only |
| x-ai/grok-4.5 | yes | no | no (C2) |
| google/gemini-3.1-pro-preview | yes | no | no (C2) |
| anthropic/claude-opus-5 | **no** (Azure only for temp) | no | no (params + C2) |
| anthropic/claude-sonnet-5 | **no** | no | no (params + C2) |
| openai/gpt-5.6-sol | **no** | no | no (params + C2) |
| openai/gpt-5.5 | **no** | no | no (params + C2) |

Two separate blockers for the closed models:

1. **Sampling parameters.** With `require_parameters: true`, an endpoint that does not
   declare `temperature` and `top_p` is not routable. Anthropic and OpenAI endpoints
   declare neither. Running them means dropping the two sampling parameters from the
   request for those rows and accepting provider-default sampling. That is a change to
   the frozen request, so it must be a signed amendment and reported per row.
2. **C2 projection.** No public tokenizer means no pinned-tokenizer projection, so the
   existing promotion rule cannot fire. The amendment would substitute a provider-usage
   projection: run the frozen smoke, take the provider-reported `prompt_tokens` per
   draw, apply the existing 10 % margin, and project the full grid from that. Same
   stop, same blinding.

A third risk, canary-testable and not an amendment: Opus 5 has thinking on by default
and Sol is a reasoning model. `reasoning.effort: "none"` with `max_tokens: 4` must
yield a parseable option number. If the canary shows reasoning tokens or empty content,
the model fails the frozen parse-rate gate and is excluded, as Mistral-7B was locally.

## Cost

Measured from the v7 study envelopes: ~236 prompt tokens and 1 completion token per
draw. 13,200 draws ≈ 3.1 M prompt tokens. With the 10 % margin, per model:

| Model | Endpoint price used ($/M in) | Projected full run |
|---|---|---|
| z-ai/glm-5.3 | 1.40 (Z.AI first-party, fp8) | ≈ $4.8 |
| z-ai/glm-5.3 | 0.76 (Reka, fp8, cheapest declaring params) | ≈ $2.6 |
| moonshotai/kimi-k3 | 3.00 (Fireworks / Parasail, third-party) | ≈ $10.3 |
| x-ai/grok-4.5 | 2.00 | ≈ $6.9 |
| google/gemini-3.1-pro-preview | 2.00 | ≈ $6.9 |
| anthropic/claude-sonnet-5 | 2.00 | ≈ $6.9 |
| openai/gpt-5.6-sol | 2.00 | ≈ $6.9 |
| anthropic/claude-opus-5 | 5.00 | ≈ $17.2 |

Prices are recorded, never used to reorder. Endpoint choice follows the v7 rule:
first-party where it declares the parameters, otherwise the highest-precision
third-party endpoint that does.

## Two tracks

**Track 1 — no amendment.** Add GLM-5.3 and Kimi-K3 to a Panel B list in the gate,
snapshot their endpoints and tokenizers, run walk → project → authorize → smoke → full
exactly as v7. Both are open-weight, which matches the sovereign-AI starting-checkpoint
framing. Cost ≈ $15 for both.

**Track 2 — closed-model amendment (AMD-PB-01).** Everything in Track 1 plus the two
substitutions above for closed rows. Candidates: Opus 5 as the closed comparator, GPT-5.6
Sol as the second, Gemini 3.1 Pro and Grok 4.5 optional. The amendment must be committed
before the canary, and the rows are labelled "provider-default sampling" in every table.

## Order of operations, either track

1. Freeze the Panel B model list and hard stop in this memo and in `gate.py`. Commit.
2. Snapshot endpoints (and tokenizers where public) into a Panel B snapshot. Commit.
3. Synthetic canary per model. Inspect wire format only.
4. Walk / project / authorize per model. Record funding once for the panel.
5. Smoke, promotion decision blind to substantive frequencies.
6. Full run. Extract. Only then look.

Nothing below step 3 spends money without `--i-have-authorized-paid-spend` and a
recorded funding decision.

## Frozen Panel B (2026-09-22)

| Row | Endpoint tag | Price ($/M in, out) | Quantization | Gate path |
|---|---|---|---|---|
| z-ai/glm-5.3 | `reka/fp8` | 0.7605 / 2.574 | fp8 | frozen v7 gate (pinned tokenizer, exact C2) |
| openai/gpt-5.6-sol | `openai` | 2.00 / 10.00 | unknown | AMD-PB-01 |

- Hard stop: **$11.00**, Panel-B-only spend. Prior spend reconciled from Panel B's own
  canary records only; v7 spend is not debited against it (v7 closed under its own $8.50).
- OpenRouter balance at freeze: $11.36 remaining of $20.00.
- Snapshot: `out/q2_stage2_panel_b_snapshot/manifest.json`, SHA-256
  `56f64dd974e2e7bfd86d0570e67feded34e9a6a1e274af2901d7cb7be41c061b`, fetched
  2026-09-22. GLM-5.3 tokenizer pinned at `zai-org/GLM-5.3` revision
  `aca966e4e02791568aa6a4ced368624b3d897f42` under `out/q2_stage2_tokenizers/glm/`.
- Activation: `Q2_PANEL=B` on every runner invocation. Without it every v7 constant is
  untouched.
- Everything else (11 cells, 12 probes, 4 orders, 25 draws, eight estimands, smoke rule,
  parse-rate gate, C1 provider audit, reasoning-off proof, C3 retries) is the v7 design
  unchanged.

## AMD-PB-01 — closed-model amendment (signed pre-outcome, 2026-09-22)

Applies to `openai/gpt-5.6-sol` only. Three substitutions, each reported per row:

1. **Sampling parameters.** The promoted OpenAI endpoint declares neither `temperature` nor
   `top_p`. Under the frozen `require_parameters: true` routing, the request for this model
   omits those two keys; provider-default sampling applies. `max_tokens: 4`,
   `reasoning.effort: "none"`, single provider, no fallback, cache off, usage included are
   unchanged. Tables label the row "provider-default sampling".
2. **Cost projection.** No public tokenizer exists, so the frozen C2 pinned-tokenizer
   projection cannot run. The projection uses a counter calibrated from the walk probe's
   provider-reported `prompt_tokens` (ratio of reported tokens to prompt characters), applied
   to each of the 528 rendered requests, plus the runner's fixed template overhead, then the
   frozen 10 % margin. It is labelled `fixed_overhead_fallback` with amendment `AMD-PB-01`
   in the artifact. The ledger books the returned cost of every draw regardless; the stop
   is enforced on real spend.
3. **Endpoint rule for GLM-5.3.** The v7 rule prefers a first-party endpoint that declares
   the parameters. Z.AI first-party is $1.40/M and would leave no room for Sol under the
   balance. GLM-5.3 runs on the Reka fp8 endpoint, which declares all four parameters, and
   the row is labelled fp8.

Signed: Alex Beltran (decision in chat, 2026-09-22). Recorded by: Claude.

## Canary record and GLM substitution (2026-09-22, pre-outcome)

Synthetic canary, Panel B, `out/q2_stage2_panel_b_canary/`:

| Model @ endpoint | HTTP | Reasoning tokens | Content | Verdict |
|---|---|---|---|---|
| openai/gpt-5.6-sol @ openai | 200 | 0 | parseable option | **PASS**, $0.000142 |
| z-ai/glm-5.3 @ reka/fp8 | 400 | n/a | "Reasoning is mandatory for this endpoint and cannot be disabled." | **FAIL** |

Two synthetic diagnostic probes outside the study (`out/q2_stage2_panel_b_diagnostics/`),
sent to establish whether the GLM-5.3 failure is endpoint-specific:

- `z-ai/glm-5.3` on the Z.AI first-party endpoint: the same 400. GLM-5.3 is a
  reasoning-mandatory model; the frozen reasoning-off proof (R-V7-1) cannot be satisfied
  on any endpoint. **GLM-5.3 is recorded as a capability exclusion.**
- `z-ai/glm-5.2` on the Z.AI first-party endpoint: HTTP 200, reasoning tokens 0, parseable
  option, $0.0000506. Diagnostic spend is debited to the Panel B stop as a non-reconciled
  upper bound of $0.0002.

**Substitution.** GLM-5.2 replaces GLM-5.3 as the GLM row: same lab, open weights, public
tokenizer and chat template (`zai-org/GLM-5.2` revision
`cf457fa734ab149ffef225f80893eb38c6ff5cdc`), honours reasoning off. Endpoint `novita/fp8`
($0.65 / $2.042 per M), the cheapest fp8 endpoint declaring all four parameters with
≥ 99 % 30-minute uptime; Z.AI's own endpoint is also fp8, at $1.40. The Panel B snapshot is
re-frozen with GLM-5.2 and Sol. No substantive frequency has been viewed for any Panel B
model; the only outputs seen are the synthetic canary replies above.

An earlier canary attempt failed in TLS before reaching OpenRouter (Python without system
root certificates); its two HTTP-0, zero-cost records are kept at
`out/q2_stage2_panel_b_canary_attempt1_ssl_failed/`. All later runs pass `--ca-file`
with the certifi bundle.

## Walk results (2026-09-22, pre-outcome)

| Model @ endpoint | HTTP | Reasoning tokens | Billed completion tokens | Gate |
|---|---|---|---|---|
| z-ai/glm-5.2 @ novita/fp8 | 200 | 0 | 1 | **promoted**; projection $2.5785 of $11.00, exact C2 (pinned chat template) |
| openai/gpt-5.6-sol @ openai | 200 | 0 | **5** | **excluded**: billed completion tokens exceed `max_tokens: 4` |

Sol's reply was the single digit "2", `finish_reason: stop`, reasoning tokens 0, but OpenAI
billed five completion tokens for it (`upstream_inference_completions_cost` $0.00005 at
$10/M). The frozen walk criterion (b) treats billed completion tokens above the cap as
evidence of hidden generation and excludes the endpoint. The exclusion is recorded in
`out/q2_stage2_panel_b_run/interlock/promotion_record_openai__gpt-5.6-sol.json` and, per the
v7 rule, cannot be resurrected in this run directory. Running Sol would need a further
signed amendment relaxing (b) for provider framing tokens when reasoning tokens are exactly
zero, in a separately labelled run directory. Not authorized by this memo.

Funding recorded for the panel: GLM-5.2 funded at $2.5785 projected; Sol excluded.

## AMD-PB-02 — framing-token amendment for the Sol row (signed pre-outcome, 2026-09-22)

Alex's decision, verbatim: "do option 2, sign the amendment and run sol".

Applies to `openai/gpt-5.6-sol` on the `openai` endpoint only, run as variant **B2** in its
own directory `out/q2_stage2_panel_b2_run/` (`Q2_PANEL=B2`). The B exclusion record stands
and is not edited. Three departures from variant B, nothing else:

1. **Criterion (b) tolerance.** Billed completion tokens may exceed `max_tokens: 4` by at
   most 8 on the `openai` tag, and only when reported reasoning tokens are exactly 0 and no
   reasoning payload is present. The walk evidence is a one-digit reply, `finish_reason:
   stop`, reasoning tokens 0, billed 5: the four extra tokens are OpenAI's hidden
   per-message framing, which the v7 rule predates. The tolerance is bounded and tag-keyed;
   GLM's endpoint stays strict. Every other part of (b) is unchanged.
2. **Roster.** B2 is the Sol row alone.
3. **Stop.** B2 runs under an $8.00 stop of its own, reconciled from the Panel B canary
   records and diagnostics. GLM-5.2's projection is $2.5785 under B's ledger, so B + B2
   stays inside the $11.00 Panel B ceiling.

The projection allowance for Sol becomes 5 completion tokens per draw (the observed billed
value), so the projected total rises accordingly. Signed: Alex Beltran (decision in chat).
Recorded by: Claude.
