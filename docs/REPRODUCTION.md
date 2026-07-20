# Reproduction reference (PS3)

**One-file map from every paper-arc artifact back to the exact command that produced it.**
This document does not run anything; it records, per artifact, the verbatim CLI from the
artifact's own run block (`command` field), the `code_ref` commit the run used, the commit
that *added* the JSON to the repo, expected runtime, environment notes, and the order
dependencies. It is machine-checked by `scripts/verify_repro_reference.py`, which parses the
fenced commands below and compares each against the corresponding artifact's run-block
`command`. Do **not** execute the commands in this file to "verify" — the verifier reads
files only.

- **Model under test (whole arc):** `mlx-community/Llama-3.2-3B-Instruct-4bit` — a single 3B,
  4-bit model — **except Phase 1**, which is a 6-model cloud panel + `gpt-4o-mini` logprobs.
- **What "code_ref" vs "added-in" means.** `code_ref` (from the run block) is the commit the
  code was at when the run executed. "added-in" is the commit that first committed the JSON.
  For the Phase-2 robustness artifacts these are *offset by one*: each commit lands the
  previous run's artifact, so e.g. R1 holdout ran at `de13bff` but was committed in `204a830`.
  Both are recorded; reproduction should check out the **`code_ref`** commit.
- **Numbers** for every artifact live in [`docs/PAPER_RESULTS.md`](PAPER_RESULTS.md) (PS1);
  this file is only about *how to regenerate* them.

---

## Environment

All MLX runs (Phase 2, P0, P2–P5, G1) require **Apple Silicon** + the project virtualenv:

```
source .venv/bin/activate      # numpy + inspect-ai + mlx / mlx-lm (Apple Silicon only)
```

- `pyproject.toml` pins only `numpy>=1.24` + `inspect-ai>=0.3` as hard deps; `mlx` / `mlx-lm`
  are the Apple-Silicon runtime installed into `.venv` for the model runs (mlx-lm **v0.31.3**
  for P5a training, per the Phase-3 log).
- **Phase 1** is not MLX: `--elicit` spends OpenRouter/OpenAI budget to elicit real option
  logprobs from `gpt-4o-mini`; the sampled sweep reads a pre-existing panel artifact and runs
  on CPU. Requires provider credentials, **not** Apple Silicon.
- **Figures** (`scripts/make_paper_figures.py`) need **matplotlib** (rendered with matplotlib
  **3.5.1**), which is **NOT** in `.venv` (see PS2 log). Render figures with a separate
  matplotlib-equipped interpreter, or run `--check` (prep only, numpy-only, no render) inside
  `.venv`. The extractor and the verifier are numpy-only and run in `.venv`.
- Launch **one MLX run at a time** (the GPU saturates; concurrent runs contend).

---

## Order dependencies

```
base model (no artifact deps):
  Phase 1 sweep/elicit · Phase 2 (all act_steer_*) · P0 w1_cosine · P2 baseline

P2 baseline  ──┐
P4 floors    ──┼─▶ P5a lora-build (reads dist_baseline from floors + dist_no_evidence
               │                     from P2 baseline to build SFT targets)
               │        │
               │        ▼
               │   mlx_lm lora train  ─▶ out/lora_deference_adapter/
               │        │
               │        ▼
               │   P5b lora-eval (needs the adapter dir AND the P5a design split)
               │
P3 tracking, P4 floors, G1 guard-grid: need only the base model + the read-only
   BSA delta file out/_bsa_delta_check.json (never written by these runs).

extractor  (scripts/extract_paper_results.py) ─▶ needs ALL 17 arc artifacts present
figures    (scripts/make_paper_figures.py)     ─▶ needs the same artifacts (reuses the
                                                   extractor's loaders); matplotlib to render
```

- **G1 needs nothing but the base model** (guards are prompt-level scaffolds on the P4 path).
- **The extractor needs every artifact**; the figures need the extractor's loaders + the
  artifacts + matplotlib.

---

## Phase 1 — logit-bias negative

These three artifacts predate the standardised run block (they carry an `experiment`/`meta`
block with `code_ref` + `generated_at`, but **no `command` field**). The commands below are
therefore **asserted by this doc** — reconstructed from
`src/alignment/logit_bias_calibration.py`'s argparse + each artifact's `experiment` metadata —
**not** verified against a run-block `command` (the verifier reports these as `asserted-by-doc`).

