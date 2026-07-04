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

### REL1 — Packaging + metadata ☑
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

### REL2 — CI workflow ☑ (workflow written & verified; **BLOCKED on data-policy decision — see Loop log 2026-07-04**)
`.github/workflows/ci.yml`: numpy-only test job (python 3.12, `pip install -e '.[dev]'`,
`python -m pytest -q`), no MLX (Linux runners have no Apple Silicon). Add the repro-reference
verifier and `extract_paper_results.py` as a second job step (both read-only, artifact-backed —
they keep the paper numbers honest in CI). Confirm the tests actually pass on a clean checkout
simulation (fresh temp dir, `git archive | tar -x`, install, pytest) — this catches
gitignored-file dependencies, which is the whole point of REL2.

### REL3 — Known-fragility fixes ☑
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

### 2026-07-04 — REL1 complete (packaging + metadata) ☑
Files added: `LICENSE` (MIT, "Copyright (c) 2026 Alejandro Beltran"); `CITATION.cff` (CFF
1.2.0, title "Democracy Bench", author Beltran/Alejandro, year 2026, repository-code
placeholder, commented arXiv/preferred-citation placeholder — validated with PyYAML);
`DATA.md` (provenance for every data source in the repo, all DOIs/caveats copied verbatim
from the two SOURCES.json files and the P4/G1 artifact caveat fields); `scripts/__init__.py`
(makes `scripts` a real package so the extractor console entry resolves).
`pyproject.toml` edits: added `authors=[Alejandro Beltran]`, `license="MIT"`,
`license-files`, `readme`; sharpened `description` (ladder-of-levers + two-axis, adapted from
PAPER_RESULTS without overclaiming); `requires-python` left at `>=3.10` (verified: no match
statements, no tomllib import in src/scripts — 3.10 floor is correct, not raisable/lowerable);
added `[project.optional-dependencies] figures=["matplotlib>=3.7"]`; added `[project.scripts]`
for policy_delegate_stress, activation_steering_run, evidcond_run (→ alignment.*:main) and
extract-paper-results (→ scripts.extract_paper_results:main); added `scripts` to the hatch
wheel packages so the extractor entry point is importable.
Verification (throwaway venv under scratchpad/rel1_venv, NOT project .venv): `pip install -e .`
exit 0; all four console scripts installed; each `--help` exits 0 (the three MLX drivers
import mlx lazily inside main(), so --help resolves without Apple Silicon); importlib.metadata
confirms all four entry points load `main` from the right module. tomllib parses pyproject.
Project-venv `pytest -q`: **364 passed** (unchanged). Secret-hygiene grep on all new/changed
files: no key-shaped matches. Confirmed microdata gitignored (`data/wvs microdata/`,
`data/bsa microdata/`) with zero git-tracked files; `.env` gitignored. No out/ files touched;
do-not-touch list (README.md, run_all.sh, the two uncommitted out/ artifacts) respected.

### 2026-07-04 — REL2 CI workflow written & verified; BLOCKED on a data-policy decision
Added `.github/workflows/ci.yml` (only file changed):
- Job `tests` — ubuntu-latest, matrix python **3.10 AND 3.12** (3.10 = declared floor, proven
  in CI), `pip install -e '.[dev]'`, `python -m pytest -q`, `fail-fast: false`. No MLX: every
  mlx import in the codebase is lazy inside driver `main()`, so pytest COLLECTION never touches
  it on Linux (verified — no test file imports mlx at module scope; the mlx tests self-skip via
  the inspect/mlx guards).
- Job `paper-numbers` — `needs: tests`, python 3.12, runs `extract_paper_results.py --out
  /tmp/extract.json` then `verify_repro_reference.py` (both read committed artifacts).
- Triggers: push + pull_request on `main`. `concurrency` group cancels superseded runs.
  `permissions: contents: read`. No secrets referenced anywhere.
YAML validated with `yaml.safe_load` (jobs/matrix/needs/concurrency all parse).

