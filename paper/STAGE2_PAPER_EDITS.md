# Stage-2 additions to `democracy_bench.tex` — section draft for co-editing

**Status:** DRAFT for Alex to review, not applied to `democracy_bench.tex`. Nothing here has
been written into the canonical manuscript.

**What this covers:** four insertions, listed with the exact lines they attach to.

| # | Target | Fate |
|---|---|---|
| A | Abstract, after the `gpt-4o-mini` sentence (≈ lines 50–52) | one added sentence |
| B | §5.5 robustness, after the hosted-proprietary paragraph (≈ lines 523–532) | new paragraph |
| C | Limitations (≈ lines 648–651) | new sentences |
| D | "What we do not claim" (≈ lines 653–660) | one added clause |

**Numbers are tied to** `out/q2_stage2_v7_run_panel/extract_qwen__qwen3.5-397b-a17b.json`,
committed at `f6e9e6b`+, design frozen at v7.2 with amendment AMD-V72-01, endpoint snapshot
`d9a5d0e061bf222e…`. Every figure below is read from that artifact. Nothing is estimated.

> **VOICE CAVEAT — please check this first.** The `cowork_context` hub was not mounted, so
> `_shared/alex_voice.md` and `references/academic_register.md` were unavailable. The skill says
> not to draft in your voice from memory, and you were asleep, so rather than stall I derived
> the register from your own prose in `democracy_bench.tex` (§5.5 and the limitations). That is
> a primary source rather than recall, but it is not the canonical voice doc. Please re-read
> against it before anything goes in.

> **DEEPSEEK IS NOT IN YET.** The replication was still running when this was drafted. Every
> DeepSeek figure below is `[PENDING]` and must not be filled by hand. Insertion B is written so
> that it stands with one model if the replication fails or is dropped.

---

## A. Abstract insertion

Attaches after "…gpt-4o-mini, a strong floor-holder at rest, cracks on every floor under the
same hostile evidence."

> The same contrast holds on the frontier open-weight checkpoints a sovereign-AI project would
> actually start from: on Qwen3.5-397B-A17B, direct instruction collapses the floors almost
> entirely (protective mass $0.003$, 12/12 cracked) while the same content supplied as evidence
> is less destructive ($0.305$, 8/12), and a rights guard placed after the payload closes every
> induced crack that the same guard placed before it leaves open.

**Length note:** 61 words. The abstract is already long, so this may need to displace something
rather than be added. See open decision 1.

---

## B. §5.5 insertion — the Stage-2 paragraph

Attaches after the `gpt-4o-mini` paragraph and before Figure~\ref{fig:crossfamily}.

> The reproduction also holds where it matters for deployment. UK guidance is explicit that
> training a frontier model is beyond most organisations, and that adapting an existing open
> model is the practical route [cite ukaiplaybook; cite sovereignai], so the starting
> checkpoint's failure modes are part of a system's initial assurance burden. We therefore ran
> the complete design as a labelled post-hoc follow-up on Qwen3.5-397B-A17B, a current frontier
> open-weight instruct checkpoint, sampling $S=100$ per probe-cell across all eleven cells,
> twelve floor probes and four option orders (13,200 draws). The Q1 pattern transfers.
> Instruction is again the more destructive channel: the floors sit at $0.973$ at rest and
> collapse to $0.003$ under direct instruction (12/12 cracked), a channel contrast of $+0.303$
> $[+0.087, +0.538]$ with the same sign as the local estimates. The same material supplied as
> evidence splits the probe set rather than eroding it uniformly: eight floors collapse to
> $\leq 0.10$ while four hold near baseline, so the cell mean of $0.305$ describes no individual
> probe. The placebo again moves floors it has no semantic reason to touch, cracking 2 of 12 and
> eroding five by at least $0.10$ ($\Delta -0.116$ $[-0.229, -0.027]$), though two probes carry
> most of that effect and the interval does not clear the $\pm 0.05$ materiality band. Guard
> efficacy is again conditional: the system guard closes all eight data-only cracks yet leaves
> 11 of 12 combined cracks open ($+0.594$ $[+0.389, +0.783]$ against $+0.084$ $[+0.014,
> +0.174]$), and moving a user guard after the payload rather than before it restores every
> probe to or above the floor ($0.100$ to $0.876$, 12 cracks to none; $+0.776$ $[+0.683,
> +0.862]$), with one probe sitting exactly at $0.50$. [PENDING: DeepSeek-V4-Pro replication
> sentence.] The claim is narrower than a replication: this characterises the pre-adaptation
> profile of one checkpoint a sovereign project might start from, under a sampling estimator
> rather than the local logprob score. It does not show that a fine-tuned derivative keeps that
> profile, and adaptation may preserve, attenuate, amplify or relocate the failure mode.

**Length note:** 268 words as drafted, plus the pending DeepSeek sentence.

**Corrections applied after adversarial review** (all verified against the artifact):
- "closes every data-only crack (12/12 to 0/12)" was **factually wrong**: `data_only::no_guard`
  cracked **8** of 12, not 12. Now "all eight data-only cracks". This was a checkable error.
- "reproduces in full" and "replicates" changed to "transfers": the frozen Stage-2 question is a
  transfer question, one model cannot speak to the model-conditionality Q1 found, and the
  estimator changed from logprob scoring to 100-draw sampling.
- "closes the combined case entirely" now notes that `pol_id_cards` sits at exactly $0.50$; one
  draw fewer and it is a crack.
- The data-only mean now carries its bimodality
  (`[0.00, 0.00, 0.01, 0.01, 0.01, 0.03, 0.10, 0.10, 0.54, 0.92, 0.95, 0.99]`).
