# Q2 Stage-2 v7.2 code review — live execution gate not passed

Reviewer: Codex  
Date: 2026-07-28  
Reviewed branch: `phase4-floor-guards`  
Current reviewed HEAD: `091b948` — *Close PS-1--PS-6 from the pre-smoke re-audit; frozen C2 serialization is now enforced*

Original review baseline: `4d0c5ac` — *Build hardened Q2 Stage-2 v7.2 runner; synthetic canary passes on Qwen3.5-397B*

Current implementation scope: cumulative Stage-2 code from `80399d7` through `091b948`

## Finalization re-review — `091b948`

### Verdict

**HOLD. Do not run smoke from this revision yet.**

Claude's PS-1--PS-6 changes are substantive and mostly correct. The re-review confirms
that the implementation now has:

- model-specific promotion plus panel-level funding authorization records;
- authorization and projection verification before transport construction;
- content-addressed, write-once projection evidence;
- exact pinned Qwen chat serialization;
- append-only persistence and accounting for every returned retry attempt;
- full-envelope canary-derived binding;
- exact decimal ledger arithmetic.

The focused suites exercised in this pass are green:

```text
tests/test_q2_v7_canary.py
tests/test_q2_v7_gate.py
tests/test_q2_v7_ledger.py
tests/test_q2_v7_study_run.py

260 passed in 265.93s
```

```text
tests/test_q2_v7_envelope.py
tests/test_q2_v7_identity.py
tests/test_q2_v7_conformance.py
tests/test_q2_v7_interlock.py
tests/test_q2_v7_study_render.py
tests/test_q2_v7_study_conformance.py

604 passed, 1 skipped in 13.20s
```

No network or paid call was made by this re-review.

Two issues remain. The first is a reproducible implementation defect. The second is the
explicit pre-outcome decision that Claude's own fix correctly surfaced rather than hiding.

### PS-7 — retries bypass the hard-stop check

**Priority: P1 — paid-execution blocker**

`execute_plan` checks `ledger.must_halt_before_next_call(...)` once before starting a
logical draw (`src/alignment/q2_v7/study_run.py:1973-1991`). `_send_draw` can then invoke
the wire sender up to five times through `execute_with_retries`, but its nested `send`
function does not repeat the ledger check (`study_run.py:1876-1898`).

This is not hypothetical. A no-network reproduction used:

- hard stop: `$0.0000006`;
- first attempt: paid HTTP 429 costing `$0.0000004`;
- retry: HTTP 200 costing `$0.0000004`;
- per-call worst case: `$0.0000004`.

Observed result:

```text
transport_calls=2
spent=0.0000008
hard_stop=0.0000006
overspent=True
halted=False
```

The first call is allowed. After it is booked, the second call must be refused because its
worst case would breach the stop. The current code sends it.

Required fix:

1. Pass the per-call worst-case amount into `_send_draw`.
2. Immediately before **every** `_post_once`, including retries, call the exact-money ledger
   pre-call gate.
3. If the retry would breach the stop, terminate the retry ladder without sending it and
   return/record a halted incomplete run with no headline.
4. Add the reproduction above as a no-network regression test.

Do not solve this by reserving five calls at the outer draw check: unused retries would
unnecessarily halt otherwise valid draws. The invariant is simply “check immediately
before every actual wire call.”

### PS-8 — DeepSeek cannot currently reach panel funding authorization

**Priority: P0 — explicit pre-smoke decision required**

The new C2 guard correctly rejects DeepSeek because its pinned repository revision contains
no chat template. `_stage_project` refuses any projection that did not use frozen exact
serialization (`src/alignment/q2_v7/study_run.py:2290-2307`).

At the same time, panel funding requires a promotion/exclusion authorization record for
every frozen panel model (`study_run.py:1517-1541`). The existing DeepSeek walk promoted
the primary endpoint, so it is not a capability exclusion. Without a valid DeepSeek
projection, its promotion cannot be authorized; without that record, the panel funding
record cannot be written; without panel funding, even Qwen smoke correctly refuses.

This is not a code nuance. The frozen method requires an input that the pinned DeepSeek
revision does not publish. Choose one pre-outcome resolution:

1. **Recommended:** adopt and pin an explicit DeepSeek chat template as a narrow signed
   amendment, with its source, exact bytes, SHA-256, rendering flags, and expected-count
   tests; or
