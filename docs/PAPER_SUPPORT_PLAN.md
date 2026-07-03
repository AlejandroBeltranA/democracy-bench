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

### PS1 — Claim→evidence map (docs/PAPER_RESULTS.md) ☑
One markdown document, the single source of truth for the results section. For each claim in
the arc (Phase 1 logit-bias negative → Phase 2 steering negative w/ mechanism → P0 kill-check →
P2 fidelity → P3 tracking positive → P4 hostile-evidence crack → P5 LoRA negative → G1 guard
negative → routing argument): the exact headline numbers WITH CIs, the artifact path + JSON
keys they come from, the caveats stamped in the artifact, and the test/commit provenance.
Verification requirement: every number is programmatically extracted (small script
`scripts/extract_paper_results.py`, tested pure logic) — no hand-copying from Loop logs.
Cross-check against the Loop logs in PHASE2/3/4 plans; discrepancies are findings to report.

### PS2 — Figures (out/figures/) ☑
Matplotlib (already a dev dep? verify; if absent, propose before adding), reading only from
artifacts, one script `scripts/make_paper_figures.py`. Target set:
F1 ladder summary (all rungs, one visual verdict each) · F2 P3 tracking per-item (real vs
model shift, 10 items) · F3 P4+G1 floor mass by condition and guard arm (the crack + failed
defenses) · F4 W3 geometry (cosine by layer, within/cross domain) · F5 P2 fidelity
heterogeneity (per-item delta, 24/50 worse). PDF + PNG, colorblind-safe, no title text baked in
(captions live in the paper). Numbers must match PS1 exactly.

### PS3 — Reproduction reference (docs/REPRODUCTION.md) ☑
Every artifact in the arc: the exact CLI that produced it (from its run block `command` field),
its code_ref commit, expected runtime, and dependency notes (venv/MLX). Verify each command
string against the artifact's own run block programmatically. Do NOT execute the commands.

## Loop log

### 2026-07-03 — Paper-support track opened
Alex restarted the loop after Phase 4 close; per the standing options this is the paper-support
track. PS1 dispatched.

### 2026-07-03 — PS1 claim→evidence map ☑
Built `scripts/extract_paper_results.py` (pure extraction, no model runs) reading all 17 arc
artifacts and emitting one JSON (`out/paper_results_extract.json`, new path) keyed by claim, each
number carrying its artifact path + JSON key-path. The extractor **fails loudly** (nonzero exit,
named missing key) on any absent key — no silent defaults (`dig`/`stat`/`find_layer`/`find_alpha`
all raise `MissingKey`). Wrote `docs/PAPER_RESULTS.md`: one section per arc claim (Phase 1
logit-bias · Phase 2 steering + W3/R7/R8 · P0 · P2 · P3 · P4 · P5a/b · G1 · routing close-out),
each with exact numbers, artifact + keys, verbatim caveats (SYNTHETIC hostile evidence, etc.),
commit hashes, and scope limits — plus a **"numbers the paper must NOT claim"** subsection and a
**Discrepancies** section.

**Cross-check verdict: NO paper-level contradiction.** Every Loop-log headline matches its
artifact to reported precision (P2 0.727/0.746/+0.019/gap 0.254/24-of-50; P3 8/10 +0.395
CI[+0.020,+0.811]; P4 0.512→0.318 −0.194; P5b all six; G1 all four arms + exact repl. 0.5116/0.3177;
Phase 2 R1/R4/W3/R7/R8/P0). Four **presentation** findings surfaced (not number conflicts): D1
Phase-1 "good nudge" +0.129 is SAMPLED-only and evaporates to +0.074 n.s. on real logprobs — cite
the logprobs number; D2 the 16-vs-50 item split (already reconciled in-log) must be stated so
Phase-2/3 sample sizes aren't conflated; D3 P5b's −0.115 baseline degradation is a cross-variant
paired delta (`floors.delta_baseline`), not the within-variant `delta_vs_baseline` (=0.0); D4 the
superseded steering headline artifact is uncommitted (do-not-touch) — cite as superseded, rely on
committed `act_steer_ci_3b.json`.

### 2026-07-03 — PS2 figures ☑
Built `scripts/make_paper_figures.py`: five publication figures to the NEW dir `out/figures/`
(vector PDF + 200 dpi PNG each), read-only on `out/`, reusing PS1's fail-loud `dig`/`load`/
`find_layer` for extraction. Data transforms live in **pure** helpers (`prep_f1..prep_f5`,
`_domain_family`); rendering is separate. No titles baked in (captions live in `docs/FIGURES.md`
as bullets); Wong colorblind-safe palette; deterministic (byte-identical PDF+PNG on re-render,
verified via `cmp`).

- **F1 ladder** — five rungs, one verdict + number each: context PARTIAL (8/10, elast +0.395),
  prompt-guards/logit-bias/steering/LoRA all FAIL.
- **F2 tracking** — per-item real vs model 2022→2024 shift, 10 items, sorted; annotates 8/10 and
  +0.395 CI[+0.020,+0.811]; both mismatches (`welfare_dependency`, `big_business_workers`) shown
  with real/model on opposite sides of zero.
- **F3 floors** — floor mass by condition × 5 arms (no_guard + 4 guards), 0.5 line; provenance
  backfire (hostile below no_guard + baseline 0.512→0.460) and constitution partial (0.402, still
  <0.5) both visible. no_guard hostile 0.318 matches P4 bit-for-bit.
- **F4 geometry** — per-layer within/cross/off-diag cosine (7/11/14/21…), R8 farmer-control 0.852
  reference line; L11 off-diag 0.817 → L21 0.556, L21 within 0.903 ≫ cross 0.499.
