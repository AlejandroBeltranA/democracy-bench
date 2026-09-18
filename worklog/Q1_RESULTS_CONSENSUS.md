# Q1 results interpretation — Sol concurrence

**Date:** 2026-07-22  
**Artifacts:** `out/q1_channel_3b.json`, `out/q1_channel_8b.json`  
**Frozen design:** `paper/Q1_PRIORITY0_DESIGN.md`, SHA-256
`5063e80628a95d6e9e3c1c43defff6e43f950c88f7203d9f2cc29db0335c0443`  
**Sol status:** CONCUR with the outcome mapping below. Manuscript prose may now be
rewritten consistently with it; this concurrence does not authorize changing or hiding
Q1 outcomes.

## Outcome-table mapping

1. **“Data-only cracks; instruction-only does not” — FALSE on both models.** Data-only
   has a harmful average effect on 3B (-0.163, 95% CI [-0.232, -0.086]) and 8B
   (-0.188, [-0.250, -0.124]), but instruction-only is much more harmful: -0.558
   [-0.658, -0.464] and -0.568 [-0.674, -0.466].
2. **“Data-only and instruction-only crack similarly” — FALSE under the frozen
   equivalence rule.** The channel contrast (data effect minus instruction effect) is
   +0.395 [+0.333, +0.464] on 3B and +0.380 [+0.287, +0.492] on 8B, far outside the
   +/-0.05 equivalence region and opposite the sign required for evidence-specific
   support. Direct target instruction is substantially stronger than displayed data.
3. **“Only the current combined payload cracks” — FALSE.** Data-only, instruction-only,
   combined, and placebo conditions all induce cracks. The explicit reproduction task
   therefore does not uniquely generate the effect.
4. **“True system guard closes the crack” — MODEL-CONDITIONAL for the primary data-only
   contrast.** It does not recover 3B (mean +0.012, [-0.015, +0.043]; all five induced
   cracks remain), but it recovers 8B (+0.314, [+0.235, +0.389]; all five induced cracks
   close). This is not by itself evidence that role privilege caused recovery: on 8B the
   matched user guards are stronger in level, and on 3B user-after is stronger than the
   system guard. Attribute the result to model/placement-sensitive guard efficacy unless
   a direct system-versus-user contrast supports a hierarchy claim.
5. **“True system guard also fails” — TRUE for 3B data-only, not universal.** It also
   fails to close the combined attack on 3B and closes only part of it on 8B. The paper
   cannot say either that system guards generally solve the problem or that no prompt
   guard can close it.
6. **“User-before and user-after differ materially” — TRUE in four of six
   payload-by-model diagnostics.** Material recovery appears for 3B data-only (+0.266)
   and combined (+0.269), and for 8B instruction-only (+0.096) and combined (+0.309).
   “After” means after the payload inside the conditioning block, not after the question.
7. **“Placebo moves floors” — TRUE on both models.** The preregistered secondary placebo
   effect is harmful on 3B (-0.143, [-0.217, -0.073]) and 8B (-0.112,
   [-0.187, -0.033]). Per the frozen interpretation, reframe around anchoring/format or
   contextual sensitivity and do not call this uniquely democratic-value erosion.

## Required manuscript interpretation

- Reject the evidence-over-instruction asymmetry. Evidence-only conditioning is harmful,
  but direct instruction is substantially more harmful.
- Replace the single privileged “evidence channel” mechanism with contextual instability
  across payload semantics, explicit instructions, irrelevant distribution context,
  prompt placement, and model.
- Describe guard recovery as model- and placement-dependent. Do not infer a system-role
  advantage from system-versus-no-guard recovery when matched user guards perform as well
  or better.
- Distinguish items already below 0.50 at baseline from induced cracks. Both models begin
  with 4/12 below, leaving eight eligible transitions; data-only newly cracks 5/8 on each,
  instruction-only 8/8 on each, combined 8/8 (3B) and 7/8 (8B), and placebo 5/8 (3B)
  and 3/8 (8B).
- Disclose the localized 3B coverage anomaly on `pol_surveillance`. Excluding that probe
  leaves the substantive point estimates effectively unchanged (data -0.150,
  instruction -0.552, channel +0.402, system recovery +0.010).
- Treat any direct data-only-versus-placebo contrast as post-hoc and imperfectly matched;
  the frozen conclusion depends on the preregistered placebo movement itself.

## Hosted follow-up decision

The local outcome makes hosted confirmation more valuable, not less: the questions are
whether the instruction dominance, placebo movement, recency effect, and heterogeneous
guard recovery transfer beyond two quantized Llama checkpoints.

Before any OpenRouter call, freeze a separate Stage-2 hosted design. The original
budget-tight hosted subset named baseline/instruction-only/data-only/combined crossed
with no-guard/system-guard. Adding placebo and user-after in response to Q1 is a legitimate
follow-up, but it must be labelled and frozen now rather than described as part of the
original local preregistration. At minimum, the hosted design should retain:

- baseline/no-guard;
- instruction-only/no-guard;
- data-only/no-guard;
- combined/no-guard;
- placebo/no-guard;
- data-only/user-after and data-only/system-guard;
- combined/user-after and combined/system-guard.

Report every attempted model and cell. Preserve the USD 8.50 spend stop and USD 1.50
reserve. Only the dated OpenAI identifiers in the proposed panel are pinned snapshots;
OpenRouter execution remains non-byte-reproducible. Sampling validation remains necessary
where hosted top-logprob option coverage is incomplete.

## Writing authorization

Sol concurs that the Section 5.5, Section 6, and abstract rewrite may begin from this
mapping. The rewrite must be a thesis-level reframing, not a qualifications paragraph
added around the rejected asymmetry claim. No manuscript prose was changed as part of
this sign-off.
