# Joint experiment protocol for three-way sign-off

**Parties:** Alex (author, final call), Fable (Claude), Sol.
**Rule:** no experiment runs until all three parties mark AGREE on its row, and the
Priority-0 freeze (Sol's plan) is committed first. Disagreement is resolved by Alex after
both models have stated their case in one round each, no more.
**Date opened:** 2026-07-21. Paper deadline 2026-07-28.

Vote key per row: `A: [ ] F: [ ] S: [ ]` (AGREE / OBJECT: reason / ABSTAIN).
All three responses are recorded below. Q1--Q4 have three-way agreement subject to their
stated gates. Q5 does not have consensus and should not run as written. Q6 is infeasible
without an independent human and must not be relabelled as human reliability evidence.

---

## Resolved facts feeding this protocol (verified against the repo, 2026-07-21)

1. The Tier-2 hostile payload contains both percentages and an explicit reproduction
   instruction (`src/alignment/steer/tier2_preference.py:40-42`). The published
   evidence-vs-instruction asymmetry is not identified by current artifacts.
2. Guards are prepended to user-message conditioning; the system role is always the
   generic survey instruction (`evidcond_run.compose_guard`, `measure.py`). "Prompt
   guards fail" is currently only "user-scaffold guards fail."
3. 3B hostile: 12/12 below 0.50 but two items (pol_protest_ban, pol_dna_database)
   INCREASE protective mass. 8B hostile: 11/12 below. Fig 3 caption and any per-item
   "erodes every floor" wording must be corrected regardless of new experiments.
4. The rationale annotator displayed item id, class badge, and model name on every card
   (`annotations/rationale_annotator.html`, render()). Coding was single-coder,
   order-shuffled, NOT blinded to model or class. Class visibility is intrinsic to the
   right-invocation judgment. Paper wording must change regardless of new experiments.
5. The headline P2/P3 artifacts use `primary: ENG`; their caveats identify the real
   2022/2024 distributions as England distributions. The target bank also contains
   Scotland and Wales, but the paper's headline tracking result is not a pooled UK or
   Great Britain estimate. The rights-floor probes and constitution are authored; they
   are not democratic-values measurements derived from BSA.
6. Local option logprobs are not currently exact full-option probabilities:
   `activation_steer.mlx_logprob_fn` truncates the vocabulary to top-40 tokens before
   `option_logprob_vector` extracts and renormalizes option numbers. The full local logit
   vector is available, so Q1 must use an exact option-token extraction path and record
   coverage. Existing headline cells need a regression check under the corrected scorer.

---

## Experiment queue

### Q1. Channel-decomposition matrix, local 3B + 8B (Sol P1) — MUST-HAVE

- **Tests for:** what moves floor mass: displayed data, an imitation instruction,
  prompt recency, or the absence of a genuinely privileged (system-role) guard.
  4 payloads (baseline / instruction-only / data-only / current combined) x 4 guard
  placements (none / user-before / user-after / true system role) x 12 floor probes,
  position-balanced option orders, format-matched placebo as secondary arm.
- **Value:** identifies the paper's central causal claim. Every headline sentence about
  "the evidence channel" depends on the data-only vs instruction-only contrast.
- **Cannot show:** why the winning channel dominates (no mechanism claim); anything about
  real public opinion (payloads remain synthetic); generalization beyond the two local
  checkpoints until Q2 runs.
- **Limitations that survive any outcome:** 4-bit local checkpoints; authored floor
  probes; prompt-template and model-family effects; the preregistered outcome table
  (Sol's plan) fixes interpretation, and
  several rows force abstract rewording — the AAAI abstract-editability check must
  complete before this runs.
- **Cost:** local wall clock only. Est. 4x4x12 x 4 orders x 2 models ~= 4x the existing
  P4 grid; overnight-scale.
- **Votes:** A: [AGREE ] F: [AGREE] S: [AGREE, contingent on the exact-local-option
  scorer and coverage regression gate in the Preconditions]

### Q2. Hosted confirmatory panel, declared ids (Sol P1b) — DROP-FIRST

- **Tests for:** whether the Q1 channel structure transfers to declared hosted models
  (gpt-4o-mini-2024-07-18, gpt-4o-2024-11-20, grok-4.5, llama-3.3-70b), behind the
  logprob smoke gate (option-token coverage recorded per call).
- **Value:** replaces the unpinned gpt-4o-mini existence proof with a pinned, coverage-
  audited one; adds one independent proprietary family.
- **Cannot show:** stability over time (providers drift); full option distributions where
  top-k coverage is incomplete (those cells fall back to sampling or are excluded, per
  the smoke-gate rule).
- **Limitations that survive:** only the dated OpenAI ids are pinned model snapshots;
  `grok-4.5` is not a dated snapshot and OpenRouter may change serving providers for all
  ids. Hosted cells are never byte-reproducible; budget caps the matrix to decisive cells,
  so the hosted result is a spot-check, not a panel.
- **Cost:** within the $3.00 cap of the $10 budget. First thing cut if time runs out.
- **Votes:** A: [AGREE ] F: [AGREE, contingent on Q1 freezing first] S: [AGREE,
  contingent on Q1 freezing first and every attempted model being reported]

### Q3. Sampling validation of decisive hosted cells (Sol P2)

- **Tests for:** whether first-token top-k logprob distributions agree with S=100
  forced-choice sampling on the pinned gpt-4o-mini decisive cells. Directly addresses
  the near-degenerate-logprob saturation worry already admitted in the paper.
- **Value:** converts the panel's most dramatic and least trustworthy number into a
  measurement with a stated cross-method check; protects against the truncated-top-k
  artifact Sol identified in the scorer.
- **Cannot show:** agreement on one model does not certify other providers' logprob
  paths. Local open-weight cells require the separate exact-option scorer/coverage
  regression gate; Q3 does not validate them.
- **Limitations that survive:** at S=100 the maximum binomial standard error is 0.05
  (the corresponding worst-case 95% margin is about 0.10); sampling and logprob paths
  share the same prompt, so shared prompt artifacts remain.
- **Cost:** within the $3.75 cap. Reported even if it disagrees with logprobs.
- **Votes:** A: [AGREE ] F: [AGREE] S: [AGREE, with the binomial-uncertainty correction
  above]

### Q4. Fabricated-shift + no-shift tracking control (Sol P3, subsumes Fable X2)

- **Tests for:** true mapping vs swapped mapping vs same-vector-both-years on the 10
  tracking items, local 3B, confirm on pinned gpt-4o-mini.
- **Value:** decides what "tracking" means. Following swapped vectors strengthens
  who-fills-the-channel and weakens any the-model-recognizes-real-shifts reading; the
  no-shift placebo rules out a bare year-label effect. Both readings are pre-committed.
- **Cannot show:** tracking over more than one real interval; anything about elasticity
  magnitude calibration.
- **Limitations that survive:** 10 items, one interval, items selected for large real
  shifts; elasticity remains direction-plus-sign evidence, not magnitude.
- **Cost:** one tracking-run equivalent locally + $0.75 hosted cap.
- **Votes:** A: [ AGREE] F: [AGREE] S: [AGREE]

### Q5. Seed replication on headline local cells (Fable X5) — NO CONSENSUS; DROP AS WRITTEN

- **Tests for:** across-seed spread (3 seeds) on 3B baseline floors, hostile evidence,
  and tracking cells, distinguishing sampling CIs from run-to-run variance. Note: the
  harness `seed` currently controls option permutations, not sampler state — this
  experiment first requires exposing a true sampler seed; if that plumbing is not trivial,
  downgrade to a rerun-variance check (same config, 3 repeats).
- **Value:** answers the "single-seed on quantized models with CIs grazing zero"
  objection with data instead of a limitations sentence. Cheap and local.
- **Cannot show:** quantization bias (all seeds share the 4-bit checkpoint); prompt/house
  effects.
- **Limitations that survive:** 3 seeds bounds run variance crudely; no hosted analogue.
- **Cost:** ~3x existing run time for affected cells, local, no budget impact.
- **Votes:** A: [ AGREE] F: [WITHDRAWN 07-21: Sol is right — verified that
  `mlx_logprob_fn` is a single deterministic forward pass over exact logits, no sampler
  state exists on the local path; Q5 is dropped, see writing correction 12] S: [OBJECT: the headline local path uses
  deterministic option logprobs, so there is no stochastic model/sampler seed to expose.
  Three repeats of the same configuration should be identical; switching to sampled
  decoding changes the estimator rather than replicating the run. Q1's fixed balanced
  option orders address the actual seeded variation. Keep quantization and prompt/house
  effects as limitations rather than calling this seed replication.]

### Q6. Independent second coder on a codesheet subset (Sol item 1) — INFEASIBLE WITHOUT A HUMAN

- **Tests for:** inter-rater agreement (Cohen's kappa) on a preregistered ~50-row subset,
  using the same annotator HTML, coder recruited by Alex, ideally with the model column
  stripped from their build (class must stay visible; it is intrinsic to the judgment).
- **Value:** upgrades the construct-validity paragraph from single-coder disclosure to a
  reliability estimate; the single highest-credibility fix available per unit effort.
- **Cannot show:** validity of the constructs themselves, only coding reliability.
- **Limitations that survive:** the primary coder remains an author; class stays visible.
- **Cost:** one colleague-hour plus a 10-line HTML edit to hide the model field.
  Feasibility is Alex's call by 07-24 (needs a human).
- **Sol response:** Fable and Sol can be used only as a disclosed **LLM-judge sensitivity
  analysis**, not as independent human coders and not as evidence of human inter-rater
  reliability. Substituting them would give up the paper's judge-free construct-validity
  claim and introduce correlated model-judge biases. If no human coder is available,
  disclose the single-coder procedure and rely on the released sheet's full recodability.
- **Votes:** A: [NO HUMANS AVAILABLE] F: [AGREE if a coder exists by 07-24, else write
  the disclosure] S: [ABSTAIN: human task is infeasible; OBJECT to substituting Fable/Sol
  as human reliability evidence]

---

## Writing corrections (consensus already, no votes needed — all verified)

1. Rationale coding: replace "blinded" with the true procedure (single coder,
   order-shuffled, model and class visible, class intrinsic to the judgment, released
   sheet + deterministic scorer allow full recoding). Upgraded by Q6 if it runs.
2. Scope the weights claim to the tested rank-8/500-iter LoRA recipe. (Sol 2 = Fable E3)
3. Fix per-item floor claims: 8B is 11/12; two 3B items rise while ending below 0.50;
   "erodes every floor" becomes "drives every floor below 0.50 (3B)" / "11/12 (8B)".
   Fig 3 caption corrected. (Sol 3)
4. 0.50 as convention; margins primary, counts secondary. (Sol 4 = Fable E4)
5. No naive pooled 51/60 sign test; descriptive or item-clustered only. (Sol 5,
   withdrawing Fable E7)
6. "Ground truth" -> "benchmark reference labels", normative status stated. (Sol 6)
7. Routing narrowed to a static allowlist over preclassified items; no zero-shot
   classifier presented as part of the result. (Sol 7; matches the registered abstract's
   "by construction".)
8. Related-work positioning vs indirect prompt injection + candidate cites, all
   [CITE NEEDED: verify before adding]. Sol agrees with the positioning but the final
   bibliography entries still require primary-source verification. (Fable E6)
9. State the attack's prompt mode explicitly; the "even when instructed to hold the
   right" framing waits for Q1's true-system-guard cell. (Fable E2, amended)
10. Geographic labeling is an accuracy issue, not a condition on the paper's democratic
    contribution or title. Democracy research need not compare countries: this paper tests
    whether models respond to changing public opinion while respecting a declared rights
    boundary. **Democracy Bench** is therefore justified by the research question itself.
    For the specific headline P2/P3 estimates, replace “British public” or “UK public” with
    “England public” because those artifacts use `primary: ENG`. England/Scotland/Wales
    target availability may be described separately, but must not be conflated with the
    headline England run. State that BSA supplies contestable public-attitude targets; the
    rights-floor probes and constitution are authored normative instruments, not democratic
    values measured by BSA.

11. Floor-direction review provenance: the review exists — `data/floor_review_signoff.json`
    (reviewer Alex Beltran, 2026-06-26, 12/12 accepted, 0 flagged, constitution accepted at
    pinned SHA). The "NEEDS INDEPENDENT REVIEW" license notes in `data/policy_items.jsonl`
    are STALE and should be amended to point at the signoff artifact, before the artifact
    freeze and after checking nothing hashes that file. In the paper, cite the signoff where
    the floor labels are introduced (S3), describe it as an author review (never
    "independent"), and report the treatment/control `floor_role` split (already recorded
    per item in both the signoff and the crack tables) alongside the aggregate floor mass.

12. Fix the Limitations sentence "Local results are single-seed ... tracking CIs reflect
    sampling error only": the local logprob path is deterministic (one forward pass, exact
    logits), so "single-seed" is the wrong frame. State instead that local cells are
    deterministic point measurements; the CIs are bootstrap intervals (state what is
    resampled); and the unquantified variance sources are prompt template, option order
    (addressed by Q1's balanced orders), and quantization. (Falls out of the Q5
    resolution.)

## Preconditions before any run

- [ ] Priority-0 design artifact committed (prompts, panel, orders, estimands,
      outcome-dependent wording, stop rule) — Sol's plan, verbatim.
- [ ] Measurement gate committed: local scoring reads every relevant option-number token
      from the full logit vector without top-40 truncation; local and hosted artifacts
      record option-token coverage; baseline/P3/P4 regression cells are compared with the
      committed artifacts before Q1 promotion. A material change triggers rerunning the
      affected headline cells, not silently mixing estimators.
- [ABSTRACT CAN BE EDITED BUT NOT REPLACED] Record what “not replaced” permits before Q1.
      If a preregistered Q1 outcome invalidates the abstract's central evidence-channel
      sentence and the submission system cannot accommodate the necessary correction,
      contact the track chairs. Do not retain a claim contradicted by the new experiment.
- [ ] Cut line agreed: Q1 + writing corrections are must-haves; drop order Q2 -> Q3
      hosted cells -> Q4 hosted confirm. Q5 is dropped unless redesigned as a distinctly
      labelled sampling-estimator robustness study; Q6 runs only if an independent human
      coder becomes available.

## Limitations that survive every outcome (for the Limitations section, pre-agreed)

Single 2022->2024 interval; authored floor probes without question-equivalent BSA
marginals; 4-bit quantized local checkpoints; headline public targets/tracking are
England-only and English-language (a generalizability boundary, not a defect in the
democracy construct); floor/contestable labels are normative reference labels; hosted
cells not byte-reproducible; the
preregistered outcome table constrains, but cannot eliminate, interpretive freedom.

The name **Democracy Bench** follows from the benchmark's substantive test: responsiveness
to changing public opinion under a rights constraint. It does not imply or require a
cross-country design. The temporal application compares aggregate England opinion
distributions across BSA waves; the separate cross-family "panel" is a panel of models.
Unless the same survey respondents are followed over time, call the public-opinion design
repeated-wave or repeated-cross-sectional tracking rather than respondent-panel analysis.
BSA supplies the public-attitude distributions on contestable items; the authored floor
probes test the separately declared normative rights boundary. The paper must not say that
BSA itself measures or validates the rights floor.