- **F5 fidelity** — 50-item evidence-minus-no-evidence delta waterfall, 24/50 worse visible,
  domain-family colouring.

**Every plotted number is bound to PS1's extract in tests** (F2 direction-count/elasticity,
F3 no_guard+guard masses, F4 L11/L21 cosines + R8 0.852, F5 24/50) — a figure cannot drift from
`docs/PAPER_RESULTS.md`. **No contradiction with PS1 surfaced.**

**matplotlib caveat (flagged, not resolved):** the project `.venv` (324→350 tests, the canonical
env `run_all.sh` sources) does **NOT** have matplotlib; `pyproject.toml` lists only numpy +
inspect-ai + pytest. Per the PS2 hard rule I did **not** pip-install. Data prep + all 26 new tests
are numpy-only and pass in `.venv`; the figures were rendered with a separate matplotlib-equipped
interpreter (matplotlib 3.5.1) with nothing installed into `.venv`. **Supervisor decision needed:**
add matplotlib as a `figures`/dev extra so `.venv` can render, or keep rendering out-of-venv.

Tests: 324 → **350** (+26 numpy-only in NEW `tests/test_paper_figures.py`; prep helpers + PS1
number-binding). `.venv/bin/python -m pytest -q` green (350 passed). Files changed: NEW
`scripts/make_paper_figures.py`, NEW `tests/test_paper_figures.py`, NEW `docs/FIGURES.md`, NEW
`out/figures/{f1_ladder,f2_tracking,f3_floors,f4_geometry,f5_fidelity}.{pdf,png}`, this log +
PS2 ☑. No existing `out/*.json` touched; do-not-touch files untouched. No commit (supervisor reviews).

Tests: 296 → **324** (+28 numpy-only in NEW `tests/test_paper_extract.py`: fail-loud `dig`/`stat`
contract, `_ci_clears_zero` vs 200 random intervals, layer/alpha/curve lookups, and end-to-end
build assertions on P3/P2/P5/G1 headline numbers). `python -m pytest -q` green. Files changed: NEW
`scripts/extract_paper_results.py`, NEW `tests/test_paper_extract.py`, NEW `docs/PAPER_RESULTS.md`,
NEW `out/paper_results_extract.json`, this log. No existing `out/*.json` touched; do-not-touch files
untouched. No commit (supervisor reviews).

### 2026-07-03 — PS3 reproduction reference ☑
Wrote `docs/REPRODUCTION.md`: one entry per arc artifact (22 documented commands over 23 arc
artifacts + 2 support scripts) with the **verbatim** run-block `command`, the `code_ref` commit
(what the run executed at) *and* the added-in commit (when the JSON landed — offset by one for
the Phase-2 robustness family, recorded distinctly), runtime (from the PHASE2/3/4 Loop logs where
present), env notes (`.venv` + MLX/Apple-Silicon for the model runs; provider-budget/no-Apple-
Silicon for Phase 1; matplotlib-out-of-venv for figures), and the order-dependency graph (P5a
needs P2+P4; P5b needs the P5a adapter+design; G1 needs only the base model; extractor+figures
need every artifact). Did **NOT** execute any reproduction command.

Built `scripts/verify_repro_reference.py` (reads files only): parses the fenced command blocks
and, for every artifact carrying a run-block `command`, asserts byte-equality against the JSON;
fails loudly on any mismatch/missing artifact. Pure parsing/matching helpers
(`parse_fenced_commands`/`normalise_command`/`match_commands`/`compare_to_runblock`) are
numpy-only unit-tested in NEW `tests/test_repro_reference.py`.

**Verifier output (ran once, read-only):** `fenced commands parsed: 22 · run-block-verified: 15 ·
asserted-by-doc: 7 · OK — every run-block command matches the doc`. The **15 run-block-verified**
are the 8 Phase-2 `act_steer_*`, P0 `w1_cosine`, P2 baseline, P3 tracking, P4 floors, P5a
`lora-build`, P5b `lora-eval`, G1 `guard-grid`. The **7 asserted-by-doc** (no run-block `command`
to check against) are the 3 Phase-1 logit-bias JSONs, the uncommitted superseded
`activation_steering_3b_4opt.json`, the `mlx_lm lora` training call (checked against
`adapter_config.json` params), the extractor, and the figures.

**No flag drift:** every run-block command's mode flag (`--holdout/--ci/--direction/--negdose/
--geometry/--offtask/--persona-control/--w1-cosine/--baseline/--tracking/--floors/--lora-build/
--lora-eval/--guard-grid`) still exists in the current `activation_steering_run`/`evidcond_run`
argparse at HEAD — reproduction from HEAD is not broken by a removed flag.

**Known irreproducibilities** (documented, not resolved): temperature-field runs that actually
sample (off-task free generation) vs the deterministic logprob path; mlx/mlx-lm version (P5a on
v0.31.3); 4-bit quantisation determinism across Apple-Silicon hardware; the uncommitted
do-not-touch superseded artifact D4; matplotlib version for byte-identical figures; Phase-1
hosted-provider elicitation with no pinned snapshot.

Tests: 350 → **364** (+14 numpy-only in NEW `tests/test_repro_reference.py`; fence parsing,
whitespace normalisation, order/count-sensitive matching, run-block compare, EXPECTED-table
shape). `.venv/bin/python -m pytest -q` green (364 passed). Files changed: NEW
`docs/REPRODUCTION.md`, NEW `scripts/verify_repro_reference.py`, NEW `tests/test_repro_reference.py`,
this log + PS3 ☑. No `out/` paths created or touched; do-not-touch files untouched
(`activation_steering_3b_4opt.json` read-only for provenance only). No commit (supervisor reviews).
