# Q2 Stage-2 v7.2 code review — live execution gate not passed

Reviewer: Codex  
Date: 2026-07-28  
Reviewed branch: `phase4-floor-guards`  
Reviewed HEAD: `4d0c5ac` — *Build hardened Q2 Stage-2 v7.2 runner; synthetic canary passes on Qwen3.5-397B*  
Implementation scope: cumulative Stage-2 code from `80399d7` through `4d0c5ac`

## Verdict

**OBJECT to further paid Stage-2 execution until R-C1--R-C6 below are fixed and
retested.**

The v7.2 package is a substantial improvement over the v5 runner. The request envelope,
endpoint snapshot binding, immutable raw-envelope abstraction, draw identities, manifest
helpers, full-grid arithmetic, completeness checks, and most provider/reasoning audits are
represented clearly. The focused offline test suites pass.

However, the executable canary does not consistently use those hardened abstractions. A
persisted failed response is treated as a successful reuse, current-run spend is omitted
after restart, and some returned responses can escape accounting. Separately, the
full-grid cost projection tokenizes concatenated message content rather than the
chat-templated model input. The superseded v5 paid CLI also remains callable.

These are integration defects, not cosmetic concerns. They can produce a false-positive
capability result, understate cumulative spend, or authorize a run using an understated
projection. A green helper-level suite therefore does not establish a safe live runner.

## Findings

### R-C1 — persisted failures become successful reuse results

**Priority: P1**

In `src/alignment/q2_v7/canary.py:215-218`, `run_one` checks only
`store.has(draw.draw_id)`. If any raw envelope exists, it constructs a new
`CanaryResult` with:

- `http_status=200`;
- `audit_ok=True`;
- `reasoning_ok=True`;
- `reused=True`.

It does not load the persisted envelope, inspect its original HTTP status, verify its
request hash, or require a linked successful validation record. `main` then accepts every
reused result through:

```python
all(r.passed or r.reused for r in results)
```

This is reproducible with the committed artifacts. The stored DeepSeek canary envelope is
HTTP 404 with no returned cost, but `run_one` reports it as an accepted HTTP-200 reuse:

```text
deepseek/deepseek-v4-pro reused=True
reported_status=200 audit_ok=True reasoning_ok=True accepted_by_main=True
```

Required behavior:

1. Load the immutable envelope rather than testing existence alone.
2. Verify that its request hash and draw identity match the recomputed request.
3. Reuse its real HTTP status, cost, audit evidence, and reasoning evidence.
4. Require a linked, hash-bound successful derived validation record before treating it
   as a passing reuse.
5. Keep failed persisted calls failed until an explicitly new draw identity is authorized;
   never convert failure into success merely because a file exists.

### R-C2 — current v7 spend disappears on restart

**Priority: P1**

In `src/alignment/q2_v7/canary.py:291-298`, the current run store is opened, but the
ledger is initialized only from the older directories in `PRIOR_RECORD_DIRS`:

```python
store = L.EnvelopeStore(run_dir)
rec = L.reconcile_prior_spend(...)
ledger = L.V7Ledger(reconciliation=rec)
```

`reconstruct_ledger` is never called for `run_dir`. On restart, `run_one` skips existing
draws while their costs remain absent from `ledger.run_usd`.

The committed v7 canary directory currently contains:

```text
qwen/qwen3.5-397b-a17b  HTTP 200  cost $0.00002301
deepseek/deepseek-v4-pro HTTP 404 cost missing
```

The main-style fresh ledger reports `$0` of v7 run spend instead of `$0.00002301`, and it
does not fail closed on the unreconciled 404 record.

Required behavior:

1. Create or reload the manifest that binds the authorized canary draw identities.
2. Call `reconstruct_ledger` on the current `EnvelopeStore` before the first budget check.
3. Include every prior successful, invalid-but-paid, diagnostic, and canary response under
   the single `$8.50` stop.
4. Stop for reconciliation when a persisted record has a missing cost; do not skip it and
   continue with an understated total.

### R-C3 — returned responses can escape ledger booking

**Priority: P1**

In `src/alignment/q2_v7/canary.py:230-250`, the canary persists a raw envelope and then:

- returns immediately for every non-200 response, without booking any returned cost;
- calls `reject_cache_hit` before `ledger.book_envelope`, so a cache rejection prevents
  booking as well.

Some provider/error responses may incur prompt cost. Whether a response is valid for the
capability gate is separate from whether it must be included in cumulative spend.

The general ledger module already provides the correct ordering in `record_response`:
persist first, book returned cost second, validate separately. The live canary bypasses
that path.

Required behavior:

1. Route every returned HTTP response through `record_response` immediately.
2. Book any finite returned cost regardless of HTTP status, provider audit, parsing,
   reasoning audit, or cache exclusion.
3. Persist and then fail closed when cost is missing, retaining the generation ID for
   reconciliation.
4. Write a separate derived record describing why the response is excluded.
5. Add live-orchestration tests for non-200-with-cost, cache-hit-with-cost,
   missing-cost, invalid-provider, and successful responses.

### R-C4 — full-grid projection omits chat-template tokens

