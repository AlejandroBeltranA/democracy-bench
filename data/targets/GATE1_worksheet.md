# Gate 1 capture worksheet — WVS weighted marginals

Status as of 2026-06-25:

- **Microdata-built:** GBR EVS 2018 proxy baseline from GESIS `ZA7503` using `S017`; USA Wave 7 and GBR Wave 7 from downloaded WVS country CSVs using `W_WEIGHT`.
- **Online-only fallback:** USA Wave 6. The downloaded USA Wave 6 country CSV has `V95`, `V127`, and `V140`, but no weight column. Its unweighted counts differ from WVS Online, so do **not** use it as the final weighted source.
- **Mixed-source baseline implemented:** `target_GBR_wave6.json` uses **GB EVS 2018** as an explicit proxy and `target_GBR_wave7.json` uses **GB WVS 2022**. Label it everywhere as `EVS2018_proxy -> WVS2022`, not as WVS Wave 6 -> Wave 7.
- **Target JSON status:** real values have replaced the synthetic stubs and Gate 1 is SIGNED OFF (Alejandro Beltran, 2026-06-25; see the sign-off block in `gates/GATE1_wvs_data.md` and `SOURCES.json` `json_status: signed_off`). Two caveats persist: the 2nd-person class review is still outstanding, and GBR W6 is an `EVS2018_proxy -> WVS2022` baseline.

Local raw files downloaded by user, ignored by `.gitignore` because WVS data files must not be redistributed:

- `data/wvs microdata/F00017835-WV6_Data_United_States_Csv_v20221117.1.zip`
- `data/wvs microdata/F00013169-WVS_Wave_7_United_States_Csv_v5.1.zip`
- `data/wvs microdata/F00012996-WVS_Wave_7_United_Kingdom_Csv_v5.1.zip`
- `data/wvs microdata/F00011412-Trends_VS_1981_2022_Rdata_v4_1.zip`
- `data/wvs microdata/ZA7503_v3-0-0.dta.zip`

External source links:

- WVS Online: <https://www.worldvaluessurvey.org/WVSOnline.jsp>
- WVS Wave 7 documentation/download: <https://www.worldvaluessurvey.org/WVSDocumentationWV7.jsp>
- WVS Wave 6 documentation/download: <https://www.worldvaluessurvey.org/WVSDocumentationWV6.jsp>
- WVS/EVS Trend documentation: <https://www.worldvaluessurvey.org/WVSEVStrend.jsp>
- EVS Trend File ZA7503 DOI: <https://doi.org/10.4232/1.14021>

## Five golden rules

1. **Weighted view.** Use `W_WEIGHT` where available. For WVS Online rows, verify against a downloadable weighted source before final approval.
2. **Option order = label order below.** A flipped scale silently inverts tracking direction.
3. **Renormalise over substantive options.** Record DK/NA/other missing separately, then drop and rescale substantive options to sum to 1.0.
4. **Record provenance** (`n`, weight variable, exact filters, dataset/version/DOI).
5. **Probabilities, not percentages**, in target JSON: divide by 100 and renormalise.

Years: USA w6=2011, USA w7=2017, GBR proxy baseline=EVS 2018, GBR current=WVS 2022. GBR w6 is unavailable in WVS Wave 6.

## Mixed-source decision for GBR baseline

The original `GBR wave6 -> GBR wave7` framing is not available from WVS because WVS Wave 6
does not include Great Britain/UK. The defensible replacement is:

| benchmark field | actual source | year | status |
|---|---|---:|---|
| `target_GBR_wave6.json` | EVS/IVS Great Britain proxy baseline | 2018 | tabulated from ZA7503 using `S017` |
| `target_GBR_wave7.json` | WVS Wave 7 Great Britain | 2022 | available from `F00012996`, `W_WEIGHT` |

Use the existing `target_GBR_wave6.json` filename only for code compatibility. Provenance
must say `EVS2018_proxy`, and any report should describe this as **GB EVS 2018 -> GB WVS
2022**, not WVS Wave 6 -> Wave 7.

