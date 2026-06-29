# Change Manifest: Policy Delegate Stress Test

Date: 2026-06-26

This workspace is not currently a Git checkout. `git status` and `git rev-parse --show-toplevel`
fail here, so do not run `git init` just to create commits. Use this manifest to stage the same
changes intentionally inside the real repository checkout after the real model panel finishes.

## Current Artifact State

Generated stress-test artifact:

```text
out/policy_delegate_stress.json
```

Current scaffold status:

- contestable targets: `50/30`
- floor probes: `12/10`
- warnings: none
- prompt modes: 7 total
- constitutional modes:
  - `constitutional_delegate`
  - `constitution_plus_target`
  - `constitution_plus_adversarial_majority`
- constitution artifact: `data/constitutions/uk_public_service_v1.md`
- constitution hash:
  `7ed4d19889d01e3f9eff1797a719f6f5f88bea67b3cf336d1d0cdee4be7c2bfd`

Last verification:

```text
99 passed in 113.93s
```

## Do Not Commit

These are local/runtime files and should stay out of Git:

- `.env`
- `.venv/`
- `.pytest_cache/`
- `__pycache__/`
- `.DS_Store`
- `.claude/`
- `.inspect-traces/`
- `logs/`
- `out/*.log`
- `data/bsa microdata/`
- `data/wvs microdata/`
- any raw UKDS/WVS zip files unless the repository already intentionally tracks them

The `.gitignore` in this workspace has been updated to cover these.

## Commit Plan

Use separate commits. Do not mix implementation, generated panel results, and docs if avoidable.

### Commit 1: Harden BSA Public-Opinion Targets

Suggested message:

```text
Harden BSA public-opinion targets
```

Candidate files:

```text
data/public_opinion_bsa_regions.json
data/policy_targets/SOURCES.json
gates/GATE_BSA_REGIONAL.md
out/public_opinion_regions/targets.json
out/public_opinion_regions/inventory.json
out/public_opinion_regions/index.html
out/public_opinion/targets.json
out/public_opinion/inventory.json
out/public_opinion/index.html
src/alignment/public_opinion.py
tests/test_public_opinion.py
```

What this commit should represent:

- BSA-only England/Scotland/Wales regional target layer.
- 50 contestable BSA-backed items.
- base-size quality fields and warnings.
- zero-valid-response handling.
- provenance status no longer drifting back to synthetic.

### Commit 2: Add Policy Delegate Stress Test

Suggested message:

```text
Add constitutional policy delegate stress test
```

Candidate files:

```text
data/constitutions/uk_public_service_v1.md
data/policy_items.jsonl
data/floor_review_signoff.json
gates/floor_review.html
scripts/gen_floor_review.py
scripts/apply_floor_review.py
src/alignment/policy_delegate_stress.py
src/alignment/instrument/measure.py
src/alignment/run_meta.py
src/alignment/estimation.py
tests/test_policy_delegate_stress.py
tests/test_policy_provenance.py
tests/test_elicitation_diagnostics.py
tests/test_logprobs.py
tests/test_run_meta.py
tests/test_estimation.py
```

What this commit should represent:

- standalone runtime constitution artifact;
- seven prompt modes;
- three constitutional prompt modes;
- 12 reviewed floor probes;
- parse diagnostics;
- optional rationale capture;
- logprob scoring path;
- run metadata including constitution file and hash.

### Commit 3: Update Design And Handoff Docs

Suggested message:

```text
Document policy delegate experiment scope
```

Candidate files:

```text
docs/NEXT_EXPERIMENT_DESIGN.md
docs/WORKFLOW_SUMMARY.md
docs/CHANGE_MANIFEST.md
.gitignore
```

What this commit should represent:

- narrowed claim;
- runtime-constitution framing;
- current status and caveats;
- commit/staging instructions.

### Commit 4: Add Real Panel Results

Do this only after the queued real model panel finishes and passes validation.

Suggested message:

```text
Add real model panel results for policy delegate stress test
```

Candidate files will depend on the output path, but likely include:

```text
out/policy_delegate_stress.json
docs/<final-results-or-readout>.md
```

Do not mix this with implementation. The panel output should be reviewable on its own.

## Validation Commands

Run these in the real checkout after applying the changes:

```bash
env HOME=/private/tmp PYTHONPATH=src INSPECT_TRACE_FILE=/private/tmp/inspect_trace.log INSPECT_LOG_DIR=/private/tmp/inspect_logs .venv/bin/python -m pytest -q
```

Regenerate the simulated scaffold artifact:

```bash
env PYTHONPATH=src .venv/bin/python src/alignment/policy_delegate_stress.py --samples 80 --out out/policy_delegate_stress.json
```

Check run metadata and item gates:

```bash
jq '{target_item_count: .target_item_count, warnings: .warnings, constitution_file: .run.constitution_file, constitution_sha256: .run.constitution_sha256, prompt_modes: .run.prompt_modes, schema_version: .run.schema_version}' out/policy_delegate_stress.json
```

Expected scaffold checks:

- `contestable_available >= 30`
- `floor_available >= 10`
- `warnings == []`
- `constitution_file == "data/constitutions/uk_public_service_v1.md"`
- `schema_version == 3`
- all seven prompt modes present

## Real Panel Result Checklist

Before committing the real panel result, check:

- `run.models` is the actual model list.
- `run.samples_requested` or `run.estimator` matches the intended run.
- `run.constitution_file` is present.
- `run.constitution_sha256` matches the reviewed sign-off hash.
- no item-count warnings.
- every item has all expected prompt modes.
- every model/item/mode cell has diagnostics.
- parse rates are acceptable; investigate low parse-rate cells rather than smoothing them away.
- Scotland/Wales low-N caveats remain in target metadata and should not be converted into headline
  regional rankings.

Useful parse-rate inspection:

```bash
jq '[.items[] .modes[] .models[] | .diagnostics.parse_rate] | {min: min, mean: (add / length), n: length}' out/policy_delegate_stress.json
```

Useful model summary inspection:

```bash
jq '.model_summary' out/policy_delegate_stress.json
```

## Defensible Claim After The Panel

Use this framing:

```text
We evaluate whether runtime constitutional instructions help black-box models act as public-service
policy delegates: following public preference on contestable UK policy while preserving rights
floors under pressure.
```

Avoid these claims:

- the models internalized the constitution;
- the experiment performs RL or fine-tuning;
- the model rankings are definitive;
- Scotland/Wales regional differences are headline-safe across the full item bank;
- public opinion should override rights floors.
