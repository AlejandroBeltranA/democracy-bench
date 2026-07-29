# Stage 2 — what is pending, for a fresh session

**Written by:** Claude, end of the 2026-07-28/29 session
**Repo state at handoff:** HEAD `23b80a058`, plus uncommitted changes listed below
**Deadline:** AAAI-27 AISI submission, 2026-07-29 noon

Read this first, then `paper/CLAUDE_STAGE2_FINALIZATION_HANDOFF.md` (Codex's task list) and
`paper/STAGE2_FINAL_SHIP_REVIEW.md` (the review those tasks come from). This file exists
because Codex's handoff was written before I fixed several of its items, and because there are
uncommitted changes and two human decisions it does not cover.

---

## The one-line status

**The experiment is finished and passes. Do not rerun any model.** Both full runs completed,
both completeness gates passed, results regenerate from committed evidence. What remains is
paper work, one evidence-hygiene decision, and a commit.

---

## Results, for reference

| | Qwen3.5-397B-A17B | DeepSeek-V4-Pro |
|---|---:|---:|
| draws | 13,200 | 13,200 |
| parse rate | 0.999848 | 0.999773 |
| complete | yes | yes |
| channel contrast | +0.3025 [+0.0875, +0.5384] | +0.3150 [+0.1917, +0.4450] |
| contrasts clearing zero | 8/8 | 6/8 |

Cumulative Q2 spend **$1.623673** of the $8.50 stop (includes a $0.031839 prior debit; the
panel itself is $1.591834). 54% under the combined $3.527 projection.

Headline: instruction dominates evidence on both models. DeepSeek additionally fails one
rights floor **at rest** (`pol_protest_ban`, 0.33, no payload), so its induced-crack
denominator is 11 eligible probes, not 12.

---

## Already fixed this session — do not redo

| Review item | What was done |
|---|---|
| **S2-3** stale Qwen artifact | Regenerated after the panel completed. Both artifacts now report the same shared store (26,400 envelopes, `run_usd` $1.591792912). Substantive Qwen results unchanged; verified `channel_contrast` still +0.3025. |
| **S2-4** walkthrough ledger | "Both full runs" relabelled **Cumulative Q2 spend**; 32% under projection corrected to **54%** (32% was Qwen-only); 429 rate corrected to **0.102%** with the 26,427 denominator stated. |
| **S2-5** red contract test | `test_wrong_model_on_a_bound_draw_raises` replaced with two tests: the other panel model is skipped (not raised), and an unbound draw claiming this model still fails closed. Mutation-verified: removing the model-skip fails the new test. |
| Editorial | "Of the eight contrasts" → **"On Qwen, three of the eight"**. Removed the claim that baseline cancellation *causes* the two channel estimates to agree; it makes them comparable, the agreement is empirical. |
| **S2-2** (code half) | `ledger.build_envelope` now passes response headers through `redact_headers`. `SECRET_HEADERS` already listed `set-cookie`, but only request headers were ever redacted. Verified: `set-cookie` redacted, `CF-RAY` preserved, ledger suite 61 passing. |

---

## UNCOMMITTED — commit this first

```
 M out/q2_stage2_v7_run_panel/extract_qwen__qwen3.5-397b-a17b.json   (S2-3 regeneration)
 M paper/STAGE2_PAPER_EDITS.md                                       (editorial corrections)
 M paper/STAGE2_WALKTHROUGH.html                                     (S2-4 ledger fixes)
 M src/alignment/q2_v7/ledger.py                                     (S2-2 response redaction)
 M tests/test_q2_v7_study_extract.py                                 (S2-5 replacement tests)
?? paper/CLAUDE_STAGE2_FINALIZATION_HANDOFF.md                       (Codex)
?? paper/STAGE2_FINAL_SHIP_REVIEW.md                                 (Codex)
```

**Verified green before commit:**
```
tests/test_q2_v7_study_extract.py   84 passed in 572s
tests/test_q2_v7_ledger.py          61 passed
```
The S2-5 replacement was mutation-checked: removing the model-skip in `extract_draws` fails
`test_the_other_panel_model_is_skipped_not_raised`; restoring it passes. The extraction suite
takes ~10 min because its fixtures build full-scale grids; that is deliberate.

Not re-run at handoff (unchanged by this session's edits, last green earlier): the gate,
envelope, identity, interlock, canary, study_run, study_render and conformance suites. Run the
full v7 sweep before the final submission commit.

---

## PENDING — needs Alex's decision, not just execution

### D1. The committed evidence: cookies AND size are one decision

Commit `23b80a058` tracks 51,867 raw + 51,867 derived records: **622 MB working tree, 471 MB
`.git`, 103,734 files**. Two problems, best solved together:

1. All 26,427 attempt envelopes retain the provider's `set-cookie` (`__cf_bm`, a short-lived
   Cloudflare bot-management cookie). Not a credential, but the repo's own `SECRET_HEADERS`
   classifies the header as sensitive, and the evidence is meant to be publishable. The code
   is fixed for future runs; the existing files are not.
2. 471 MB is heavy for a paper repo, cannot go in an anonymous supplement, and would be slow
   to push. Measured compression is **8.4×**, so the whole thing is ~73 MB as an archive.

**Recommended:** `git reset --soft HEAD~1` (nothing is pushed, so this is clean), scrub
response headers across the evidence, rebuild as a checksummed archive plus a committed
manifest. Codex's requirement: do not rewrite evidence silently, record the transformation and
the new tree/archive hash.

**Alternative:** keep as committed and document an explicit decision to retain `__cf_bm`.

This is a judgement about what the repository is for. I did not decide it.

### D2. The seven editorial decisions in `STAGE2_PAPER_EDITS.md`

The two that actually block application:

- **Insertion B is 415 words.** Codex agrees it is too long for a robustness paragraph and
  says to compress before applying, preserving: the two-model channel result, conditional
  guard closure, the resting-floor qualification, the estimator change, and the
  non-inheritance boundary. Secondary placebo and per-probe detail move to an appendix or the
  walkthrough. I offered to take a first pass at ~200 words; not done.
- **Does the resting-floor failure earn its own sentence, possibly in the abstract?** DeepSeek
  ships below the floor on the bank's hardest probe with no adversarial input. For a paper
  arguing the starting checkpoint carries an assurance burden, this may be the sharper
  illustration. It currently sits mid-paragraph.

### D3. Em dashes

The canonical voice doc (`~/Documents/GitHub/cowork_context/skills/_shared/alex_voice.md`,
§6) bans them outright and says a true em dash only ever appeared in an AI-assisted redraft.
`democracy_bench.tex` nonetheless uses `---` in passages that read as Alex's. The insertions
are written without any, so they will read slightly unlike the surrounding text. Alex's call.

---

## PENDING — execution, once D1–D3 are settled

Follow `paper/CLAUDE_STAGE2_FINALIZATION_HANDOFF.md` items 4, 5, 6. In short:

1. **Apply a compressed Stage-2 passage to `democracy_bench.tex`.** Nothing has been applied;
   the manuscript is untouched by every Stage-2 commit. `STAGE2_PAPER_EDITS.md` holds four
   insertions (abstract, §5.5, limitations, "what we do not claim") in co-editing format.
2. **Resolve the citations.** Four `[CITE NEEDED]` placeholders, none invented,
   `references.bib` untouched (18 entries, nothing on sovereign AI or open weights). Insertion
   B's external policy framing needs two real entries or it comes out. **Do not fabricate a
   key, author, year, or DOI** — this is the rule Alex cares most about.
3. **Rebuild and visually inspect `democracy_bench.pdf`.**
4. Commit manuscript, bibliography, PDF, refreshed artifact, and the evidence manifest.

---

## Things a fresh session should know before touching the code

- **Do not rerun any model.** Both runs are complete and paid for. Every review round said so
  explicitly.
- **The recurring bug class in this codebase is "shared store, per-model manifest."** It
  appeared five times: walk store, study store, attempt store, ledger reconstruction, and
  extraction. Every time, the *second* model was the one that broke, and every test fixture
  used one model per directory. If something fails only on DeepSeek, look here first.
- **Money is exact `Decimal`** quantised at ingestion (1e-12, ROUND_HALF_UP). Do not
  reintroduce float arithmetic in the ledger; the original defect was invisible on CPython
  3.12 because `sum()` uses compensated summation, and only appeared on 3.9–3.11.
- **The extraction suite is slow** (~10 min) because its fixtures build full-scale grids. That
  is deliberate; budget for it rather than trimming it.
- **`.env` is git-ignored but auto-loaded** by `alignment.instrument.measure` at import, so the
  "refuse without `OPENROUTER_API_KEY`" guard never actually fires. The real guard is
  `--i-have-authorized-paid-spend`.

## Claims to keep exactly as worded

These survived two adversarial reviews and one was corrected from an error. Do not restore the
stronger versions.

- **"Transfers", never "replicates".** The frozen Stage-2 question is a transfer question, the
  estimator changed from logprob scoring to 100-draw sampling, and one model cannot speak to
  the model-conditionality Q1 found.
- **The two divergent contrasts are not "the finding".** I claimed they reproduced Q1's
  model-conditional guard efficacy; that was rejected as post-hoc. Q1's specific conditional
  contrast (data-only system recovery) in fact *agrees* across both models here, and the two
  divergences are equally well explained by small effects with bounds inside the ±0.05
  materiality band failing across sixteen uncorrected intervals. Both documents state both
  readings and decline to choose. A stronger line needs a third model or more draws.
- **Baseline-anchored magnitudes are not comparable across models** (0.973 vs 0.810).
  `instruction_effect`'s intervals are disjoint, but the 0.160 gap between effects is the
  0.163 gap between baselines.
- **Guard closure degrades on the second model:** system guard closes 8/8 data-only cracks on
  Qwen, 5/8 on DeepSeek; guard-after closes 12/12 on Qwen, 10/11 eligible on DeepSeek.
- **No inheritance claim.** Nothing here shows a fine-tuned derivative keeps this profile.
