# Q2 Stage-2 final experiment and paper ship review

Reviewer: Codex  
Date: 2026-07-29  
Reviewed HEAD: `23b80a0584df5bf2f1895fe496397a76fee5ca80`  
Experiment commits: `48f158b5767ef8e0bb222c78a9d6cdbe21291d6f`,
`2959e9cef5e5c3f2a5ca43b82e742f723e1fed49`,
`23b80a0584df5bf2f1895fe496397a76fee5ca80`

## Verdict

**The experiment passes. The repository is not yet submission-ready.**

Do not rerun either model. Both full runs completed, both frozen completeness gates passed,
the extraction interlock opens for each model, and the substantive results regenerate from
the persisted envelopes. The final evidence commit contains all 51,867 raw and 51,867 derived
records. The remaining work is to apply and tighten the paper draft, correct two audit-ledger
statements, refresh one stale artifact field, and rebuild the manuscript.

## Independently verified experiment record

| | Qwen3.5-397B-A17B | DeepSeek-V4-Pro |
|---|---:|---:|
| attempted draws | 13,200 | 13,200 |
| coordinates | 528 | 528 |
| parse rate | 0.999848 | 0.999773 |
| complete | yes | yes |
| halted/incomplete | no | no |
| channel contrast | +0.3025 [+0.0875, +0.5384] | +0.3150 [+0.1917, +0.4450] |
| instruction effect | -0.9700 [-0.9933, -0.9308] | -0.8100 [-0.8975, -0.7075] |
| data effect | -0.6675 [-0.8767, -0.4383] | -0.4950 [-0.6009, -0.3900] |
| contrasts clearing zero | 8/8 | 6/8 |

The principal paper claims checked against the committed extraction JSON are accurate:

- instruction reduces resting protective mass by 99.7% on Qwen and 100% on DeepSeek;
- the baseline-free channel contrast is positive and closely aligned on both models;
- Qwen's system guard closes 8/8 induced data-only cracks; DeepSeek closes 5/8;
- guard-after closes 12/12 combined cracks on Qwen and 10/11 eligible cracks on DeepSeek;
- DeepSeek has one floor below 0.50 at rest, so its induced-crack denominator is 11;
- the two DeepSeek null contrasts are `combined_system_recovery` and `data_placement`.

The authoritative ledger reconstructed from all attempt records, including retries and walk
records, reports:

```text
prior Q2 debit:        $0.031839140
current panel run:     $1.591834192
cumulative Q2 spend:   $1.623673332
hard stop:             $8.500000000
remaining:             $6.876326668
booked records:        26,429
```

There were 26,400 terminal study draws and 26,427 wire-attempt records: 26,400 HTTP 200s and
27 paid HTTP 429s, all on Qwen and absorbed by the retry ladder.

## Submission blockers

### S2-1 — the canonical paper was not redrafted

`paper/STAGE2_PAPER_EDITS.md` explicitly says it is a co-editing draft and has not been
applied. `paper/democracy_bench.tex`, `paper/references.bib`, and
`paper/democracy_bench.pdf` are unchanged by the Stage-2 result commits.

Before submission:

1. resolve the editorial choices listed in `STAGE2_PAPER_EDITS.md`;
2. insert the chosen text into `democracy_bench.tex`;
3. add real bibliography entries for the two citations used in insertion B, or remove the
   external policy framing;
4. rebuild and visually inspect the PDF.

The current 415-word §5.5 insertion is too long for a robustness paragraph. Compress it before
application. Preserve the two-model channel result, conditional guard closure, resting-floor
qualification, estimator change, and non-inheritance boundary; move secondary placebo and
per-probe detail to an appendix or the walkthrough.

### S2-2 — the evidence commit retains provider cookies

Commit `23b80a0` closes the reproducibility gap by tracking:

```text
51,867 raw JSON files
51,867 derived JSON files
26,400 terminal study draws
26,427 wire-attempt records, including retries
```

Request `Authorization` values are correctly redacted. However, all 26,427 attempt envelopes
also retain the provider's response `set-cookie` value (`__cf_bm`, a Cloudflare bot-management
cookie). It is not an API credential and is short-lived, but it is unnecessary response state
and the repository's own secret-header policy classifies `set-cookie` as sensitive. Scrub it
from the publishable history or document an explicit decision to retain it. Do not rewrite the
evidence content silently: record the transformation and new tree/archive hash.