2. approve a different sealed conservative DeepSeek length-calibration method as a signed
   amendment, with evidence that it upper-bounds the full 528-request grid.

Do not mark DeepSeek as a capability exclusion merely to get past the funding gate: its
endpoint walk passed, so that would misstate the evidence.

### Minimal path to smoke

There is no need for another broad rewrite:

- [ ] fix PS-7 and add its one regression test;
- [ ] record the narrow PS-8 pre-outcome amendment and implement its deterministic input;
- [ ] rerun `walk`/`project` in a fresh run directory as required by `091b948`;
- [ ] record both model promotion decisions and the panel funding decision;
- [ ] rerun the focused pre-smoke gate;
- [ ] review the exact clean commit and fresh artifacts.

After those checks pass, Qwen smoke can be authorized immediately. The extractor/CLI
integration noted later in this document remains a pre-**full-run** item, not a reason to
delay a valid outcome-blinded smoke.

## Pre-smoke re-audit — 2026-07-28

Reviewed state:

- branch: `phase4-floor-guards`;
- exact HEAD: `84a3fa8` — *Promote both models on their primary endpoints; pin
  tokenizers; project the full grid*;
- worktree before this review edit: clean;
- cumulative implementation: `4d0c5ac..84a3fa8`;
- source and focused-test hashes were captured before the final test run and compared
  afterward; they were byte-identical.

### Pre-smoke verdict

**OBJECT. Claude is not authorized to run either 240-draw smoke yet.**

The implementation-scope gap has narrowed substantially. There is now an executable
walk/project/smoke/full runner, deterministic study rendering, manifest binding, restart
reconstruction, per-draw validation, an outcome-blinding interlock module, extraction, and
extensive no-network coverage. Both synthetic endpoint walks promoted their primary
endpoints, and committed projection artifacts report that both complete models fit under
the unified stop.

That is not sufficient to start the smoke. The frozen staged-authorization record required
before smoke does not exist and is not enforced by the smoke entry point. The cost
projection still does not implement the frozen documented-tokenizer method, existing
projection files are trusted without integrity/binding checks, and one focused runner test
fails. Two persistence/integrity defects also remain from the earlier review.

No implementation fix was made as part of this audit.

### PS-1 — the required promotion/funding authorization is absent and smoke does not enforce it

**Priority: P0 — direct pre-smoke blocker**

The frozen design says that the smoke may run only after endpoint-promotion decisions and
the funding decision are recorded
(`paper/Q2_STAGE2_HOSTED_DESIGN.md:690-702`). The current run directory contains:

- two walk records;
- two full-grid projections;
- two model manifests;
- the two paid synthetic walk envelopes and their derived records.

It contains no `interlock/promotion_record.json` and no
`interlock/funding_record.json`.

The implementation provides write-once record helpers in
`src/alignment/q2_v7/interlock.py:279-334`, but the executable runner never calls them.
`STAGES` contains only `walk`, `project`, `smoke`, and `full`
(`src/alignment/q2_v7/study_run.py:71`). `_stage_smoke` proceeds directly from `_prepared`
to `run_smoke` (`study_run.py:1503-1512`) without checking either record.

There is also no sound two-model binding yet. The interlock uses one fixed promotion
filename per run directory, while this run has a distinct manifest per model. A single
write-once record cannot bind both model promotion decisions unless the schema is changed
to a panel-level decision or the records are made model-specific.

Required before smoke:

1. Define and implement an unambiguous two-model authorization record scheme.
2. Derive the promotion records from the immutable walk/projection evidence; do not rely on
   a manually transcribed endpoint tag or amount.
3. Record the funding decision, hard stop, reconciled prior spend, and available headroom,
   bound to the exact model manifest(s) and projection artifact hash(es).
4. Make `_stage_smoke` fail closed before creating a transport or sending a request unless
   the applicable promotion and authorized-funding records exist, validate, and match the
   selected model, endpoint, manifest, snapshot, and projection.
5. Add a no-network test proving that missing, refused, malformed, stale, cross-model, and
   wrong-manifest records all produce zero transport calls.

### PS-2 — R-C4 remains open: projections use a fixed overhead, not the pinned chat serialization

**Priority: P1 — pre-smoke cost-gate blocker**

The frozen C2 method applies the official pinned tokenizer to the exact serialized
system+user messages for every request
(`paper/Q2_STAGE2_HOSTED_DESIGN.md:1122-1138`).

