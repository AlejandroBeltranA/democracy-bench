# AAAI Submission Readiness Review

Date: 2026-07-20  
Reviewed draft: `paper/democracy_bench.pdf` / `paper/democracy_bench.tex`  
Likely target checked: AAAI-27, especially AISI and AI Alignment fit

## Verdict

Not ready for full AAAI submission yet.

The draft is probably ready for an AAAI-27 abstract submission by the July 21, 2026 abstract deadline if the title and abstract are stable. I would not upload the full paper as-is for the July 28, 2026 full-paper deadline.

## What Is Working

- The compiled PDF is 6 pages, US Letter, anonymous in the rendered author block, and uses embedded Type 1 / TrueType fonts.
- The PDF metadata does not expose an author identity.
- The paper-specific validation tests passed: `88 passed`.
- The full local test suite passed: `401 passed, 1 skipped`.
- The reproduction verifier completed successfully: 19 run-block-verified commands plus 7 asserted-by-doc entries.
- The rendered figures are legible enough for review, though Figure 2 is dense.

## Objective AISI Contribution Critique

This is a real contribution, but it should be framed as an AISI problem-modeling and evaluation paper, not as a new algorithm paper or a deployment paper.

The strongest contribution is the policy-delegate evaluation formulation: a deployed public-sector model should not be evaluated only by whether it resembles a population snapshot. It should be evaluated on whether it can represent a public, be steered, track public preference change over time, and hold rights floors when majority pressure points the other way.

The paper's central scientific result is the "tracks and cracks" asymmetry:

- Evidence-in-context is the only rung that lets the model track a real 2022 to 2024 public-opinion shift.
- The same evidence channel is also the attack surface: hostile synthetic "public opinion" evidence cracks rights floors.
- Prompt guards and the tested lightweight fine-tuning recipe do not close that channel.
- The pattern replicates across model scale and family.

That is the paper's most defensible and memorable contribution. It is policy-relevant because it turns a vague governance question - can a model follow the public without abandoning rights? - into a measurable failure mode.

### AISI Scorecard

| AISI criterion | Current strength | Assessment |
|---|---:|---|
| Significance of the problem | Good / Excellent | Public-sector LLM delegation is significant and under-specified. The policy-delegate framing is timely. |
| Engagement with literature | Fair | Strong on LLM alignment and benchmarks; thin on public administration, democratic theory, social choice, policy legitimacy, and survey methodology. This is the biggest AISI weakness. |
| Significance to the AI community | Good | The tracking/floor split and evidence-channel failure are useful scientific insights for AI evaluation in societal settings. |
| Soundness | Fair / Good | The empirical artifact is strong, but some claims are too broad given one polity, one time interval, synthetic hostile evidence, single-seed local runs, and pending item-class review. |
| Facilitation of follow-up work | Good | Harness, artifacts, tests, and derived targets are a strong point, assuming the anonymous supplement is clean and complete. |
| Scope and promise for social impact | Fair / Good | Clear path to assurance/evaluation practice, but no real deployment, stakeholder study, or field validation. |

### What The Paper Is Not

The draft needs to be disciplined about what it is not claiming:

- It is not proving that LLMs should serve as democratic policy delegates.
- It is not validating a deployable governance system.
- It is not showing social impact in practice.
- It is not establishing a universal democratic-legitimacy benchmark across countries.
- It is not proving that class-aware routing is complete or robust unless item classification is independently validated.

The paper is instead showing that a plausible governance mechanism has a measurable failure mode, and that simple prompt-level or lightweight weight-level fixes do not solve it.

### Best AISI Framing

The contribution should be stated as:

1. A problem formulation for public-sector LLM assurance: representation, steerability, temporal tracking, and rights floors.
2. A survey-grounded evaluation harness that uses human public-opinion distributions rather than LLM judges.
3. An empirical safety finding: the evidence channel that enables public-preference tracking also creates a rights-floor attack surface.
4. A deployment-relevant design principle: public-opinion evidence should be routed by item class, while treating the item classifier as a security and legitimacy boundary.

Suggested contribution paragraph:

> Democracy Bench contributes a problem formulation and evaluation harness for public-sector LLM assurance. Rather than asking whether a model matches a static public-opinion snapshot, it asks whether a model can track a changing public on contestable policy questions while holding rights floors that should not be overridden by majority pressure. The core empirical finding is an asymmetry: evidence-in-context enables limited temporal tracking, but the same channel can be exploited to erode rights floors, and prompt or lightweight fine-tuning guards do not close the channel. The result reframes "democratic alignment" as an assurance problem about evidence routing, item classification, and institutional control.

