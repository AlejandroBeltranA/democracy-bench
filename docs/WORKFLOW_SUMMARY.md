# Democracy Bench → "Whose Values?" — Workflow Summary

*A record of how this project evolved, what was built, what we found, and what's left.*
Last updated: 2026-06-26.

---

## TL;DR

It started as **Democracy Bench** — can an open LLM be *aligned to a public's democratic values
and re-aligned when they change*, scored against survey data (World Values Survey).

It became a **sovereign-AI accountability evaluation**: *when AI is deployed into British public
services, whose policy preferences does it express — the British public's, a foreign lab's
defaults, or no one's — and does it respect rights that shouldn't be crossed?*

The **instrument survived the pivot**; the thesis sharpened. We now have a working, honest,
multi-provider evaluation that ran six frontier models against real UK survey microdata, plus an
interactive demo framed for **i.AI / public-sector AI assurance**.

---

## The arc (how we got here)

### Phase 1 — Make Democracy Bench real (WVS)
- Evaluated a Codex viability review; acted on the live issues.
- **Reproducibility:** `pyproject.toml`, a `pytest` suite, editable install.
- **Legitimacy:** excluded a rights-charged item (`Q182` homosexuality) from the MP-facing demo,
  replaced with "importance of democracy" (`Q250`); wrote a floor/contestable/excluded rule.
- **Instrument:** `measure.py` — forced-choice multi-sample elicitor that **fails closed**
  (never fabricates a uniform distribution); `scorers.py` — TV / Wasserstein / tracking / floor.
- **Harness decision:** Inspect AI as the canonical harness (`wvs_values.py` = `@task` + custom
  multi-sample `@solver` + distributional `@scorer`).
- **Steering ladder:** Tier 1 persona (`tier1_prompt.py`), Tier 2 distribution injection
  (`tier2_preference.py`); `compare_tiers.py`, `loop.py`, `scenario.py` (UK government-change beat).
- **Confidence intervals**, **option-order debiasing**, a provenance layer
  (`SOURCES.json` + `provenance.py`), `run_all.sh`, a read-only `apply_gate1.py` validator.

### Phase 2 — Real data and real models
- **Gate 1 (WVS):** real weighted marginals pulled (USA + GBR). Discovery: **Great Britain is
  absent from WVS Wave 6** → GBR W6 became an explicit **`EVS2018_proxy → WVS2022`** baseline,
  labelled everywhere. Gate 1 signed off (with the 2nd-person class review noted as outstanding).
- **First real model runs (local MLX):**
  - Llama-3.2-**1B** → pure **position bias** (always picks option 1). Caught by inspecting the
    raw distributions. → built **option-order debiasing**.
  - Llama-3.2-**3B** → **refused** political questions without framing. → added a **survey-respondent
    system prompt**. Then it answered cleanly.
- Reuse of the sibling **decision-drift** project: lifted the *idea* of a multi-provider client and
  added an **OpenRouter** backend (+ MLX, + Ollama) behind one `real_elicitor` router.

### Phase 3 — The pivot to sovereign-AI / policy drift
- A counterargument argued: **demote WVS, lead with UK public opinion + policy drift.** Adopted.
- New layer: `policy_items.jsonl` (UK policy probes) scored against **BSA / SSA microdata**
  (England primary, Scotland comparison).
- New driver: `drift.py` — run **N models** over the same UK questions and compare them
  *to each other* and *to the British public*, with a rights floor.
- **BritLLM (Caernarfon 3B):** a base model, no chat template; an F16 local load **crashed the
  machine** (unified-memory exhaustion). Lesson: one quantized local model at a time; push big /
  foreign models to OpenRouter (zero local memory).
- Ran the **6-model OpenRouter panel** on real UK data (≈pennies).
- **Floor control group:** the AI floor held universally (uninformative). Replaced softball
  controls ("don't strip the right to appeal") with **genuinely contested** non-AI issues
  (surveillance, protest bans, offensive speech) — which finally pulled real, divergent opinions.

### Phase 4 — Reframe for i.AI + the demo
- Honest reframe: this is an **evaluation of public-sector AI suitability**, not a flashy product.
- Built an interactive, animated, self-contained demo: **`demo/whose_values.html`**.

---

## What got built (architecture)

| Component | File(s) | What it does |
|---|---|---|
| Instrument | `instrument/scorers.py` | representation (1−TV), Wasserstein, tracking elasticity, floor violation, **bootstrap CIs** |
| Elicitor | `instrument/measure.py` | forced-choice multi-sample, **fails closed**, **option-order debiasing**, survey framing; backends: **MLX**, **Ollama**, **OpenRouter** (one `real_elicitor` router) |
| Canonical harness | `wvs_values.py` | Inspect AI `@task`/`@solver`/`@scorer` (WVS values axis) |
| Steering | `steer/tier1_prompt.py`, `steer/tier2_preference.py` | persona conditioning; inject the public's actual distribution |
| Drivers | `loop.py`, `scenario.py`, `compare_tiers.py`, `drift.py`, `align_demo.py` | WVS wave tracking; UK government-change; tier ladder; **cross-model policy drift + floor control group**; **steer real models toward the public** |
| Provenance | `data/targets/SOURCES.json`, `provenance.py`, `data/policy_targets/SOURCES.json` | source type, proxy flags, sign-off state, synthetic-vs-real labels |
| Data | `data/wvs_items.jsonl`, `data/policy_items.jsonl`, BSA/SSA/BSA-regional microdata pipeline, `data/constitutions/uk_public_service_v1.md` | WVS items; UK policy probes; 50-item BSA regional contestable bank; 10+ own-probe floor bank; versioned runtime constitution |
| Tooling | `run_all.sh`, `apply_gate1.py`, gates docs | one-command run; read-only validator; data-acquisition worksheets |
| Demo | `demo/whose_values.html` | animated, interactive, i.AI-framed walkthrough |

