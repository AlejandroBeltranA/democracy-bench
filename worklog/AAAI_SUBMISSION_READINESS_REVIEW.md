# AAAI AISI Submission Readiness

Date: 2026-07-21

Current draft:

- Main paper: `paper/democracy_bench.pdf` / `paper/democracy_bench.tex`
- Checklist: `paper/ReproducibilityChecklist.pdf` / `paper/ReproducibilityChecklist.tex`
- Target: AAAI-27 Special Track on AI for Social Impact (AISI)

Official AAAI pages checked:

- Submission instructions: https://aaai.org/conference/aaai/aaai-27/submission-instructions/
- AISI call: https://aaai.org/conference/aaai/aaai-27/aisi-call/
- Supplementary material: https://aaai.org/conference/aaai/aaai-27/supplementary-material/

## Current Verdict

The paper itself is close to submission-ready for AISI. The extensive edits materially improved the
track fit: the paper now reads as a public-sector assurance and evaluation contribution, not as a
generic alignment benchmark or a premature deployment claim.

Do not submit the current supplement zip. The remaining blocker is packaging, not the core
manuscript. `democracy_bench_aaai27_supplement.zip` is stale relative to `HEAD`, includes
reviewer-facing stale/internal material, and needs to be rebuilt from a strict allowlist.

## Current Verification Snapshot

Observed on 2026-07-21:

- Git branch: `phase4-floor-guards`
- Worktree: clean
- `HEAD`: `0c1a8ca2046cce57b818019623fedaff3cd349c9`
- Main PDF: 8 pages, US Letter, anonymous author line, embedded fonts, no Type 3 fonts
- Checklist PDF: 2 pages, US Letter, embedded fonts
- Current LaTeX logs: no undefined citations/references and no overfull boxes in
  `paper/democracy_bench.log` or `paper/ReproducibilityChecklist.log`
- Stale log warning: `paper/build.log` still contains old undefined `ssa` and overfull warnings;
  exclude or regenerate it
- Paper-specific tests: `91 passed`
- Reproduction verifier: `20` run-block verified, `7` asserted-by-doc
- Full test suite: `404 passed, 1 skipped`

Commands run:

```bash
git status --short --branch
pdfinfo paper/democracy_bench.pdf
pdffonts paper/democracy_bench.pdf
pdfinfo paper/ReproducibilityChecklist.pdf
pdffonts paper/ReproducibilityChecklist.pdf
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
```

Visual check:

- Page 1: anonymous and readable.
- Page 5: cross-family/frontier result is coherent and visually intact.
- Page 6: social-impact discussion and figures are dense but acceptable.
- Page 7: technical content, checklist-style reproducibility, conclusion, ethical statement, and
  start of references fit before the page limit boundary.
- Page 8: references only.

## Objective Contribution Assessment

This is now a credible AISI submission, with a specific contribution type:

- Problem modeling for public-sector LLM delegation.
- Evaluation methodology, not a new model or algorithm.
- Assurance tooling, not field deployment.
- Empirical evidence of a channel-specific governance failure mode.

The core contribution is the policy-delegate evaluation formulation. The paper separates four things
that ordinary "alignment" or opinion-representation scores collapse:

- Representation: does the model match a current public distribution?
- Steerability: can the model be moved to a target distribution?
- Tracking: does it move when public opinion moves?
- Rights floors: does it preserve non-negotiable protections under majority pressure?

The strongest empirical result is not "hostile evidence cracks floors" by itself. That part is close
to expected by construction. The contribution is the asymmetry:

- Evidence-in-context is the only rung that gives a real tracking signal.
- The same evidence channel is the attack surface.
- The adversarial prompt alone does not have the same effect.
- Prompt guards and the tested LoRA do not close the channel.
- The pattern replicates across scale and family.
- The floor crack reaches a hosted frontier model, `gpt-4o-mini`, even though the frontier result is
  only a crack reproduction, not a tracking reproduction.

That makes the paper useful as an assurance result: a plausible governance channel for aligning a
model to public input has a measurable, reproducible failure mode that simple prompt- and
weight-level fixes do not close.

