# AAAI AISI Submission Readiness

Date: 2026-07-20  
Current draft: `paper/democracy_bench.pdf` / `paper/democracy_bench.tex`  
Target: AAAI-27 Special Track on AI for Social Impact (AISI)

## Current Verdict

The paper is now close to submission-ready for AISI. The major conceptual issues from the first review have been addressed: the paper is framed as a public-sector assurance/evaluation contribution, the bibliography placeholders were fixed, the checklist was cleaned up, the release language was qualified, and the routing remedy was narrowed from a cure to a design principle.

What remains is final submission hygiene: clean source/logs, package the anonymous supplement, rerun verification, and keep the claims disciplined.

## Contribution Assessment

This is a real AISI contribution, but its contribution type is specific:

- It is a problem-modeling and evaluation paper.
- It is not a new algorithm paper.
- It is not a deployment paper.
- It is not evidence that LLMs should serve as democratic policy delegates.

The strongest contribution is the policy-delegate evaluation formulation. Existing opinion-alignment benchmarks mostly ask whether a model resembles a population snapshot. Democracy Bench asks whether a model can represent a public, be steered, track public preference change over time, and hold rights floors when majority pressure points the other way.

The central scientific result is the evidence-channel asymmetry:

- Evidence-in-context is the only rung that enables limited tracking of a real 2022 to 2024 public-opinion shift.
- The same evidence channel is also the attack surface: hostile synthetic "public opinion" evidence cracks rights floors.
- The adversarial prompt alone does not produce the same effect.
- Prompt guards and the tested lightweight fine-tuning recipe do not close the channel.
- The pattern replicates across model scale and family.

This should be framed as an assurance result: a plausible public-sector governance mechanism has a measurable failure mode that simple prompt- and weight-level fixes do not close.

## AISI Fit

The current framing is much better for AISI than the first draft. The paper now has a clearer social-impact claim: it helps public-sector deployers test and block unsafe delegation before deployment.

Reviewer-facing strengths:

- Significant problem: public-sector LLM delegation is timely and under-specified.
- Clear evaluation contribution: representation, steerability, tracking, and rights floors are separated instead of collapsed into one alignment score.
- Judge-free measurement: human survey distributions are used rather than LLM judges.
- Useful failure mode: the evidence channel that enables tracking can also erode rights floors.
- Follow-up potential: harness, item banks, derived targets, figures, tests, and reproduction scripts support extension.

Reviewer-facing risks:

- The flagship positive is statistically fragile: elasticity `+0.395`, CI `[+0.020, +0.811]`, 10 items, one polity, one interval.
- The bare hostile-evidence crack is partly definitional; the novelty is the asymmetry plus guard/fine-tune failures.
- The floor/contestable boundary is a normative choice, not a settled fact.
- There is no live deployment, stakeholder study, or field validation.
- Single-seed 4-bit local model results and API/provider dependencies need to stay visible as limitations.

## Claim Discipline

Keep these claims:

- "Evidence-in-context enables limited temporal tracking."
- "The same evidence channel creates a rights-floor attack surface."
- "The asymmetry is deployment-relevant: evidence cracks floors while the adversarial prompt alone does not."
- "Class-aware routing is a design principle / necessary control for this channel."
- "The harness is an assurance instrument, not a deployed governance system."

Avoid or soften these claims:

- Do not imply that tracking is solved.
- Do not headline the hostile-evidence crack alone as if it were surprising by itself.
- Do not describe class-aware routing as a complete or independently validated governance cure.
- Do not imply demonstrated social impact in practice.
- Do not call the artifact "fully reproducible" without qualifying raw microdata, provider credentials, MLX/Apple Silicon, and asserted-by-doc entries.

## Already Resolved

- Bibliography draft notes were removed from reviewer-visible references.
- BSA and SSA citations were replaced with exact UK Data Service study numbers and DOIs.
- Recent arXiv/workshop/proceedings metadata were updated for PoliticsBench and ParliaBench.
- AISI grounding was added through democratic theory and public-sector assurance framing.
- The routing claim was scoped to closing the evidence channel under current item labels.
- Concrete classifier failure modes were added.
- The reproducibility checklist now explains partial answers and login-gated data.
- Release language now distinguishes committed derived artifacts from raw survey microdata.
- The discussion now includes an assurance workflow and a "What we do not claim" paragraph.

## Remaining Work

### 1. Clean the final PDF and LaTeX logs

Required:

- Strip drafting aids from `paper/democracy_bench.tex`: `xcolor`, `\todo`, `\verifyc`, and associated drafting comments.
- Fix the small overfull Table 1 warning.
- Rebuild from scratch.
- Confirm no undefined citations, no unresolved references, no reviewer-visible draft notes, and embedded fonts.

Current known state:

- `paper/democracy_bench.pdf` is 7 pages.
- Fonts are embedded.
- Paper tests pass.
- One small overfull table warning remains.
- Drafting macros remain in source but do not appear in the rendered PDF.

### 2. Package the anonymous supplement

Include:

- Code needed to regenerate reported derived results.
- Derived aggregate targets.
- Run artifacts under `out/` that support reported claims.
- Figures and figure-generation scripts.
- Reproduction instructions.
- Citation and data-provenance manifests.
- Reproducibility checklist PDF.

Exclude:

- Raw UKDS/GESIS microdata.
- Provider credentials or `.env`.
- Local user paths.
- Author names, institution names, acknowledgements, or non-anonymous metadata.
- Anything that violates data-provider terms.

Check that the supplement wording matches the paper and checklist: derived artifacts are released; raw survey microdata must be obtained separately.

### 3. Rerun verification after final rebuild

Run:

```bash
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
```

Also run PDF checks:

```bash
pdfinfo paper/democracy_bench.pdf
pdffonts paper/democracy_bench.pdf
pdftotext -layout paper/democracy_bench.pdf -
```

Render and inspect:

- `paper/democracy_bench.pdf`
- `paper/ReproducibilityChecklist.pdf`

### 4. Final submission-form choices

Deadlines checked:

- Abstract deadline: July 21, 2026
- Full paper deadline: July 28, 2026
- Supplement/code deadline: July 31, 2026

Recommended AISI keywords:

- Policy and Social Development
- Computational Social Science and Humanities
- Philosophical and Ethical Issues

## Repo Submission Preparation Plan

Goal: produce two clean submission artifacts from the repo:

1. `paper/democracy_bench.pdf` plus `paper/ReproducibilityChecklist.pdf`
2. An anonymous supplement archive containing only code, derived data, run artifacts, figures, and reproduction instructions that can be shared under the stated license and data-provider constraints.

### Step 0. Freeze the intended submission state

Before packaging, decide exactly which working-tree changes belong in the submission state.

Current caution:

- `README.md`, `scripts/run_all.sh`, and `tests/test_repro_reference.py` are modified in the working tree.
- Do not package from an ambiguous dirty tree unless those changes are intentionally part of the submission state.

Recommended workflow:

```bash
git status --short --branch
git diff --stat
git diff -- README.md scripts/run_all.sh tests/test_repro_reference.py
```

Then either commit the intended changes or make a written note that the supplement was built from a dirty tree. The cleaner option is to commit a final "submission prep" commit after verification.

### Step 1. Clean paper source and rebuild PDFs

Source cleanup:

- Remove drafting-only LaTeX aids from `paper/democracy_bench.tex`: `xcolor`, `\todo`, `\verifyc`, and associated comments.
- Fix the remaining small overfull Table 1 warning.
- Keep `\usepackage[submission]{aaai2027}` for double-blind review.
- Do not edit `paper/aaai2027.sty` or `paper/aaai2027.bst`.

Build:

```bash
cd paper
latexmk -pdf democracy_bench.tex
latexmk -pdf ReproducibilityChecklist.tex
cd ..
```

Log checks:

```bash
rg -n "Undefined|undefined|Citation|Reference|Overfull|Error|Emergency|rerun|There were|Package natbib Warning" \
  paper/democracy_bench.log paper/ReproducibilityChecklist.log
```

PDF checks:

```bash
pdfinfo paper/democracy_bench.pdf
pdffonts paper/democracy_bench.pdf
pdftotext -layout paper/democracy_bench.pdf - | rg -n "TODO|TBD|confirm|camera-ready|placeholder|author|affiliation|acknowledg"
```

Expected final state:

- No undefined citations or references.
- No reviewer-visible draft notes.
- Fonts embedded.
- Main PDF stays within AAAI page limits.
- Checklist PDF is separate and clean.

### Step 2. Create a supplement staging directory

Build the supplement in a staging directory rather than zipping the repo root directly.

Suggested layout:

```text
submission_supplement/
  README.md
  LICENSE
  CITATION.cff
  DATA.md
  pyproject.toml
  src/
  scripts/
  tests/
  data/
  annotations/
  out/
  docs/
  paper/
```

Include from `paper/`:

- `democracy_bench.tex`
- `references.bib`
- `ReproducibilityChecklist.tex`
- `ReproducibilityChecklist.pdf`
- final figure PDFs/PNGs if needed for rebuild

Do not include from `paper/` unless required:

- LaTeX temporary files: `.aux`, `.bbl`, `.blg`, `.log`, `.fls`, `.fdb_latexmk`, `.synctex.gz`
- AAAI style files if redistribution is prohibited by the author kit/license. If excluded, state in supplement README that the AAAI-27 author kit is required to rebuild the PDF.

### Step 3. Exclude sensitive or non-redistributable files

Hard exclusions:

- `.git/`
- `.env` and any credential/config secret
- raw UKDS/GESIS microdata, especially `data/bsa microdata/`
- local virtualenvs and caches: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`
- local app/plugin files: `.claude/`, `.codex/`, editor settings if they identify the author
- generated logs that expose local paths or usernames
- any file containing `/Users/`, personal names, emails, API keys, or provider tokens

Large-file decision:

- Do not include base model checkpoints.
- Include derived JSON artifacts that support claims.
- For LoRA adapter weights (`out/lora_deference_adapter/*.safetensors`), make an explicit decision:
  - Include only if size and licensing permit and the adapter is needed for reproduction.
  - Otherwise include the training recipe, design split, eval artifact, and instructions to regenerate the adapter.

Audit commands:

```bash
rg -n "OPENROUTER|OPENAI|ANTHROPIC|API_KEY|TOKEN|SECRET|/Users/|abeltran|gmail|@|\\.env|bsa microdata|UKDA.*\\.tab|\\.zip" \
  submission_supplement

find submission_supplement -name ".git" -o -name ".env" -o -name "__pycache__" -o -name ".pytest_cache"
```

Any hit must be inspected manually; not every `@` is a leak, but every credential/path hit is a blocker.

### Step 4. Write supplement README instructions

The supplement README should be short and direct. It should include:

- What is included: code, derived targets, run artifacts, figures, tests.
- What is not included: raw BSA/SSA/WVS microdata, provider credentials, base model weights.
- Data access note: raw survey microdata must be obtained from UK Data Service / WVS or GESIS directly.
- Environment note: local model reproduction uses Apple Silicon + MLX / `mlx-lm`; cloud-panel reproduction requires provider credentials.
- Minimal verification commands:

```bash
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
```

- Full rebuild note: PDF rebuild requires AAAI-27 author-kit style files if they are not redistributed in the supplement.

Suggested README wording:

> This supplement contains the code, derived aggregate targets, run artifacts, figures, and tests needed to regenerate the reported quantitative claims from committed derived artifacts. It does not redistribute raw survey microdata or base model weights. Raw survey data must be obtained from the UK Data Service and WVS/GESIS under their terms. Some cloud-model reproduction requires provider credentials; local open-weight runs require Apple Silicon and MLX/`mlx-lm`.

### Step 5. Produce the archive

After staging and auditing:

```bash
zip -r democracy_bench_aaai27_supplement.zip submission_supplement
```

Then inspect the archive contents:

```bash
unzip -l democracy_bench_aaai27_supplement.zip | rg -n "\.git|\.env|bsa microdata|__pycache__|pytest_cache|/Users|\.zip$"
```

Do not upload until this inspection is clean.

### Step 6. Final verification record

Create a short final record, either in a commit message or a local note, containing:

- Git commit SHA used for the final PDF and supplement.
- Main PDF page count.
- Checklist PDF page count.
- Paper-specific test result.
- Repro verifier result.
- Full test-suite result.
- Supplement archive filename and size.
- Statement that raw microdata and credentials were excluded.

Recommended final commands:

```bash
git rev-parse HEAD
pdfinfo paper/democracy_bench.pdf | rg "Pages|Page size|File size"
pdfinfo paper/ReproducibilityChecklist.pdf | rg "Pages|Page size|File size"
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
du -h democracy_bench_aaai27_supplement.zip
```

## Verification Status

Most recent checks observed:

- Paper-specific tests: `88 passed`
- Reproduction verifier: 19 run-block verified, 7 asserted-by-doc
- Full suite from earlier review: `401 passed, 1 skipped`
- Current PDF: 7 pages, US Letter, embedded fonts

Rerun all checks after any final edits or supplement packaging.

## Bottom Line

Do not spend deadline time adding new experiments unless one is already essentially complete. The remaining risk is presentation, claim calibration, source/log cleanliness, and anonymous packaging. The contribution is now clear enough for AISI if the final submission makes the assurance framing explicit and does not overstate the fragile tracking result or the routing remedy.
