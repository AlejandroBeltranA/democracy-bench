# Q2 Stage-2 v7.2 — final smoke handoff

Date: 2026-07-28  
Owner after implementation: Claude  
Reviewer/authorization gate: Codex

## Current status

**WAITING FOR FINAL COMMIT AND CODEX AUTHORIZATION. DO NOT SEND THE SMOKE YET.**

The broad review is finished. Do not reopen settled issues or perform another architectural
rewrite. Complete only the two remaining smoke gates below, commit the exact result, and let
the active Codex monitor review that commit.

## Required final changes

### 1. PS-7 — hard stop before every retry

The exact-money ledger must be checked immediately before every actual `_post_once`,
including retries.

Acceptance test:

- stop: `$0.0000006`;
- paid HTTP 429: `$0.0000004`;
- proposed retry: worst case `$0.0000004`;
- expected: exactly one transport call, spend `<=` stop, run halted/incomplete, no headline.

The retry must not be sent after the first attempt is booked.

### 2. PS-8 — deterministic DeepSeek C2 input

Commit the narrow pre-outcome amendment and every implementation input it names. The
DeepSeek serialization/calibration must be:

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

1. Finish PS-7 and PS-8.
2. Run the focused no-network pre-smoke tests.
3. Commit all code, tests, amendment text, pinned inputs, and updated snapshot evidence.
4. Leave the worktree stable.
5. The active Codex monitor will review the new commit immediately.

Codex will update this file to one of:

- `AUTHORIZED — RUN QWEN SMOKE NOW`; or
- `HOLD — <one concrete reproduced blocker>`.

No paid smoke should run before the explicit `AUTHORIZED` marker appears below.

## Authorization

**PENDING — NOT YET AUTHORIZED**

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
