# Gate BSA Regional: Harmonised Public-Opinion Targets

Date: 2026-06-26

Owner: Codex for BSA extraction, target construction, low-N warnings, and provenance consistency.

Status: microdata-built, expanded to 50 contestable items, pending independent review.

## Purpose

Produce the harmonised public-opinion target layer for the next policy-delegate experiment:
England, Scotland, and Wales filtered from the same British Social Attitudes survey files by
Government Office Region.

This layer is preferred for headline regional claims because all three polities come from the same
survey programme and survey design. The mixed BSA/SSA layer remains useful as a Scotland depth
check, but it is not the headline regional comparison.

## Active Artifacts

Primary target:

```text
out/public_opinion_regions/targets.json
```

Inventory:

```text
out/public_opinion_regions/inventory.json
```

Extraction config:

```text
data/public_opinion_bsa_regions.json
```

Dashboard:

```text
out/public_opinion_regions/index.html
```

## Source Files And Weights

| Year | Study | Weight | Region filter |
|---|---|---|---|
| 2022 | UKDA-9283 British Social Attitudes Survey, 2022 | `BSA22_final_wt` | `GOR` |
| 2023 | UKDA-9363 British Social Attitudes Survey, 2023 | `BSA23_final_wt` | `GOR` |
| 2024 | UKDA-9478 British Social Attitudes Survey, 2024 | `BSA24_final_wt_GB18` | `GOR` |

Region coding is taken from the configured `GOR` filters:

| Polity | Code(s) |
|---|---|
| England | English GOR codes in each year |
| Scotland | Scotland GOR code |
| Wales | Wales GOR code |

The target output records, per series: study, year, programme, variable, weight, filters,
unweighted base, weighted count, weighted distribution, valid codes, option labels, and base-size
quality.

## Base-Size Rules

| Unweighted base | Use |
|---:|---|
| `n >= 300` | acceptable for headline regional item claims |
| `100 <= n < 300` | directional only |
| `0 < n < 100` | do not use for model ranking or headline claims |
| `n = 0` | unusable; exclude from comparisons |

These thresholds are now written into `out/public_opinion_regions/targets.json` under
`base_size_thresholds`, and every affected series carries `base_quality` plus `base_warning`.

## Included Item Bank

The current BSA-only regional config contains 50 contestable items. This satisfies the 30 to 50
contestable-item target for the exploratory Policy Delegate Stress Test, but it remains pending
independent review of wording, option order, valid/missing handling, and floor-vs-contestable
classification.

| Domain | Item ids |
|---|---|
| Broad/longitudinal | `tax_spend`, `nhs_satisfaction`, `governing_britain`, `trust_gov`, `welfare_scale_grouped` |
| NHS and healthcare | `ae_satisfaction`, `dentist_satisfaction`, `gp_satisfaction`, `hospital_satisfaction`, `nhs_quality_care`, `nhs_treatment_range`, `nhs_gp_wait`, `nhs_hospital_wait`, `nhs_ae_wait`, `nhs_spend_level`, `nhs_tax_spend`, `nhs_free_principle`, `nhs_universal_principle`, `nhs_tax_funded_principle` |
| Social care | `social_care_satisfaction`, `social_care_who_pays` |
| DWP trust | `dwp_fairness_trust`, `dwp_honesty_trust`, `dwp_accuracy_trust` |
| Redistribution and welfare | `redistribution`, `more_welfare_poor`, `welfare_dependency`, `welfare_damage_lives`, `welfare_proudest_achievement`, `disability_benefits_difficulty`, `disabled_benefits_spend`, `benefits_damp_mould`, `benefits_insulation_rent`, `jobcentre_missed_weekly`, `jobcentre_missed_quarterly`, `benefits_duty_find_better_job`, `benefit_fraud_wrongness`, `benefit_cheat_poverty_reason` |
| Tax, spending, climate, and economy | `tax_high_incomes`, `tax_middle_incomes`, `tax_low_incomes`, `defence_spending`, `climate_petrol_tax`, `climate_flying_tax`, `big_business_workers` |
| Government responsibility | `gov_resp_jobs`, `gov_resp_healthcare`, `gov_resp_old_living`, `gov_resp_unemployed_living`, `gov_resp_reduce_income_diff` |

## Current 2024 Regional Base Profile

The latest target series for all 50 items is 2024. Across 150 polity-item cells:

| Polity | Headline-capable | Directional | Too low for headline use |
|---|---:|---:|---:|
| England | 50 | 0 | 0 |
| Scotland | 7 | 15 | 28 |
| Wales | 0 | 22 | 28 |

Interpretation:

- England 2024 can be used as the primary public target across the full item bank.
- Scotland/Wales module cells are often too small for headline regional model rankings.
- Low-base Scotland/Wales cells stay in the artifact for transparency, but the dashboard and JSON
  warnings must be carried through to any model-result interpretation.

## Excluded Or Deferred Items

These should not be added to the next model panel until their source mapping and base profile are
clean:

| Candidate | Reason deferred |
|---|---|
| Immigration level | not yet mapped in the harmonised BSA regional config |
| Rights-adjacent punishment, surveillance, or protest items | require independent floor-vs-contestable review before use |
| Assisted dying | requires independent contestable-vs-floor review before use |
| AI due process | own-probe floor item, not a BSA public-opinion target |
| Scotland-only constitutional items | useful for Scotland-specific analysis, not a harmonised England/Scotland/Wales comparison |

## Harmonisation Decisions

- Use BSA-only regional extraction for headline England/Scotland/Wales comparisons.
- Keep mixed BSA/SSA extraction separate and label it as mixed source.
- Preserve original option labels and valid-code order from the BSA dictionary.
- Exclude `n=0` series from pairwise comparisons.
- Keep low-N series in the target artifact for transparency, but mark them as directional or
  not headline-safe.
- Do not use BSA targets as rights floors unless the item directly measures the rights-floor
  principle. Most floor probes remain own-probe items with independent review.

## Acceptance Checks

Required before rerunning the real model panel:

- all configured variables resolve in the source files;
- every usable distribution sums to approximately 1.0;
- zero-response series are marked unusable and excluded from comparisons;
- every series has `n_unweighted`, `base_quality`, and `base_warning` where applicable;
- every comparison has `min_n_unweighted` and `base_quality`;
- synthetic/real provenance labels agree across `out/public_opinion*`,
  `data/policy_targets/SOURCES.json`, and model-run artifacts;
- independent review confirms included item wording, option order, and floor/contestable status.

## Sign-Off

```text
Gate BSA regional sign-off
  Date:
  Reviewer(s):
  Extraction config reviewed:       yes / no
  Weight choices reviewed:          yes / no
  Region filters reviewed:          yes / no
  Item mappings reviewed:           yes / no
  Low-N treatment reviewed:         yes / no
  floor/contestable class review:   yes / no
  APPROVED for model-panel rerun:   yes / no
```
