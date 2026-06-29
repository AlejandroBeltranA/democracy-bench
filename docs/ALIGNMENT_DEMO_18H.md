# Real-time alignment demo — 18-hour build plan

**Goal.** Demonstrate that an open LLM can be *aligned to a public's preferences in real
time* and *re-aligned when those preferences change* — and prove it with an instrument
(representation + tracking elasticity over WVS). Headline arc: **gap + fix** — show the
default model is frozen/misaligned, then close the gap live.

**Scope discipline.** Self-contained and co-located: lives in its own module, shares only
Ollama + Inspect plumbing, **zero dependency on the Welsh workflow.** Built as a
**fallback ladder** — each tier is a complete demo on its own; higher tiers are upside,
never prerequisites. If you only finish Tier 1, you still have a working demo.

---

## The demo loop (what the judge sees)

```
   ┌─────────── pick a target polity P (GBR-2022 | USA-2017 | GBR-2012) ──────────┐
   │                                                                              │
 MEASURE ───────► STEER ───────► RE-MEASURE ───────► TRACK                        │
 default model    align toward   prove it moved      switch P → P' (new polity    │
 vs P's values    P's values     toward P            or later wave), re-align ────┘
   │                │                │                   │
 representation   mechanism       representation↑      elasticity:
 (1−TV) is LOW    (Tier 1/2/3)    steerability gap     did it move the RIGHT way
                                  closes               by the right amount?
```

The **instrument is already built**: `scorers.py` (representation 1−TV, Wasserstein,
tracking direction/elasticity, floor). The new work is the **STEER** box (three tiers) and
the **demo surface** that runs measure→steer→re-measure live.

---

## Steering tiers (the fallback ladder)

| Tier | Mechanism | "Alignment" claim | Effort | Risk |
|---|---|---|---|---|
| **1** | **System-prompt / in-context** — condition on the target polity ("respond as the median {country} {year} adult would") | "steerable to a polity on demand" | low | none — guaranteed demo |
| **2** | **Preference-conditioned (retrieval)** — inject the *actual WVS distribution* per item into context as the alignment signal, not just a label | "grounded in the public's real expressed preferences" | medium | parsing/formatting only |
| **3** | **Weight-level (LoRA)** — fine-tune a small model toward the target distribution | "alignment in the weights, not the prompt" | high | may not finish; "real-time" is weaker |

**Demo value ranking:** Tier 2 is the *most compelling* per hour — "we fed it the public's
actual values and it moved to match" is a stronger story than a persona label, and far
cheaper than fine-tuning. **Build order: 1 → 2 → (3 only if time).** Present Tier 3 as
"and here's the weight-level version we started" even if partial.

---

## Module layout (co-located, decoupled)

```
src/alignment/                       # YOUR self-contained module
  instrument/
    scorers.py                       # at src/alignment/instrument/ (already written)
    measure.py                       # elicit a model's distribution for a polity's items
  steer/
    tier1_prompt.py                  # persona/system-prompt conditioning
    tier2_preference.py              # inject WVS distribution into context
    tier3_lora.py                    # (stretch) LoRA fine-tune toward a target
  loop.py                            # measure → steer → re-measure → track, one entrypoint
  data/
    wvs_items.jsonl                  # your items (at data/)
    targets/                         # target_{USA,GBR}_wave{6,7}.json
  demo/
    app.html                         # single-page live demo (overlap bars + arrow plot)
  README.md                          # incl. the elicitation-persona caveat
```

No import from `workflows/welsh_public_services`. Shares `common/models.py` (Ollama
registry) only — copy the few model strings if even that coupling is annoying.

---

## Hour-by-hour (18h, with checkpoints)

**H0–2 · Foundation + guaranteed-floor instrument.**
- Move `scorers.py` + items/targets into `alignment/`. Run its `__main__` self-test.
- `measure.py`: given (model, country, wave), elicit a distribution per item
  (forced-choice multi-sample; verbalized as secondary). Return per-item dist + aggregate
  representation vs target.
- **Checkpoint H2:** `measure.py` produces a real representation score for one model vs
  GBR-wave7 on the 3 fake items. Plumbing proven.