## AISI Fit

The fit is now substantially stronger than the earlier draft.

Strengths:

- The problem is socially important and concrete: public-sector models making or shaping decisions
  about real people.
- The contribution engages problem modeling and social-impact evaluation, which AISI explicitly
  values.
- The democratic-theory framing now does real work: representation, responsiveness, and rights are
  not decorative citations.
- The artifact is useful beyond the paper: harness, item banks, derived targets, run artifacts,
  figures, tests, and reproduction mapping.
- The revised discussion frames deployment consequences without pretending there has been live
  deployment impact.

Remaining acceptance risks:

- The positive tracking result remains thin: one polity, one 2022->2024 interval, ten trackable
  items, CIs that barely clear zero for the primary 3B.
- The rights-floor taxonomy is a normative boundary; the paper now admits this, but reviewers may
  still disagree with specific floor labels.
- The hostile-evidence distribution is synthetic red-team data. That is acceptable, but the paper
  must keep saying it.
- The frontier result strengthens transfer, but it is hosted, unpinned, and API-dependent. The
  limitation paragraph is necessary and should stay.
- This is not a stakeholder-engagement or deployment study. Submit it as an assurance benchmark,
  not as evidence of realized social impact.

## Resolved Since Earlier Reviews

- Title and abstract now carry the public/rights framing.
- Related work now includes democratic representation, responsiveness, and rights.
- The "only local open-weight models" generalization gap is partly closed by the `gpt-4o-mini`
  floor-crack reproduction.
- The paper correctly says the frontier result is a crack reproduction, not full tracking.
- The BSA-only results path is clearer; SSA is no longer implied as used in the paper.
- Class-aware routing is scoped as a necessary architectural control under current labels, not a
  complete governance system.
- The limitations section now explicitly covers single-seed quantized local results, synthetic
  hostile evidence, normative floor labels, BSA non-redistribution, and hosted model drift.
- The reproducibility checklist now states that code/data are included in the supplement rather than
  deferred to publication.

## Remaining Blockers

### P1. Rebuild the Supplement From a Strict Allowlist

Current `democracy_bench_aaai27_supplement.zip` should not be uploaded.

Observed issues:

- It was produced around commit `6b6826f`, while current `HEAD` is `0c1a8ca`.
- It includes `submission_supplement/paper/README.md`, which says:
  `Mistral/Gemma dropped, see paper text`; that is stale and contradicts the current paper.
- It includes `submission_supplement/CITATION.cff` with a placeholder GitHub URL.
- It includes internal "Codex" language in data/provenance files.
- It includes `submission_supplement/data/targets/public_opinion_counterargument.md`, which still
  has a section titled "Open Questions For Claude".
- It includes legacy/superseded artifacts such as `out/policy_drift.json` and WVS scenario files
  that are not needed for the current BSA-only paper claims and create avoidable confusion.

The current zip does avoid raw microdata and `.env`, but that is not enough. Rebuild it.

### P1. Do Not Zip the Repo Root

The live workspace contains files that must not enter an anonymous supplement:

- `.env`
- `data/bsa microdata/`
- `data/wvs microdata/`
- `.venv/`
- `.claude/`
- `.inspect-traces/`
- logs and caches
- root docs with personal/internal/build-history context
- ignored `democracy_bench_aaai27_supplement.zip`

The raw microdata directories are present locally and ignored by git. A manual zip of the workspace
would violate the data-provider and anonymity constraints.

### P1. Sanitize Reviewer/Author Metadata in Included Data Files

If `data/policy_items.jsonl`, `data/floor_review_signoff.json`, `DATA.md`, or provenance manifests
are included, they need an anonymization pass. In the live repo these files contain reviewer names
or local provenance language. Either remove those fields from the supplement or rewrite them to
anonymous role labels such as `reviewer_1`.

### P2. Exclude Stale Build Artifacts

Do not include:

- `paper/build.log`
- `paper/*.aux`
- `paper/*.bbl`
- `paper/*.blg`
- `paper/*.log`
- `paper/companion.html`

