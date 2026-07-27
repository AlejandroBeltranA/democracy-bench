# Stage-2 hosted runner review — execution gate not yet passed

Reviewer: Sol  
Date: 2026-07-22  
Reviewed commits:

- `8ed6a64` — Stage-2 v5 freeze, A/F/S unanimous
- `80399d7` — hosted runner and no-network readiness suite

## Verdict

**OBJECT to any paid call, including the synthetic canary, pending R-E1--R-E7 below.**

The implementation is a strong scaffold: the frozen panel, exact provider slugs, eleven
cells, twelve probes, four Williams orders, role placements, shared inference settings,
48-call smoke enumeration, 528-call matrix enumeration, sampling counts, top-k coverage
rule, and smoke/matrix request reuse are represented correctly. The focused readiness
suite passes 42/42.

However, several tests certify behavior that contradicts the v5 execution gate. In the
current implementation, a paid response can be discarded without being stored or charged
to the ledger; process restart resets cumulative spend; the opted-in OpenRouter routing
metadata is not parsed; and the purported raw artifacts omit the raw requests and
responses. A green focused suite therefore does not yet establish safe paid execution.

No Stage-2 canary, smoke, manifest, or gate artifact was found under `out/` during this
review. That is consistent with no run having been made through this runner, although it
cannot prove that no unrelated API request occurred elsewhere.

## Required revisions

### R-E1. Persist and account for every returned paid response before validation

In `execute_call`, transport returns at `src/alignment/q2_hosted.py:729`, but provider
validation and scoring occur before persistence and ledger booking. A provider mismatch,
missing logprobs, malformed response, or other scoring failure can therefore discard an
already-paid response, book zero cost, and leave the request eligible to be purchased
again.

Required behavior:

1. Immediately after a successful HTTP response, persist an immutable raw envelope
   containing the complete request body, relevant request headers with the credential
   redacted, complete response body, relevant response headers, generation ID, timestamp,
   request key, bucket, and returned usage/cost.
2. Book the returned cost regardless of whether routing, coverage, parsing, or scoring
   later passes.
3. Add validation and scoring status to a separate derived record, or append it through a
   second immutable artifact linked to the raw record.
4. Exclude invalid calls from promotion and estimands, but never erase their audit or cost
   history.

The current test `test_provider_mismatch_blocks_headline_data` explicitly requires no raw
record and no booked cost after a returned mismatched response. Replace that assertion:
the call must be excluded from headline data **and** retained and charged in the audit
ledger.

OpenRouter notes that some no-content/provider-failure cases may still incur prompt cost:
<https://openrouter.ai/docs/api/reference/errors-and-debugging>.

### R-E2. Make missing cost fail closed and support generation-record reconciliation

`response_cost` currently maps an absent `usage.cost`/`usage.total_cost` to `0.0`. That
silently turns an accounting failure into a free call.

Required behavior:

- A successful non-cached response without a finite, non-negative returned cost fails the
  accounting gate; it must not be treated as zero.
- Persist the response ID and `X-Generation-Id` so cost can be reconciled through the
  OpenRouter generation endpoint when necessary.
- Explicitly identify and test legitimate cache-hit zero-cost responses if caching can
  occur. Prefer sending `X-OpenRouter-Cache: false` so sampling draws cannot inherit an
  account/preset cache configuration.
- After recording actual cost, assert component, pre-top-up, and global totals. The
  pre-flight estimate prevents starting a call near a cap; the post-call assertion detects
  an underestimated call and halts before the next request.

OpenRouter documents automatic usage information and generation-ID reconciliation here:
<https://openrouter.ai/docs/cookbook/administration/usage-accounting>.

### R-E3. Reconstruct cumulative spend on restart

`main` creates a new zeroed `Ledger` for every invocation. When `execute_call` finds a
stored record, it returns it without restoring that cost into the new ledger. Canary and
smoke invocations, model-by-model invocations, or an interrupted/restarted smoke can
therefore reset the $3 pre-top-up ceiling and the component totals.

Required behavior:

- Reconstruct the ledger from every immutable raw record in the run directory before the
  first budget check.
- Store the original bucket and actual cost in every record.
- Verify that each record belongs to the frozen run manifest and appears only once.
- Treat canary and study spend separately while still enforcing their shared $3 pre-top-up
  ceiling.
- Add restart tests after one successful call, after one invalid-but-paid response, between
  models, between canary and smoke commands, and immediately below every cap.

The current restart test only proves that a completed request is not resent. Its assertion
that the restarted ledger should remain at zero is incorrect for cumulative cap
enforcement.

### R-E4. Parse and require the documented routing metadata

The request correctly sends `X-OpenRouter-Metadata: enabled`, but `resolved_provider`
looks for `response["metadata"]`. OpenRouter returns the opted-in routing object under
`response["openrouter_metadata"]`. In addition, `provider_matches` currently treats
missing routing metadata as success and reduces exact provider slugs to a base name.