**Sampled multi-model sweep** → `out/logit_bias_calibration.json`
(code_ref `25372f9d` per meta; added-in `22fd706`, 2026-06-30). Reads the pre-existing panel
`out/policy_delegate_stress.json` (S=24 sampled dists); CPU, no provider budget.

```
python -m alignment.logit_bias_calibration --sweep
```

**Real-logprobs re-run, 4-option** → `out/logit_bias_calibration_logprobs_gpt4omini_4opt.json`
(code_ref `25372f9d`; added-in `22fd706`). Spends OpenAI budget (elicits real option logprobs).

```
python -m alignment.logit_bias_calibration --elicit openai/gpt-4o-mini --n-options 4 --n-orders 4 --out out/logit_bias_calibration_logprobs_gpt4omini_4opt.json
```

**Real-logprobs re-run, 5-option** → `out/logit_bias_calibration_logprobs_gpt4omini_5opt.json`
(code_ref `25372f9d`; added-in `22fd706`).

```
python -m alignment.logit_bias_calibration --elicit openai/gpt-4o-mini --n-options 5 --n-orders 4 --out out/logit_bias_calibration_logprobs_gpt4omini_5opt.json
```

- **Runtime:** not recorded in the artifacts or logs (network-bound provider elicitation).
- **Env:** provider credentials (OpenRouter/OpenAI); no Apple Silicon required.

---

## Phase 2 — activation-steering negative (+ mechanism)

All eight are produced by `python -m alignment.activation_steering_run` with one mode flag.
Each has a run-block `command` (verified by the verifier). All: MLX / Apple Silicon, `.venv`,
model `Llama-3.2-3B-Instruct-4bit`, 16 four-option ENG contestable items + 12 floor probes.

**R1 held-out (layers 11/14)** → `out/act_steer_holdout_3b.json`
(code_ref `de13bff`; added-in `204a830`).

```
python -m alignment.activation_steering_run --holdout
```

**R1 held-out, late layers (17/21)** → `out/act_steer_holdout_late_3b.json`
(code_ref `b4a97ad`; added-in `eef036a`). Same command; the layer set differs by code state at
`code_ref` (17/21 vs 11/14) — reproduction requires checking out the matching `code_ref`.

```
python -m alignment.activation_steering_run --holdout
```

**R4 CIs (headline grid)** → `out/act_steer_ci_3b.json`
(code_ref `d67d433`; added-in `b4a97ad`). Runtime **~57 min** (5 layers × 6 alphas × 16 items ×
3 seeds × 4 orders, 2000-boot CIs).

```
python -m alignment.activation_steering_run --ci
```

**R2 random-direction control** → `out/act_steer_randctrl_3b.json`
(code_ref `204a830`; added-in `b7335b9`).

```
python -m alignment.activation_steering_run --direction random
```

**R3 negative-dose** → `out/act_steer_negalpha_3b.json`
(code_ref `b7335b9`; added-in `d67d433`).

```
python -m alignment.activation_steering_run --negdose
```

**W3 geometry** → `out/act_steer_geometry_3b.json`
(code_ref `eef036a`; added-in `5d666dd`). Runtime **~2 min**.

```
python -m alignment.activation_steering_run --geometry
```

**R7 off-task capability** → `out/act_steer_offtask_3b.json`
(code_ref `5d666dd`; added-in `bcf8613`). Runtime **~2–4 min** (10 probes, 12 tokens each).

```
python -m alignment.activation_steering_run --offtask
```

**R8 wrong-persona control** → `out/act_steer_personactrl_3b.json`
(code_ref `bcf8613`; added-in `a37a4e3`). Runtime **~2–4 min**.

```
python -m alignment.activation_steering_run --persona-control
```

**Held-out family runtime:** the held-out runs (2 layers, k=4) are **~15–20 min** each.

### Superseded original (do-not-touch, uncommitted)

`out/activation_steering_3b_4opt.json` (the original 0.692→0.752 dose-response curve) is
**uncommitted** and on the do-not-touch list. It has an `experiment` block (code_ref `de13bff`,
generated 2026-07-02) but **no run-block `command`**. Its command is **asserted by this doc**
(a full dose sweep over layers 7/11/14/17/21 × alphas 0–8), not verified. Cite it only as the
*superseded* point-estimate curve; the corrected CI verdict lives in `act_steer_ci_3b.json`.

```
python -m alignment.activation_steering_run
```

---

## P0 — steering kill-check

`out/act_steer_w1_cosine_3b.json` (code_ref `af32f35`; added-in `a9b5d90`). MLX / `.venv`.
Layers 11/7/14, personas median-England-2022 vs 2024. Runtime: **cheap, ~minutes**.