### Main Reviewer Risk

The biggest objective risk is that AISI reviewers see the draft as "an LLM benchmark using political survey data" rather than "AI for societal governance assurance." To avoid that, the paper needs stronger non-CS grounding and a clearer explanation of how the evaluation would change public-sector AI practice.

Concrete revision goals:

- Add non-CS related work on public administration, administrative justice, democratic legitimacy, public opinion measurement, and social choice / majority constraints.
- Explain why the rights-floor boundary is a social-impact problem-modeling choice, not just a benchmark design detail.
- Make the public-sector assurance workflow explicit: what a deployer would test, what failure would block deployment, and what routing/classification controls would be required.
- Treat item-class labeling as a legitimacy bottleneck and open governance problem, not as a solved internal benchmark choice.
- Soften "demonstrably sufficient" language unless the independent class review is complete.
- Make the social-impact claim about preventing unsafe delegation and improving assurance practice, not about deploying an autonomous policy delegate.

## Submission Blockers

### 1. Visible Bibliography Draft Notes

The reference page still prints draft notes such as:

- `Recent preprint; confirm affiliations/venue before camera-ready`
- `Confirm series/edition numbers for the 2022--2024 waves used`
- `use the version matching the data actually used`

These originate in `paper/references.bib` and are visible in `paper/democracy_bench.pdf`. This is a submission blocker, not polish.

Required fixes:

- Replace the BSA placeholder citation with exact UK Data Service citations for the 2022, 2023, and 2024 collections.
- Update PoliticsBench and ParliaBench metadata from their current arXiv records.
- Remove all reviewer-visible reminder notes from bibliography entries.

Relevant verified sources:

- BSA 2022: UKDS SN 9283, DOI `10.5255/UKDA-SN-9283-2`
- BSA 2023: UKDS SN 9363, DOI `10.5255/UKDA-SN-9363-2`
- BSA 2024: UKDS SN 9478, DOI `10.5255/UKDA-SN-9478-2`
- PoliticsBench arXiv page now notes acceptance to the ICML 2026 Trustworthy AI for Good Workshop.
- ParliaBench arXiv page now lists an LREC 2026 proceedings reference.

### 2. Track Fit Is Unresolved

The TeX source labels the submission as AISI, but the current related-work section is mostly LLM benchmark and steering work. AAAI-27 AISI review criteria explicitly include engagement with literature within and outside computer science, significance of the social-impact problem, facilitation of follow-up work, and likely impact on practice.

Current risk: an AISI reviewer may see the paper as technically interesting but under-grounded in public administration, public opinion measurement, political theory, social choice, public-sector AI governance, or democratic legitimacy literature.

Action:

- Decide whether this is primarily an AISI paper or an AI Alignment paper.
- If AISI: add non-CS context and make the public-sector deployment/social-impact contribution explicit.
- If AI Alignment: frame it around governance frameworks, institutional accountability, pluralistic coordination, and evaluation tools. The current contribution may fit that track more naturally.

### 3. The Architectural Remedy Is Overclaimed

The manuscript says class-aware evidence routing is the "demonstrably sufficient" guard, but the same draft admits that the second-person item-class review is still pending. Since the item classifier is the new security boundary, the pending legitimacy review directly weakens the main remedy.

Current risk: reviewers can fairly object that the paper's proposed fix depends on a classifier whose legitimacy and robustness are not yet independently validated.

Action:

- Either complete and document the independent item-class review before submission, or soften the claim.
- Replace "demonstrably sufficient" with language such as "necessary architectural control under the current item labels" unless the review is completed.
- Add a concrete failure-mode discussion for misclassification, contested rights labels, and adversarial item framing.

### 4. Reproducibility Checklist Is Not Submission-Clean

`paper/ReproducibilityChecklist.pdf` exists as a separate 2-page PDF, which matches AAAI-27's separate-upload requirement. It is not clean yet:

- It still includes the template "Instructions for Authors" block.
- Several answers are `partial` with no explanatory text.
- It does not clearly explain non-redistributable raw survey data, provider credentials, Apple Silicon / MLX requirements, or asserted-by-doc entries.