The current main LaTeX log is fine, but `paper/build.log` contains stale warnings from an earlier
draft. Logs are not needed in the supplement and create avoidable reviewer noise.

### P2. Keep Page Budget Tight

The PDF is 8 pages, with page 8 references only. That is acceptable under the AAAI technical-page
rule because technical content fits within the first 7 pages and references continue after. Do not
add technical text unless something else is removed.

### P2. Prepare a Short OpenReview Abstract

The paper abstract is good but dense. The submission form may be easier with a shorter abstract that
keeps the same spine:

- public-sector delegation problem
- representation/tracking/rights-floor split
- evidence-in-context tracks but is the attack surface
- cracks replicate across scale/family and on `gpt-4o-mini`
- class-aware routing is necessary but not complete

## Repo Submission Preparation Plan

Goal:

1. Submit `paper/democracy_bench.pdf` as the main paper.
2. Upload `paper/ReproducibilityChecklist.pdf` separately, as AAAI requires.
3. Upload a clean anonymous supplement archive that contains only redistributable code, derived
   data, artifacts, figures, and instructions.

### Step 1. Freeze the Submission Commit

Use the clean current state or make a final submission-prep commit after packaging fixes.

```bash
git status --short --branch
git rev-parse HEAD
```

Record the final SHA in `SUPPLEMENT_README.md`.

### Step 2. Rebuild/Confirm PDFs

```bash
cd paper
latexmk -pdf democracy_bench.tex
latexmk -pdf ReproducibilityChecklist.tex
cd ..
```

Check:

```bash
rg -n "Undefined|undefined|Citation|Reference|Overfull|Error|Emergency|rerun|There were|Package natbib Warning" paper/democracy_bench.log paper/ReproducibilityChecklist.log
pdfinfo paper/democracy_bench.pdf
pdffonts paper/democracy_bench.pdf
pdfinfo paper/ReproducibilityChecklist.pdf
pdffonts paper/ReproducibilityChecklist.pdf
pdftotext -layout paper/democracy_bench.pdf - | rg -n "TODO|TBD|placeholder|camera-ready|acknowledg"
```

Expected:

- Main PDF remains 8 pages with page 8 references only.
- Checklist remains separate.
- No Type 3 fonts.
- No undefined citations/references.
- No reviewer-visible draft notes.

### Step 3. Stage a Fresh Supplement Directory

Create a new directory, for example:

