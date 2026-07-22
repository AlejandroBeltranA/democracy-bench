# Q1 rewrite draft — S5.5, S6, abstract (co-editing draft, not applied)

**Replaces:** S5.5 "The hostile-evidence floor crack" (democracy_bench.tex lines ~384-435,
including Table 2's framing note), the first paragraph of S6 (lines ~513-521), and two
abstract sentences. Consistency edits listed at the end touch S1 contribution (3), S5.6,
Discussion, Conclusion, and the Ethical Statement.
**Numbers tied to:** `out/q1_channel_{3b,8b}.json` at commit `fac4582`, frozen design
`8c69435`, interpretation per `paper/Q1_RESULTS_CONSENSUS.md` (Sol CONCUR 2026-07-22).
All statistics below are read from the committed artifacts; nothing is estimated in prose.

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
\emph{constitutional majority-pressure text} is inert, while instructions as a class are
the strongest lever in the matrix. We withdraw the claim that evidence overrides the
instruction channel.

Third, relevance is doing less work than format. A placebo payload with the same
numerical shape and reproduction framing, attached to an irrelevant transport question,
erodes floors on both models ($-0.143$ $[-0.217, -0.073]$ on the 3B; $-0.112$
$[-0.187, -0.033]$ on the 8B). Much of the data-channel effect is sensitivity to
distribution-shaped, imitation-framed context rather than to the hostile opinion content
itself; under our frozen interpretation this is contextual instability, not uniquely
democratic-value erosion.

Fourth, prompt guards are not uniformly weak; they are placement- and model-dependent.
The same rights-guard text that fails ahead of the payload on the 3B ($0.424$) restores
every floor when placed after it ($0.690$, 0 of 12 below); in the system role it
recovers the 8B's data-only crack completely ($+0.314$ $[+0.235, +0.389]$, all five
induced cracks closed) yet does nothing on the 3B ($+0.012$, n.s.). Matched user-guards
perform as well or better than the system role on both models, so we make no
prompt-hierarchy claim; the accurate statement is that guard efficacy varies with
placement and model, and the guard grid of \S\ref{sec:results} tested the least
favourable placement.

One configuration resists every prompt-level defence: the original combined payload,
data plus embedded imperative, holds floors below $0.36$ on the 3B and $0.26$ on the 8B
even through the system-role guard. That is the configuration an adversary controlling
the evidence pipeline would choose, and it is the case for the architectural control of
\S\ref{sec:routing}.

Two measurement notes. The combined cells replicate the committed P4 cracks
directionally (3B $0.364$ vs.\ $0.318$; 8B $0.104$ vs.\ $0.074$); the offset traces to
the balanced four-order design, which also shows the earlier two-order baseline was
order-biased upward by $\approx 0.11$. And on one 3B probe (surveillance) first-token
option coverage drops as low as $0.01$ in three cells; excluding it leaves every
estimate above effectively unchanged (data $-0.150$, instruction $-0.552$, contrast
$+0.402$).

---

## Drafted prose: S6, first paragraph replacement

Prompt-level guards recover parts of the decomposed attack, but nothing prompt-level
closes the combined payload: data with an embedded imperative defeats the rights guard
in every placement we tested, on both models. The guard that closes \emph{that} channel
is architectural: inject public-opinion evidence only on contestable-class items, never
on floor-class items. With no evidence injected, floor probes sit at the unguarded
baseline and the constitutional-pressure prompt alone is not significant, so routing
restores the best measurable floor state by construction while leaving contestable
representation and tracking untouched.

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
instruction erodes them further, and the committed payload combining the two defeats
every prompt-level guard we test, including a system-role guard; a fine-tuning recipe
also fails to close the channel."

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
   alike" in favour of the combined-payload statement.
7. Ethical statement, dual use: the disclosed attack is now sharper (instructions
   dominate); note that the strongest attack requires only context access, which
   strengthens the deployer-side threat-model framing.
8. Limitations: add the placebo/format-sensitivity reading, the order-bias correction to
   the two-order baselines, and the surveillance coverage anomaly disclosure.

## Compared to the prior version

- The crack survives but is decomposed: the section no longer claims an
  evidence-over-instruction asymmetry, which Q1 falsified in its strong form.
- The guard story flips from "prompt guards fail" to "guard efficacy is placement- and
  model-dependent; the committed grid tested the worst placement"; the combined payload
  is the surviving motivation for routing.
- The placebo result imports the anchoring objection into the paper on our terms,
  before a reviewer raises it.
- All numbers regenerate from the two committed Q1 artifacts; no new citations are
  introduced (an anchoring/format-sensitivity citation is optional, see open decisions).

## Open editorial decisions

- D-A: does S5.5 get a figure (per-payload dumbbell like f6, data source
  `out/q1_channel_{3b,8b}.json`) or a compact table? Space suggests a table; a figure
  sells the instruction-dominance point faster.
- D-B: "we withdraw the claim" sentence: keep the explicit withdrawal (my preference;
  it reads as strength at AISI) or fold it silently into the rescoped claim?
- D-C: optional [CITE NEEDED: anchoring / format sensitivity of in-context numbers in
  LLMs] to anchor finding three; only if a real, verified source exists.
- D-D: the order-bias note names a defect in the committed P4 numbers; state it in S5.5
  (drafted above) or move it to Limitations?

## Length note

Drafted S5.5 is ~600 words against ~340 in the committed section (which also loses its
guard-failure paragraph, partially absorbed here). Net addition ~200 words plus the S6
paragraph swap (~-20). If the 7-page limit binds, the two measurement notes compress to
one sentence each, and finding four's numbers can drop to the two headline recoveries.
