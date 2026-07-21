# Pre-submission review plan (adversarial review of 2026-07-21)

Source: Claude's adversarial review of `democracy_bench.tex`, run against the reviewer
objections most likely at AAAI-27 AISI. Abstract registered 2026-07-21; full paper due
2026-07-28. Each proposed edit and experiment below is for Alex to accept or reject;
nothing beyond Part A has been applied.

Verdict key: `[ ]` undecided, `[Y]` do it, `[N]` rejected, `[D]` done.

---

## Part A: applied 2026-07-21 (already in the registered version)

- Abstract: "The only guard we found to close this channel" replaced with "The remaining
  guard is architectural ... closing the channel by construction". Reason: routing is
  demonstrated by construction, not by a run; the old wording overclaims and would be
  falsified if the classifier experiment (X4) partially fails.
- Abstract: "a frontier model: gpt-4o-mini" replaced with "a hosted proprietary model".
- Body: all five remaining "frontier" uses swept to hosted/proprietary/API wording
  (lines around the Table 1 note, S5.6, the f6 caption, and Limitations).
- Figure f6: in-figure label "gpt-4o-mini (frontier)" regenerated as "gpt-4o-mini (API)"
  (`scripts/make_paper_figures.py` plus its test assertions; 35/35 figure tests pass;
  f1/f4/f5 byte changes are font-subsetting noise, visually identical; extractor key
  `frontier_crack_gpt4omini` left untouched, it is an artifact key, not display text).
- PDF rebuilt, 8 pages, zero LaTeX warnings, zero "frontier" occurrences.

---

## Part B: proposed paper edits (writing only, no new runs)

| id | verdict | where | change | reviewer objection it answers |
|----|---------|-------|--------|-------------------------------|
| E1 | [ ] | S6, first sentence | "the guard that demonstrably closes this channel" still overclaims; align with the registered abstract wording ("closes the channel by construction") | Untested defence presented as demonstrated |
| E2 | [ ] | S5.5 | State explicitly which prompt mode the hostile-evidence attack runs under, and add one sentence leading with the guarded arm: even when instructed to hold the right, hostile evidence drags floor mass to 0.402. This closes the "delegate role-play, not value erosion" reading | Crack is task compliance in delegate mode |
| E3 | [ ] | S5.5 and S6 | Scope the weights-channel claim to the tested recipe: "cannot be fine-tuned into the weights without lobotomy" becomes "the standard cheap recipe we tested degrades floors and capability"; add one caveat that each ladder rung is a single instantiation (DPO, trained steering vectors untested) | Channel-level conclusions from n=1 per rung |
| E4 | [ ] | S3 Metrics + Limitations | One sentence acknowledging the 0.50 floor threshold is a convention; note margins (already reported) are the primary quantity and the below-floor counts are secondary. Matters because the 3B baseline is 0.512, within noise of the line | Arbitrary threshold, baseline hugs it |
| E5 | [ ] | S3 Instrument validity | State who coded the 150 rationales, blinding procedure, and inter-rater agreement if there was a second coder; if single-coder, say so plainly | Authors coding their own benchmark |
| E6 | [ ] | S2 | Position against indirect prompt injection: the evidence-over-instruction asymmetry is adjacent to known channel-dominance results; state what is new here (population referent, tracking metric, legitimacy boundary). Also consider silicon sampling (Argyle et al.), pluralistic alignment (Sorensen et al.), Collective Constitutional AI, Habermas Machine (Tessler et al.). ALL of these are [CITE NEEDED: verify authors, venues, years against real sources before adding; none verified yet, do not trust this table for bibliographic detail] | Missing related work; novelty vs injection literature |
| E7 | [ ] | S5.4 or S5.6 | Add a pooled tracking-significance statement computed from existing artifacts: direction-match across the six-model panel (8+8+7+10+9+9 of 60) under a combined sign test. The single-model 8/10 is p ~= 0.055 one-sided and a reviewer will compute it; the pooled panel is decisive and needs no new runs, only arithmetic over committed artifacts | Headline direction-match not significant on its own |
| E8 | [ ] | f7 caption | "Every point lies on or above the y=x line" is a strong universal with no test reported; either add a sign test over probe-model points or soften to "points lie on or above" | Untested universal claim |

---

## Part C: proposed experiments (priority order)

Each entry: what, why, design, rough cost. All local runs use the existing harness path
and throwaway `--out` targets first (never clobber canonical `out/*.json`); promoted
artifacts get new filenames.

### X1. Placebo-distribution control on floor items (highest value per unit cost)
- **Objection answered:** the crack may be distribution imitation (anchoring), not value
  erosion; likewise tracking may be number-copying. This is the single most damaging
  review line and the cheapest to answer.
- **Design:** rerun the P4 floor battery on the 3B (and 8B if cheap) with (a) a neutral
  50/50 synthetic distribution and (b) an irrelevant-topic distribution injected through
  the same evidence channel. If floor mass barely moves under (a) and (b) but cracks
  under 75 percent hostile, the crack is content-driven, not format-driven, and the paper
  gains a strong new control. If floor mass moves under placebo too, we need to reframe
  before a reviewer does it for us.
- **Cost:** same shape as one existing P4 condition: 12 floor probes x 2 new conditions,
  local MLX, roughly one existing-P4-run's wall clock per model.

### X2. Fabricated-shift control on tracking items
- **Objection answered:** "tracks a real public shift" vs "reads whatever numbers are in
  context". Changing the evidence year changes the numbers shown, so the current design
  cannot distinguish these.
