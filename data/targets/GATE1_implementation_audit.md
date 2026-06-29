# Gate 1 Implementation Audit

Date: 2026-06-26

Scope: current Gate 1 WVS/EVS target implementation, provenance state, runtime scoring
behavior, validator coverage, and test status.

## Current status

Gate 1 is internally consistent at the target/provenance level:

- `data/targets/SOURCES.json` records `json_status: signed_off`.
- `gates/GATE1_wvs_data.md` contains the human sign-off block.
- `data/targets/GATE1_worksheet.md` records the final mixed-source decision.
- `scripts/apply_gate1.py` validates target vector shape and signed-off sample sizes.

Persistent caveats are still material:

- The 2nd-person class review remains outstanding. Floor/contestable/excluded assignments
  are single-reviewer approved, not independently reviewed.
- GBR Wave 6 is not WVS6. It is an EVS 2018 proxy baseline and must be labelled
  `EVS2018_proxy -> WVS2022`.
- USA Wave 6 uses WVS Online weighted view because the downloaded country CSV lacks a
  weight column.

## Remaining findings

### P1: Classification legitimacy is still single-reviewer

`data/targets/SOURCES.json` correctly marks `second_person_class_review: false`, and the
validator emits a warning. Do not describe the benchmark as fully independently reviewed
until a second person has checked the floor/contestable/excluded item assignments.

### P2: Gate 1 validator is shape/provenance validation, not source reproduction

`scripts/apply_gate1.py` confirms target files are well-formed, required variables exist,
vectors sum to probability mass, and signed-off sources have sample sizes. It does not
recompute the weighted marginals from raw WVS/EVS files. That is acceptable for a read-only
gate check, but should not be oversold as a reproducibility script.

### P3: Q240/Q250 are transformed survey instruments

`data/wvs_items.jsonl` records the 10-point-to-4-bin mappings for Q240 and Q250. Any written
claim should say the model is elicited on a 4-option bucketed version of the WVS item, not on
the native 10-point instrument.

## Verification

Latest local check:

```bash
python scripts/apply_gate1.py
python -m pytest -q
```

Expected status after the Inspect sandbox fix:

- Gate 1 validator exits `0` with caveat warnings.
- Full suite passes: 101 tests.

## Recommended next actions

1. Close the independent 2nd-person class review and flip
   `gate1_signoff.second_person_class_review` only after that review is real.
2. Keep the `EVS2018_proxy -> WVS2022` and USA Wave 6 weighted-online caveats visible in
   slides, logs, and demo copy.
3. If time permits, add a reproduction script that rebuilds `target_*.json` from the local
   raw microdata and WVS Online captures; keep raw data uncommitted.