```
python -m alignment.activation_steering_run --w1-cosine
```

---

## P2 — baseline deference fidelity gap

`out/evidcond_baseline_3b.json` (code_ref `9061cf5`; added-in `19c2e11`). MLX / `.venv`.
50 contestable ENG items + 12 floor probes, n_orders=2. Runtime **3:50 wall** (~248 forward
passes). Reads the item bank + scorers; no artifact deps.

```
python -m alignment.evidcond_run --baseline
```

---

## P3 — evidence tracking (flagship positive)

`out/evidcond_tracking_3b.json` (code_ref `19c2e11`; added-in `4eb5df4`). MLX / `.venv`.
10 Bonferroni-significant items, n_orders=2. Reads **real** BSA 2022/2024 ENG distributions
from `out/_bsa_delta_check.json` (**read-only**, never written). Runtime **48 s wall**
(30 forward passes).

```
python -m alignment.evidcond_run --tracking
```

---

## P4 — hostile-evidence floor crack (safety headline)

`out/evidcond_floors_3b.json` (code_ref `4eb5df4`; added-in `65b272c`). MLX / `.venv`.
12 four-option floor probes × 4 conditions, n_orders=2. Hostile evidence is **SYNTHETIC**
red-team data (`hostile_distribution`, ~75% anti-rights mass), **not** real BSA data. Runtime
**1:52 wall** (96 forward passes).

```
python -m alignment.evidcond_run --floors
```

---

## P5a — LoRA data build + design + adapter training

Two steps: (1) the design/data build (own run block), then (2) the **`mlx_lm lora`** training
call that produces the adapter (**no run block** — parameters below are read from
`out/lora_deference_adapter/adapter_config.json`, so the training command is **asserted by this
doc**, not run-block-verified).

**Step 1 — data build + design echo** → `out/lora_deference_design.json`
(code_ref `0ba2646`; added-in `81b1543`). Writes `out/lora_deference_data/` (train 3,101 /
valid 163). Reads `out/evidcond_floors_3b.json` (dist_baseline) and `out/evidcond_baseline_3b.json`
(dist_no_evidence), both read-only — so P2 and P4 must exist first.

```
python -m alignment.evidcond_run --lora-build
```

**Step 2 — train the adapter (mlx_lm lora, v0.31.3)** → `out/lora_deference_adapter/`.
LoRA rank 8, `--num-layers 8`, batch 4, 500 iters, lr 1e-4, mask-prompt, max-seq 384, seed 0
(3.47M trainable params, 0.108%). Runtime **~34 min** (0.25–0.29 it/s), peak 5.1 GB. Apple
Silicon, `.venv`.

```
mlx_lm.lora --model mlx-community/Llama-3.2-3B-Instruct-4bit --train --data out/lora_deference_data --fine-tune-type lora --num-layers 8 --batch-size 4 --iters 500 --learning-rate 1e-4 --mask-prompt --max-seq-length 384 --seed 0 --adapter-path out/lora_deference_adapter --save-every 250
```

---

## P5b — LoRA eval battery (the negative)

`out/evidcond_lora_eval_3b.json` (code_ref `81b1543`; added-in `7808005`). MLX / `.venv`.
**Depends on the P5a adapter** (`out/lora_deference_adapter/`, loaded via
`mlx_lm.load(model, adapter_path=...)`) **and** the P5a design split
(`out/lora_deference_design.json`, read-only — held-out set NOT re-derived). Every measurement
runs twice (adapter OFF vs ON). Runtime **~14.5 min**.

```
python -m alignment.evidcond_run --lora-eval
```

---

## G1 — prompt-level floor guards

`out/floorguard_grid_3b.json` (code_ref `f26d510`; added-in `23924d7`). MLX / `.venv`.
5 guard arms × 4 conditions on 12 floor probes, n_orders=2. Guards are prompt-level scaffolds
prepended to the P4 conditioning (same logprob path, **no adapter**); the constitution guard
reads `data/constitutions/uk_public_service_v1.md` (sha256 pinned in the run block). Synthetic
hostile evidence. **Needs only the base model.** Runtime **6:21 wall** (~750 forward passes).

```
python -m alignment.evidcond_run --guard-grid
```

---

## Extractor and figures (support artifacts)

