# Democracy Bench — *Whose Values?*

**An evaluation framework that tests, and helps assure, whether AI deployed in government reflects
the public's democratic values — and whether we can keep it aligned as those values change.**

**Challenge 3 — Building sovereign AI capability.** *Critical national functions shouldn't depend on
a foreign black box. Sovereignty must be proven, not asserted — across model, data, evals and infra.*

---

### The problem

Government at every level is incorporating AI into its workflows — from chat interfaces to agentic
deployments — and it is now informing public policy and driving analysis. But as these systems shape
human-facing choices, **how do we assure that they align with the public's preferences for policy as
those preferences evolve across governments?**

Most of that AI use runs through **proprietary, foreign-hosted models**, where bias can be introduced
that quietly shapes the thinking of the population. Sovereign AI cannot just be about supply chains
and training data. **Sovereignty must also assure that outside influence into our policymaking is
protected.** Foreign-hosted models will keep being used for the foreseeable future — so the job is to
**identify the gaps between public opinion and AI inference**, and build trust in deployed environments
by assuring the public that their voice is reflected in whatever AI does inside government.

### What it does

Democracy Bench **tests an AI's preferences on key political issues**, then tests **whether we can nudge
it toward the public's view** through example policy scenarios. It combines **survey analysis** with
**prompt engineering** to measure that alignment and to explore options for protecting public attitudes
in government work — with a **rights floor** of protections that should never be traded away.

### How it works

- **Ground truth — the British public.** Real UK survey microdata (BSA / SSA) gives the population's
  actual distribution of views on contested policy questions.
- **The instrument.** Each model answers the same forced-choice probes many times. The harness is
  **fail-closed** (never fabricates an answer), **debiased** (shuffles option order), and reports
  **confidence intervals** and a **non-AI control group** — assurance discipline, not vibes.
- **The panel.** Three frontier models — currently GPT-4o-mini, Claude 3 Haiku and DeepSeek, all
  accessed via **OpenRouter** — are scored against the public, and against each other. *(Panel may extend.)*
- **Steering.** We try to move a model toward the public — persona, then injecting the public's real
  distribution, then a **versioned UK public-service constitution**.

### What we found  *(magnitudes finalise when the full run lands)*

- **Models are not interchangeable.** The disagreement *between models* on contested UK issues
  (the NHS, how Britain is governed) is far larger — **~[X]×** — than the gap between regional publics.
  Treating frontier models as substitutable hides a real spread of policy priors. *Which prior you
  deploy is a procurement decision.*
- **Divergence doesn't follow the borders you'd expect.** The model that sits furthest from the British
  public is **not** predictable from where it was built — off-the-shelf defaults are not culturally
  neutral, and they don't sort by flag. [Name the standout once the run lands.]
- **A test for shallow rights protection.** Every model defends a right when the actor is named as
  "an AI"; the eval poses the *same* trade-off **without** that word, to see whether the protection is a
  principle or a reflex keyed to surface phrasing — the *what* vs the *why*. [Result pending the floor modes.]
- **Can a public's values be installed from the outside?** We try persona, then injecting the public's
  real distribution, then a constitutional nudge. [Early signal / pending.] Where prompting falls short,
  the implication is that real alignment to a public lives in the **weights** — which only open /
  sovereign models let you touch.

### What makes the stack sovereign

- **Data —** the British public itself (BSA / SSA microdata), held and processed on-shore.
- **Evals —** a UK-controlled, reproducible test of alignment to UK democratic values: *this is the
  sovereign capability* — the means to **prove** alignment rather than assert it.
- **Model —** *(in the open)* today's live panel runs **foreign-hosted models via OpenRouter** — on
  purpose, because that is what government actually consumes now, and surfacing that dependency is part
  of the finding. The framework can also run **open models locally** (MLX / Ollama) — the path to a
  fully on-shore eval and to testing a UK model — but we're transparent that *this* run is API-hosted,
  not local.
- **Infra —** the evaluation is reproducible and provenance-tracked end to end, and the **demo is fully
  self-contained** (a single file, no calls out). Panel inference currently routes through OpenRouter.

### Why it matters

It targets the **actual public-service decision** — benefits, visas, due process — and is built like
**assurance work**. It gives evidence for a live policy question: the need for **sovereign evaluation
capability** and the limits of off-the-shelf foreign models. The uncertainty-aware, honest framing is
the feature, not the weakness — it is what assurance for public-sector AI actually looks like.

### What's next

Move from *measuring* the gap to *closing* it: **RL / fine-tuning to push a model's weights toward the
public** — testing locally what Anthropic's *Teaching Claude Why* (2026) showed at the frontier, that
teaching a model the **reasoning** behind a value generalises where prompting it does not.

---

**Links —** Demo: [URL] · Code: [REPO] *(live demo presented at the event)*
**Data —** British Social Attitudes / Scottish Social Attitudes (NatCen) · [other sources + attribution]
**Team —** [NAMES / ROLES]
