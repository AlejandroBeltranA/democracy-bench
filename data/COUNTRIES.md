# Reference polities & survey waves (values axis)

The values axis evaluates a model against a **specific polity at a specific time**, and
the temporal "tracking" signal compares two approved target snapshots. Two countries are
wired for the MVP. The USA comparison is WVS Wave 6 -> WVS Wave 7; the Great Britain
comparison is an explicit EVS 2018 proxy baseline -> WVS 2022 because GB is absent from
WVS Wave 6.

| Country | code | Wave 6 fieldwork | Wave 7 fieldwork | Δ window | Notes |
|---|---|---|---|---|---|
| United States | `USA` | 2011 | 2017–2018 | ~6 yrs | mixed-mode CAWI/CATI in W7 |
| Great Britain | `GBR` | EVS 2018 proxy | 2022 | ~4 yrs | report as `EVS2018_proxy -> WVS2022`, not plain WVS6 -> WVS7 |

## Why two countries

Comparing **USA** and **GBR** turns the demo into a cross-national tracking story:
the same model is scored against two different polities and two different value shifts.
A model that "represents" both today but tracks neither shift is the headline failure;
a model that tracks one polity but not the other is an even more interesting finding.

## Data-acquisition checklist (per country, per wave)

1. Download the per-country WVS file (or the integrated WVS-EVS trend file) from
   worldvaluessurvey.org (registration) or GESIS.
2. For each selected variable, compute the **weighted marginal distribution** over the
   item's answer options. **Use the survey weight**: `W_WEIGHT` for WVS country files,
   `S017` for the EVS/IVS Great Britain proxy baseline, and WVS Online weighted view for
   USA Wave 6 unless a verified weighted microdata source replaces it.
3. Drop "Don't know / No answer" into a separate mass; decide per item whether to
   renormalize over substantive options or keep a refusal channel (see PLAN §4).
4. Write `targets/target_{CODE}_wave{N}.json` as `{ "<VAR>": [p1, p2, ...], ... }`,
   options in the SAME order as the item's `scale.labels`.
5. Record the source file + weight variable + n in `gates/` as the Gate-1 sign-off.

## Important consistency rules

- Option order in the target vector **must** match `scale.labels` order in
  `wvs_items.jsonl`. The scorer assumes index alignment; a flipped scale silently
  inverts tracking direction.
- "UK" vs "GB": WVS Wave 7 is **Great Britain**. Keep the code `GBR` and label it GB,
  not UK, to avoid implying Northern Ireland coverage you don't have at W6/W7 parity.
- Same variable codes (`Q235`, `Q240`, `Q250`) are used across countries in Wave 7,
  so one `wvs_items.jsonl` serves all countries; only the targets differ.

> The JSON targets in `data/targets/` are real signed-off WVS/EVS weighted marginals.
> Carry the two caveats with any score: the 2nd-person class review is still outstanding,
> and the GBR baseline is `EVS2018_proxy`, not native WVS6.