Action:

- Remove template instructions from the rendered checklist if the official kit permits.
- Add concise explanations for every `partial`.
- Make the checklist consistent with the main paper's limitations and the actual reproduction path.

### 5. Release / Reproducibility Language Is Too Strong

The paper repeatedly says the harness, targets, figures, and results pipeline are released and fully reproducible. The local checks support a strong artifact story, but not an unconditional one:

- Raw BSA/WVS microdata are not redistributable.
- Some reproduction entries are `asserted-by-doc`, not run-block verified.
- Provider credentials are required for cloud/API runs.
- MLX / Apple Silicon and 4-bit quantized checkpoints are part of the local reproduction path.
- Some known irreproducibilities are documented in `docs/REPRODUCTION.md`.

Action:

- Keep the artifact claim, but qualify it precisely.
- Prefer "the released package regenerates the reported numbers from committed derived artifacts; raw survey microdata must be obtained separately" over "fully reproducible" unless all required supplements are packaged and upload-ready.
- Ensure the anonymous code/data supplement actually includes the derived targets, run artifacts, scripts, and reproduction instructions at submission time.

## Minor Issues

- LaTeX reports one small overfull box in Table 1.
- Figure 2 is dense and could be enlarged or simplified if space allows.
- `paper/ReproducibilityChecklist.pdf` is older than the current manuscript PDF.
- The first-page anonymous submission notice comes from the AAAI style file, so it is not a custom anonymity problem.

## Evidence Checked

Commands run during review:

```bash
pdfinfo paper/democracy_bench.pdf
pdffonts paper/democracy_bench.pdf
pdftotext -layout paper/democracy_bench.pdf -
pdftoppm -r 160 -png paper/democracy_bench.pdf /private/tmp/democracy_bench_pdf_review/main
python -m pytest tests/test_paper_extract.py tests/test_repro_reference.py tests/test_paper_figures.py
python scripts/verify_repro_reference.py
python scripts/extract_paper_results.py
python -m pytest -q
```

Observed results:

- `paper/democracy_bench.pdf`: 6 pages, US Letter, embedded fonts, no visible author metadata.
- Paper-specific tests: `88 passed`.
- Full suite: `401 passed, 1 skipped`.
- Reproduction verifier: 26 fenced commands parsed; 19 run-block verified; 7 asserted-by-doc.
- Build logs: no undefined citations or references; one small overfull hbox in the rights-floor table.

## Official Sources Consulted

- AAAI-27 submission instructions: https://aaai.org/conference/aaai/aaai-27/submission-instructions/
- AAAI-27 main technical call: https://aaai.org/conference/aaai/aaai-27/main-technical-track-call/
- AAAI-27 supplementary material page: https://aaai.org/conference/aaai/aaai-27/supplementary-material/
- AAAI-27 AISI call: https://aaai.org/conference/aaai/aaai-27/aisi-call/
- BSA 2022 UKDS page: https://doc.ukdataservice.ac.uk/doc/9283/mrdoc/UKDA/UKDA_Study_9283_Information.htm
- BSA 2023 UKDS page: https://doc.ukdataservice.ac.uk/doc/9363/mrdoc/UKDA/UKDA_Study_9363_Information.htm
- BSA 2024 UKDS page: https://doc.ukdataservice.ac.uk/doc/9478/mrdoc/UKDA/UKDA_Study_9478_Information.htm
- PoliticsBench arXiv page: https://arxiv.org/abs/2603.23841
- DeliberationBench arXiv page: https://arxiv.org/abs/2603.10018
- ParliaBench arXiv page: https://arxiv.org/abs/2511.08247

## Recommended Priority Order

1. Fix bibliography placeholders and exact data citations.
2. Decide AISI vs AI Alignment and rewrite framing accordingly.
3. Complete or soften the class-aware-routing remedy claim.
4. Clean and explain the reproducibility checklist.
5. Package anonymous code/data supplement and align release language with what is actually included.
6. Rebuild PDFs, rerun paper tests and full tests, and re-render pages for final visual inspection.

---

## Response and Completion Log (Claude, 2026-07-20)

Second independent read of the same draft, plus the fixes actually applied. The two
reviews converge on the big picture, which is the useful signal: **the contribution is a
problem formulation + evaluation, not an algorithm or a deployment; the "tracks and
cracks" asymmetry is the memorable result; literature grounding and scope are the
weaknesses; the remedy is a diagnosis's argument, not a validated cure.**

