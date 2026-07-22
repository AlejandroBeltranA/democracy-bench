# Q1 rewrite draft — S5.5, S6, abstract (co-editing draft, not applied)

**Replaces:** S5.5 "The hostile-evidence floor crack" (democracy_bench.tex lines ~384-435,
including Table 2's framing note), the first paragraph of S6 (lines ~513-521), and two
abstract sentences. Consistency edits listed at the end touch S1 contribution (3), S5.6,
Discussion, Conclusion, and the Ethical Statement.
**Numbers tied to:** `out/q1_channel_{3b,8b}.json` at commit `fac4582`, frozen design
`8c69435`, interpretation per `paper/Q1_RESULTS_CONSENSUS.md` (Sol CONCUR 2026-07-22).
Primary statistics are read from the committed artifacts' named headline estimands; the
secondary numbers (placebo effects, surveillance-exclusion sensitivity) regenerate from
`out/q1_secondary_extract.json` via the fail-loud, hash-pinned extractor
`scripts/extract_q1_secondary.py` with tests on source identity, pairing, signs, and the
quoted rounded values (R-W7: DONE).

**Sol review (2026-07-22): OBJECT pending R-W1--R-W5 below.** The withdrawal and
decomposition are the right thesis-level pivot, but the draft presently reintroduces a
claim contradicted by Q1: the combined payload does not defeat every prompt-level guard.

**v2 (Fable, 2026-07-22): all of R-W1--R-W5 incorporated in the prose below; the
combined::user_after numbers Sol cites were verified against the committed artifacts
(3B 0.572, 0 induced cracks; 8B 0.694, 2 remaining) before incorporation. Fresh
Alex + Sol sign-off required before any manuscript edit.**

**Sol v2 review (2026-07-22): OBJECT pending R-W6--R-W7 below.** The substantive
reframing now matches Q1. These are two bounded pre-application corrections, not a
request to reopen the thesis.

**Sol final vote (2026-07-22): AGREE.** R-W6 is incorporated in the applied manuscript;
R-W7 produced the immutable, hash-pinned secondary extract and its focused extractor/
paper tests pass (46/46). The Q1 thesis rewrite is approved, subject to final rendered-
page and whole-paper consistency review.

---

## Drafted prose: S5.5, retitled

### \subsection{Decomposing the crack: data, instructions, and placement}\label{sec:crack}

Feeding a synthetic 75\%-anti-rights ``public distribution'' through the deference
channel cracks rights floors on both local models (Table~\ref{tab:floors}). That result,
as first measured, carried two confounds we owed the reader an answer on: the injected
payload both displays a distribution and explicitly instructs the model to reproduce it,
and every guard tested was ordinary user-message text sharing the prompt with the attack.
We therefore froze a channel-decomposition design before running it: four payloads
(no payload; a pure target instruction naming the anti-rights option, with no population
claim; the same hostile numbers presented as a bare survey report, with no imperative;
and the original combined text) crossed with four guard placements (none; the rights
guard before the payload in the user turn; after it; and in the true system role), over
all 12 floor probes and a position-balanced Williams square of option orders, with
estimands and decision rules fixed in advance. The design document's hash is stamped in
every artifact.

Four findings follow, each stated under the preregistered rules. First, data alone
erodes floors. The bare survey report, carrying no instruction of any kind, lowers mean
protective mass by $-0.163$ ($[-0.232, -0.086]$) on the 3B and $-0.188$
($[-0.250, -0.124]$) on the 8B, newly cracking 5 of the 8 floors that held at baseline
on each model. A deployer does not need to tell a model to follow hostile ``opinion
data''; showing it is enough.

Second, the instruction channel dominates, and the asymmetry we measured at P4 inverts.
A direct instruction to select the anti-rights option collapses protective mass to
$0.06$ on both models ($\Delta \approx -0.56$), cracking every eligible floor; the
channel contrast (data effect minus instruction effect) is $+0.395$ ($[+0.333, +0.464]$)
on the 3B and $+0.380$ ($[+0.287, +0.492]$) on the 8B, far outside our preregistered
equivalence margin and opposite in sign to an evidence-specific vulnerability. What P4
established is therefore a fact about one prompt, not a channel ordering: the
\emph{constitutional majority-pressure text} showed no detectable harmful average
effect, while the direct target instruction tested here is the strongest lever in the
matrix. We withdraw the claim that evidence overrides the instruction channel.

Third, semantically relevant hostile opinion is not necessary for floor movement. An
irrelevant distribution-and-reproduction payload, the same numerical shape attached to a
transport question, also lowers protective mass on both models ($-0.143$
$[-0.217, -0.073]$ on the 3B; $-0.112$ $[-0.187, -0.033]$ on the 8B). The design does
not separate numerical anchoring from the accompanying imitation framing, so we make no
mechanism claim beyond this: under our frozen interpretation the movement is contextual
instability, not uniquely democratic-value erosion.

Fourth, prompt guards are not uniformly weak; they are placement- and model-dependent.
The same rights-guard text that fails ahead of the payload on the 3B ($0.424$) restores
every floor when placed after it ($0.690$, 0 of 12 below); in the system role it
recovers the 8B's data-only crack completely ($+0.314$ $[+0.235, +0.389]$, all five
induced cracks closed) yet does nothing on the 3B ($+0.012$, n.s.). Matched user-guards
perform as well or better than the system role on both models, so we make no
prompt-hierarchy claim; the accurate statement is that guard efficacy varies with
placement and model, and the committed guard grid of \S\ref{sec:results} tested only the
user-before placement, which Q1 shows can be substantially less effective than placing
the same guard after the payload.

