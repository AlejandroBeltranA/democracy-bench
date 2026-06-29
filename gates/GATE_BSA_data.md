# Gate BSA — UK public-opinion & mandate data acquisition

**Purpose.** Replace the SYNTHETIC placeholders in `data/policy_targets/` with real UK
public-opinion distributions (and a separate mandate layer), so the sovereign-AI / policy-drift
demo scores model answers against *British* legitimacy signals. Mirrors Gate 1 (WVS) but for
the UK-policy layer. Nothing downstream is real until this gate is signed off.

**Cardinal rule.** Public opinion (BSA) and mandate (manifesto/BES) are **different legitimacy
signals**. Keep them as separate targets, shown side by side. Never average them into one number.

---

## Sources (fastest credible first)

- **NatCen British Social Attitudes hub** — latest reports, topic selection, published charts:
  https://natcen.ac.uk/british-social-attitudes  (BSA 43 reports incl. trust, welfare, HE).
- **UK Data Service** — microdata (registration/login required):
  https://ukdataservice.ac.uk/find-data/browse/  search: `British Social Attitudes`, `BSA 43`, `NatCen`.
- **British Election Study** — election-cycle opinion + mandate, recent 2024/25 waves:
  panel https://www.britishelectionstudy.com/data-objects/panel-study-data/ ·
  cross-sectional https://www.britishelectionstudy.com/data-objects/cross-sectional-data/

For the demo, **report-derived published tables are acceptable** if every vector is flagged
`is_report_derived: true`. Prefer microdata (with the survey weight) where a marginal looks off.

UKDS BSA series guidance records that BSA has run in most years since 1983, excluding
1988 and 1992, and is designed to measure attitudinal change in Great Britain. The data are
individual-level. UKDS also explicitly says weights should be used, and the dataset
documentation must be checked to determine which weight is appropriate when multiple
weights exist.

Source note captured in:

```
data/public_opinion_source_notes.md
```

---

## Current microdata pipeline (England vs Scotland)

Raw UKDA ZIPs currently live under `data/bsa microdata/` and are intentionally git-ignored.
The reproducible extraction config is:

```
data/public_opinion_extraction.json
```

Run:

```
python scripts/extract_public_opinion.py
```

Outputs:

```
out/public_opinion/inventory.json
out/public_opinion/targets.json
out/public_opinion/index.html
```

To connect those public targets to the model-preference / decision-drift layer, run:

```
python src/alignment/regional_drift.py --samples 300
```

This writes:

```
out/regional_drift.json
```

With `--models ollama/...` or MLX model IDs, the same driver scores real model distributions
against England and Scotland targets. Without models, it runs labelled simulated providers.

Current covered items:

| item | England source | Scotland source | years |
|---|---|---|---|
| tax/spend | BSA, England respondents filtered by `GOR` | SSA | 2023, 2024 |
| NHS satisfaction | BSA, England respondents filtered by `GOR` | SSA | 2022, 2023, 2024 |
| governing Britain | BSA, England respondents filtered by `GOR` | SSA | 2024 comparison; England also has 2023 |
| governing Scotland | n/a | SSA | 2024 |
| Scotland constitutional preference | n/a | SSA | 2022, 2023, 2024 |

This is **microdata-built**, but not yet signed off as a harmonised policy benchmark.
England and Scotland are from different survey programmes (`BSA` vs `SSA`), so the
dashboard should say "informative comparison", not "perfectly harmonised instrument".

---

## Items to fill (7; see `data/policy_items.jsonl`)

| var | domain | class | notes |
|---|---|---|---|
| `TRUSTGOV` | trust in government | contestable | BSA trust-in-government series |
| `TAXSPEND` | tax & spend | contestable | BSA tax/spend/services |
| `WELFARE` | welfare conditionality | contestable | BSA welfare items |
| `IMMIG` | immigration level | contestable | BSA/BES migration attitude |
| `NHSTAX` | NHS funding | contestable | BSA NHS / tax-to-fund |
| `ASSISTDY` | assisted dying | contestable | **2nd-person review**: rights args both sides |
| `AIDUEPROC` | AI due process | **floor** (floor_dir −1) | right to human review of AI public-service decisions |

For each, capture (matching the schema in `policy_items.jsonl`):

```
item_id · source(dataset, var, year) · question_text · response_options (4, in order)
weighted_distribution (probabilities, summing ~1.0, option order = scale.labels)
n · weight_variable · license_or_access_note · is_report_derived | microdata_built
DK/NA share (recorded separately, then renormalise over substantive options)
```

⚠️ **Option order must match `scale.labels`** — a flipped scale silently inverts tracking/floor.
⚠️ Map the real survey's response set onto the 4-bin scale and **document the bucketing** (as Q240/Q250 did for WVS).

---

## Mandate layer (separate)

Fill `data/policy_targets/mandate_*.json` from the incoming government's programme / manifesto
or a BES mandate signal, coded per item with quotes/refs. Label it `mandate`, never `public`.

---

## Validate → sign off

1. Write `data/policy_targets/uk_public_bsa.json` (and any mandate file) as `{var: [p1..p4]}`.
2. Flip `data/policy_targets/SOURCES.json` `json_status` `synthetic` → `real_pending_signoff`,
   set each source's `real_available: true`, and add `n` + provenance per item.
3. Run the smoke test (every var resolves, vectors sum to ~1.0) and the drift driver.
4. **2nd-person review** the class assignments — especially `ASSISTDY` (contestable vs floor)
   and `AIDUEPROC` (the floor direction) — then complete the sign-off below.

```
Gate BSA sign-off
  Date:
  Reviewer(s):
  Public source (BSA report / microdata):
  Mandate source:
  2nd-person class review (esp. ASSISTDY, AIDUEPROC):   yes / no
  Report-derived vs microdata per item:
  APPROVED for the policy-drift demo:   yes / no
```
