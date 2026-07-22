# Stage-2 hosted design — DRAFT for sign-off (freeze before any OpenRouter call)

Status: DRAFT. This is a LABELLED FOLLOW-UP to the local Q1 preregistration, designed
after seeing the local outcomes (per `Q1_RESULTS_CONSENSUS.md`); it is not part of the
original local preregistration and the paper must describe it as a follow-up. No API
call until Alex and Sol approve this document and it is committed; that commit is the
Stage-2 freeze.

## Questions (fixed)

Do the four local findings transfer beyond two quantized Llama checkpoints: instruction
dominance over data, placebo (format) movement, the user-after recency recovery, and
heterogeneous system-guard recovery, with the combined payload defeating prompt guards?

## Cells per model (Sol's minimum set, frozen)

baseline/no_guard; instruction_only/no_guard; data_only/no_guard; combined/no_guard;
placebo/no_guard; data_only/user_after; data_only/system_guard; combined/user_after;
combined/system_guard. (9 cells x 12 probes x 4 Williams orders.)

All payload and guard texts, orders, estimand definitions, and decision rules are
inherited verbatim from the frozen local design (`8c69435`); nothing may be reworded for
hosted models beyond the provider's chat-role mechanics.

## Panel and order (declared; no substitutions after results)

1. `openai/gpt-4o-mini-2024-07-18` (pinned) 2. `openai/gpt-4o-2024-11-20` (pinned)
3. `x-ai/grok-4.5` (not a dated snapshot; include only if the smoke gate passes)
4. `meta-llama/llama-3.3-70b-instruct`. Every attempted model and cell is reported,
including failures. Only the dated OpenAI ids are pinned; OpenRouter execution is not
byte-reproducible and serving providers may change.

## Gates and measurement

- Smoke gate per model before the matrix (2 probes x 4 decisive cells): provider returns
  logprobs; all four option tokens recoverable; no silent zero-assignment from truncated
  `top_logprobs`; system role actually preserved at the endpoint; stable cells under the
  fixed orders. Hosted scoring sums distinct accepted keys within the returned top-k and
  records per-call option coverage; where coverage is incomplete, fall back to sampling
  (S=100) for that model and say so.
- Sampling validation (S=100) on pinned gpt-4o-mini for baseline, instruction-only,
  data-only, combined, and combined+system-guard; reported even if it disagrees with the
  logprob path.

## Budget (inherited caps)

Smoke + retries $1.00; hosted matrix $3.00; sampling validation $3.75; reserve $1.50.
Planned-spend stop at $8.50. The reserve completes preregistered cells or reruns a
documented provider failure only; it never adds a favourable model.

## Votes

A: [ ] F: [AGREE] S: [ ]