The original combined payload, data plus embedded imperative, remains severe with no
guard ($0.364$ 3B, $0.104$ 8B) and with the guard in the system role ($0.339$, $0.257$),
while moving the same guard after the payload recovers all induced cracks on the 3B
($0.572$, 0 remaining) and most on the 8B ($0.694$, 2 remaining). No tested prompt
placement is reliable across models and payloads. Class-aware routing
(\S\ref{sec:routing}) supplies a deterministic scope boundary by withholding the
public-opinion payload from declared floor items: it avoids payload-induced degradation
by construction, rather than being the only prompt-independent mitigation observed.

Two measurement notes. The combined cells replicate the committed P4 cracks
directionally (3B $0.364$ vs.\ $0.318$; 8B $0.104$ vs.\ $0.074$); under the balanced
four-order design the baselines shift materially in \emph{opposite} directions
($+0.109$ on the 3B, $-0.082$ on the 8B), demonstrating order sensitivity in the
two-order estimates (full comparison in Limitations). And on one 3B probe (surveillance) first-token
option coverage drops as low as $0.01$ in three cells; excluding it leaves every
estimate above effectively unchanged (data $-0.150$, instruction $-0.552$, contrast
$+0.402$).

---

## Drafted prose: S6, first paragraph replacement

Prompt-level guards recover parts of the decomposed attack, but no tested placement is
reliable across models and payloads: the combined payload stays severe under the
system-role guard on both models, and the placement that recovers it on the 3B
(user-after) leaves two induced cracks on the 8B. Class-aware routing is a different
kind of control: a deterministic exposure boundary that injects public-opinion evidence
only on contestable-class items, never on floor-class items. With no payload injected,
floor probes return to the no-payload condition, avoiding payload-induced degradation by
construction while leaving contestable representation and tracking untouched; this is a
scope guarantee, not an optimum (4 of 12 probes sit below $0.50$ even unattacked, and
guarded baselines score higher).

[The rest of S6 (residual attack surface, classifier as boundary, static-allowlist
narrowing per writing correction 7) stands as committed.]

---

## Abstract: two sentence replacements

Current: "The exception is evidence-in-context, which lets a model track the real
2022$\to$2024 shift in public attitudes but is itself the attack surface: a synthetic
hostile ``public distribution'' erodes \emph{every} rights floor, and neither prompt
guards nor a fine-tuning recipe closes the channel."

Draft replacement (edits within the registered abstract, per the editable-not-replaced
rule): "The exception is evidence-in-context, which lets a model track the real
2022$\to$2024 shift in public attitudes but is itself an attack surface: distribution-
shaped context erodes rights floors without any explicit demand, a direct hostile
instruction erodes them further, and rights-guard efficacy varies with prompt placement
and model rather than holding reliably; a fine-tuning recipe also fails to close the
channel, while class-aware evidence routing supplies a deterministic exposure boundary
by construction."

