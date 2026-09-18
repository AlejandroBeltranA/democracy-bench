# paper/ — frozen design specifications

This folder no longer holds the manuscript. What it holds is the set of **frozen design
documents that the runners read at run time**, which is why the path has to stay exactly where
it is.

Two of them are opened and hashed on every run:

| Document | Read by | Recorded as |
|---|---|---|
| `Q1_PRIORITY0_DESIGN.md` | [`src/alignment/q1_channel.py:35`](../src/alignment/q1_channel.py) | `design_doc` + `design_doc_sha256` in each Q1 channel artifact |
| `Q2_STAGE2_HOSTED_DESIGN.md` | [`src/alignment/q2_hosted.py:62`](../src/alignment/q2_hosted.py) | `design_doc_sha256` in each Stage-2 run manifest |

The point of the hash is that the design cannot be quietly edited after the fact to match a
result. A manifest in `out/` names the SHA-256 of the spec the run was executed under; if the
spec here has changed since, the hashes disagree and you know.

The rest are the requirement sources that the conformance tests cite by requirement ID:

| Document | Requirement IDs | Tested in |
|---|---|---|
| `Q2_STAGE2_RUNNER_REVIEW.md` | R-E1 … R-E7 | `tests/test_q2_v7_ledger.py`, `tests/test_q2_v7_conformance.py` |
| `Q2_STAGE2_HOSTED_DESIGN.md` | R-V7-1 … R-V7-7 | `tests/test_q2_v7_envelope.py`, `tests/test_q2_v7_study_conformance.py` |
| `Q2_STAGE2_FRONTIER_DECISION.md` | S-F1 … S-F6 | `tests/test_q2_v7_conformance.py` |
| `Q2_STAGE2_V72_CODE_REVIEW.md` | R-C1 … R-C6 | `tests/test_q2_v7_study_conformance.py` |
| `FLAGSHIP_AIRTIGHT_PRIORITY_PLAN.md` | scope note | referenced from `src/alignment/q1_channel.py` |

## Where the manuscript went

The AAAI-27 manuscript (`democracy_bench.tex`, its PDF, the bibliography, the reproducibility
checklist and the HTML companion) is **withheld from the public repo while the paper is under
double-blind review**, and is git-ignored here. Publishing an anonymised submission from a
repository under my own name would defeat the anonymity it is submitted under.

Everything the manuscript reports is still here and still checkable without it:

- [`docs/PAPER_RESULTS.md`](../docs/PAPER_RESULTS.md) — every reported number, with its
  artifact path, JSON key path, and originating commit.
- [`docs/REPRODUCTION.md`](../docs/REPRODUCTION.md) — the verbatim command behind each artifact.
- `out/figures/` — the figures, regenerable by `python scripts/make_paper_figures.py`.

I will add the manuscript, or a link to the preprint, once the review concludes.
