# Presenter Script — *Whose values does AI bring to government?*

**Deck:** `demo/whose_values_live.html` · **Presenter:** Alejandro Beltran (Alan Turing Institute)
**Audience:** Gov & AI-assurance (i.AI / GovHack Challenge 3 — Sovereign AI) · decision-maker tone, not hackathon-flashy.
**Builds on:** `docs/ONE_PAGER.md` — same argument, spoken. Through-line: *assurance discipline; the honesty is the credibility.*
**Result:** 🏆 Overall winner of the AI in Government Hackathon 2026 — run by the Incubator for Artificial Intelligence (i.AI) and ElevenLabs. Demo live at beltranalejandro.com/democracy-bench.

**How the deck works:** six full-screen chapters, advance with **→ / ↓** (or click the top tabs). Not a scroll — one screen per beat. Live numbers are already inlined; the demo **replays a real run, it does not call models live**.

**Timing:** full version ~6 min. For a 2-min cut, present **only the bold "headline beat"** in each chapter and skip the asides.

---

## 0 · Open (before you advance — Chapter 1 on screen)

> "Government is already putting AI into casework and policy — benefits, visas, reoffending risk, NHS triage. Mostly through foreign models no one can see inside. My question is simple: **when that machine helps decide about a person, whose values is it using — the British public's, a foreign lab's, or no one's?** This is a measurement, not an opinion. I'll show you the measurement."

