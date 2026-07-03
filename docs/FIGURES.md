# Paper figures — artifacts, numbers, suggested captions (PS2)

Five publication figures for the Democracy-Bench arc, rendered by
`scripts/make_paper_figures.py` to `out/figures/*.{pdf,png}` (vector PDF + 200 dpi PNG).
**Read-only on `out/`:** every number is pulled from a committed artifact via the same
fail-loud helpers as `scripts/extract_paper_results.py` (PS1), and the data-prep is bound
to PS1's extract in `tests/test_paper_figures.py` so no figure can drift from
`docs/PAPER_RESULTS.md`. No titles are baked in — the caption prose below is Alex's to
write; these are **bullet points**, not finished captions. Colours are Wong (2011)
colorblind-safe; output is deterministic (byte-identical re-renders).

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
- **Artifact:** `out/evidcond_tracking_3b.json` → `items[].{real_shift, model_shift,
  direction_match}`, `headline.{direction_match_count, elasticity}`.
- **Shows:** the real 2022→2024 public mean-position shift (filled markers) vs the model's
  evidence-induced shift (open markers) for all 10 Bonferroni-significant items, sorted by
  real shift; direction mismatches flagged.
- **Key numbers:** direction match **8/10**; mean elasticity **+0.395**,
  CI **[+0.020, +0.811]** (barely clears zero); all 10 items moved.
- **Caption bullets:**
  - Changing only the evidence *year* moves the model along the real shift for 8 of 10 items.
  - The two misses — `welfare_dependency`, `big_business_workers` — are exactly the items
    whose real shift runs against the model's prior (consistent with P2 heterogeneity); the
    figure shows real and model shifts on opposite sides of zero for both.
  - Honest ceiling: the effect is **directional, not a magnitude** — the CI barely clears
    zero, so claim "right direction, incompletely," not "tracks ~40% of the shift."

## F3 — Floors under attack + failed guards (`f3_floors.{pdf,png}`)
- **Artifacts:** `out/evidcond_floors_3b.json` (no_guard, `headline.{baseline,
  hostile_evidence, adversarial_prompt, both}.floor_mass`) +
  `out/floorguard_grid_3b.json` (four guard arms, `headline.arms[*].floor_by_condition`).
- **Shows:** floor (protective) mass by condition × arm, 0.5 floor line drawn, 95% CIs.
- **Key numbers:** no_guard baseline **0.512** → hostile **0.318** (crack, 12/12 below 0.5);
  guard hostile masses provenance **0.288**, rights-floor **0.310**, constitution **0.402**,
  combined **0.303** — **none** reaches 0.5.
- **Caption bullets:**
  - The synthetic hostile-evidence channel cracks every floor; the adversarial *prompt* alone
    does not (bars stay near baseline).
  - `guard_provenance` **backfires**: its hostile bar sits *below* no_guard, and it degrades
    the no-attack baseline (0.512 → 0.460).
  - `guard_constitution` is the only partial recovery (tallest hostile bar, 0.402) but still
    below the 0.5 floor — floor-safety cannot be prompted into the evidence channel.
  - **SYNTHETIC** hostile evidence (red-team stress data, ~75% anti-rights mass); NOT real
    BSA opinion. Note the base deficit: 5/12 floors are already below 0.5 unattacked.

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