**Priority: P1**

In `src/alignment/q2_v7/gate.py:196-203`, `render_request` defines the tokenizer input as:

```python
payload_text = "\n".join(str(m.get("content", "")) for m in messages)
```

This omits message roles, chat-template delimiters, generation markers, and other special
tokens. It therefore is not the exact serialized model input described by the frozen C2
method. The endpoint snapshot pins tokenizer configuration and chat-template files, but
the implementation never applies them.

The fixed 10% margin is intended to cover tokenizer/provider drift; it is not evidence
that omitted prompt-serialization overhead is bounded. The error is especially relevant
for shorter prompts, where fixed template overhead can exceed 10%.

Required behavior:

1. Pass the structured messages to a pinned-tokenizer adapter.
2. Apply the exact pinned chat template, including roles, special tokens, and generation
   prompt behavior matching the served checkpoint.
3. Count the resulting token IDs, then apply the frozen 10% margin.
4. Record the tokenizer repository, revision, file hashes, template mode, and raw/projected
   count for every request.
5. Add frozen expected-count tests using the actual pinned tokenizer assets, not only an
   injected word-count function.

### R-C5 — the superseded v5 paid runner remains callable

**Priority: P1**

`src/alignment/q2_hosted.py:936-976` still exposes a paid CLI for the superseded v5
four-model, logprob-based design:

```text
python -m alignment.q2_hosted --stage smoke ...
```

With a generic paid-spend acknowledgement and no `--model`, it can make 48 smoke calls for
each of four old panel models. That path does not use the v7 reasoning-off envelope,
committed endpoint snapshot, cache prohibition, v7 manifest, or unified ledger.

Required behavior:

1. Disable paid execution from the superseded entry point, or redirect it to an explicit
   archived/legacy read-only mode.
2. Make the reviewed v7 command the only live Stage-2 entry point.
3. Add a no-network test proving the old CLI refuses all paid stages.
4. Update module and operator documentation so no current instruction points at the v5
   runner.

### R-C6 — canary success does not validate the returned answer

**Priority: P2**

`CanaryResult.passed` in `src/alignment/q2_v7/canary.py:196-199` requires HTTP 200,
provider audit, reasoning audit, and returned cost, but it does not validate
`message.content`. `run_one` extracts the content only for display.

An empty response, prose response, or out-of-range digit can therefore pass despite the
canary claiming to verify wire format. The promotion audit in `gate.py` already requires a
parsed leading digit, so the live canary is weaker than the pure gate it is meant to feed.

Required behavior:

1. Parse the response with the frozen anchored option parser.
2. Require a valid digit in `[1,4]`; because this synthetic prompt explicitly requests
   `2`, preferably require exactly `2`.
3. Include parsing status in the derived validation record and `CanaryResult.passed`.
4. Test empty content, prose, punctuation variants, out-of-range digits, and the expected
   exact response.

## Implementation-scope gap

The repository does not yet contain an integrated v7 study runner. The v7 package provides:

- a live synthetic canary;
- pure request, identity, ledger, promotion, projection, completeness, and bootstrap
  helpers.

It does not provide one executable path that performs the full sequence:

1. render the 528 exact requests;
2. load and verify the pinned tokenizers;
3. create the 13,200-draw manifest;
4. reconcile prior and current spend;
5. execute and persist the endpoint capability walk;
6. write the full-grid projection artifact;
7. reuse the first 240 smoke draws;
8. execute the remaining draws with restart and hard-stop enforcement;
9. write linked derived validation records;
10. run completeness and headline extraction from raw envelopes.

This is acceptable for a canary-only milestone if stated explicitly. It is not a complete
Stage-2 runner and must not be presented as study-ready.

## Test record

Commands run from the repository root under the active Python environment:

```text
python -m pytest -q \
  tests/test_q2_v7_envelope.py \
  tests/test_q2_v7_identity.py \
  tests/test_q2_v7_ledger.py \
  tests/test_q2_v7_gate.py \
  tests/test_q2_v7_conformance.py

484 passed, 2 skipped in 13.20s
```

```text
python -m pytest -q tests/test_q2_hosted.py

51 passed in 1.62s
```

These results certify the tested helpers. They do not cover
`alignment.q2_v7.canary.run_one`, its restart behavior, or the live orchestration defects
above.

## Re-test gate

Before any further paid Stage-2 call:

- [ ] R-C1: successful reuse requires loading and revalidating the persisted result.
- [ ] R-C2: current-run spend is reconstructed before the first budget check.
- [ ] R-C3: every returned response is persisted and accounted before validation.
- [ ] R-C4: the full-grid projection uses the pinned chat-template serialization.
- [ ] R-C5: the superseded v5 paid CLI is disabled.
- [ ] R-C6: canary content must pass the anchored parser.
- [ ] Live-canary orchestration has direct no-network tests, including the committed
      HTTP-404 restart case.
- [ ] Focused v7 and legacy regression suites pass.
- [ ] The review is repeated against the exact revision proposed for the next paid call.

Until those conditions hold, the correct status is:

**offline v7.2 scaffolding passes its focused tests; live execution gate not passed.**