- **Design:** on the 10 tracking items, feed evidence with the 2022 to 2024 shift
  direction inverted (or years swapped). If the model follows fabricated shifts with
  similar elasticity, the honest claim becomes "the channel transmits whatever it is
  fed", which actually strengthens the who-fills-the-channel framing; say so explicitly.
- **Cost:** one tracking-run equivalent per model; 3B alone suffices for the paper.

### X3. Real BSA evidence on floor items
- **Objection answered:** only a synthetic 75 percent extreme is tested; the deployment
  question is whether genuine opinion evidence erodes floors.
- **Design:** where BSA has real marginals adjacent to floor topics, inject the real
  distribution through the evidence channel and measure floor mass. Requires checking
  which floor probes have a defensible BSA counterpart; may only cover a subset, which is
  fine if stated.
- **Cost:** target-building work plus one P4-shaped run; the target curation is the real
  cost, not compute.

### X4. Routing classifier evaluation (converts S6 from memo to result)
- **Objection answered:** the defence is asserted, never run.
- **Design:** implement the floor-vs-contestable classifier as a zero-shot call over the
  existing item bank (62 items have ground-truth labels by construction); measure
  accuracy, then attack it with adversarially rephrased floor items (the framing attack
  S6 already names) and report the floor false-negative rate and the induced crack rate
  when misrouted items receive hostile evidence.
- **Cost:** small: one classification pass over the bank plus a rephrased floor set
  (write ~3 rephrasings per floor probe, 36 calls) plus one partial P4 run on the
  misrouted subset.

### X5. Seed replication on headline cells
- **Objection answered:** single-seed on 4-bit quantized models, CIs grazing zero.
- **Design:** 3 seeds on the 3B headline cells (baseline floors, hostile evidence,
  tracking). Report across-seed spread next to the sampling CIs.
- **Cost:** 3x the existing 3B run time for the affected cells; overnight locally.

### X6. Check before running: guarded-arm attack data may already exist
- E2 may need no new run at all: if the existing guard-arm artifacts already contain the
  constitutional-guard-plus-hostile-evidence cell, the "even when instructed to hold the
  right" framing is a writing change over committed data. Check `out/` before scheduling
  anything.

### X7. Optional, likely post-deadline: one stronger weights-rung instantiation
- A DPO or targeted-layer LoRA attempt at closing the channel. Only worth it if E3's
  softening is judged too weak; otherwise defer to the camera-ready or a follow-up.

---

## Suggested triage vs the 07-28 deadline

Writing-only (E1 to E8): all fit before the deadline; E1, E2, E3 are the ones reviewers
will otherwise convert into rejection reasons. X6 first (may be free), then X1 and X4
(cheap, each defuses a major objection and yields a new sentence or small table), then
X2. X3, X5, X7 are honest-limitations material if they do not fit; naming them as known
controls in Limitations is itself worth doing.

## Reconciliation with Sol's plan (2026-07-21, after verification)

Sol's `FLAGSHIP_AIRTIGHT_PRIORITY_PLAN.md` supersedes the experimental core of this plan.
Claude verified Sol's load-bearing factual claims against the repo and they all hold:
the Tier-2 payload contains an explicit reproduction instruction
(`src/alignment/steer/tier2_preference.py:40`); guards are user-content prepends while the
system role stays generic (`compose_guard`, `measure.py`); 3B has two per-item protective-mass
increases under hostile evidence (pol_protest_ban, pol_dna_database) though all 12 end below
0.50; 8B hostile is 11/12 below, so the Fig 3 caption "both models" overclaims; the coded
codesheet exposes item/class/model/prompt/answer columns.

Status changes to this plan:

- **X1 superseded** by Sol's channel-decomposition matrix (the 50/50 control was a dose, not a
  placebo; Sol's format-matched placebo is correct).
- **X2 superseded** by Sol's Priority 3 (same design, adds the no-shift placebo arm, which is
  needed to rule out a bare year-label effect).
- **X3 withdrawn**: floors are authored items with no question-equivalent BSA marginals (this
  plan's own gate, now answered negatively).
- **X4 withdrawn as an experiment**: replaced by Sol's item 7, narrow S6 to a static allowlist
  over preclassified items (which matches the registered abstract's "by construction" wording).
- **E7 withdrawn as stated**: the pooled sign test is invalid, the same 10 items recur across
  models so the 60 direction-matches are not independent. Report 51/60 descriptively or
  item-clustered only.
- **E1, E3, E4, E5, E8 stand** and coincide with Sol's writing corrections; E2 stands but its
  "guarded arm" reading must wait for the true system-role guard cell; E6 stands (Sol does not
  cover related-work positioning).
- **Two additions to Sol's Priority 0**: (a) check whether AAAI allows editing the registered
  abstract at full-paper submission; if locked, every row of the preregistered outcome table
  needs an abstract-compatibility note before any run; (b) an explicit cut line: local 3B/8B
  matrix + writing corrections are must-haves, the hosted panel drops first if time runs out.

## Decisions log

- 2026-07-21: abstract registered with Part A edits.
- 2026-07-21: Sol's plan verified and adopted as the experimental spine; X1--X4 and E7
  superseded or withdrawn as above.

## Open questions

- Was there a second rationale coder? (Determines whether E5 is a disclosure or an
  inter-rater computation.)
- Which prompt mode did the P4 attack use? (Feeds E2; check run blocks in `out/`.)
- Do any floor probes have defensible real-BSA counterpart marginals? (Gates X3.)