The evidence adds roughly 471 MB to `.git`. If the repository itself is a deliverable, prefer
a checksummed release archive plus a compact manifest over 103,734 ordinary Git blobs.

### S2-3 — the committed Qwen extraction artifact has a stale spend block

The Qwen extraction was committed before DeepSeek populated the shared study store.
Regeneration from the final 26,400 draws matches every substantive Qwen field exactly, but
the shared-run `spend` block changes:

```text
committed Qwen artifact:  run_usd=$1.255077595, envelopes=15,401
final regenerated value: run_usd=$1.591792912, envelopes=26,400
```

The DeepSeek artifact regenerates byte-for-byte. Regenerate and recommit the Qwen artifact
after the panel is complete, or change/document the spend schema as explicitly model-local.
Do not leave two supposedly final artifacts describing different snapshots of the shared
store.

### S2-4 — two walkthrough ledger statements are wrong or ambiguous

In `paper/STAGE2_WALKTHROUGH.html`:

- `$1.624` is labelled “Both full runs”, but it is cumulative Q2 spend and includes the
  `$0.031839` prior debit. Label it **Cumulative Q2 spend**.
- `$1.624` against the combined `$3.526838` projection is about **54% under**, not 32% under.
  The 32% figure described Qwen alone before DeepSeek finished.
- the panel-wide 429 rate is `27 / 26,427 = 0.102%`; `0.2%` is Qwen-only
  (`27 / 13,227`). Label the denominator.

### S2-5 — the focused extraction suite is red

Commit `48f158b` changes `extract_draws` so records for the other panel model are skipped
before the current model's manifest check. The live final extraction and independent
regeneration prove the new shared-store behaviour works on this run, but the pre-existing
single-model contract test was neither changed nor replaced:

```text
FAILED tests/test_q2_v7_study_extract.py::test_wrong_model_on_a_bound_draw_raises
8 passed, 153 deselected
```

The failed test expects a wrong-model bound draw to raise; the implementation now deliberately
skips it. Replace that obsolete assertion with a no-network shared-store regression containing
both panel models. It must prove that each extraction selects only its requested model, while
an unbound study record claiming the requested model still fails closed. Then rerun the focused
Stage-2 suite. This is not a reason to rerun paid work.

## Exact-HEAD verification record

At `23b80a0584df5bf2f1895fe496397a76fee5ca80`:

- both complete extraction artifacts were checked against the persisted draw counts and
  headline claims;
- the DeepSeek artifact regenerates byte-for-byte;
- the Qwen substantive result regenerates exactly, with only the stale shared-store `spend`
  block differing;
- the authoritative ledger was reconstructed from all 26,427 attempt records;
- the focused extraction/interlock selection above produced one failed contract test, as
  recorded in S2-5.

## Editorial corrections

- In the limitations insertion, change “Of the eight preregistered contrasts, three have
  interval bounds inside the materiality band” to **“On Qwen, three of the eight…”**. Across
  both models there are sixteen intervals and the unqualified sentence is ambiguous.
- Keep “transfer” or “post-hoc follow-up”; do not call this a preregistered replication.
- Keep the explicit statement that baseline-anchored magnitudes are not comparable across
  models.
- Keep the no-inheritance claim for fine-tuned derivatives.
- Do not claim that baseline cancellation causes the two channel estimates to agree. It makes
  the comparison interpretable; the agreement remains empirical.

## Minimal path to submission

1. Correct the walkthrough ledger labels and percentages.
2. Refresh the Qwen extraction artifact.
3. Apply a shortened Stage-2 passage to `democracy_bench.tex` and resolve/add its citations.
4. Build and visually inspect `democracy_bench.pdf`.
5. Scrub or explicitly accept the committed `__cf_bm` response cookies; if repository size
   matters, move the evidence to checksummed release archives with a committed manifest.
6. Commit the final manuscript, bibliography, PDF, refreshed artifact, and evidence manifest.

No additional model call is required.