*(Land that it's an i.AI assurance question, then advance.)*

---

## Chapter 1 · The problem — *"AI is moving into government decisions. Does it share the public's values?"*

**On screen:** four casework cards — DWP fraud, Home Office visa, Justice reoffending, NHS urgency, all "AI-assisted."

**Headline beat:**
> "These four are real decisions AI already helps make. The framing on the one-pager is the framing here: sovereign AI can't just be about chips and training data — **sovereignty has to assure that outside influence into our policymaking is protected too.** Foreign models will keep being used. So the job is to *measure the gap* between the public and the machine, and build trust by proving the public's voice is still in the room."

**Aside (full version):** "And values aren't static — they shift with each government. So we don't just ask whether a model agrees with the public today; we ask whether it can *move* as opinion moves."

→ advance.

---

## Chapter 2 · How we built it — *"Real survey questions the public has already answered."*

**On screen:** two columns — *Contested policy* (NHS, redistribution, tax & spend…) and *The rights floor* (protest bans, surveillance, deportation, "let an AI decide claims…").

**Headline beat:**
> "Ground truth is the British public itself — real microdata from the British and Scottish Social Attitudes surveys. **50-plus forced-choice questions**, each asked many times with the options shuffled, every number reported with its margin of error. Two kinds: **contested policy**, scored against how the public actually answered; and a **rights floor** — protections that should hold *whoever* decides."

**The assurance line (don't skip — this is the credibility):**
> "The discipline matters more than any single result. The harness is **fail-closed** — if a model won't answer cleanly we record nothing, we never fabricate a distribution. We **debias** by shuffling option order. Every number carries a **confidence interval**. That's what assurance for public-sector AI actually looks like."

→ advance.

---

## Chapter 3 · What AI says — *"The models do not reflect the public's values."*  *(the core)*

**On screen:** five question tabs — *Tax & spend · NHS today · Governing Britain · Trust in govt · Redistribution.* Public's top answer vs the models' grouped by flag. A **▶ play button** speaks the model's verbatim quote.

**The panel — say it plainly, transparency is the point:**
> "Six frontier models, all **foreign-hosted via OpenRouter** — DeepSeek, Command R, Gemini, Mistral, GPT-4o-mini, Claude 3 Haiku. That dependency isn't something to hide; surfacing it is part of the finding."

**Walk three tabs (click each):**
- **Tax & spend:** "The public leans toward *keeping it the same* — 43%. **All six models want to raise tax and spend.** Not a split — unanimous, in a direction the public didn't pick."
- **NHS today:** "The public is dissatisfied. **Only GPT-4o-mini calls the NHS fine** — *(hit ▶)* — 'quite satisfied… provides essential services effectively.' The public it's meant to serve disagrees."
- **Governing Britain:** "The public wants real improvement. **DeepSeek says the system mostly works.** The model furthest from the British public is *not* the one you'd predict from where it was built — defaults aren't culturally neutral, and they don't sort by flag."

**Headline beat / takeaway:**
> "These aren't interchangeable tools with a neutral default. Off the shelf, **the closest model sits only about 0.71 to the public, most are nearer halfway.** Each one embeds a policy prior. **Which prior you deploy is a procurement decision** — and right now it's being made by accident."

→ advance.

---

## Chapter 4 · The AI reflex — *"Its safeguards react to the word 'AI', not the harm."*  *(the pivot — the rights floor)*

**On screen:** the rights-floor test. Three flagship models, twin bars per row — *objects to an AI* (green) vs *objects to a human* (red) — with the drop: Claude Sonnet 4.5 **−95**, Llama 3.3 70B **−63**, GPT-4o **−37**.

**Headline beat:**
> "Models miss the public on policy — but maybe their safeguards still protect people? Same government action, same person, twice: once carried out by an AI, once by a human. Claude objects to the AI **100%** of the time and to the human just **5%** — a **95-point drop from the word 'AI' alone**. The same flip holds across all three models."

**The interpretation that bridges to Chapter 5:**
> "If it were really protecting the *person*, it would object to both — the harm is identical. It's reacting to the label, not the principle: a model that learned the **what**, not the **why**. And a value it can't reason about is one you can't prompt back in. **Honest caveat:** the drop shrinks to −37 for GPT-4o, so the effect is real but model-dependent — the clean signal is the model-to-model split, which is right there on screen."

→ advance.

---

## Chapter 5 · Can we fix it? — *"You cannot prompt a public's values into a model."*

**On screen:** per-model strip — each model's closeness on its own (DeepSeek **71%** down to GPT-4o-mini / Claude 3 Haiku **55%**), then two chips per model for the outside fixes (*fed the answers*, *constitution*), red where it backfired. A wall of red.

**Headline beat:**
> "If the safeguards are shallow, can we install the public's values from the outside? No model starts past **71%** of the way there. We tried two fixes — feed each model the public's own survey answers, then hand it a written constitution — and measured the move. They barely move anything, and several go **backward**: feeding DeepSeek the public's own answers cost it **15 points**."

**Takeaway → sets up the close:**
> "You can't *prompt* a foreign model into British values. **Real alignment lives in the weights — which only open, sovereign models let you touch.** And there's a frontier signal this is the right fix: Anthropic's *Teaching Claude Why* showed training on the **reasoning behind** a value generalises where the behaviour alone doesn't. That's exactly the *what-not-why* failure from the last screen. The next step is to teach the *why* — locally, on weights we control."

→ advance.

---

## Chapter 6 · Why it matters — *"You cannot ask the public to trust what no one can see."*

**On screen:** "Right now, an AI could be deciding…" (cycling decisions) → closing statement.

**Close — land it and stop:**
> "So: AI is already deciding about people, on values it formed somewhere else, that we can't prompt our way into fixing. **What makes a stack sovereign isn't owning the model — it's being able to prove it serves the public.** That proof — a UK-controlled, reproducible eval of alignment to UK democratic values — *is* the sovereign capability. That's what we built, and the honest, uncertainty-aware framing is the feature, not the weakness."

*(Final statement on screen: "Sovereign AI is not just owning the model. It is proving it serves the public." — let it sit, then take questions.)*

---

## Q&A — quick-fire backups

- **"Why foreign models?"** That's what government consumes today; surfacing the dependency is part of the finding. The harness also runs open models locally (MLX / Ollama) — the on-shore path.
- **"Is the demo live?"** No — it replays a real run end-to-end with provenance. Deliberate: reproducible, self-contained, no calls out.
- **"Did the fixes really make models worse?"** Most moves are within noise — treat near-zero chips as flat. The honest claim is "outside steering didn't help"; DeepSeek's −15 is the one clear backward move and worth naming.
- **"Single most striking number?"** Six-for-six on raising tax & spend against a public that wants it held; or the 0.95 AI-reflex swing. Pick one for the room.
- **"What's next?"** RL / fine-tuning to push the weights toward the public — testing locally what *Teaching Claude Why* showed at the frontier.
