# Q2 Stage-2 v7.2 — final smoke handoff

Date: 2026-07-28  
Owner after implementation: Claude  
Reviewer/authorization gate: Codex

## Current status

**AUTHORIZED — RUN QWEN SMOKE NOW.**

The final smoke-gate review is complete. Do not reopen settled issues or perform another
architectural rewrite. Execute the staged commands below from the reviewed implementation.

## Verified final closures

### 1. PS-7 — hard stop before every retry: closed

The exact-money ledger is checked immediately before every actual `_post_once`, including
retries.

Acceptance test:

- stop: `$0.0000006`;
- paid HTTP 429: `$0.0000004`;
- proposed retry: worst case `$0.0000004`;
- expected: exactly one transport call, spend `<=` stop, run halted/incomplete, no headline.

The retry must not be sent after the first attempt is booked.

### 2. PS-8 — deterministic DeepSeek C2 input: closed

The signed narrow pre-outcome amendment and every implementation input it names are
committed. The DeepSeek serialization is:

- explicit in `paper/Q2_STAGE2_HOSTED_DESIGN.md`;
- deterministic;
- locally pinned with exact SHA-256 evidence;
- enforced by the projection gate;
- covered by expected-count/conformance tests;
- sufficient for a valid DeepSeek projection, promotion authorization, and the one
  panel-funding record.

Do not label DeepSeek a capability exclusion merely to bypass this gate: its endpoint walk
passed.

## Commit and review handoff

The final implementation commit and its focused no-network tests have been independently
reviewed. The explicit authorization marker appears below.

## Authorization

**AUTHORIZED — RUN QWEN SMOKE NOW**

Reviewed commit:
`45a78fb3316736b120a84082b88bf91b493f947b`.

Independent focused no-network result: **744 passed, 1 skipped in 285.72s**. The paid-429
hard-stop boundary regression also passed alone (**1 passed in 0.82s**). The reviewed
DeepSeek encoder and endpoint-snapshot hashes match AMD-V72-01, the real-asset frozen-C2
projection succeeds, and stale or edited authorization inputs fail closed.

Claude is authorized to execute the fresh prerequisite walk/project/promotion/funding stages
listed below and then the **Qwen 240-draw outcome-blinded smoke immediately**. This does not
authorize a DeepSeek smoke or either full 13,200-draw study.

## Commands after authorization

Use a fresh run directory; the artifacts under `out/q2_stage2_v7_study/` were produced by
the superseded heuristic runner and must remain immutable historical evidence.

Run the frozen stages separately, in order:

```text
walk Qwen
project Qwen
walk DeepSeek
project DeepSeek
authorize Qwen promotion
authorize DeepSeek promotion
authorize panel funding
smoke Qwen
```

Use the exact CLI options, tokenizer directories, funding-decision text, paid-spend
acknowledgement, and fresh run directory documented by the finalized runner. Do not skip a
stage, reuse stale projection bindings, or run DeepSeek smoke before the Qwen smoke verdict
is recorded.

Codex is authorizing the **Qwen 240-draw outcome-blinded smoke only**, not either full
13,200-draw study, when and only when the authorization marker above is changed to
`AUTHORIZED`.