### Where the two reviews differ

- **Statistical fragility of the flagship (Claude adds).** The one positive rung, tracking,
  is elasticity +0.395 with a CI of [+0.020, +0.811] that *barely* clears zero, on 10
  items, single seed, one 2022->2024 interval. The whole "tracks and cracks" arc pivots on
  it. Codex's soundness row flags breadth (one polity, one interval) but not this
  within-result fragility, which is what a statistically-minded reviewer will actually
  press. Addressed by framing, not new data (see below); author judged flagship-thickening
  low-value at this stage.
- **The crack is partly definitional (Claude adds).** A channel built to *track* a
  distribution tracks a hostile one near-tautologically. The defensible novelty is the
  *asymmetry* (evidence cracks, identical prompt is inert) plus the guard/fine-tune
  failures, not the bare crack. Codex bills the crack itself as the headline; the paper now
  narrows the claim explicitly.
- **Codex is sharper on AISI positioning.** Its assurance-workflow framing, the "What The
  Paper Is Not" discipline list, and the AISI-rubric scorecard are better than Claude's
  free-form critique and were adopted largely as proposed.

### Completed (this session)

All five mechanical blockers are resolved, and the framing is reworked to the reviews'
shared recommendation. Verified: paper compiles clean, content within the 7-page limit
(references on pp. 6-7 do not count), no undefined citations, no reviewer-visible draft
notes; 88 paper tests pass; repro verifier 19 run-block-verified + 7 asserted-by-doc.

- **Blocker 1 (bibliography):** removed every reviewer-visible reminder note; replaced the
  placeholder survey cite with verified UK Data Service entries. **Correction to this
  audit:** Scotland coverage is Scottish Social Attitudes (ScotCen), a series separate from
  BSA that the audit omitted; added `@ssa` (SN 9296/9364/9557, DOIs verified) alongside
  `@bsa` (SN 9283/9363/9478) and fixed the in-text attribution. PoliticsBench -> ICML 2026
  Trustworthy AI for Good Workshop; ParliaBench -> LREC 2026 pp. 4797-4818 (both arXiv-verified).
- **Blocker 2 (track fit):** author chose **keep AISI + add grounding.** New democratic-theory
  Related Work paragraph (Pitkin mandate-independence; Dahl majority rule + inclusion; Page &
  Shapiro policy responsiveness; Binns political philosophy for ML), all four web-verified.
- **Blocker 3 (overclaim):** "demonstrably sufficient" scoped to *closing the evidence
  channel* in abstract and Sec. Routing; added the concrete classifier failure modes
  (misclassification, contested labels, adversarial framing). Contribution (4) reframed
  "architectural remedy" -> "design principle."
- **Blocker 4 (checklist):** removed the template instructions block; a justification added
  to every `partial` and the login-gated data answers (non-redistributable microdata,
  provider credentials, MLX/Apple Silicon, asserted-by-doc). 2 pages, clean.
- **Blocker 5 (release language):** qualified to "regenerates every number from committed
  *derived* artifacts; raw microdata login-gated, obtained separately."
- **Assurance/diagnosis reframing (both reviews):** Discussion now opens by casting the
  harness as an assurance instrument with an explicit deployer workflow, including "treat a
  floor crack under hostile evidence as a deployment blocker, not a tuning target"; the
  crack novelty is narrowed to the asymmetry; a "What we do not claim" paragraph was added.

### Superseded by an author decision

- The **second-person item-class review** that this audit treats as a legitimacy bottleneck
  (Blocker 3, the soundness row, "What The Paper Is Not" #5) is **not a requirement** per the
  author; it was removed as a stated pending obligation and replaced with the honest framing
  that the floor/contestable labels are a stated, revisable normative choice a deployer can
  adapt. The reviewer *question* ("what legitimates these labels?") does not vanish; the
  grounding paragraph plus the "revisable choice" framing now carry it.

### Not done (by choice)

- **Flagship-thickening** (more items / intervals / a frontier-model crack) is deferred:
  author judged it low-value versus the framing work with the deadline in view. The abstract
  can be registered (07-21) to keep the 07-28 full-paper option open, but the plan is to
  finish fully.
- Remaining human-only: pick the AISI keyword on the submission form; package and check the
  anonymous code/data supplement for upload.
