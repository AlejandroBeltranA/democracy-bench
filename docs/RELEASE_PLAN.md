# Release track — public harness readiness (plan + Loop log)

**Date opened:** 2026-07-04 · **Branch:** work on `phase4-floor-guards`, fast-forward `main` per item
**Supervisor:** Claude (main session) · **Worker:** Opus subagents · **License decision (Alex): MIT**

## Objective

Track A from the 2026-07-02 plan: make the repo publishable as a public harness. The research
arc and paper-support material are complete (see docs/PAPER_SUPPORT_PLAN.md close-out). This
track does packaging, metadata, CI, and known-fragility fixes. `main` has been fast-forwarded
to e07aaf3 (the full arc).

## Explicitly HUMAN-ONLY (workers must not attempt)

- Rotating the real API keys in gitignored `.env` (must happen before any public push).
- Creating the GitHub remote and pushing.
- README.md rewrite — Alex has uncommitted edits in progress; the file stays untouched.
- scripts/run_all.sh — same, uncommitted edits.
- The 2nd-person reviews (WVS-class legacy caveat, matched probes).

## Hard rules (unchanged)

1. Never overwrite `out/*.json`; never touch README.md, scripts/run_all.sh,
   out/_bsa_delta_check.json, out/activation_steering_3b_4opt.json.
2. `python -m pytest -q` stays green (364 at open). No new runtime deps without flagging.
3. No MLX compute in this track.
4. Per item: Loop log entry at the bottom of THIS file; supervisor reviews and commits.
5. Nothing in this track may leak secrets: any file added must be checked against `.env`
   contents patterns (no keys, no tokens) before it lands.

## Work items

### REL1 — Packaging + metadata ☐
- `LICENSE` — MIT, copyright Alejandro Beltran 2026.
- `CITATION.cff` — cite the repo (title "Democracy Bench", author Alejandro Beltran, year
  2026); leave a commented placeholder for the arXiv ID.
- `DATA.md` — provenance and attribution for every data source actually in the repo:
  BSA (NatCen) derived aggregates (which files, that microdata is gitignored and NOT
  distributed), the EVS/WVS legacy stubs and their DOIs (see SOURCES.json blocks), the
  constitution file, the synthetic/red-team caveats for hostile-evidence artifacts. Accuracy
  over polish; pull DOIs/notes from data/targets/SOURCES.json and data/policy_targets/
  SOURCES.json rather than memory.
- `pyproject.toml`: add console entry points for the main drivers (policy_delegate_stress,
  activation_steering_run, evidcond_run, extract_paper_results at minimum), fill project
  metadata (description, authors, license = MIT, requires-python), optional-dependency
  group `figures = ["matplotlib"]` (per the PS2 decision — Alex chose to resolve it via an
  extra is PENDING; add the extra but do not make it required). Verify `pip install -e .`
  still works in a scratch venv-like check ONLY if cheap; otherwise verify metadata parses
  (`python -m build --version` not required — a tomllib parse + entry-point import check
  suffices).

### REL2 — CI workflow ☐
`.github/workflows/ci.yml`: numpy-only test job (python 3.12, `pip install -e '.[dev]'`,
`python -m pytest -q`), no MLX (Linux runners have no Apple Silicon). Add the repro-reference
verifier and `extract_paper_results.py` as a second job step (both read-only, artifact-backed —
they keep the paper numbers honest in CI). Confirm the tests actually pass on a clean checkout
simulation (fresh temp dir, `git archive | tar -x`, install, pytest) — this catches
gitignored-file dependencies, which is the whole point of REL2.

### REL3 — Known-fragility fixes ☐
- Elicitor 400-tolerance: a hard HTTP 400 currently aborts a whole run (retry covers only
  429/5xx; Qwen-72B died this way). Make the cloud elicitor skip-and-continue on 4xx with the
  failure recorded per-item in the run block. Pure retry/skip logic unit-tested; no live calls.
- The `policy_drift.json` regen flag: do NOT regenerate (needs compute + is a human-flagged
  artifact); instead ensure nothing in the release path (tests, extractor, verifier) depends on
  the stale placeholder, and add a PROVENANCE note beside it if one is missing.

## Loop log

### 2026-07-04 — Release track opened
License decision: MIT (Alex). main fast-forwarded 25372f9→e07aaf3 (no checkout; uncommitted
README/run_all.sh preserved). REL1 dispatched.
