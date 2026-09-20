# Worklog — the working record, not the documentation

This folder is the project's build record: planning documents, phase handoffs, adversarial
reviews, session logs, editorial drafts, and the pitch material from the hackathon weekend
this started as. It is kept in the open repo deliberately.

**Read this first, before you read anything in here:**

- **Nothing in this folder is a finding.** These are point-in-time documents. Several were
  written *before* the runs they plan, and some of what they predict turned out to be wrong —
  which is the point of keeping them. A few contain unfilled placeholders (`[X]×`, "pending")
  from before the numbers landed.
- **The findings live elsewhere.** For results, read [`docs/PAPER_RESULTS.md`](../docs/PAPER_RESULTS.md),
  the claim-to-artifact map where every number is regenerated from committed JSON by a
  fail-loud extractor. For how to rerun any of it, [`docs/REPRODUCTION.md`](../docs/REPRODUCTION.md).
  Where a document in here disagrees with those, those win.
- **This folder is excluded from the anonymous paper supplement** by
  `scripts/build_supplement.py`, because none of it is needed to replicate the results.

## Why keep it public at all

Two reasons.

The first is that a benchmark makes claims about model behaviour, and the honest way to read
such a claim is to know what the author was hoping to find when they designed the run. The
worklog shows the hypotheses that died. The activation-steering rung is the clearest case: the
original result was a real, large, in-sample improvement, and the documents here record the
moment it was killed by a held-out test and re-explained as a generic persona axis. A repo that
only ships the surviving claims hides that the survivors were selected.

The second is that this was built with heavy AI assistance, and that is better shown than
laundered. Anthropic's Claude and OpenAI's Codex both appear in these documents as named
reviewers of designs and code, and several of the adversarial reviews that changed the paper
were theirs. The discipline that makes that trustworthy is not the model — it is the gates:
fail-closed elicitation, held-out tests, preregistered channel design, a fail-loud extractor
binding every reported number to a committed artifact, and human sign-off checklists in
[`gates/`](../gates/). Those are what you should audit. The working notes just show them being
applied.

## Roughly what is in here

| Group | Files |
|---|---|
| Original plan and pitch | `PLAN.md`, `ONE_PAGER.md`, `DEMO_PRESENTER_SCRIPT.md`, `DEMO_TALKING_POINTS.md`, `ALIGNMENT_DEMO_18H.md` |
| Build logs and session notes | `BUILD_LOOP.md`, `SESSION_2026-06-26.md`, `CHANGE_MANIFEST.md`, `DEMO_CONSOLIDATION_HANDOFF.md` |
| Experiment planning | `FRONTIER_CRACK_PLAN.md`, `PAPER_SUPPORT_PLAN.md`, `RELEASE_PLAN.md` |
| Adversarial reviews and consensus | `AAAI_SUBMISSION_READINESS_REVIEW.md`, `PRE_SUBMISSION_REVIEW_PLAN.md`, `PROTOCOL_CONSENSUS.md`, `Q1_RESULTS_CONSENSUS.md`, `PUBLIC_OPINION_MODEL_OUTPUT_CRITIQUE.md` |
| Stage-2 frontier run handoffs | `CLAUDE_STAGE2_FINALIZATION_HANDOFF.md`, `STAGE2_*.md`, `STAGE2_WALKTHROUGH.html`, `Q2_STAGE2_V72_SMOKE_HANDOFF.md` |
| Editorial drafts | `DECISION_AND_DRAFT_INDEX.md`, `Q1_REWRITE_DRAFT.md` |

Design documents that the code actually depends on are **not** here. Those live in
[`paper/`](../paper/), because the runners read them and hash them into every run manifest —
see that folder's README.