The implementation instead:

- concatenates message contents without roles or delimiters
  (`src/alignment/q2_v7/gate.py:252-266`);
- adds `12` tokens per message plus `8` generation-prompt tokens
  (`gate.py:240-249`);
- loads `tokenizer.json` directly and exposes only `count(text)`
  (`src/alignment/q2_v7/study_run.py:1392-1420`);
- calculates `tokenizer(payload_text) + fixed_overhead`
  (`gate.py:438-440`).

That is a new heuristic, not the frozen documented-tokenizer method. It happens to be
conservative for the committed Qwen assets: applying the pinned Qwen chat template to all
528 requests produced an exact count 18 tokens lower than the heuristic for every request
(for one representative request: exact `161`, bare content `147`, heuristic `179`).
Conservatism does not make the result the preregistered method. For DeepSeek, the committed
tokenizer/config assets expose no chat template at all, so the claimed exact serialized
input cannot be independently reconstructed from the pinned files.

Required before smoke:

1. Apply the exact served chat serialization for each endpoint and count the resulting
   token IDs, including roles, special tokens, and the generation prompt.
2. Pin every template/config input needed to reproduce that serialization for both models.
3. If exact DeepSeek serialization cannot be pinned, obtain a fresh pre-outcome design
   amendment approving a specified conservative method; do not silently substitute a
   heuristic for frozen C2.
4. Add fixed expected-count tests using the committed real tokenizer/template assets.
5. Regenerate and re-review both projection artifacts after the method is corrected.

### PS-3 — projection artifacts are neither content-verified nor bound to later paid stages

**Priority: P1 — pre-smoke cost-gate blocker**

`write_projection` returns an existing same-name artifact without verifying that its bytes
equal the newly computed projection (`src/alignment/q2_v7/study_run.py:662-669`).
`read_projection` is an unchecked `json.loads` (`study_run.py:672-673`). `_prepared` then
trusts that file to price every smoke/full call (`study_run.py:1486-1500`).

The loader does not validate the artifact's model, endpoint, snapshot, prices, request-set
digest, total, or relationship to the manifest. The manifest does not bind the projection
hash. Consequently, fixing C2 and rerunning `project` in the same directory would silently
retain the old heuristic artifact, and a stale or edited artifact could authorize paid
calls using different prices or token counts.

Required before smoke:

1. Make projection writes immutable by content: identical bytes may resume; different bytes
   at the same logical identity must raise.
2. Canonically hash the artifact and bind that digest into the pre-smoke authorization.
3. On every smoke/full invocation, validate model, endpoint, snapshot, tokenizer identity,
   all 528 request hashes, row uniqueness, prices, arithmetic totals, and manifest binding
   before constructing the transport.
4. Recreate the corrected artifacts under a new content-addressed or otherwise unambiguous
   identity; do not reuse the committed heuristic files.

### PS-4 — a paid non-terminal retry response is not persisted or booked

**Priority: P1**

`_send_draw` collects retry responses in memory and persists only the terminal response
(`src/alignment/q2_v7/study_run.py:1061-1100`). If a non-terminal response returns a
positive cost, the function raises at lines `1085-1094` before persisting that response and
before persisting the terminal response.

Failing closed is preferable to continuing with understated spend, but it does not satisfy
R-E1/R-C3: every returned paid response must become durable evidence and count against the
unified stop. A process exit after this exception leaves no record from which the cost can
be reconstructed.

Required before smoke:

1. Give every wire attempt an immutable attempt identity separate from the logical
   manifest-bound sampling draw, or persist attempts in a dedicated append-only attempt
   store linked to that draw.
2. Persist and book every returned attempt before deciding whether to retry or validate.
3. Preserve exactly one terminal sampling outcome for completeness/estimands.
4. Add tests for a paid 429/5xx followed by success, paid exhaustion, missing-cost
   non-terminal responses, and restart after each case.

### PS-5 — canary derived records are bound to the wrong raw hash

**Priority: P1**

The canary writes:

```python
raw_sha256 = canonical_sha256(env.response_body or {})
```

at `src/alignment/q2_v7/canary.py:291-297`. The rest of the v7 pipeline binds a derived
record to `RawEnvelope.content_sha256()`, which hashes the complete immutable envelope.
Study replay and extraction reject mismatched bindings.