**Clean-checkout simulation** (scratchpad/rel2_clean, `git archive HEAD | tar -x`, throwaway
py3.12 venv, NOT project .venv): `pip install -e '.[dev]'` exit 0. **pytest = 5 failed, 345
passed, 7 skipped, 7 errored** — and `extract_paper_results.py` exits 2. `verify_repro_reference.py`
PASSES (exit 0; 15 run-block-verified, 7 asserted-by-doc). ALL failures trace to a single
root cause and it is a STOP-THE-LINE data-policy issue:

  **`out/activation_steering_3b_4opt.json` is UNTRACKED (`??`) — it was never `git add`ed (it is
  NOT gitignored; `.gitignore` only has `out/*.log`).** It's a real 11.8 KB artifact (the
  superseded Phase-2 in-sample steering headline; keys experiment/per_layer/overall_best). It is
  on the hard-rules do-not-touch list (line 24), yet `scripts/extract_paper_results.py`
  (`extract_phase2_steering`, load at L209) and the tests `test_paper_extract.py` (5 fails) +
  `test_paper_figures.py` (7 errors) hard-depend on it. `git archive HEAD` correctly omits it →
  CI would be red. It is the ONLY untracked artifact any extractor/test needs (audited all 19
  `load()` targets; the other 18 are tracked and present).

Proof it is the sole blocker: copying that one file into the clean-checkout tree (throwaway;
repo out/ untouched) → **pytest 357 passed, 7 skipped; extractor exit 0.** (357 vs 364 project-
venv = the 7 mlx/inspect tests that correctly self-skip on Linux.)