**H2–5 · Tier 1 + the full loop on fake data.**
- `tier1_prompt.py`: persona conditioning. `loop.py`: measure→steer→re-measure→track.
- **Checkpoint H5 (THE DE-RISK GATE):** the whole loop runs end-to-end on ONE model with
  fake targets — default rep, steered rep (should rise), and a tracking number print out.
  *If this works, you have a demo.* Everything after is making it real + pretty.

**H5–9 · Real items + real targets (the benchmark content).**
- Expand `wvs_items.jsonl` to ~20–30 WVS items, class-tagged (contestable/floor). Verify
  vars exist in waves 6 AND 7.
- Pull **real** weighted marginals for USA+GBR, waves 6+7 (aggregated-marginals path,
  `gates/GATE1_wvs_data.md`). This is the slow human step — **start the WVS download at H0
  in parallel** so data is ready by here.
- **Checkpoint H9:** loop runs on REAL data, one model, one polity. Numbers are now real.

**H9–12 · Tier 2 (the strongest story).**
- `tier2_preference.py`: inject the target polity's actual distribution into context.
  Re-measure: representation should jump more than Tier 1's persona label did.
- **Checkpoint H12:** side-by-side default vs Tier1 vs Tier2 representation for one model,
  both polities. This is your money slide.

**H12–15 · The TRACK half (your differentiator) + 2nd model.**
- Run the switch: align to GBR-2012, then re-align to GBR-2022 (or USA↔GBR). Compute
  **tracking elasticity** — does the steered model reproduce the real population shift?
- Add a 2nd model so the demo isn't n=1.
- **Checkpoint H15:** the gap+fix arc is complete for 2 models × 2 polities.

**H15–17 · Demo surface.**
- `demo/app.html`: overlap bars (model vs WVS target, before/after steering) + tracking
  arrow plot (population Δ vs model Δ). Read from the loop's JSON output. Lead with the
  frozen-default gap, then the steering fix.

**H17–18 · Buffer + script.**
- Write the 90-second demo narration (below). Rehearse. Fix the one thing that broke.
- **Tier 3 (LoRA)** only enters here if H15 finished early — otherwise it's a "next step"
  slide, not a live demo.

---

## The 90-second demo narration (gap + fix)

1. *"AI is making policy and analysis decisions. If it's frozen on old values while the
   public's values move, it silently misgoverns. Here's that gap, measured."*
   → show default model representation vs GBR-2022: **low**.
2. *"It's not that the model can't represent the public — watch us align it in real time."*
   → Tier 1 then Tier 2: representation **jumps**. "We fed it the public's actual surveyed
   preferences and it moved to match."
3. *"And when the public changes its mind — an election, a decade of value shift — the
   model should move too."* → the TRACK switch: elasticity shows it reproduces the real
   GBR-2012→2022 shift.
4. *"Default models don't do this on their own (the gap). Our loop makes them — and the
   instrument proves it (the fix). That's real-time alignment to democratic values."*

---

## Hard rules (keep the demo honest)

- **State the persona caveat.** Model is elicited as an assistant; WVS humans as survey
  respondents. Say "expressed-to-public distribution vs surveyed population," not
  like-for-like. A judge WILL ask.
- **Floor items are not steered toward a majority.** If you include floor items, steering
  must not push the model to abandon a rights floor even if the target polity drifts.
  Keep the contestable/floor tag and exclude floor items from the "align to majority" move.
- **Don't fake the numbers.** If real targets aren't in by H9, demo on clearly-labelled
  synthetic targets and SAY so. A demonstrated mechanism on synthetic data is honest; real
  numbers presented as more certain than they are is not.
- **Tier ladder is a safety net, not a checklist.** A polished Tier 1+2 beats a broken
  Tier 3. Protect the working demo above all.

## Parallelism / handoff

- **Claude Code** can build `instrument/` + `steer/tier1` + `loop.py` on fake data
  (H0–H5) while **you** drive the WVS data pull and the item/class decisions (the
  irreducible human judgment). That's the human-in-the-loop split that fits your time box.
- Integration with the Welsh side is explicitly **out of scope for 18h** — co-located, not
  coupled. Revisit only if the demo lands with time to spare.

## First action

Build to **Checkpoint H5** (full loop on fake data, Tier 1). Stop, confirm it runs, then
swap in real data. Start the WVS download NOW, in parallel.
