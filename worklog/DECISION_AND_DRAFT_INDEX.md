# Flagship paper decision and draft index

**As of:** 2026-07-27  
**Purpose:** Shareable map of the decisions, designs, reviews, prose drafts, and remaining
gates for the AAAI-27 AISI submission.

This file is an index, not a new experimental amendment. Where an older proposal conflicts
with a later signed result interpretation or reconciliation, the later document/section
listed here controls.

## Current position in one page

1. **Paper contribution.** Democracy Bench is an assurance/evaluation framework for testing
   whether a model can respond to changing public opinion while respecting an authored
   rights boundary. It is not a cross-country comparison, a deployment-impact study, or a
   ranking of model political attitudes.
2. **Geographic scope.** The headline public-opinion estimates are England-only,
   repeated-wave/repeated-cross-sectional BSA tracking. Scotland and Wales are present in
   the target infrastructure but are not pooled into the headline estimates. The floor
   probes and constitution are authored normative instruments, not BSA measurements.
3. **Q1 mechanism result.** The original evidence-over-instruction asymmetry is withdrawn.
   Data-only context lowers protective mass, but the tested direct instruction is much more
   harmful. A semantically irrelevant distribution also moves floors.
4. **Q1 replacement thesis.** The supported finding is contextual instability across
   payload semantics, explicit instruction, irrelevant distribution context, prompt
   placement, and model—not a uniquely democratic-evidence mechanism.
5. **Guard result.** Guard efficacy is model- and placement-dependent. Neither “system
   guards solve the problem” nor “every prompt guard fails” is supported. Routing is a
   deterministic exposure boundary and scope guarantee, not a demonstrated optimal or
   uniquely sufficient mitigation.
6. **Q1 status.** The design was frozen, the experiment completed, the outcome mapping was
   concurred, and the approved thesis rewrite was applied to the manuscript.
7. **Hosted follow-up purpose.** Stage 2 is a labelled post-Q1 transfer experiment. It
   tests within-model effects under controlled payload and guard placement; it is not part
   of the original Q1 preregistration.
8. **Current proposed Stage-2 panel.** Use current frontier open-weight instruct systems as
   plausible sovereign-AI adaptation starting checkpoints: Qwen3.5-397B-A17B as primary
   and DeepSeek-V4-Pro as an independent replication. Use the complete 11-cell, 12-probe,
   four-order, S=100-per-cell sampling design on each promoted model.
9. **Sovereign-AI claim boundary.** Stage 2 may characterize the **pre-adaptation assurance
   profile** of a starting checkpoint. It may not claim that contextual instability is
   invariant under fine-tuning or necessarily inherited by a downstream derivative. Every
   derivative requires re-evaluation.
10. **Execution status.** V7.2 has A/F/S approval and its endpoint/tokenizer snapshot is
    bound, but it is not operative until the design and snapshot land in the freeze commit.
    The hardened runner and its no-network gate remain prerequisites. After the freeze and
    runner gate, only the minimal synthetic canary is authorized; later stages retain their
    separate interlocks.

## Authoritative reading order