**Extractor** → `out/paper_results_extract.json` (added-in `b5a33ce`). No run block; numpy-only
in `.venv`; reads **all 17 arc artifacts** and fails loudly on any missing key. Command
asserted by this doc (verified against the script's own docstring/CLI, not a JSON run block).

```
python scripts/extract_paper_results.py --out out/paper_results_extract.json
```

**Figures** → `out/figures/*.{pdf,png}` (added-in `aa672ff`). No run block; needs matplotlib
(3.5.1, out-of-venv). Reuses the extractor's loaders; deterministic (byte-identical on
re-render). `--check` runs the numpy-only prep with no render. Command asserted by this doc.

```
python scripts/make_paper_figures.py
```

---

## Phase 5 — 8B replication of the core battery (model robustness)

Four `_8b` artifacts replicate the P2/P3/P4/G1-subset battery on a **second, larger** model,
`mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` (numbers in
[`docs/PAPER_RESULTS.md` §10](PAPER_RESULTS.md#10-model-robustness--8b-replication)). MLX /
Apple Silicon, `.venv`, same item sets and `n_orders=2` as the 3B runs. These reuse the
**same runners** as P2/P3/P4/G1 — the only difference from the committed 3B commands is the
`--model` flag; **the run-block `command` field does not echo `--model`** (it is the runner's
hardcoded canonical string), so the verified command below is byte-identical to the 3B one and
the model override is documented here in prose.

- **The `--model` flag.** `alignment.evidcond_run` takes `--model`
  (`ap.add_argument("--model", default="mlx-community/Llama-3.2-3B-Instruct-4bit")`, threaded to
  `run_baseline`/`run_tracking`/`run_floors`/`run_guard_grid`). The default is unchanged, so the
  committed 3B run-block commands stay reproducible; the 8B runs pass
  `--model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit`. The run block records the actual model
  under `run.models`, not in `run.command` — so the verifier matches the canonical command string.
- **Model download.** The 8B-4bit weights (~4.5 GB) download once from the MLX community hub
  (the 4bit variant was not pre-cached — only 3bit/8bit were). Allowed once, per the Phase 5 plan.
- **Throughput / runtimes.** ~1.11 s / forward pass (vs 3B's ~0.33 s → 3.4× slower). P2 baseline
  **4:44**, P3 tracking **1:23**, P4 floors **~3:55** (incl. load), G1-subset **~17 min** (12
  probes × 3 arms × 4 conds × 2 orders = 288 passes). All far under the 45-min ceiling.

**P2 baseline (8B)** → `out/evidcond_baseline_8b.json` (code_ref `ae506633`; added-in `9e087de`).
Run with `--model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit`.

```
python -m alignment.evidcond_run --baseline
```

**P3 tracking (8B)** → `out/evidcond_tracking_8b.json` (code_ref `ae506633`; added-in `9e087de`).
Reads the read-only BSA delta file `out/_bsa_delta_check.json`. Run with the same `--model` flag.

```
python -m alignment.evidcond_run --tracking
```

**P4 floors (8B)** → `out/evidcond_floors_8b.json` (code_ref `9e087de1`; added-in `7006f7d`).
SYNTHETIC hostile evidence (red-team stress data). Run with the same `--model` flag.

```
python -m alignment.evidcond_run --floors
```

**G1 guard-grid subset (8B)** → `out/floorguard_grid_8b.json` (code_ref `9e087de1`; added-in
`7006f7d`). Subset arms `{no_guard, guard_rights_floor, guard_constitution}` (provenance/combined
were dominated 3B arms, not re-run). Run with the same `--model` flag.

```
python -m alignment.evidcond_run --guard-grid
```

---

## Frontier crack — P4 floors on gpt-4o-mini (API elicitation, generalization)

`out/evidcond_floors_gpt4omini.json` (code_ref `452168c`; run `2026-07-20`) reproduces the P4
hostile-evidence floor crack on a **frontier/API model**, `gpt-4o-mini`, via OpenRouter option
logprobs (numbers in
[`docs/PAPER_RESULTS.md` §12](PAPER_RESULTS.md#12-frontier-crack--p4-on-gpt-4o-mini-api-logprobs-generalization)).
The floors logic is unchanged; a backend switch
(`evidcond_run._logprob_backend`) selects `M.openrouter_logprob_fn` for API model ids
(`openrouter/*`, `openai/*`) instead of the MLX path. Run with
`--model openrouter/openai/gpt-4o-mini --out out/evidcond_floors_gpt4omini.json`; as with the 8B,
the run-block `command` is the canonical string below (the `--model`/`--out` overrides are
prose-documented, not echoed).

- **NOT MLX / NOT Apple-Silicon.** This spends OpenRouter budget (<$1 for 12 probes × 4
  conditions × `n_orders=2`) and needs `OPENROUTER_API_KEY` in `.env`. gpt-4o-mini is the only
  cloud model that exposes option logprobs; the other cloud providers do not.
- **NOT byte-reproducible.** Hosted, unpinned model — the numbers can drift under the same name;
  see Known irreproducibilities #7. The run-block records the model id and run date.
- **Fail-closed preserved.** A probe with no option-number logprob is recorded in `skipped` and
  dropped (never faked); the run aborts if skips exceed `max_skip` (default 1). This run scored
  12/12 with 0 skips.

```
python -m alignment.evidcond_run --floors
```

---

## Known irreproducibilities

Byte-identical reproduction is **not** guaranteed for the following; the headline verdicts are
robust to all of them, but exact floats / bytes may differ:

1. **Temperature fields in run blocks.** Every MLX run block records `temperature: 0.8`, but
   the representation/floor numbers come from the **logprob** path (deterministic given the
   model + prompt), not from sampling at that temperature — the field is a config echo. The
   off-task (`--offtask`) and any free-generation probes *do* sample and are **not**
   bit-reproducible run-to-run.
2. **MLX / mlx-lm version.** P5a trained on mlx-lm **v0.31.3**; a different mlx/mlx-lm version
   can change kernel numerics, LoRA init, and the trained adapter weights.
3. **4-bit quantisation determinism across hardware.** The 4-bit quantised forward pass can
   differ at the last bits on different Apple-Silicon chips / OS / Metal versions, so logprobs
   (and every derived mass/gain) may not be bit-identical off the original machine. G1's exact
   replication of P4 (0.5116 / 0.3177) held **on the same machine**; treat cross-hardware
   equality as approximate.
4. **The superseded steering artifact `activation_steering_3b_4opt.json` is uncommitted** and
   on the do-not-touch list — it cannot be checked out from git history, so its exact bytes are
   irreproducible by definition. Cite it as the superseded curve; rely on the committed
   `act_steer_ci_3b.json`.
5. **matplotlib version for byte-identical figures.** Figures are deterministic *within* a
   matplotlib version (verified via `cmp` at 3.5.1), but a different matplotlib can change PDF
   structure and PNG antialiasing, so the `out/figures/*.{pdf,png}` bytes are version-bound.
6. **Phase-1 provider elicitation.** `--elicit` calls a hosted `gpt-4o-mini`; provider-side
   model updates or logprob availability changes can shift the held-out gains. There is no
   pinned provider snapshot.
7. **Frontier crack provider elicitation.** `out/evidcond_floors_gpt4omini.json` (§ Frontier
   crack) elicits option logprobs from a hosted, unpinned `gpt-4o-mini` over OpenRouter — same
   provider-drift caveat as #6: not byte-reproducible, no snapshot pin, spends budget, needs
   credentials, not Apple-Silicon. The model id and run date are recorded in the run block; the
   direction and channel asymmetry are the transferable finding, not the exact (saturated) masses.

---

## What the verifier checks vs asserts

`scripts/verify_repro_reference.py` parses the fenced command blocks in this file and, for each
artifact that has a run-block `command`, asserts byte-equality against the JSON. Entries with
**no** run-block `command` are reported as `asserted-by-doc` (the doc is the authority; there is
nothing in a JSON to check against):

- **run-block-verified:** all 8 Phase-2 `act_steer_*` (holdout, holdout-late, ci, randctrl,
  negalpha, geometry, offtask, personactrl), P0 `w1_cosine`, P2 baseline, P3 tracking, P4
  floors, P5a `lora-build` (design), P5b `lora-eval`, G1 `guard-grid`, and the **four Phase-5
  8B replication** artifacts (`evidcond_{baseline,tracking,floors}_8b`, `floorguard_grid_8b` —
  the run-block `command` is the runner's canonical string, byte-identical to its 3B twin; the
  `--model` override is prose-documented, not in the command), and the **frontier crack**
  (`evidcond_floors_gpt4omini.json` — same canonical `--floors` command; the `--model`/`--out`
  overrides are prose-documented; the COMMAND is verified even though the API numbers are not
  byte-reproducible, #7). 20 verified total.
- **asserted-by-doc (no run-block `command`):** the 3 Phase-1 logit-bias artifacts, the
  superseded `activation_steering_3b_4opt.json`, the `mlx_lm lora` training call (checked against
  `adapter_config.json` params), the extractor, and the figures.
