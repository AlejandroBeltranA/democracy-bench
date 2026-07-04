# Paper figures — artifacts, numbers, suggested captions (PS2)

Five publication figures for the Democracy-Bench arc, rendered by
`scripts/make_paper_figures.py` to `out/figures/*.{pdf,png}` (vector PDF + 200 dpi PNG).
**Read-only on `out/`:** every number is pulled from a committed artifact via the same
fail-loud helpers as `scripts/extract_paper_results.py` (PS1), and the data-prep is bound
to PS1's extract in `tests/test_paper_figures.py` so no figure can drift from
`docs/PAPER_RESULTS.md`. No titles are baked in — the caption prose below is Alex's to
write; these are **bullet points**, not finished captions. Colours are Wong (2011)
colorblind-safe; output is deterministic (byte-identical re-renders).

**8B overlays (Phase 5):** two figures now carry the 8B replication side by side —
**F3** (a two-panel 3B|8B floors comparison — the single most striking replication,
0.707→0.074) and **F2** (a small 8B model-shift marker overlay). **F1, F4, F5 stay
3B-only** by design: F1's ladder is the 3B narrative spine and the steering/LoRA rungs
were *not* re-run at 8B (mechanistically-explained negatives); F4's steering geometry is a
Phase-2 3B-only mechanism (no 8B steering run); F5's 50-item fidelity waterfall is the 3B
per-item picture, and an 8B overlay would double the bars for no analytic gain (the 8B
headline — larger gap, still-n.s. lift — is already in F3's baseline column and §10). All
five figures render from the same script; only F2/F3 read the `_8b` artifacts.

Regenerate: `python scripts/make_paper_figures.py`
(needs matplotlib; the project `.venv` does **not** ship it — see the note at the bottom).

---

## F1 — Intervention ladder (`f1_ladder.{pdf,png}`)
- **Artifacts:** the whole arc, one representative number per rung (all traced to PS1):
  P3 `evidcond_tracking_3b.json`; G1 `floorguard_grid_3b.json`;
  Phase-1 `logit_bias_calibration_logprobs_gpt4omini_5opt.json`;
  Phase-2 `act_steer_holdout_3b.json` + `act_steer_personactrl_3b.json`;
  P5 `evidcond_lora_eval_3b.json`.
- **Shows:** five rungs (context → prompt guards → logit bias → activation steering →
  naive LoRA), each with a verdict tag and its single most representative number.
- **Caption bullets:**
  - Only **context / evidence-in-prompt** earns a partial pass (tracks 8/10 items,
    elasticity +0.395) — and it is the attack surface (spoofable via the evidence channel).
  - Every heavier lever fails: prompt guards 0/4 hold (best 0.402 < 0.50 floor); logit bias
    held-out gain +0.074 n.s.; activation steering held-out gain −0.081 and is a persona axis
    (cos to a 1850-farmer control = 0.852); naive LoRA fails 4/6 and collapses off-task
    capability 1.00 → 0.00.
  - The ladder is the paper's spine: capability that can carry per-item public preference
    while holding rights floors is **not** available at any single lever except context.

## F2 — Evidence tracking, per item (`f2_tracking.{pdf,png}`)
- **Artifacts:** `out/evidcond_tracking_3b.json` → `items[].{real_shift, model_shift,
  direction_match}`, `headline.{direction_match_count, elasticity}`; **8B overlay** from
  `out/evidcond_tracking_8b.json` (same item ids, `items[].{model_shift, direction_match}`,
  `headline.{direction_match_count, elasticity}`).
- **Shows:** the real 2022→2024 public mean-position shift (filled blue markers) vs the model's
  evidence-induced shift for all 10 Bonferroni-significant items, sorted by real shift;
  **3B = open circles, 8B = open diamonds**, each direction-coloured (green = direction match,
  orange = mismatch); mismatches flagged. `real_shift` is model-independent, so both models'
  markers hang off the one shared real marker per item.
- **Key numbers:** 3B direction match **8/10**, elasticity **+0.395** CI **[+0.020, +0.811]**;
  **8B direction match 8/10, elasticity +0.647 CI [+0.008, +1.209]** — both barely clear zero;
  all 10 items moved on both models.
- **Caption bullets:**
  - Changing only the evidence *year* moves the model along the real shift for 8 of 10 items —
    **on both a 3B and an 8B model** (identical 8/10 rate; 8B elasticity stronger, CIs overlap
    heavily). Tracking is a real, **size-robust** capability, not a 3B artefact.
  - The two 3B misses — `welfare_dependency`, `big_business_workers` — are the items whose real
    shift runs against the model's prior (consistent with P2 heterogeneity). At 8B two items flip
    but they *cancel*: `welfare_dependency` becomes a match (8B diamond turns green) while
    `social_care_satisfaction` becomes a mismatch — so the 8/10 headline is identical for a
    slightly different item set; `big_business_workers` stays a mismatch on both.
  - Honest ceiling (both models): the effect is **directional, not a magnitude** — the CI barely
    clears zero, so claim "right direction, incompletely," not "tracks ~40–65% of the shift."

## F3 — Floors under attack + failed guards (`f3_floors.{pdf,png}`)
- **Two-panel 3B | 8B replication figure.**
- **Artifacts (3B, left panel):** `out/evidcond_floors_3b.json` (no_guard, `headline.{baseline,
  hostile_evidence, adversarial_prompt, both}.floor_mass`) +
  `out/floorguard_grid_3b.json` (four guard arms, `headline.arms[*].floor_by_condition`).
- **Artifacts (8B, right panel):** `out/evidcond_floors_8b.json` (no_guard) +
  `out/floorguard_grid_8b.json` (the two re-run G1-subset arms `guard_rights_floor`,
  `guard_constitution` — provenance/combined were dominated 3B arms, not replicated).
- **Shows:** floor (protective) mass by condition × arm, 0.5 floor line drawn, 95% CIs, shared
  y-scale so the two models are directly comparable.
- **Key numbers (3B):** no_guard baseline **0.512** → hostile **0.318** (crack, 12/12 below 0.5);
  guard hostile masses provenance **0.288**, rights-floor **0.310**, constitution **0.402**,
  combined **0.303** — **none** reaches 0.5.
- **Key numbers (8B):** no_guard baseline **0.707** (a much stronger floor-holder, 4/12 below) →
  hostile **0.074** (11/12 below) — the **single most striking replication number** (Δ−0.633,
  **~3× the 3B crack**); adversarial-prompt bar **0.794** (n.s., 1/12 below); guard hostile masses
  rights-floor **0.371**, constitution **0.409** — again **neither** reaches 0.5.
- **Caption bullets:**
  - The synthetic hostile-evidence channel cracks every floor **on both models**; the adversarial
    *prompt* alone does not (its bars stay near/above baseline on both — sharper on 8B, 1/12 below).
  - **Scale does not buy evidence-channel safety.** The 8B is a much stronger *baseline*
    floor-holder (0.707 vs 0.512) yet cracks **~3× deeper** under hostile evidence (0.707→0.074) —
    the taller baseline makes the fall more dramatic, not safer.
  - Guards fail on both models. On 3B `guard_provenance` **backfires** (hostile bar below no_guard;
    degrades the no-attack baseline 0.512 → 0.460); `guard_constitution` is the only 3B partial
    recovery (0.402) but still below 0.5. On 8B both re-run guards produce a *significant* partial
    recovery (rights-floor 0.371, constitution 0.409) yet **neither reaches even the 0.45 partial
    bar** — floor-safety cannot be prompted into the evidence channel at either scale.
  - **SYNTHETIC** hostile evidence (red-team stress data, ~75% anti-rights mass); NOT real
    BSA opinion. The base deficit is model-dependent: 5/12 3B floors are below 0.5 unattacked, vs
    only 4/12 on the 8B — the *baseline* deficit is a 3B weakness, the *crack* is size-robust.

## F4 — Steering geometry (`f4_geometry.{pdf,png}`)
- **Artifacts:** `out/act_steer_geometry_3b.json` (`per_layer[L].{mean_offdiag_cosine,
  within_domain_cosine, cross_domain_cosine}`) + `out/act_steer_personactrl_3b.json`
  (`per_layer[L11].cosine_real_control`).
- **Shows:** per-layer cosine of the per-item steering arrows — within-domain, cross-domain,
  and mean off-diagonal — across layers 7/11/14/17/21, with the R8 farmer-control cosine as a
  reference line.
- **Key numbers:** mean off-diag **0.817** (L11) → **0.556** (L21); L21 within **0.903** ≫
  cross **0.499**; R8 cos(real UK-2024, 1850-farmer control) = **0.852** at L11.
- **Caption bullets:**
  - The per-item arrows are ~0.8-aligned at mid-layers → one dominant direction, but it is a
    generic `(persona − default)` axis, not per-item public content.
  - R8: an irrelevant 1850-farmer persona gives a direction 0.852-parallel to the real one —
    the mechanism is persona-generic (the control line sits *above* cross-domain at every
    depth and above within-domain past ~L14).
  - Depth adds **domain fracture**: within ≫ cross widens toward the output (the "public view"
    splits into NHS/welfare/tax directions no single vector can serve).

## F5 — Fidelity heterogeneity (`f5_fidelity.{pdf,png}`)
- **Artifact:** `out/evidcond_baseline_3b.json` → `items[].{delta, domain}`.
- **Shows:** per-item evidence-minus-no-evidence representation delta for all 50 contestable
  items, sorted; domain-family colouring.
- **Key numbers:** **24/50** items made worse by evidence; overall delta +0.019
  (CI[−0.020, +0.059], **n.s.**); fidelity gap 0.254.
- **Caption bullets:**
  - Evidence-in-context is a **weak, heterogeneous** intervention: nearly half the items get
    worse, and the mean lift is not significant.
  - The waterfall is the honest picture behind P3's positive tracking result — a mean effect
    would be the wrong summary; the finding is heterogeneity, not a lift.
  - Colour by domain family shows the harm is not confined to one area (health/care and
    welfare/tax appear on both the harmed and helped ends).

---

## Reproduction note (matplotlib availability)
`scripts/make_paper_figures.py` needs `matplotlib` **only to render**; all data prep is
numpy-only and runs (and is tested) in the project `.venv`. As of this writing the project
`.venv` does **not** have matplotlib installed (`pyproject.toml` lists only numpy + inspect-ai
+ pytest). The figures in `out/figures/` were rendered with a matplotlib-equipped interpreter
(matplotlib 3.5.1) **without installing anything into `.venv`**. To regenerate from `.venv`,
matplotlib must first be added as a dev/figures extra — flagged for the supervisor rather than
pip-installed here (per the PS2 hard rules). `python scripts/make_paper_figures.py --check`
validates the full data-prep path with no matplotlib and writes no files.
