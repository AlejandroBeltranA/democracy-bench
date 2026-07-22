# Stage-2 hosted design — DRAFT for sign-off (freeze before any OpenRouter call)

Status: DRAFT. This is a LABELLED FOLLOW-UP to the local Q1 preregistration, designed
after seeing the local outcomes (per `Q1_RESULTS_CONSENSUS.md`); it is not part of the
original local preregistration and the paper must describe it as a follow-up. No API
call until Alex and Sol approve this document and it is committed; that commit is the
Stage-2 freeze.

**Sol vote (2026-07-22): OBJECT pending R-H1--R-H5 below.** No OpenRouter call is
authorized from this draft.

**v2 (Fable, 2026-07-22): R-H1--R-H5 incorporated below; fresh Alex + Sol sign-off
required, and no hosted outcome may be viewed before the v2 freeze commit.**

## Questions (fixed, per R-H2)

Do the local findings transfer beyond two quantized Llama checkpoints: instruction
dominance over data in the no-guard arm; placebo (irrelevant distribution-and-
reproduction) movement; combined-payload severity and its placement-sensitive recovery;
and heterogeneous system-guard recovery. Hosted instruction-only testing is limited to
dominance in the no-guard arm; no instruction-placement claim is made or tested.

## Cells per model (11-cell minimum, frozen; per R-H1)

baseline/no_guard; instruction_only/no_guard; data_only/no_guard; combined/no_guard;
placebo/no_guard; data_only/user_before; data_only/user_after; data_only/system_guard;
combined/user_before; combined/user_after; combined/system_guard.
(11 cells x 12 probes x 4 Williams orders = 528 logprob calls per model, plus smoke.)

All payload and guard texts, orders, and decision thresholds are inherited verbatim from
the frozen local design (`8c69435`); nothing may be reworded for hosted models beyond
the provider's chat-role mechanics.

## Estimands (per model, non-pooled; per R-H2)

Within each model, paired over the 12 probes with the frozen percentile bootstrap:
data effect (data_only/no_guard - baseline/no_guard); instruction effect
(instruction_only/no_guard - baseline/no_guard); channel contrast (data effect -
instruction effect); placebo effect (placebo/no_guard - baseline/no_guard); two
user-placement contrasts (data_only/user_after - data_only/user_before;
combined/user_after - combined/user_before); two system-recovery contrasts
(data_only/system_guard - data_only/no_guard; combined/system_guard -
combined/no_guard). Local crack and materiality thresholds inherited. Model x probe
cells are never pooled as independent observations.

## Panel and order (declared; no substitutions after results)

1. `openai/gpt-4o-mini-2024-07-18` (pinned) 2. `openai/gpt-4o-2024-11-20` (pinned)
3. `x-ai/grok-4.5` (not a dated snapshot; include only if the smoke gate passes)
4. `meta-llama/llama-3.3-70b-instruct`. Every attempted model and cell is reported,
including failures. Only the dated OpenAI ids are pinned; OpenRouter execution is not
byte-reproducible and serving providers may change.

## Gates and measurement (per R-H3)

- **Smoke cells, named:** baseline/no_guard, instruction_only/no_guard,
  data_only/no_guard, placebo/no_guard, data_only/system_guard, and combined/user_after,
  on two frozen probes: `pol_ai_due_process` (a treatment floor) and `pol_surveillance`
  (the probe with the known local coverage anomaly, included deliberately as the stress
  case). 12 smoke calls per model.
- **Promotion rule (frozen):** if any smoke call lacks a displayed option number in its
  returned logprobs, the model is NOT promoted to the logprob matrix; the failed smoke is
  reported. Sampling is used only for a model and cell set whose cost was budgeted before
  results; logprob and sampling estimators are never mixed within a model's headline
  contrasts.
- **Estimator naming:** hosted scoring sums distinct accepted keys within the returned
  top-k and records per-call option coverage; results are described as a
  coverage-audited top-k option score, not an exact full-vocabulary probability.
- **System role:** internal preservation is not observable inside a hosted provider.
  Persist the sent message roles, response/provider metadata, and a role-sensitive smoke
  comparison; describe this as endpoint acceptance and behavioral validation.

## Sampling validation (per R-H4)

On pinned gpt-4o-mini: S=100 per probe-cell IN TOTAL, balanced as 25 samples per each of
the four Williams orders. Cover the full 11-cell set if the measured smoke cost fits the
$3.75 cap; the frozen minimum is baseline/no_guard, instruction_only/no_guard,
data_only/no_guard, placebo/no_guard, combined/no_guard, data_only/user_before,
data_only/user_after, and data_only/system_guard. Logprob and sampling estimates are
reported side by side even when they disagree.