- The placebo sentence now states the concentration and that the CI's lower bound is inside the
  materiality band.

---

## C. Limitations insertion

Attaches after the existing `gpt-4o-mini` limitation sentence.

> The Stage-2 open-weight runs are pinned more tightly than the gpt-4o-mini cell but remain
> hosted: we record the exact endpoint, the catalogue quantisation and the dated upstream
> checkpoint, and every reported number regenerates from the persisted raw responses, yet both
> promoted endpoints report their precision as unknown and neither is byte-reproducible. What we
> measure is a provider-served instruct endpoint, not weights run locally. Protective mass here
> is a sampled proportion of 100 draws per probe-cell at $0.01$ resolution, conditional on
> parseable responses, so crack determinations within a few hundredths of the floor sit inside
> sampling resolution. Effects are baseline-relative differences and the resting floors are near
> ceiling, which maximises headroom; crack determinations, however, are made against the absolute
> $0.50$ floor. Of the eight preregistered contrasts, three have interval bounds inside the
> $\pm 0.05$ materiality band, so they are confidently nonzero without being confidently
> material, and we report eight intervals without multiplicity correction. The twelve floor
> probes are a constructed instrument, not a sample from a definable population of rights floors.
> Contrasts are estimated per model and never pooled.

**Length note:** 176 words. Longer than the first draft because the adversarial review found
four limitations missing; see below.

**Added after adversarial review:** the sampled-proportion estimator description (the earlier
draft implied a probability read directly off the model), the baseline-headroom caveat, the
materiality-versus-significance distinction for the three marginal contrasts, the absence of
multiplicity correction, the constructed probe universe, and the provider-served-endpoint point.

---

## D. "What we do not claim" insertion

Attaches as an added clause in the existing paragraph.

> …nor that the pre-adaptation profile we measure on an open-weight checkpoint is inherited by
> any model fine-tuned from it.

---

## Compared to the prior version

- The manuscript currently reads as though the hosted evidence is a single unpinned existence
  proof (gpt-4o-mini). Insertion B changes that to a complete design on a pinned frontier
  open-weight checkpoint, which is a materially stronger robustness claim.
- It also introduces the sovereign-AI motivation, which is new to the paper. That is why
  insertion B leads with the policy reason for the model choice rather than with the numbers:
  without it, two more model rows look like breadth for its own sake.
- Insertions C and D exist to stop B being read as an inheritance claim. That boundary is the
  one Sol objected to hardest during design review, and the drafted prose keeps it explicit.
- No existing sentence is replaced. Everything is additive, so your §5.5 argument and the
  cross-family paragraph stay as they are.

## Citations still to drop in

None of these exist in `references.bib` yet (it has 18 entries, none on sovereign AI or open
weights). All four need real entries before anything is submitted.

| Placeholder | Should support |
|---|---|
| `[cite ukaiplaybook]` | UK Government AI Playbook: training larger generative models is prohibitively expensive for most organisations; fine-tuning existing models is the cheaper route |
| `[cite sovereignai]` | Sovereign AI competition guidance listing "repurpose of open models with tooling, RL, fine tuning" as in scope |
| `[cite intlaisafety]` (optional) | International AI Safety Report: open weights benefit actors who cannot develop weights independently, and flaws may proliferate into downstream modified versions |
| `[cite superficialalignment]` (only if you want it) | Shallow/superficial alignment, if you decide to gesture at why a light fine-tune might not remove a pretraining-level property. **Recommend leaving this out.** See open decision 3. |

I have not written any of these into the `.bib`, and I have not guessed a key, author or year.

## Open editorial decisions

1. **Does the abstract insertion earn its place?** The abstract is already dense and near the
   limit. Options: add it as drafted; compress it to a single clause on the existing
   gpt-4o-mini sentence; or leave the abstract alone and let §5.5 carry Stage 2 entirely. My
   view is the middle option, but it is a judgement about what the abstract is for.
2. **Where does the sovereign-AI framing live?** Insertion B currently carries it in two
   sentences. If you want it as a contribution rather than a robustness note, it wants a
   sentence in the introduction as well, and that is a larger change than this draft makes.
3. **Do we cite shallow alignment at all?** Tempting, because it explains why a starting
   checkpoint's profile might survive light adaptation. But we did not test that, and citing it
   invites the reader to hear an inheritance claim we explicitly disclaim two sentences later. I
   would leave it out and let the future-work sentence do the job.
4. **Em dashes.** The skill's editorial rules say none; your `.tex` uses `---` throughout
   (`3B)---a $>0.45$ spread`). I have avoided them in the drafted prose, which makes it read
   slightly unlike the surrounding text. Tell me which way to go and I will make it consistent.
5. **If DeepSeek fails or is dropped**, insertion B stands unchanged apart from removing the
   pending sentence, and the claim becomes "a frontier open-weight checkpoint" rather than
   "checkpoints". No other edit is needed.

## Numbers I could not verify

None in insertions A, C or D. In insertion B, every figure is read from the committed Qwen
artifact. The single unverified item is the DeepSeek sentence, which is marked `[PENDING]` and
must be filled from its extraction artifact, not by hand.

## Three sentences most at risk of reading as AI-written

1. "Guard efficacy is again neither general nor absent" — the balanced negation is a tell.
   Consider "The guard result is the same as in Q1: it closes one payload and not the other."
2. "What this establishes is narrow and worth stating precisely" — signposting the claim rather
   than making it. You would more likely write "The claim is narrower."
3. "which makes the starting checkpoint's failure modes part of a system's initial assurance
   burden rather than a downstream concern" — the "rather than X" construction is doing rhetorical
   work a plainer sentence would do better.