Required behavior:

- Parse `openrouter_metadata.requested`, `strategy`, `attempt`,
  `endpoints.available[]`, `attempts[]`, and the selected endpoint.
- Require exactly one selected endpoint on a successful study response.
- Require the requested and returned model IDs to match the frozen model.
- Require the selected provider to match the frozen endpoint. Preserve both its display
  name and exact routing information; do not allow a missing value to pass.
- Confirm that fallback behavior did not occur and surface unexpected router/pipeline
  transformations.
- Fail the canary and smoke when this audit evidence is absent. Do not promote a model on
  `None` metadata.

The current tests explicitly assert `provider_matches("openai", None) is True`; reverse
that expectation. OpenRouter's response schema is documented here:
<https://openrouter.ai/docs/guides/features/router-metadata>.

### R-E5. Store genuinely raw, reproducible artifacts

The current `RawStore` record contains derived display probabilities, coverage, usage,
and identifiers, but not the full request, full response, response headers, top-logprob
entries, generation ID, or `openrouter_metadata`. This does not satisfy the v5 requirement
to persist complete requests and responses.

Required behavior:

- Use one immutable raw envelope per attempted request that received a response.
- Redact only secrets; do not discard message roles/content, response logprobs, router
  metadata, usage, or identifiers.
- Keep the outcome-blinded gate view separate from raw artifacts.
- Generate all scored/aggregated artifacts deterministically from the raw envelopes, with
  a fail-loud extractor test.

### R-E6. Make the manifest bind exact requests and permit exact restart

The current manifest hashes call coordinates only. It does not bind the rendered messages,
item content, request parameters, provider block, design hash, item-bank hash, or code
revision. `write_manifest` also refuses any existing file, so a process that crashes after
manifest creation cannot resume.

Required behavior:

- Include the canonical request SHA-256 for every call, plus hashes of the frozen design,
  relevant item-bank inputs, inherited payload/guard source, and runner revision.
- For sampling, include every draw identity while retaining its identical request body.
- On restart, recompute the candidate manifest. Reuse an existing manifest only when it is
  byte-identical or hash-identical; reject any mismatch.
- Add tests proving that changing one prompt character, role, provider slug, item label,
  parameter, or call coordinate changes the manifest hash.

### R-E7. Enforce complete inputs before any headline aggregation

`aggregate_logprob_mass` averages whichever orders happen to be present. It does not
require all four Williams orders for every cell/probe. A partial set could therefore
produce protective mass and, if partial coverage were sufficiently broad, flow into an
estimand.

Required behavior:

- Require exactly four unique orders per cell/probe.
- Require exactly eleven cells and twelve probes for a promoted model before logprob
  headline extraction.
- Reject duplicate or unexpected orders/cells/probes.
- Require the declared sampling branch to contain exactly 9,600 or 13,200 records and
  apply an explicit valid-response rule before sampling estimates are emitted.
- Add an end-to-end incomplete-model test at the raw-record-to-estimand boundary, not only
  a direct `hosted_estimands` unit test with missing dictionary keys.

## Scope still to be built

The live CLI currently supports only `canary` and `smoke`. This is appropriate for a
pre-top-up milestone, but the following remain absent and must pass a separate review
before adding the $10 or running the hosted matrix:

- promoted-model matrix execution and exact reuse of smoke records;
- measured-smoke cost projection and deterministic model stop rule;
- cost-only selection of the eight- versus eleven-cell sampling branch;
- sampling execution, restart, parsing, coverage, and aggregation;
- fail-loud per-model artifact extraction and the eight frozen estimands;
- crack and materiality diagnostics inherited from Q1;
- a final audit report reconciling manifest calls, raw records, returned cost, key usage,
  promotion decisions, exclusions, and generated results.

## Re-test gate

Before the first paid synthetic canary:

- [ ] R-E1--R-E7 implemented.
- [ ] Tests that encoded zero-cost/no-record failure behavior replaced.
- [ ] No-network suite covers successful, invalid-but-paid, missing-cost, missing-metadata,
      wrong-model, restart, existing-manifest, cap-boundary, and full-response persistence
      cases.
- [ ] Focused Stage-2 suite passes.
- [ ] Broader non-MLX test suite passes in a Python version supported by `pyproject.toml`.
- [ ] Alex, Fable, and Sol concur that the implementation satisfies the frozen v5 gate.
- [ ] Only then run the minimal synthetic canary under the existing $3 ceiling.

## Test record from this review

- `pytest -q tests/test_q2_hosted.py`: **42 passed**.
- A repository-wide `pytest -q` attempt aborted during collection while importing the
  native MLX dependency from `tests/test_exact_local_scorer.py` under the active Python
  3.9 environment. This was not a Stage-2 assertion failure, but it means the full suite
  was not certified in this review. The project declares Python `>=3.10`, so the broader
  suite should be rerun in a supported environment.