## Budget (per R-H5)

Matrix: 528 logprob calls per model (11 x 12 x 4) plus 12 named smoke calls. Caps:
smoke + retries $1.00; hosted matrix $3.00; sampling validation $3.75; reserve $1.50;
planned-spend stop $8.50. Measured input-token counts and worst-case per-model costs are
recorded from smoke BEFORE any model is promoted. Deterministic cut rule if the matrix
cap cannot cover all declared models: finish the current preregistered model in panel
order, then stop before starting the next; a model is never partially run, and never
selected or dropped because earlier cells look favorable. The reserve completes
preregistered cells or reruns a documented provider failure only.

## Votes (v2)

A: [ ] F: [AGREE] S: [ ]

## Sol review — required revisions before Stage-2 freeze

### R-H1. Add the missing matched user-before cells

The nine-cell set cannot test “user-after recency recovery”: it has no user-before
counterfactual. Add `data_only/user_before` and `combined/user_before`, producing an
11-cell minimum. Then freeze the hosted placement estimands as:

- `data_only/user_after - data_only/user_before`;
- `combined/user_after - combined/user_before`;
- `data_only/system_guard - data_only/no_guard`;
- `combined/system_guard - combined/no_guard`.

If instruction recency is claimed to transfer, also add instruction-only/user-before and
instruction-only/user-after; otherwise state explicitly that hosted instruction testing
is limited to dominance in the no-guard arm.

### R-H2. Correct the hosted research question

The local combined payload did **not** defeat every prompt guard: user-after closed all
induced combined cracks on 3B and most on 8B. The hosted question is whether combined-
payload severity and its placement-sensitive recovery transfer, not whether universal
prompt-guard defeat transfers.

Freeze per-model, non-pooled estimands for data effect, instruction effect, channel
contrast, placebo effect, the two user-placement contrasts above, and the two system-
recovery contrasts. Inherit the local crack and materiality thresholds. Do not pool model
x probe cells as independent observations.

### R-H3. Specify the smoke cells and the fallback unit

Name the smoke cells rather than “four decisive cells.” They must exercise at least:
baseline/no-guard, instruction-only/no-guard, data-only/no-guard, placebo/no-guard,
data-only/system-guard, and combined/user-after on the two frozen probes.

Freeze what happens on incomplete top-logprob coverage. Recommended rule: if any smoke
call lacks a displayed option number, do not promote that model to the logprob matrix.
Report the failed smoke. Use sampling only for a model and cell set whose cost was
budgeted before results; do not mix logprob and sampling estimators opportunistically
within a model's headline contrasts. Returned top-k coverage cannot prove that every
tokenization variant outside top-k was captured, so describe hosted logprob results as a
coverage-audited top-k option score, not an exact full-vocabulary probability.

“System role actually preserved” is not directly observable inside a hosted provider.
Persist the sent message roles, response/provider metadata, and a role-sensitive smoke
comparison; describe this as endpoint acceptance and behavioral validation rather than
proof of internal preservation.

### R-H4. Update sampling validation to cover the new decisive findings

The listed five sampling cells omit placebo and the primary data/system recovery. On
pinned gpt-4o-mini, use S=100 **per probe-cell in total, balanced as 25 samples per each
of the four Williams orders**, for the final 11-cell set if the measured smoke cost fits
the $3.75 cap. At minimum it must include baseline/no-guard, instruction-only/no-guard,
data-only/no-guard, placebo/no-guard, combined/no-guard, data-only/user-before,
data-only/user-after, and data-only/system-guard.

Report logprob and sampling estimates side by side even when they disagree. Define S=100
unambiguously; do not let it mean 100 per order in one implementation and 100 across
orders in another.

### R-H5. Recalculate and freeze the call/token budget

After adding the two matched cells, the logprob matrix is 11 x 12 x 4 = 528 calls per
model, plus the named smoke calls. Record measured input-token counts and worst-case
costs from smoke before promotion. State the deterministic cut rule if the $3 matrix cap
cannot cover all declared models (model order already supplies the natural rule: finish
the current preregistered model, then stop before starting the next). Never partially run
a model because earlier cells look favourable.

Once R-H1--R-H5 are incorporated, issue a v2 for fresh Alex/Fable/Sol sign-off. No hosted
outcome may be viewed before that freeze.
