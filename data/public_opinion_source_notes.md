# Public Opinion Source Notes

Source captured from the UK Data Service British Social Attitudes Survey series page, pasted into this workspace on 2026-06-25.

## British Social Attitudes

The British Social Attitudes Survey is designed to produce annual measures of attitudinal movements in Great Britain. It has run in most years since 1983 and is intended for monitoring continuity and change in attitudes across social issues.

Available BSA years are separate annual datasets from 1983 onward, excluding 1988 and 1992. The data are individual-level survey records.

UKDS states that most survey data can be downloaded as SPSS, Stata, or tab-delimited files. Downloads generally require a UK Data Service login.

Each dataset catalogue record should be treated as the source of truth for:

- Collection overview, population, sample, geography, and fieldwork.
- Documentation: user guide, questionnaire, and technical report.
- Exact question wording.
- Variable coding and derived variable construction.
- Weight variable names, construction, and instructions for which weight to use.

## Weighting Rule

UKDS explicitly says weights should be used when analysing BSA. The documentation must be checked for the correct weight, especially where multiple weights exist.

For this repo, every extracted distribution must record:

- Weight variable used.
- Unweighted base.
- Weighted base.
- Substantive response codes retained.
- Non-substantive response codes excluded or separately recorded.

## Repeatability

BSA has core questions repeated in most years, plus rotating modules on social, economic, political, and moral issues. The extraction pipeline should prefer repeated items where possible, but should not assume every desired policy domain exists in every year.

ISSP modules are included in the self-completion part of BSA from 1985 onward and can support cross-national comparison. They should be treated as their own source layer, not silently mixed with ordinary BSA items.

## Adjacent UK Surveys

UKDS points to related attitude surveys:

- Scottish Social Attitudes Survey
- Northern Ireland Life and Times Survey
- Young People's Social Attitudes Survey
- Young Life and Times Surveys

For the current England-vs-Scotland platform, Scotland uses SSA. This is useful but not identical to filtering BSA to Scotland; source-programme differences must stay visible in outputs.

## Implication For The Demo

The current public-opinion layer should be described as:

> Microdata-built weighted public-opinion distributions from BSA and SSA, suitable for an informative England-vs-Scotland policy-attitudes demo, pending harmonisation review and sign-off.

It should not be described as a fully harmonised UK public-opinion benchmark until item wording, mode, weights, and response scales have been reviewed item by item.
