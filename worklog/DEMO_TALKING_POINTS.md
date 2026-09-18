# Demo Talking Points — "Whose Values?" public submission

*A fill-in-the-blanks narrative scaffold for the self-hosted demo. Each act below is one
anchor/section in the scrolly. Fill the **[BRACKETED]** prompts in your voice; the *italic lines*
are my suggested framing — accept, edit, or delete. When you hand this back, it's everything I need
to re-author `whose_values.html` into the six-act spine and inline the live run's numbers.*

- **Audience / frame:** Gov & AI-assurance (i.AI). Decision-maker tone, not hackathon-flashy.
- **Through-line:** assurance discipline — fail-closed, debiasing, CIs, a control group, provenance.
  The honesty is the credibility.
- **Argument shape:** decision-drift findings (Acts 2–4) build the problem to a sharp point →
  "teaching the why" (Act 5) is the **resolution**, not a co-thesis.
- **Hosting:** one self-contained HTML on your website. Replays real runs; does not run models live.

---

## 0 · Hook — one screen

**Goal:** make a policy-maker care in ten seconds.

**Talking points to cover**
- [ x] **The one-sentence thesis**, in your words. *Suggested: "When AI helps decide a UK benefits,
  visa, or due-process case, whose values does it use — the British public's, a foreign lab's, or
  no one's?"*
- [x ] **The single most striking number** to put on screen. *Candidates from the run: models disagree
  ~8× more than England-vs-Scotland; or the foreign outlier reporting Britain is "governed well"
  while the public wants change.* → **[PICK ONE + FINAL FIGURE]**
- [ x] One line on **why this is a measurement, not an opinion** (sets up the assurance frame).

**Feeds from:** headline stat from the final run. **Visual:** title + one big number + "Start ↓".

---

## 1 · How we ask — the instrument

**Goal:** a cold reader trusts the method before they see any finding. This is the self-explainability anchor.

**Talking points to cover**
- [x ] What a **probe** is: a real survey question, forced-choice, asked many times per model.
- [x ] **Ground truth = real UK survey microdata** (BSA / SSA). *Name the source + year + base sizes.*
- [x ] The four assurance moves, in plain words:
  - **Fail-closed** — if the model won't answer cleanly, we record nothing; we never fabricate a distribution.
  - **Option-order debiasing** — shuffle the answers per sample so we measure beliefs, not position bias.
  - **Confidence intervals** — every number carries sampling error.
  - **A control group** — non-AI versions of the same rights trade-offs (pays off in Act 3).
- [x ] One line defining **representation** in plain language (how close the model sits to the public). *Avoid "1−TV" up front; offer it on the "?" hover.*

**Feeds from:** instrument description; `instrument/measure.py`, `instrument/scorers.py`.
**Visual:** a single annotated probe → distribution-vs-public bar.

---

## 2 · Whose values? — the decision-drift core

**Goal:** off-the-shelf models are not interchangeable and not culturally neutral.

**Talking points to cover**
- [ x] **The panel** — which models, with country-of-origin flags. *Currently 3 models, all via
  OpenRouter: GPT-4o-mini, Claude 3 Haiku, DeepSeek (may extend).* Be transparent on screen that the
  panel is **foreign-hosted via OpenRouter** — that dependency is part of the point, not something to hide.
- [x ] **Models diverge — a lot.** *Suggested: on the NHS and on how Britain is governed, cross-model
  disagreement is ~[X]× larger than the England-vs-Scotland public gap.* → **[FINAL TV FIGURES]**
- [ x] **The foreign outlier.** *Suggested: [MODEL] reports Britain is governed well / the NHS is fine —
  the public is dissatisfied and wants change.* → **[FINAL FIGURE + which model]**
- [x ] The nuance that keeps you honest: **don't lump models by country** *(e.g. two models from the
  same country behaved very differently)*. → **[CONFIRM whether this still holds in the new run]**
- [x ] Takeaway line: **AI defaults embed a policy prior. Which one is a procurement question.**

**Feeds from:** `out/policy_drift.json` (drift block). **Visual:** model-vs-public bars; divergence-vs-public-gap comparison.

---

## 3 · The rights floor & the "AI reflex" — the pivot

**Goal:** the protection that looks reassuring is brittle — keyed to surface, not principle. This sets up the resolution.

**Talking points to cover**
- [x ] **What the floor is:** rights that shouldn't be traded away (we *score* them, never steer toward them).
- [x ] **The reflex:** every model defends the floor when the mechanism is **"an AI"** (protective ≈ 1.0).
- [x ] **Pose the same trade-off without "AI"** and they split — protest bans, surveillance, offensive
  speech. → **[FINAL AI-EXCESS TABLE: model · AI floor · non-AI controls · AI-excess]**
- [ x] The interpretation that bridges to Act 5: *the protection is triggered by the word "AI," not by
  the underlying principle. That's a model that learned the **what**, not the **why** — and it breaks
  the moment the case is phrased differently.*
- [x ] **Honest confound to name out loud:** part of the gap is that the AI probe is simply less
  contested than the controls; the clean signal is the **model-to-model split on the contested items**.

**Feeds from:** `out/policy_drift.json` (floor + controls). **Visual:** AI-excess table + per-model split bars.

---

## 4 · Can you fix it from the outside? — steering

**Goal:** prompting can't install a public's values; that's the sovereign-capability case.

Alex - I'm not entirely sure about this point. I guess we'll have to wait for the results to land. 

**Talking points to cover**
- [ ] The ladder we tried: **Tier 1 persona** → **Tier 2 inject the public's real distribution** →
  **constitutional nudge**.