Canary replay also re-evaluates the raw response without requiring or verifying its linked
successful derived record. R-C1 is therefore improved but not fully closed as originally
specified.

Required before smoke:

1. Write `env.content_sha256()` into canary derived records.
2. On reuse, require the derived record, verify its raw hash, and preserve a persisted
   invalid verdict.
3. Add a test that round-trips a real canary envelope/derived pair through the same binding
   check used by study replay.

### PS-6 — the focused runner suite is red at the hard-stop boundary

**Priority: P2, but the no-network gate must be green before smoke**

`tests/test_q2_v7_study_run.py:756-766` fails because ten returned costs of `0.0001`
sum to `0.0010000000000000002`; `ledger.total_spent_usd` therefore reports a value greater
than its `0.001` hard stop. The runner halts and emits no headline, but the ledger violates
the explicit tested invariant.

Required before smoke:

1. Represent money with exact decimal or integer units throughout booking, comparison, and
   reporting, or define one canonical quantization rule at ingestion.
2. Do not fix this only by weakening the assertion; prove that pre-call checks, reconstructed
   totals, projection totals, remaining headroom, and reports share the same exact rule.
3. Rerun the complete focused gate with zero failures.

### Remaining integration work before the full run

This does not independently block an outcome-blinded smoke once PS-1 through PS-6 are
closed, but it still blocks describing the implementation as end-to-end study-ready:

- the CLI has no extraction/artifact stage (`study_run.py:71`, `1549-1554`);
- the runner writes `manifest_<model>.json` in the root run directory
  (`study_run.py:785-796`), while default extraction searches for `manifest.json` inside
  the envelope-store directory (`study_extract.py:79-126`);
- the runner does not connect a completed full run to `extract_model` and
  `write_artifact`.

Close and test that integration before authorizing the full study, even if it is deliberately
kept separate from the smoke gate.

### Disposition of the original R-C findings

- R-C1: **partially fixed**; raw replay is real, but canary derived binding/reuse remains open.
- R-C2: **fixed** for current canary, shared walk, and study-store reconstruction.
- R-C3: **fixed for canary and walk**; still open for non-terminal study retries (PS-4).
- R-C4: **not fixed**; the exact template method was replaced by a fixed-overhead heuristic.
- R-C5: **fixed**; the v5 paid CLI errors before constructing a live transport.
- R-C6: **fixed**; canary content must parse and equal the requested option.

### Re-test record for `84a3fa8`

Commands were run from the repository root under the active Python environment. No network
or paid study call was made by this audit.

```text
python -m pytest -q tests/test_q2_v7_study_run.py

1 failed, 60 passed in 106.39s
```

Failure:

```text
test_full_run_halts_before_a_call_that_would_breach_the_hard_stop
assert 0.0010000000000000002 <= 0.001
```

```text
python -m pytest -q \
  tests/test_q2_v7_envelope.py \
  tests/test_q2_v7_identity.py \
  tests/test_q2_v7_ledger.py \
  tests/test_q2_v7_gate.py \
  tests/test_q2_v7_conformance.py \
  tests/test_q2_v7_canary.py \
  tests/test_q2_v7_interlock.py \
  tests/test_q2_v7_study_render.py \
  tests/test_q2_v7_study_conformance.py

730 passed, 1 skipped in 16.04s
```

```text
python -m pytest -q tests/test_q2_v7_study_extract.py

65 passed in 615.99s
```

Total: **855 passed, 1 skipped, 1 failed**.

### Conditions for a new smoke authorization

- [ ] PS-1: valid per-model or panel-level promotion and authorized-funding records exist
      and `_stage_smoke` enforces them before any transport can send.
- [ ] PS-2: C2 uses the exact pinned serialization/tokenizer method, or an explicitly
      approved pre-outcome amendment replaces it.
- [ ] PS-3: corrected projection artifacts are content-verified and bound to the manifest
      and authorization records.
- [ ] PS-4: every paid retry attempt is durably persisted and booked.
- [ ] PS-5: canary derived records use the full envelope hash and are verified on reuse.
- [ ] PS-6: every focused Stage-2 test passes.
- [ ] The review is repeated against the exact clean commit proposed for smoke.

Until every box above is checked, there is **no authorization for Claude or any other
operator to run `study_run smoke`**.

## Original `4d0c5ac` review (historical)

### Verdict at the original baseline

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