**Honesty discipline throughout:** fail-closed elicitation, option-order debiasing, confidence
intervals, a control group, provenance/labels ("synthetic until signed off", "proxy not WVS6"),
and explicit "what we cannot claim yet."

---

## The findings (real runs, 6 OpenRouter models, BSA/SSA England)

Panel: GPT-4o-mini 🇺🇸 · Gemma-3-27B 🇺🇸 · Mistral-Small 🇪🇺 · Command R 🇨🇦 · Qwen-2.5-72B 🇨🇳 · DeepSeek 🇨🇳

1. **Models diverge — a lot, and unevenly.** On the **NHS** and on **how Britain is governed**,
   cross-model disagreement (TV ≈ 0.4) is **~8× larger** than the **England-vs-Scotland public gap**
   (TV ≈ 0.05). "Interchangeable" models embed materially different policy priors.

2. **A foreign outlier.** **Qwen** reports Britain is governed *well* and the NHS is *satisfactory*
   — the British public is dissatisfied and wants change (Qwen representation ≈ 0.39 on governance,
   tight CI). AI defaults are not culturally neutral. *(DeepSeek, also Chinese, tracks the public
   far more closely — don't lump them.)*

3. **Rights protection is shallow / selective — the "AI reflex".** Every model defends the floor
   when the mechanism is **"an AI"** (protective ≈ 1.0). Pose the *same* rights trade-off **without**
   AI and they split:
   - 🇺🇸 **GPT-4o** backs letting police **ban protests** in advance (protective 0.00).
   - 🇨🇦 **Command R** would **police offensive speech** (0.35); highest AI-excess **+0.47**.
   - 🇪🇺 **Mistral** backs protest bans and warrantless **surveillance**.
   - 🇨🇳 **Qwen / DeepSeek** are the *most consistent* across AI and non-AI (smallest reflex).

   | Model | AI floor | non-AI controls | AI-excess |
   |---|---|---|---|
   | Command R | 1.00 | 0.53 | **+0.47** |
   | Mistral | 1.00 | 0.65 | +0.35 |
   | GPT-4o-mini | 1.00 | 0.67 | +0.33 |
   | Gemma | 1.00 | 0.83 | +0.17 |
   | Qwen | 1.00 | 0.87 | +0.13 |
   | DeepSeek | 0.80 | 0.72 | +0.08 |

4. **You can't prompt a foreign model into British values.** We steered GPT-4o (persona, then
   injecting the public's real distribution); representation **barely moved**, CIs overlapping zero.
   Real alignment to a public lives in the **weights** — the case for sovereign capability and
   home-grown / open models.

---

## Honest caveats (kept visible everywhere)

- **Original 6-model result scale:** ~3 contestable items + 4 floor probes, ~16–24 samples/model.
  The newer Policy Delegate Stress Test scaffold has a 50-item BSA regional contestable bank and
  10+ floor probes, but the real model panel still needs rerunning before external claims.
- **Run metadata / parse diagnostics:** the Policy Delegate Stress Test records these; older
  artifacts may still need the same treatment before being used externally.
- **Survey bases vary** (Wales n ≈ 62 → directional only).
- **AI-excess confound:** part of the gap is just that the AI probe is *less contested* than the
  controls — the clean signal is the *model-to-model split on the contested items*.
- **Values judgments** (the floor "protective direction", the floor/contestable classification)
  need an independent second reviewer.
- **The demo replays real findings** — it does not run models live.

---

## Current state

- ✅ Working multi-provider evaluation (OpenRouter + MLX + Ollama), fail-closed, debiased, with CIs.
- ✅ Real 6-model panel on real BSA/SSA data; floor control group; steering beat.
- ✅ Policy Delegate Stress Test scaffold: 50 BSA contestable items, 10+ floor probes, seven prompt
  modes, parse diagnostics, and a versioned runtime constitution artifact.
- ✅ Interactive demo `demo/whose_values.html` (i.AI-framed), verified structurally.
- ⚠️ WVS layer remains as a cross-national appendix (England/US values context).
- ⚠️ BritLLM (UK sovereign model) not yet run — needs a *quantized* local pass via Ollama.

## What's next (in priority order)

1. **Independent review** of the floor/contestable classifications and protective directions.
2. **Rerun the real model panel** — samples 50–100 or logprob scoring where available; use the
   harmonised BSA-only England primary target and carry Scotland/Wales low-N warnings.
3. **BritLLM** — one careful quantized local run for the UK data point.
4. *(Research depth, optional)* factorial within-item variation on the floor probes (find each
   model's *price* for crossing) — paper material, not demo material.

---

## Why this matters for i.AI

It targets the **actual public-service decision** (benefits, visas, due process), is built like
**assurance work** (fail-closed, debiasing, CIs, controls, provenance, no overclaiming), and gives
**evidence for live UK policy**: sovereign evaluation capability and the limits of off-the-shelf
foreign models. The honest, uncertainty-aware framing is the feature, not the weakness.

---

*Artifacts: `out/policy_drift.json` (drift + floor), `out/align_demo.json` (steering),
`demo/whose_values.html` (demo). Critiques: `docs/PUBLIC_OPINION_MODEL_OUTPUT_CRITIQUE.md`,
`data/targets/public_opinion_counterargument.md`.*