- [ ] **The honest result:** steering a frontier model barely moved it; CIs overlap zero. → **[FINAL FIGURES]**
- [ ] Takeaway: **you can't prompt a foreign model into British values — real alignment lives in the
  weights**, which only open / sovereign models let you touch.
- [ ] This is the **outside-in** half of the pair: Act 4 = can't-prompt-it, Act 5 = must-train-it.

**Feeds from:** `out/align_demo.json` (steering / tiers). **Visual:** default → Tier1 → Tier2 climb (or flat line, honestly).

---

## 5 · Teaching the why — the resolution

**Goal:** name the fix and the frontier evidence behind it; land the project's contribution.

**Talking points to cover**
- [x ] Restate the tension from Acts 3–4: protection is brittle (surface, not principle) **and** you
  can't prompt your way out.
- [x ] **The frontier result** (Anthropic, *Teaching Claude Why*, 2026): training on the **reasoning
  behind** aligned behavior generalizes out-of-distribution far better than training on the behavior
  itself — *teaching the "why" beat training on the "what" (a ~19× reduction in misalignment in their
  setup); constitution-style training survived and amplified through RL.*
- [x ] **The map onto our work:** the AI-reflex gap **is** that out-of-distribution failure — the model
  protected the *evaluated* phrasing, not the principle. Teaching the reasoning is what should close it.
- [x ] **Our local test:** the **constitutional nudge** (a versioned UK public-service constitution,
  `data/constitutions/uk_public_service_v1.md`) is the first probe of whether giving the model the
  *why* narrows the AI-excess gap on UK policy. → **[STATE what the nudge result shows in the new run,
  or "early/indicative" if not yet conclusive]**
- [x ] The ask: **sovereign evaluation + the ability to train on reasons, not just behaviours.**

**Feeds from:** `out/policy_delegate_stress.json` (constitutional modes / `constitutional_nudge`).
**Visual:** AI-excess gap with vs without the constitution.

---

## 6 · What we can & can't claim

**Goal:** the honesty that makes a decision-maker trust the rest.

**Talking points to cover**
- [ ] **Caveats kept visible** (carry these from the run, don't soften):
  - the **AI-excess confound** (Act 3).
  - the demo **replays real runs; it does not run models live.**
  - **[ANY GATE STILL OPEN / SYNTHETIC LAYER]** *(e.g. UK government-change scenario data status).*
  *(Internal-only, kept OUT of the external demo: the 2nd-person class review and the survey-base /
  low-N notes. Wales is left out entirely.)*
- [ ] **What's next** (1–2 lines): **RL / fine-tuning to push the weights toward the public** — testing
  whether we can do locally what the Anthropic paper did (align by teaching the reasoning, not just
  prompting it). The natural sequel to Act 5.
- [ ] Closing line for i.AI: *the uncertainty-aware framing is the feature — this is what assurance for
  public-sector AI actually looks like.*

---

## Things I still need from you to build
ALEX
AI in government is making decisions on modelling, policy, and analysis. How can we assure the public that it is making decisions aligned with their values? 
The public usage of AI chatbots has exploded; however most of the usage is through proprietary models where bias could be introduced that affects the thinking of the population.
How do we align deployed models to have our democratic values; can they reflect human agency as it evolves.

- [ ] **Thesis sentence** (§0) and **the one hook number** (§0).
- [ ] **Final figures** for §2, §3 (the AI-excess table), §4 — or "pull from `out/*.json` when the run lands."
- [ ] **Final model list + flags** (§2).
- [ ] **Constitutional-nudge result** wording (§5) — conclusive vs indicative.
- [ ] **Public-vs-MP audience calls** (§6 and throughout): is Q182 still excluded? all six models named?
  any model you'd rather not single out by name?
- [ ] The **i.AI "why care" close** in your voice (§6).

## Build notes (mine, for when this comes back)

- Re-author `demo/whose_values.html` into these six anchors; keep its nav rail + scroll engine.
- Wire **jump-back nav** (left rail, scroll-progress, click-to-jump) + a per-chart **"?"** that reveals
  method/caveat inline (progressive disclosure) + optional **"2-min / full"** toggle.
- Regenerate the inlined `DATA` blob from the **final** run artifacts — do not ship H5-era numbers.
- Consolidate to **one** canonical self-contained file for the link; retire/appendix `app.html` and
  the duplicate `index.html`.




SO HERE'S MY STORY:

Government across all levels are incorproating AI into their workflows. From simple chat interfaces to agentic deployments, it is informing public policy and driving analysis. But as these systems decide about human facing choices, how can we assure that they align with public preferences for policy as these evolve over governments? 

What this evalaution framework does is test AI for its preferences on key political issues, and then tests if we can nudge it in the direction of the public's view through example scenarios on policy issues. It combines survey analysis and prompt engineering to test for that alignment and explore options for protecting public attitudes in government work. 

Sovereign AI cannot just be about supply chains and training data, sovereignty in AI needs to assure that outside influence into our policymaking processes is also protected from external influence. The use of foreign hosted models will continue for the immediate future so the objective of this project is to identify those gaps between public opinion and AI inference so that we can build trust in deployed enviornments by assuring the public that their voice is also reflected in whatever AI is doing within government. 

The prompt from the hackathon was: Challenge 3: Building sovereign AI capability.
Why? Critical national functions shouldn't depend on a foreign black box. Sovereignty must be proven, not asserted across the whole stack. from model and data to hardware.
Examples: Evals that test model alignment to democratic values. "democracy-bench"
Ask yourself: can i articulate what makes my stack (model, data, evals or infra) sovereign? can i prove alignment to democratic values?