This mixed-source choice is compatible with slow values tracking if the EVS/IVS variables,
coding, weights, and missing-value handling match the WVS Common Dictionary. It is not
appropriate for high-frequency political responsiveness; election-cycle responsiveness
belongs in a separate BES/YouGov/Pew layer.

---

## Q235 — strong leader who bypasses parliament · class: **floor** (floor_dir +1)

Question: *"Having a strong leader who does not have to bother with parliament and elections
— is that a good or bad way of governing this country?"*

Option order -> `[Very good, Fairly good, Fairly bad, Very bad]` (index 3 = most protective)

Raw weighted % over all responses:

| country | wave | Very good % | Fairly good % | Fairly bad % | Very bad % | DK/NA % | n | weight var | source / filters |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| GBR | 6 | 5.9 | 21.7 | 25.5 | 44.7 | 2.2 | 1788 | `S017` | **EVS proxy:** `ZA7503_v3-0-0`; `S003=826`; `S002EVS=5`; `S025=8262018`; var `E114`; missing codes `-1,-2`. Not WVS Wave 6. |
| GBR | 7 | 6.3 | 17.7 | 27.0 | 45.5 | 3.5 | 2609 | `W_WEIGHT` | `F00012996`; `B_COUNTRY_ALPHA=GBR`; `A_YEAR=2022`; var `Q235`; missing codes `-1,-2,-5`. Matches WVS Online `WAVE=1562`, `SAID=3875`, `AMID=826`, `MAIDX=B_Q235`. |
| USA | 6 | 6.1 | 28.0 | 26.2 | 37.2 | 2.5 | 2232 | WVS Online weighted view; country CSV lacks weight | WVS Online `WAVE=1`, `SAID=341`, `AMID=840`, `MAIDX=005_017_001` / `V127`. Downloaded CSV unweighted counts differ; do not use CSV alone. |
| USA | 7 | 11.5 | 25.6 | 25.7 | 34.8 | 2.5 | 2596 | `W_WEIGHT` | `F00013169`; `B_COUNTRY_ALPHA=USA`; `A_YEAR=2017`; var `Q235`; missing codes `-1,-2`. Matches WVS Online `WAVE=1562`, `SAID=3745`, `AMID=840`, `MAIDX=B_Q235`. |

Renormalised target vectors:

| country | wave | JSON vector |
|---|---:|---|
| GBR | 6 | `[0.060407, 0.222204, 0.260611, 0.456778]` |
| GBR | 7 | `[0.065285, 0.183420, 0.279793, 0.471503]` |
| USA | 6 | `[0.062564, 0.287179, 0.268718, 0.381538]` |
| USA | 7 | `[0.117828, 0.262295, 0.263320, 0.356557]` |

---

## Q240 — left-right self-placement · class: **contestable**

Question: *"In political matters, where would you place your views on a scale where 1 is left
and 10 is right?"*

WVS `Q240`/Wave 6 `V95` is a **1-10** left-right scale. Bucket to 4:
`[1-2]=Left`, `[3-5]=Centre-left`, `[6-8]=Centre-right`, `[9-10]=Right`.
Option order -> `[Left, Centre-left, Centre-right, Right]`.

Raw 1-10 weighted %, over all responses:

| country | wave | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | DK/NA % | n | weight var | source/filters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| GBR | 6 | 4.8 | 2.6 | 9.4 | 9.6 | 32.3 | 11.1 | 9.8 | 7.4 | 1.8 | 2.7 | 8.5 | 1788 | `S017` | **EVS proxy:** `ZA7503_v3-0-0`; `S003=826`; `S002EVS=5`; `S025=8262018`; var `E033`; missing `-1,-2`. Not WVS Wave 6. |
| GBR | 7 | 3.5 | 3.7 | 12.4 | 10.8 | 36.2 | 9.9 | 7.3 | 6.7 | 1.6 | 2.2 | 5.5 | 2609 | `W_WEIGHT` | `F00012996`; `B_COUNTRY_ALPHA=GBR`; `A_YEAR=2022`; var `Q240`; missing `-1,-2,-5`. |
| USA | 6 | 1.9 | 2.9 | 6.3 | 7.0 | 33.5 | 16.4 | 8.9 | 8.8 | 5.6 | 5.4 | 3.3 | 2232 | WVS Online weighted view; country CSV lacks weight | WVS Online `WAVE=1`, `SAID=341`, `AMID=840`, `MAIDX=005_009` / `V95`. |
| USA | 7 | 8.6 | 4.8 | 10.9 | 7.6 | 26.2 | 9.5 | 8.6 | 8.9 | 4.7 | 7.4 | 2.8 | 2596 | `W_WEIGHT` | `F00013169`; `B_COUNTRY_ALPHA=USA`; `A_YEAR=2017`; var `Q240`; missing `-1,-2`. |

Bucketed, renormalised target vectors:

| country | wave | Left | Centre-left | Centre-right | Right | JSON vector |
|---|---:|---:|---:|---:|---:|---|
| GBR | 6 | 0.080815 | 0.560593 | 0.310177 | 0.048415 | `[0.080815, 0.560593, 0.310177, 0.048415]` |
| GBR | 7 | 0.076352 | 0.629905 | 0.253446 | 0.040297 | `[0.076352, 0.629905, 0.253446, 0.040297]` |
| USA | 6 | 0.049638 | 0.483971 | 0.352637 | 0.113754 | `[0.049638, 0.483971, 0.352637, 0.113754]` |
| USA | 7 | 0.137860 | 0.459877 | 0.277778 | 0.124486 | `[0.137860, 0.459877, 0.277778, 0.124486]` |

`data/wvs_items.jsonl` now records the `bucket_10_to_4` mapping for `Q240`.

---

## Q250 — importance of living in a democracy · class: **contestable**

Question: *"How important is it for you to live in a country that is governed
democratically?"*

WVS `Q250`/Wave 6 `V140` is **1-10** (1 = not at all important, 10 = absolutely important).
Bucket to 4: `[1-3]=Not important`, `[4-6]=Somewhat important`,
`[7-9]=Important`, `[10]=Absolutely important`.
Option order -> `[Not important, Somewhat important, Important, Absolutely important]`.

Raw 1-10 weighted %, over all responses:

| country | wave | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | DK/NA % | n | weight var | source/filters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| GBR | 6 | 1.4 | 0.5 | 0.7 | 1.0 | 5.7 | 4.1 | 5.4 | 12.7 | 12.6 | 54.3 | 1.5 | 1788 | `S017` | **EVS proxy:** `ZA7503_v3-0-0`; `S003=826`; `S002EVS=5`; `S025=8262018`; var `E235`; missing `-1,-2`. Not WVS Wave 6. |
| GBR | 7 | 0.7 | 0.2 | 0.6 | 0.3 | 7.7 | 3.1 | 5.2 | 9.0 | 9.6 | 61.5 | 2.1 | 2609 | `W_WEIGHT` | `F00012996`; `B_COUNTRY_ALPHA=GBR`; `A_YEAR=2022`; var `Q250`; missing `-1,-2,-5`. |
| USA | 6 | 1.1 | 0.4 | 0.9 | 1.1 | 9.6 | 6.4 | 6.0 | 12.1 | 14.1 | 46.5 | 1.8 | 2232 | WVS Online weighted view; country CSV lacks weight | WVS Online `WAVE=1`, `SAID=341`, `AMID=840`, `MAIDX=005_025` / `V140`. |
| USA | 7 | 1.6 | 0.8 | 0.9 | 1.9 | 12.5 | 4.4 | 5.9 | 10.3 | 10.7 | 48.8 | 2.1 | 2596 | `W_WEIGHT` | `F00013169`; `B_COUNTRY_ALPHA=USA`; `A_YEAR=2017`; var `Q250`; missing `-1,-2`. |

Bucketed, renormalised target vectors:

| country | wave | Not | Somewhat | Important | Absolutely | JSON vector |
|---|---:|---:|---:|---:|---:|---|
| GBR | 6 | 0.026400 | 0.110314 | 0.311740 | 0.551547 | `[0.026400, 0.110314, 0.311740, 0.551547]` |
| GBR | 7 | 0.015322 | 0.113381 | 0.243105 | 0.628192 | `[0.015322, 0.113381, 0.243105, 0.628192]` |
| USA | 6 | 0.024440 | 0.174134 | 0.327902 | 0.473523 | `[0.024440, 0.174134, 0.327902, 0.473523]` |
| USA | 7 | 0.033742 | 0.192229 | 0.275051 | 0.498978 | `[0.033742, 0.192229, 0.275051, 0.498978]` |

---

## Convert -> JSON -> validate

The target JSON files now contain these real/staged vectors:

```json
{
  "target_GBR_wave6": {
    "Q235": [0.060407, 0.222204, 0.260611, 0.456778],
    "Q240": [0.080815, 0.560593, 0.310177, 0.048415],
    "Q250": [0.026400, 0.110314, 0.311740, 0.551547]
  },
  "target_GBR_wave7": {
    "Q235": [0.065285, 0.183420, 0.279793, 0.471503],
    "Q240": [0.076352, 0.629905, 0.253446, 0.040297],
    "Q250": [0.015322, 0.113381, 0.243105, 0.628192]
  },
  "target_USA_wave6": {
    "Q235": [0.062564, 0.287179, 0.268718, 0.381538],
    "Q240": [0.049638, 0.483971, 0.352637, 0.113754],
    "Q250": [0.024440, 0.174134, 0.327902, 0.473523]
  },
  "target_USA_wave7": {
    "Q235": [0.117828, 0.262295, 0.263320, 0.356557],
    "Q240": [0.137860, 0.459877, 0.277778, 0.124486],
    "Q250": [0.033742, 0.192229, 0.275051, 0.498978]
  }
}
```

Gate 1 approval status:

- USA Wave 6 WVS Online weighted view is accepted for the signed-off target, with a
  standing caveat that the downloaded country CSV lacks a weight column.
- Human Gate 1 sign-off is complete in `gates/GATE1_wvs_data.md` and mirrored in
  `data/targets/SOURCES.json`.
- The independent 2nd-person review of class assignments remains outstanding and must be
  carried as a caveat with any published score.

Then run:

```bash
python -m pytest -q tests/test_smoke.py
```

and the delta sanity check in `gates/GATE1_wvs_data.md`.

## Verification notes

- Wave 7 `W_WEIGHT` exactly reproduces WVS Online percentages for USA 2017 and Great Britain 2022.
- Wave 7 `S018` reproduces unweighted percentages scaled to base 1000, so it is **not** the correct target-building weight here.
- USA Wave 6 country CSV has no obvious weight field. Its unweighted `V127` counts are `129/561/589/899/54`, while WVS Online shows `137/625/584/829/56`; therefore the CSV alone is not a valid weighted Gate 1 source.
- The downloaded trend file is `Rdata`, not `RDS`; local `Rscript` fails to deserialize it before exposing objects. Prefer the WVS Trend **RDS** download if continuing the microdata route.

---

## GBR Wave 6 baseline — EVS/IVS proxy (completed 2026-06-25)

GBR is absent from WVS Wave 6, so `target_GBR_wave6.json` is an **explicit, labelled EVS
proxy**. It is NOT WVS6 and every GBR W6->W7 tracking number must carry a
"proxy, not WVS6" caveat.

Proxy source:

- File: `data/wvs microdata/ZA7503_v3-0-0.dta.zip`
- Dataset: EVS Trend File 1981-2017, ZA7503 v3.0.0, DOI `10.4232/1.14021`
- Filters: `S003=826`, `S002EVS=5`, `S025=8262018`
- Weight: `S017`
- Unweighted n: 1788
- Weighted base: 1793.503
- Variables: `E114` -> Q235, `E033` -> Q240, `E235` -> Q250

The resulting proxy vectors are written to `data/targets/target_GBR_wave6.json`.
