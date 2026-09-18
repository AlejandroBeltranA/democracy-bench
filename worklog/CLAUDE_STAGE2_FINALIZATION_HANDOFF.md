# Claude handoff: finalize Q2 Stage 2 for submission

Date: 2026-07-29  
Reviewed repository HEAD: `23b80a0584df5bf2f1895fe496397a76fee5ca80`  
Full audit: `paper/STAGE2_FINAL_SHIP_REVIEW.md`

## Authorization and scope

The two paid experiments are accepted. **Do not rerun Qwen or DeepSeek and do not make any
additional paid model call.**

You are authorized to make the remaining local code, artifact, walkthrough, bibliography,
manuscript, and PDF changes needed to finish Stage 2. Keep this tightly scoped. Do not reopen
settled design questions, refactor unrelated code, or expand the empirical claims.

## Required work

### 1. Restore a green extraction contract

The exact-HEAD focused check currently fails:

```text
FAILED tests/test_q2_v7_study_extract.py::test_wrong_model_on_a_bound_draw_raises
8 passed, 153 deselected
```

`extract_draws` now deliberately skips records belonging to the other panel model before
checking the requested model's manifest. The old single-model test still expects that record
to raise.

Replace the obsolete assertion with a no-network shared-store regression that proves:

1. a store containing valid Qwen and DeepSeek draws extracts only the requested model;
2. extracting each model does not admit the other model's draws;
3. an unbound study record claiming the requested model still fails closed;
4. non-study envelopes remain ignored under the existing contract.

Do not weaken the target-model manifest checks merely to make the suite pass.

### 2. Refresh the final Qwen extraction artifact

Regenerate the Qwen artifact from the completed shared panel store using the frozen extraction
configuration. Its substantive results already regenerate exactly; only its shared-store
`spend` snapshot is stale.

Expected final Qwen spend fields:

```text
run_usd:            1.591792912
n_booked_envelopes: 26400
n_study_draws:      13200
```

The DeepSeek artifact already regenerates byte-for-byte. Do not alter substantive estimands,
bootstrap settings, or frozen design inputs.

### 3. Correct the walkthrough

In `paper/STAGE2_WALKTHROUGH.html`:

- relabel `$1.624` from “Both full runs” to **“Cumulative Q2 spend”**;
- replace “32% under projection” with approximately **54% under projection**;
- report the panel-wide 429 rate as **27 / 26,427 = 0.102%**, or retain 0.2% only if it is
  explicitly labelled Qwen-only (`27 / 13,227`);
- keep the distinction between 26,400 terminal study draws and 26,427 wire attempts.

### 4. Apply a shortened Stage-2 result to the canonical manuscript

`paper/STAGE2_PAPER_EDITS.md` is a draft, not the paper. Apply the selected Stage-2 material
directly to `paper/democracy_bench.tex`.

Keep the manuscript addition compact. It must retain:

- both models completed 13,200 draws;
- instruction destroyed 99.7% and 100% of resting protective mass;
- the baseline-free channel contrasts were `+0.303` and `+0.315`;
- Qwen's data-only system guard closed 8/8 induced cracks and DeepSeek's closed 5/8;
- guard-after closed 12/12 combined cracks on Qwen and 10/11 eligible cracks on DeepSeek;
- one DeepSeek probe was below the floor at rest, making its eligible denominator 11;
- resting-baseline magnitudes are not comparable across models;
- this is a post-hoc transfer study, not a preregistered replication;
- no inheritance claim is made for fine-tuned derivatives.

Do not paste the entire 415-word draft into §5.5. Remove secondary per-probe and placebo detail
unless it is essential to the surrounding argument.

In the limitations language, say **“On Qwen, three of the eight…”**, not the ambiguous “Of the
eight…”.

### 5. Resolve citations without placeholders

No `[cite ...]` placeholder may remain in the manuscript.

For the fastest defensible submission path, remove the external sovereign-AI policy setup if
verified bibliography entries are not already available. The Stage-2 empirical result does not
depend on that framing. If the framing is retained, add complete, verified entries to
`paper/references.bib` and use valid LaTeX citation keys.

### 6. Rebuild and inspect the paper

Rebuild `paper/democracy_bench.pdf` from the edited canonical source. Confirm:

- the LaTeX build succeeds without undefined citations or references;
- the Stage-2 text appears in the PDF;
- tables, figures, page breaks, and bibliography render correctly;
- no draft markers, citation placeholders, or internal review notes appear.

### 7. Handle the evidence-cookie issue proportionately

The committed attempt envelopes contain the provider's short-lived Cloudflare `__cf_bm`
response cookie. Request authorization is redacted correctly.

Remove `set-cookie` from the publishable evidence representation and document the deterministic
sanitization. **Do not rewrite Git history or force-push without Alex's separate authorization.**
If the repository is not being published with the paper, record this as a repository-release
task rather than delaying the manuscript submission.

The evidence commit also adds roughly 471 MB to `.git`. Do not reorganize it during the paper
finalization unless repository publication is part of the immediate submission.

## Required verification

Run, at minimum:

```bash
python -m pytest -q \
  tests/test_q2_v7_study_extract.py \
  tests/test_q2_v7_interlock.py \
  tests/test_q2_v7_study_run.py
```

Also run the repository's paper build command and `git diff --check`.

Verify after regeneration that:

- DeepSeek remains byte-identical;
- every substantive Qwen result remains unchanged;
- Qwen's final spend block matches the completed shared store;
- the canonical `.tex`, bibliography if applicable, and rebuilt PDF are included in the final
  commit.

## Completion record

Make one focused finalization commit. In the commit message or a short appended section below,
record:

- the exact commit hash;
- tests run and pass counts;
- paper build result;
- confirmation that no paid call was made;
- confirmation that both experiment result sets were unchanged;
- any cookie/repository-release work deliberately deferred.

Once all required checks are green, Stage 2 is cleared for submission. No further Codex
re-review is required unless a substantive estimand, experimental artifact, or empirical claim
changes.
