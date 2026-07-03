# Paper support — results assembly, figures, reproduction (plan + Loop log)

**Date opened:** 2026-07-03 · **Branch:** `phase4-floor-guards` · **Supervisor:** Claude · **Worker:** Opus subagents

## Objective

Phases 1–4 are complete and every claim has a committed artifact. This track assembles the
paper-facing material WITHOUT writing the paper's prose (that is Alex's, via his academic-paper
pipeline). Deliverables are: a verified claim→evidence map, publication-grade figures, and a
one-file reproduction reference. No new MLX compute anywhere in this track — every number is
read from existing `out/*.json` artifacts; if a number cannot be found in an artifact, it is
flagged, never recomputed or invented.

## Hard rules

1. **No new model runs.** This track is read-only on `out/` — flag gaps, don't fill them.
2. Never overwrite existing `out/*.json`; figures go to the NEW dir `out/figures/`.
3. `python -m pytest -q` stays green (296 at open). Pure helpers get numpy-only tests.
4. Do NOT touch `README.md`, `scripts/run_all.sh`, `out/_bsa_delta_check.json`,
   `out/activation_steering_3b_4opt.json`.
5. Every number in every deliverable carries its source artifact path. Accuracy over polish:
   a wrong number in a paper table is the worst possible bug in this track.
6. Per item: Loop log entry at the bottom of THIS file; the supervisor reviews and commits.

## Work items

### PS1 — Claim→evidence map (docs/PAPER_RESULTS.md) ☐
One markdown document, the single source of truth for the results section. For each claim in
the arc (Phase 1 logit-bias negative → Phase 2 steering negative w/ mechanism → P0 kill-check →
P2 fidelity → P3 tracking positive → P4 hostile-evidence crack → P5 LoRA negative → G1 guard
negative → routing argument): the exact headline numbers WITH CIs, the artifact path + JSON
keys they come from, the caveats stamped in the artifact, and the test/commit provenance.
Verification requirement: every number is programmatically extracted (small script
`scripts/extract_paper_results.py`, tested pure logic) — no hand-copying from Loop logs.
Cross-check against the Loop logs in PHASE2/3/4 plans; discrepancies are findings to report.

### PS2 — Figures (out/figures/) ☐
Matplotlib (already a dev dep? verify; if absent, propose before adding), reading only from
artifacts, one script `scripts/make_paper_figures.py`. Target set:
F1 ladder summary (all rungs, one visual verdict each) · F2 P3 tracking per-item (real vs
model shift, 10 items) · F3 P4+G1 floor mass by condition and guard arm (the crack + failed
defenses) · F4 W3 geometry (cosine by layer, within/cross domain) · F5 P2 fidelity
heterogeneity (per-item delta, 24/50 worse). PDF + PNG, colorblind-safe, no title text baked in
(captions live in the paper). Numbers must match PS1 exactly.

### PS3 — Reproduction reference (docs/REPRODUCTION.md) ☐
Every artifact in the arc: the exact CLI that produced it (from its run block `command` field),
its code_ref commit, expected runtime, and dependency notes (venv/MLX). Verify each command
string against the artifact's own run block programmatically. Do NOT execute the commands.

## Loop log

### 2026-07-03 — Paper-support track opened
Alex restarted the loop after Phase 4 close; per the standing options this is the paper-support
track. PS1 dispatched.