| Order | Document | What it controls | Current status |
|---:|---|---|---|
| 1 | [PROTOCOL_CONSENSUS.md](PROTOCOL_CONSENSUS.md) | Joint triage, verified corrections, experiment priority, terminology, and limitations | Consensus record; later Q1/Q2 documents supply results and amendments |
| 2 | [Q1_PRIORITY0_DESIGN.md](../paper/Q1_PRIORITY0_DESIGN.md) | Frozen local channel-decomposition design, prompts, estimands, orders, and decision rules | **Frozen and completed** |
| 3 | [Q1_RESULTS_CONSENSUS.md](Q1_RESULTS_CONSENSUS.md) | Authoritative outcome-table mapping and permitted interpretation | **Sol concurred; controls Q1 claims** |
| 4 | [Q1_REWRITE_DRAFT.md](Q1_REWRITE_DRAFT.md) | Approved §5.5, §6, abstract, and consistency rewrite with review trail | **Final vote AGREE; applied to manuscript** |
| 5 | [democracy_bench.tex](democracy_bench.tex) | Current paper prose | Working submission manuscript |
| 6 | [Q2_STAGE2_HOSTED_DESIGN.md](Q2_STAGE2_HOSTED_DESIGN.md#v72-closure--c1--c4-incorporated--endpoint-snapshot-created-and-bound-fable-2026-07-27-sol-verified) | Frozen 11-cell hosted estimands, historical v5/v6 trail, and current v7.2 amendment | **V7.2 A/F/S approved; bound snapshot verified; pending freeze commit and runner gate** |
| 7 | [Q2_STAGE2_RUNNER_REVIEW.md](../paper/Q2_STAGE2_RUNNER_REVIEW.md) | Audit and implementation requirements R-E1–R-E7 | **Execution gate failed; paid calls objected to** |
| 8 | [Q2_STAGE2_FRONTIER_DECISION.md](Q2_STAGE2_FRONTIER_DECISION.md#alex-reconciliation-with-solcodex-review-2026-07-23) | Current sovereign-AI/open-weight direction and reconciled claim boundary | **A/F/S concur; v7.2 operationalizes the direction; execution gate remains open** |

For the frontier decision memo, read the top **CURRENT STATUS** box and the final
**Alex reconciliation with Sol/Codex review** section first. The earlier GPT-5.4 proposal,
four-model sovereign panel, logprob proposal, and “cannot paint over” language are retained
only as an audit trail and are superseded where the reconciliation says so.

## Decision ledger

### Scientific and reporting decisions

| Decision | Disposition | Source |
|---|---|---|
| Democracy research here need not be comparative across countries | **Accepted** | [Protocol, writing correction 10](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Describe the opinion design as repeated-wave or repeated-cross-sectional, not a respondent panel | **Accepted** | [Protocol, surviving limitations](PROTOCOL_CONSENSUS.md#limitations-that-survive-every-outcome-for-the-limitations-section-pre-agreed) |
| Label headline targets and tracking as England public opinion | **Accepted** | [Protocol, writing correction 10](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Treat BSA attitudes and authored rights floors as distinct sources/constructs | **Accepted** | [Protocol, writing correction 10](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Evidence-only conditioning is uniquely dominant over instruction | **Rejected by Q1** | [Q1 outcome mapping](Q1_RESULTS_CONSENSUS.md#outcome-table-mapping) |
| Placebo movement means semantic relevance is unnecessary for movement | **Accepted, bounded** | [Q1 required interpretation](Q1_RESULTS_CONSENSUS.md#required-manuscript-interpretation) |
| Identify the placebo mechanism specifically as anchoring | **Not identified**; anchoring versus imitation remains open | [Q1 rewrite](Q1_REWRITE_DRAFT.md) |
| Claim universal prompt-guard failure | **Rejected** | [Q1 outcome mapping](Q1_RESULTS_CONSENSUS.md#outcome-table-mapping) |
| Claim privileged system-role recovery | **Rejected without a direct matched contrast** | [Q1 required interpretation](Q1_RESULTS_CONSENSUS.md#required-manuscript-interpretation) |
| Describe guard efficacy as model- and placement-dependent | **Accepted** | [Q1 required interpretation](Q1_RESULTS_CONSENSUS.md#required-manuscript-interpretation) |
| Use 0.50 as a natural ground-truth threshold | **Rejected** | [Protocol, writing correction 4](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Use 0.50 as a disclosed convention, with margins primary and counts secondary | **Accepted** | [Protocol, writing correction 4](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Use “ground truth” for normative item labels | **Rejected**; use “benchmark reference labels” | [Protocol, writing correction 6](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Present coding as blinded or multi-coder | **Rejected as factually incorrect** | [Protocol, writing correction 1](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Substitute LLM judges for unavailable independent human coders | **Rejected** | [Protocol, Q6](PROTOCOL_CONSENSUS.md#q6-independent-second-coder-on-a-codesheet-subset-sol-item-1--infeasible-without-a-human) |
| Scope the LoRA result to the tested rank-8/500-iteration recipe | **Accepted** | [Protocol, writing correction 2](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Use a naive pooled 51/60 model-item sign test | **Rejected** | [Protocol, writing correction 5](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Present routing as a static allowlist/exposure boundary | **Accepted** | [Protocol, writing correction 7](PROTOCOL_CONSENSUS.md#writing-corrections-consensus-already-no-votes-needed--all-verified) |
| Present routing as a learned optimum, the only mitigation, or a complete governance system | **Rejected** | [Q1 rewrite](Q1_REWRITE_DRAFT.md) |

### Q1 decisions

| Decision | Disposition | Source |
|---|---|---|
| Separate data-only, instruction-only, combined, placebo, and no-payload conditions | **Frozen and run** | [Q1 factors](Q1_PRIORITY0_DESIGN.md#factors) |
| Cross payloads with no guard, user-before, user-after, and system guard as specified | **Frozen and run** | [Q1 factors](Q1_PRIORITY0_DESIGN.md#factors) |
| Use four first-order-balanced option orders | **Frozen and run** | [Q1 option orders](Q1_PRIORITY0_DESIGN.md#option-orders) |
| Use exact summed option-event probabilities with coverage records | **Frozen and run** | [Q1 measurement](Q1_PRIORITY0_DESIGN.md#measurement-r1-incorporated-summed-exact-estimator) |
| Preserve and report the failed original mechanism prediction | **Accepted** | [Q1 outcome mapping](Q1_RESULTS_CONSENSUS.md#outcome-table-mapping) |
| Apply a thesis-level rewrite rather than add a caveat around the old claim | **Accepted and applied** | [Q1 rewrite](Q1_REWRITE_DRAFT.md) |

### Stage-2 decisions

| Decision | Disposition | Source |
|---|---|---|
| Label Stage 2 as a post-Q1 hosted follow-up | **Frozen** | [Hosted design status](../paper/Q2_STAGE2_HOSTED_DESIGN.md) |
| Preserve the complete 11-cell design and eight within-model estimands | **Accepted** | [Hosted cells](Q2_STAGE2_HOSTED_DESIGN.md#cells-per-model-11-cell-minimum-frozen-per-r-h1) |
| Use sampling as the uniform headline estimator | **Accepted direction**; must be incorporated into v7 | [Frontier reconciliation, Instrument](Q2_STAGE2_FRONTIER_DECISION.md#instrument) |
| Use endpoint-specific logprobs as the uniform headline | **Rejected** | [Frontier reconciliation, Instrument](Q2_STAGE2_FRONTIER_DECISION.md#instrument) |
| Run GPT-5.4 as the primary frontier witness | **Superseded** | [Frontier memo current status](../paper/Q2_STAGE2_FRONTIER_DECISION.md) |
| Run a broad four-model cheap/open-weight panel | **Superseded** | [Frontier reconciliation, Panel](Q2_STAGE2_FRONTIER_DECISION.md#panel--two-models-sampling-only) |
| Run Qwen3.5-397B-A17B primary plus DeepSeek-V4-Pro replication | **Current proposed panel** | [Frontier reconciliation, Panel](Q2_STAGE2_FRONTIER_DECISION.md#panel--two-models-sampling-only) |
| Run all 11 cells, 12 probes, four orders, 25 draws/order (S=100), per model | **Accepted in principle, conditional on gates and budget** | [Frontier final position](Q2_STAGE2_FRONTIER_DECISION.md#final-sol-position-on-framing) |
| Motivate open weights as plausible UK sovereign-AI adaptation starting checkpoints | **Accepted** | [UK policy basis](Q2_STAGE2_FRONTIER_DECISION.md#sol-second-addendum-uk-sovereign-ai-policy-basis-2026-07-23) |
| Call the tested instruct systems “raw base models” | **Rejected** | [Correct claim boundary](Q2_STAGE2_FRONTIER_DECISION.md#correct-claim-boundary) |
| Claim that the steering profile necessarily survives downstream fine-tuning | **Rejected unless tested on a matched derivative** | [Correct claim boundary](Q2_STAGE2_FRONTIER_DECISION.md#correct-claim-boundary) |
| Characterize the checkpoint’s pre-adaptation profile as an initial assurance burden | **Accepted** | [Frontier reconciliation, Framing](Q2_STAGE2_FRONTIER_DECISION.md#framing--adopt-the-bounded-pre-adaptation-boundary-drop-inheritanceinvariance) |
| Continue using the standalone open-weight logprob canary script for paid calls | **Rejected/retired** | [Frontier reconciliation, Concessions](Q2_STAGE2_FRONTIER_DECISION.md#concessions-s-sov4s-sov6-accepted) |
| Make another paid call before the hardened execution gate passes | **Rejected** | [Runner verdict](Q2_STAGE2_RUNNER_REVIEW.md#verdict) |

## Draft and manuscript map

### Applied or controlling prose

- [democracy_bench.tex](democracy_bench.tex) — current manuscript. The Q1 thesis rewrite
  was applied in commit `14cffeb`, followed by consistency edits.
- [Q1_REWRITE_DRAFT.md](Q1_REWRITE_DRAFT.md) — co-editing record for the applied §5.5,
  §6, abstract, and eight consistency edits. Keep it as the rationale/audit trail; do not
  paste it over the manuscript again.
- [Q1_RESULTS_CONSENSUS.md](Q1_RESULTS_CONSENSUS.md) — controlling claim-to-result map
  if manuscript language and an older results summary diverge.

### Designs and decision drafts

- [FLAGSHIP_AIRTIGHT_PRIORITY_PLAN.md](../paper/FLAGSHIP_AIRTIGHT_PRIORITY_PLAN.md) — initial
  high-level priority plan that replaced “add more model names” with mechanism
  identification.
- [PRE_SUBMISSION_REVIEW_PLAN.md](PRE_SUBMISSION_REVIEW_PLAN.md) — original adversarial
  review and X1–X7 menu. Its experiment triage is historical where superseded by the joint
  protocol and Q1 result.
- [PROTOCOL_CONSENSUS.md](PROTOCOL_CONSENSUS.md) — three-way protocol and writing
  corrections.
- [Q1_PRIORITY0_DESIGN.md](../paper/Q1_PRIORITY0_DESIGN.md) — frozen Q1 design.
- [Q2_STAGE2_HOSTED_DESIGN.md](../paper/Q2_STAGE2_HOSTED_DESIGN.md) — hosted v5/v6 design history
  plus the A/F/S-approved v7.2 amendment. Its snapshot is bound and verified; the freeze
  commit and hardened runner gate remain before any call.
- [Q2_STAGE2_FRONTIER_DECISION.md](../paper/Q2_STAGE2_FRONTIER_DECISION.md) — GPT-5.4 proposal,
  capability review, open-weight redirection, sovereign-AI debate, and final
  reconciliation. Historical text is intentionally retained, so use its final
  reconciliation rather than isolated earlier paragraphs.
- [Q2_STAGE2_RUNNER_REVIEW.md](../paper/Q2_STAGE2_RUNNER_REVIEW.md) — implementation review and
  hard execution blockers.

### Evidence maps and artifacts

- [Q1 local results, 3B](../out/q1_channel_3b.json) and
  [Q1 local results, 8B](../out/q1_channel_8b.json) — frozen Q1 primary artifacts.
- [Q1 secondary extract](../out/q1_secondary_extract.json) — hash-pinned secondary values
  used by the approved rewrite.
- [GPT-5.4 capability probes](../out/q2_stage2_canary/gpt54_probe/) — historical
  capability evidence; GPT-5.4 is no longer the proposed primary.
- [Open-weight logprob diagnostics](../out/q2_stage2_canary/openweight_logprob/) and
  [clean re-probe](../out/q2_stage2_canary/openweight_logprob_reprobe/) — diagnostic
  evidence supporting sampling; neither directory qualifies an endpoint for the study.
- [PAPER_RESULTS.md](../docs/PAPER_RESULTS.md) — useful claim-to-artifact map for the
  pre-Q1 empirical arc, but **not controlling for Q1**. It still contains stale pre-Q1
  statements (including “blinded” coding and the old evidence-channel narrative), so Q1
  consensus and the current manuscript override it until it is regenerated.
- [AAAI_SUBMISSION_READINESS_REVIEW.md](AAAI_SUBMISSION_READINESS_REVIEW.md) —
  pre-Q1 submission audit. Its supplement-packaging warnings remain useful; its scientific
  contribution assessment predates Q1 and must not override the Q1 reframing.

## Superseded positions that must not return to the paper

- Evidence-in-context is uniquely stronger than a direct instruction.
- A semantically irrelevant placebo leaves floors unchanged.
- The combined payload defeats every prompt guard.
- System-role placement is generally superior to matched user placement.
- Routing is the only mitigation or a demonstrated optimum.
- The hosted result is part of the original Q1 preregistration.
- GPT-5.4 is the current primary frontier model.
- A large cheap-model panel is preferable merely for model-count breadth.
- The tested Qwen/DeepSeek products are raw pretrained base models.
- Fine-tuning necessarily preserves the measured starting-checkpoint profile.
- The retired logprob canary or its two-of-four “usable” rule qualifies a study endpoint.
- Missing cost, routing metadata, or raw envelopes may be treated as harmless.

## Remaining decisions and gates

### Before any Stage-2 paid study call

1. Commit the A/F/S-approved **v7.2 pre-outcome amendment** and its bound endpoint/tokenizer
   snapshot as the freeze. V7.2 freezes:
   - exact model IDs and one exact provider endpoint per model;
   - reasoning-off controls and accepted decode parameters;
   - `X-OpenRouter-Cache:false`;
   - `provider.only`, no fallbacks, and `require_parameters:true`;
   - `max_tokens=4`, no seed, and the anchored leading-option parser;
   - the strengthened parse/completeness rules;
   - all 528 unique requests and 13,200 draws per model;
   - the full-grid cost projection and stop rule.
2. Implement and independently verify every R-E1–R-E7 runner requirement.
3. Pass no-network tests for immutable raw persistence, paid-invalid responses, cost
   reconciliation, restart accounting, exact routing, manifest identity, completeness,
   and fail-loud extraction.
4. Run only the frozen minimal synthetic capability gate. Later, separately authorized
   stages may run the endpoint-promotion gate and declared
   outcome-blinded smoke. Promote a model only under the frozen capability, parse,
   completeness, routing, and cost rules.
5. Obtain explicit execution authorization after each audit interlock and before the full
   matrix.

### Before submission

1. Do not draft Stage-2 findings into the paper until valid artifacts exist. If Stage 2
   does not clear the gates by the cut line, omit the new result rather than weaken the
   design.
2. Regenerate [PAPER_RESULTS.md](../docs/PAPER_RESULTS.md) so it no longer contradicts
   the Q1 result or coding disclosure.
3. Complete a whole-paper terminology and numerical consistency sweep against
   [Q1_RESULTS_CONSENSUS.md](Q1_RESULTS_CONSENSUS.md).
4. Verify and pin any newly added indirect-prompt-injection and sovereign-AI citations
   against primary sources.
5. Render and visually inspect the final paper and checklist, then rebuild the anonymous
   supplement from the strict allowlist described in
   [AAAI_SUBMISSION_READINESS_REVIEW.md](AAAI_SUBMISSION_READINESS_REVIEW.md).

## Compact handoff

The completed local result is ready to write and has already been applied: Q1 rejects the
original evidence-over-instruction mechanism and supports a broader contextual-instability,
placement-sensitive assurance result. The proposed hosted extension is scientifically
motivated as a pre-adaptation test of two frontier open-weight checkpoints relevant to a
build-on-open-weights sovereign-AI strategy. That extension remains pre-outcome and
unexecuted. Its next legitimate artifact is the signed v7 design amendment—not another
diagnostic script or an informal API run.