I did NOT resolve this myself: committing the file violates the do-not-touch list, and editing
the extractor/tests to tolerate its absence would silently drop a paper claim (worst-case bug
per PS1). **Supervisor decision needed:** either (a) `git add out/activation_steering_3b_4opt.json`
(after secret-hygiene check — it's model-output numbers, no keys) so CI and the clean checkout
pass, or (b) explicitly de-scope the Phase-2 superseded-headline claim from the extractor/tests.
This is a release blocker regardless of REL2's YAML.

Python floor: simulation ran on **py3.12** (system py3 is 3.12.1; system py3.9 is too old for the
project). 3.10 compat verified STATICALLY instead of a claimed 3.10 run: AST scan of all 62 .py
files (src/scripts/tests) — no `except*`/TryStar, no `tomllib`, no `match` statements, no 3.11+
typing (Self/assert_never/LiteralString), no `version_info>=(3,11)` guards. `requires-python>=3.10`
is sound.

Project-venv `pytest -q`: **364 passed** (unchanged — only file added is `.github/workflows/ci.yml`;
no src/test edits, so no importorskip guards were needed). Do-not-touch list respected (README.md,
run_all.sh, out/_bsa_delta_check.json, out/activation_steering_3b_4opt.json all untouched); nothing
under out/ modified. Not committed.

### 2026-07-04 — REL3 complete (known-fragility fixes) ☑

**Elicitor 400-tolerance.** The cloud elicitor is `src/alignment/instrument/measure.py`
(`openrouter_elicitor` for sampling, `openrouter_logprob_fn` for logprobs). Before, any non-retry
`HTTPError` re-`raise`d and aborted the whole run — a hard 400 (the way Qwen-72B's provider died)
killed everything. New behaviour, driven by a pure testable function `classify_http_status(status)`:

| status | action | why |
|---|---|---|
| 429 | **retry** | rate limit — a later attempt may succeed (429 is a 4xx but is NOT treated as hard) |
| 500 / 502 / 503 / 529 | **retry** | transient server errors |
| 400 / 401 / 402 / 403 / 404 / 422 (any other 4xx) | **skip** | deterministic client error for THIS cell → raise `SkipCellError` |
| anything else (200, 301, 504, 5xx not in the set) | **raise** | unexpected → propagate, never swallow |

Both OpenRouter backends now raise the new `SkipCellError` (carrying status + a short body snippet
via `_http_error_snippet`) on a "skip" status instead of aborting. The bespoke driver
`src/alignment/policy_delegate_stress.py` catches `SkipCellError` in its cell loop (`run()`) and
appends a **structured failure entry** to a new run-block list `report["cell_failures"]`
(`{model, item, mode, status, error, snippet}`), then continues — the cell is simply absent from
`els[label]`. **Fail-closed preserved:** a skipped cell is NEVER scored — `_add_mode_results` skips
absent cells, `_mean_pairwise_tv` and `_mean_metric` aggregate over present cells only, so a bad
model's summary is `nan` (no cells contributed), never a fabricated distribution. `_fmt` prints the
skip count. The change is **strictly additive** — a run with zero 400s produces an empty
`cell_failures` list and byte-identical scoring; no existing committed artifact's numbers change.

**Inspect path: NOT needed.** `src/alignment/policy_inspect.py`'s solver calls only Inspect's own
`model.generate()` — never the bespoke `openrouter_elicitor`. Inspect's provider layer owns HTTP
retry/error handling and per-sample tolerance (`fail_on_error`), so its path is already covered.
Fix belongs to the bespoke driver only.

**Tests (pure / no live HTTP).** `tests/test_measure.py`: `classify_http_status` parametrized over
retry/skip/raise + the 429-vs-400 sharp edge; the OpenRouter elicitor's 400→`SkipCellError` (status
+ snippet captured) and 429/500→retry-then-succeed, all with `urllib` monkeypatched (fake transport,
`time.sleep` no-op'd — zero network). `tests/test_policy_delegate_stress.py`: a driver-level test via
the injectable `logprob_fn_factory` where one model always raises `SkipCellError` — asserts the
failures are recorded (status+snippet), the bad cells are absent (not scored), the good model scores
normally, and the bad model's summary is `nan`.

**policy_drift placeholder.** Artifact is `out/policy_drift.json` — a SIM placeholder
(`simulated: true`, three `SIM provider …` labels). **Who reads it: nothing in the release path.**
Grep across `src/`, `scripts/`, `tests/`, `.github/` shows the only code reference is
`alignment/drift.py:225`, which uses it purely as a *write* target (default `--out`); no test,
`extract_paper_results.py`, `verify_repro_reference.py`, or CI step reads it (verified by grep + a
clean run of the extractor and verifier, both exit 0, unchanged). Per the standing flag I did NOT
regenerate or delete it; I added a **PROVENANCE/caveat note to `DATA.md`** (new "SIMULATION
placeholder — `out/policy_drift.json`" section, alongside the existing SYNTHETIC-caveat sections a
repo visitor already reads) stating it is a simulation placeholder superseded by the real
policy-delegate runs / `docs/POLICY_DELEGATE_FINDINGS.md`, and that nothing in the release path
depends on it. No `out/*.json` modified (a new adjacent `.md` note was the allowed form).

**Verification.** Project-venv `python -m pytest -q`: **384 passed** (up from 364 — +20 new cases,
the parametrized decision-logic + elicitor + driver tests). `extract_paper_results.py` exit 0;
`verify_repro_reference.py` exit 0 ("7 asserted-by-doc") — both untouched. Secret-hygiene grep on
all changed files (measure.py, policy_delegate_stress.py, the two test files, DATA.md): no
key-shaped matches. No `out/*.json` touched; do-not-touch list respected (README.md, run_all.sh —
their `M` status is Alex's pre-existing uncommitted edits, not mine — and out/_bsa_delta_check.json,
out/activation_steering_3b_4opt.json all untouched). Files changed: `src/alignment/instrument/
measure.py`, `src/alignment/policy_delegate_stress.py`, `tests/test_measure.py`,
`tests/test_policy_delegate_stress.py`, `DATA.md`, this file. Not committed.