```text
submission_supplement/
  SUPPLEMENT_README.md
  LICENSE
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

Prefer a minimal allowlist over copying entire directories.

Include:

- `src/alignment/` code required by paper extraction and reproduction
- `scripts/extract_paper_results.py`
- `scripts/verify_repro_reference.py`
- `scripts/make_paper_figures.py`
- other scripts directly referenced by `docs/REPRODUCTION.md`
- tests needed for the paper/repro/figure verification path
- `docs/REPRODUCTION.md`
- `docs/PAPER_RESULTS.md`
- `annotations/rationale_codesheet*.csv` and scorer inputs required by the construct-validity claim
- `data/public_opinion_bsa_regions.json`
- current item banks and constitutions, sanitized where needed
- derived aggregate targets and inventories used by the paper
- only `out/*.json` artifacts that support reported claims or are required by verifier tests
- `out/figures/f1_ladder.*`, `f2_tracking.*`, `f3_floors.*`, `f6_crossfamily.*`, `f7_reflex.*`
- `paper/democracy_bench.tex`
- `paper/references.bib`
- `paper/ReproducibilityChecklist.tex`

Strongly consider excluding:

- root `README.md`
- root `DATA.md`
- `paper/README.md`
- `CITATION.cff`
- WVS legacy demos/scenarios unless a specific test or cited claim requires them
- `out/policy_drift.json`
- `paper/companion.html`

If any of those are included, sanitize and update them first.

### Step 4. Write a Supplement README for Reviewers

The supplement README should be the only prose entry point. It should say:

- This is an anonymous AAAI-27 supplement.
- It contains code, derived aggregate targets, run artifacts, figures, and tests.
- It does not contain raw BSA/WVS/GESIS microdata, provider credentials, or model weights.
- Raw survey microdata must be obtained directly from the UK Data Service and WVS/GESIS.
- Some cloud-model reproduction requires provider credentials.
- Local open-weight reproduction assumes Apple Silicon plus MLX / `mlx-lm`.
- The paper's quantitative claims can be regenerated from committed derived artifacts.
- The `gpt-4o-mini` frontier result is provider/API-dependent and may drift.

Minimal verification commands:

```bash
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
```

### Step 5. Audit the Staged Supplement

Run these against the staged directory before zipping:

```bash
rg -n "OPENROUTER|OPENAI|ANTHROPIC|API_KEY|TOKEN|SECRET|/Users/|abeltran|gmail|@|\\.env|bsa microdata|wvs microdata|UKDA.*\\.tab|\\.zip|PLACEHOLDER|Claude|Codex" submission_supplement
find submission_supplement -name ".git" -o -name ".env" -o -name "__pycache__" -o -name ".pytest_cache" -o -name "*.log" -o -name "*.aux" -o -name "*.blg" -o -name "*.bbl"
```

Every hit needs manual review. Some terms such as `OpenAI`, `Anthropic`, or `Claude` are legitimate
model/provider names in the paper context; personal names, local paths, placeholders, credentials,
raw microdata paths, and internal build-agent references are blockers.

Then test from the staged directory:

```bash
cd submission_supplement
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
cd ..
```

### Step 6. Build and Inspect the Archive

```bash
zip -r democracy_bench_aaai27_supplement.zip submission_supplement
unzip -l democracy_bench_aaai27_supplement.zip
zipgrep -n "OPENROUTER\\|OPENAI\\|ANTHROPIC\\|API_KEY\\|TOKEN\\|SECRET\\|/Users/\\|abeltran\\|gmail\\|\\.env\\|bsa microdata\\|wvs microdata\\|PLACEHOLDER\\|Claude\\|Codex" democracy_bench_aaai27_supplement.zip
```

Do not upload until the archive inspection is clean or all remaining hits are legitimate model or
provider references.

### Step 7. Final Verification Record

Record:

- final git SHA
- main PDF page count
- checklist PDF page count
- paper-specific test result
- reproduction verifier result
- full test-suite result
- supplement archive filename and size
- statement that raw microdata, credentials, model weights, local paths, and identifying metadata
  were excluded

Suggested commands:

```bash
git rev-parse HEAD
pdfinfo paper/democracy_bench.pdf | rg "Pages|Page size|File size"
pdfinfo paper/ReproducibilityChecklist.pdf | rg "Pages|Page size|File size"
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python -m pytest -q
du -h democracy_bench_aaai27_supplement.zip
```

## Claim Discipline for Final Submission

Keep:

- "Democracy Bench is an assurance harness for public-sector policy-delegate risk."
- "Evidence-in-context enables limited tracking of a real public-opinion shift."
- "The same evidence channel is a rights-floor attack surface."
- "The channel asymmetry is the finding: hostile evidence cracks floors; the adversarial prompt
  alone does not."
- "Class-aware evidence routing is a necessary control under current labels, not a complete
  governance system."
- "`gpt-4o-mini` reproduces the floor crack; the open-weight families track and crack."

Avoid:

- "Tracking is solved."
- "The hostile-evidence crack alone is surprising."
- "Routing solves governance."
- "The paper demonstrates live social impact."
- "The artifact is fully reproducible" without the raw-microdata/provider/model caveats.
- "Frontier models track and crack" unless also saying only the crack was reproduced on
  `gpt-4o-mini`.

## Bottom Line

Submit the paper after final packaging, not after new experiments. The revised contribution is now
clear enough for AISI: it offers a concrete assurance benchmark and a channel-specific failure mode
for public-sector LLM delegation. The remaining work is to make the artifact anonymous,
redistributable, current, and boring to inspect.