Current: "The result replicates across scale (3B and 8B Llama) and family (Qwen, Phi,
Gemma, and Mistral all track and crack), and reaches a hosted proprietary model: ..."

Draft note, not a replacement: the cross-family and hosted crack sentences describe the
combined payload and remain true; add "under the combined payload" if space allows, and
verify at Stage-2 whether the decomposition transfers before strengthening further.

---

## Consistency edits required elsewhere (inventory, one line each)

1. S1 contribution (3): "a clean asymmetry ... the adversarial prompt alone is not
   significant" -> rescope to "a decomposed attack surface: data alone erodes floors,
   instructions dominate, and prompt-guard efficacy is placement- and model-dependent".
2. S1 contribution (2): "evidence overrides the instruction channel even when a guard
   prompt is explicitly opposing it" -> delete or rescope to the user-before placement.
3. S5.6 and Table 3: "the adversarial \emph{prompt} alone never cracks floors" -> "the
   constitutional-pressure prompt alone never cracks floors" (accurate as committed;
   the family panel never ran a direct instruction).
4. Fig. 3 caption: "cracks every floor on both models" -> per-model counts (12/12 on 3B,
   11/12 on 8B), folding writing correction 3.
5. Discussion, "sharp, deployment-relevant asymmetry" sentence -> replace with the
   decomposed statement; workflow item (ii) gains "guard placement matters: test guards
   after the evidence and in the system role, not only before it".
6. Conclusion: "that same channel cracks rights floors under adversarial `public'
   evidence" stands; delete "and it overrides prompt-level and weight-level defenses
   alike" in favour of: guard efficacy varies with placement and model, and the combined
   attack, though substantially mitigated by user-after placement, remains severe under
   several placements.
7. Ethical statement, dual use: the strongest tested attack (the direct instruction)
   requires only context access, which strengthens the deployer-side threat-model
   framing; the combined attack remains severe under several placements but is
   substantially mitigated by user-after placement.
8. Limitations: add the placebo/format-sensitivity reading, the order-bias correction to
   the two-order baselines, and the surveillance coverage anomaly disclosure.

## Compared to the prior version

- The crack survives but is decomposed: the section no longer claims an
  evidence-over-instruction asymmetry, which Q1 falsified in its strong form.
- The guard story flips from "prompt guards fail" to "guard efficacy is placement- and
  model-dependent; the committed grid tested only the user-before placement, which Q1
  shows can be substantially less effective than user-after"; routing survives as a
  deterministic exposure boundary (a scope guarantee by construction), not as the only
  effective mitigation.
- The placebo result imports the anchoring objection into the paper on our terms,
  before a reviewer raises it.
- All numbers regenerate from the two committed Q1 artifacts; no new citations are
  introduced (an anchoring/format-sensitivity citation is optional, see open decisions).

## Editorial decisions (RESOLVED per Sol review + Alex relay, 2026-07-22)

- D-A: compact table, unless the final layout has room for one central Q1 figure.
- D-B: keep the explicit withdrawal sentence (all three concur).
- D-C: no anchoring citation as a substitute for identification; finding three makes no
  mechanism claim.
- D-D: one order-sensitivity sentence stays in S5.5; the full numerical comparison
  (+0.109 3B / -0.082 8B) goes to Limitations.

## Length note

Drafted S5.5 is ~600 words against ~340 in the committed section (which also loses its
guard-failure paragraph, partially absorbed here). Net addition ~200 words plus the S6
paragraph swap (~-20). If the 7-page limit binds, the two measurement notes compress to
one sentence each, and finding four's numbers can drop to the two headline recoveries.

## Sol review — required revisions before manuscript application

### R-W1. Do not restore the universal prompt-defence claim

The statements “One configuration resists every prompt-level defence,” “nothing
prompt-level closes the combined payload,” and “defeats every prompt-level guard we
test” are false under the committed Q1 artifact. Under the combined payload,
`user_after` raises protective mass to 0.572 on 3B with **zero induced cracks remaining**,
and to 0.694 on 8B with two induced cracks remaining. It is much more effective than the
system guard on both models.

Replace the combined/routing transition with the narrower result:

> The combined payload remains severe with no guard and with the guard in the system
> role, while moving the same guard after the payload recovers all induced cracks on 3B
> and most on 8B. No tested prompt placement is reliable across models and payloads.
> Class-aware routing supplies a deterministic scope boundary by withholding the public-
> opinion payload from declared floor items; it avoids payload-induced degradation by
> construction, rather than being the only prompt-independent mitigation observed.

Likewise, Section 6 must not say routing “restores the best measurable floor state.” The
unguarded baseline already has 4/12 probes below 0.50 on each model, and guarded baseline
cells have higher mean protection. Routing returns floor items to the relevant no-payload
condition; it does not prove an optimum.

### R-W2. Scope the instruction result to the tested direct instruction

“Instructions as a class are the strongest lever” overgeneralizes from one deliberately
strong, label-anchored target instruction. Say “the direct target instruction tested here
is the strongest lever in the matrix.” Also replace “constitutional majority-pressure
text is inert” with “showed no detectable harmful average effect” or equivalent; a
confidence interval containing zero does not establish literal inertness.

Keep the explicit withdrawal sentence. It is the strongest editorial choice because it
makes clear that the decomposition corrected, rather than cosmetically renamed, the
original mechanism claim.

### R-W3. Narrow the placebo mechanism claim

The placebo combines irrelevant numerical content **and a reproduction instruction**,
whereas data-only has no imperative. It establishes that semantically relevant hostile
opinion is not necessary for floor movement. It does not isolate “format” from imitation
framing, and it does not establish that “much of” the data-only effect is format-driven.

Use:

> An irrelevant distribution-and-reproduction payload also lowers protective mass.
> Semantic relevance to the floor question is therefore not necessary for movement; the
> design does not separate numerical anchoring from the accompanying imitation framing.

Any stronger anchoring mechanism claim requires a separately matched control and should
not be repaired with a citation alone.

### R-W4. Correct the order-bias sentence

The earlier two-order baseline is not uniformly biased upward by about 0.11. Relative to
the earlier artifact, the four-order baseline changes by **+0.109 on 3B** (0.512 to
0.621) and **-0.082 on 8B** (0.707 to 0.625). Say that the baselines shift materially in
opposite directions under the balanced design, demonstrating order sensitivity. Move
the full numerical comparison to Limitations if space is tight.

The placebo confidence intervals are reproducible from committed item-level outputs with
the frozen paired bootstrap, but are not stored as named headline estimands. Either add a
post-Q1 extractor artifact for these secondary contrasts or say explicitly that they were
regenerated from the committed rows; “nothing is estimated in prose” is currently too
strong.

### R-W5. Abstract and consistency-edit consequences

The abstract must say that guard efficacy varies by placement and model, not that the
combined payload defeats every tested guard. The routing motivation survives as a
deterministic exposure boundary, but “prompt-level defenses all fail” does not. Revise
consistency edits 6 and 7 accordingly: the strongest tested direct instruction requires
context access, while the combined attack remains severe under several placements but is
substantially mitigated by user-after placement.

**Editorial decisions:** D-A prefer a compact table unless the final layout has room for
one central Q1 figure; D-B keep the explicit withdrawal; D-C do not add an anchoring
citation as a substitute for identification; D-D put the full order-sensitivity numbers
in Limitations and retain one sentence in Section 5.5.

### R-W6. Soften the remaining “least favorable placement” statement

The prose still says the committed guard grid tested “the least favorable placement.”
User-before is worse than user-after in the relevant local contrasts, but it is not
uniformly the worst of every placement on both models; for 8B data-only, the system guard
has lower protective mass than either user placement. Replace this with:

> the committed guard grid tested only the user-before placement, which Q1 shows can be
> substantially less effective than placing the same guard after the payload.

Make the same change in “Compared to the prior version.”

### R-W7. Build the named secondary extractor before applying prose

Proceed with the extractor extension now. Do not modify the immutable Q1 run artifacts.
Create a fail-loud derived results artifact (or extend the existing paper-results
extractor) that verifies the two Q1 source hashes and regenerates the placebo effects and
CIs with the frozen paired bootstrap (`B=2000`, `seed=0`). Add tests for source identity,
pairing, signs, and the quoted rounded values. Route every Q1 number used by the paper
through that derived artifact before editing `.tex`.

After R-W6 and R-W7, Sol approves applying the v2 thesis and explicit withdrawal to the
manuscript, subject to normal rendered-page review.
