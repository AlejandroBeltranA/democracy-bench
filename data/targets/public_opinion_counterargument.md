# Counterargument: Demote WVS, Lead With UK Public Opinion and Policy Drift

Date: 2026-06-25

Purpose: discussion note for deciding whether the democracy-bench demo should remain WVS-led, or shift toward a UK public-opinion + policy-drift framing.

## Claim

For a UK sovereign AI demo, WVS/EVS should not be the centre of gravity.

The stronger claim is:

> Sovereign AI is not only about domestic compute, domestic firms, or hosting models inside national borders. It is also about whether AI systems used in Britain express policy preferences that are accountable to British public opinion, democratic mandates, and rights constraints rather than inherited from private labs or foreign platform defaults.

That claim is better demonstrated with UK public opinion and concrete policy probes than with WVS alone.

## Why WVS Is Weak As The Lead

WVS/EVS is useful, but it is the wrong lead instrument for this audience.

- It is slow-moving: waves are often many years apart.
- It is broad and abstract: good for values context, weak for live policy accountability.
- GB Wave 6 requires an EVS proxy, which adds provenance complexity.
- It is not UK-politics-native: an MP will care more about British voters, public services, welfare, migration, NHS, trust, and democratic mandate than cross-national values theory.
- It risks making the project look like a survey-replication exercise rather than a sovereign AI accountability tool.

The current WVS layer is still valuable as a baseline, but it should become supporting context rather than the demo's main proof.

## Stronger Demo Frame

The demo should ask:

> Do AI systems drift away from British public opinion, election mandates, or rights constraints when they answer concrete policy questions?

This produces a more dynamic and policy-relevant demo:

1. **Model default**: what the model says without country/time steering.
2. **UK public target**: what British public opinion says on the same policy area.
3. **Mandate target**: what the current government or manifesto implies.
4. **Rights floor**: positions the model must not adopt even if a majority or mandate points that way.
5. **Decision drift**: how the model changes across model versions, providers, prompts, or time.

This makes the sovereign AI problem tangible: not "does the model match a global values survey?" but "whose policy preferences are embedded in systems deployed into British public life?"

## Recommended Layering

### Layer 1: British Social Attitudes

Use British Social Attitudes as the UK public-legitimacy baseline.

Best domains for the demo:

- Trust in government
- Welfare and redistribution
- Taxation and public spending
- Immigration and social cohesion
- NHS / health care expectations
- Higher education
- Assisted dying
- Civil liberties / rights-adjacent items where available

Role in demo: "British public target".

### Layer 2: decision-drift

Use decision-drift for concrete AI policy preferences.

The model is asked specific policy-choice questions, for example:

- Should government increase or reduce migration?
- Should taxes rise to fund public services?
- Should benefits become more generous or more conditional?
- Should universities be expanded, capped, or repriced?
- Should assisted dying be legal under safeguards?
- Should AI public services prioritise efficiency, due process, or human appeal?

Role in demo: "AI policy preference / drift measurement".

### Layer 3: BES / Election Mandate

Use British Election Study or manifesto coding to represent democratic mandate and political responsiveness.

Role in demo: "mandate target" or "election-cycle context".

This should not be blended naively with public opinion. Mandates and public opinion are different legitimacy signals.

### Layer 4: WVS/EVS

Keep WVS/EVS as slow-values context and cross-national comparison.

Role in demo:

- UK vs US / cross-national contrast
- Long-horizon democratic values baseline
- Evidence that model defaults are not culturally neutral

Do not lead with it.

## Counterargument To Preserve

There is still a case for WVS:

- It gives a principled baseline that is not just polling volatility.
- It supports cross-national "sovereignty means local values" comparisons.
- It helps separate deep values from day-to-day policy preference.

But this is an appendix argument. The main demo should be policy-specific and UK-facing.

## Data We Need

### Primary BSA Sources

1. **NatCen British Social Attitudes hub**
   - Use for latest reports, topic selection, published charts, and quick issue framing.
   - Link: https://natcen.ac.uk/british-social-attitudes

2. **BSA 43 latest reports**
   - NatCen lists BSA 43 reports, including "Who supports Reform?", "Higher Education", and the overall BSA 43 report.
   - These are useful for an initial UK political-attitudes demo because they are current and policy-facing.
   - Start from the NatCen BSA hub above and download the latest report PDFs/tables.

3. **UK Data Service catalogue**
   - Use for microdata downloads. Registration/login is usually required.
   - Link: https://ukdataservice.ac.uk/find-data/browse/
   - Search terms: `British Social Attitudes`, `British Social Attitudes Survey`, `BSA 43`, `BSA 42`, `NatCen`.

4. **BSA / NatCen topic trend pages and report tables**
   - Use if microdata is slow to access. For a demo, published tables are acceptable if clearly labelled as report-derived rather than microdata-built.
   - Priority topics: trust in government, welfare, redistribution, immigration, NHS, higher education, assisted dying.

### Secondary Sources

5. **British Election Study panel and cross-sectional data**
   - Use for election-cycle public opinion and mandate responsiveness.
   - Panel data hub: https://www.britishelectionstudy.com/data-objects/panel-study-data/
   - Cross-sectional data hub: https://www.britishelectionstudy.com/data-objects/cross-sectional-data/
   - BES has recent 2024/2025 data, which is more dynamic than WVS.

6. **Manifesto / government mandate data**
   - Use only as a separate mandate layer.
   - Do not treat manifesto positions as public opinion.

## Minimum Viable Data Slice

For the next demo, do not boil the ocean. Build 6-8 public-opinion targets:

1. Trust in government
2. Tax/spend preference
3. Welfare generosity / conditionality
4. Immigration level or migration attitude
5. NHS/public-service priority
6. Higher education funding or expansion
7. Assisted dying
8. One civil-liberties / due-process floor item

For each item, store:

- `item_id`
- `source`
- `year`
- `question_text`
- `response_options`
- `weighted_distribution`
- `n`
- `weight_variable`
- `license_or_access_note`
- `is_report_derived` vs `microdata_built`

## Demo Narrative

The public demo should say:

> This prototype audits whether AI systems express policy preferences aligned with British public opinion, democratic mandate, and rights constraints. WVS/EVS provides slow-values context, but the core sovereign AI question is policy drift: when AI systems advise, explain, rank, or recommend policy choices, whose preferences are they expressing?

That is sharper than:

> This model matches WVS marginals.

## Open Questions For Claude

1. Should public opinion and mandate be displayed side by side, or combined into a single target?
2. Which issues should be treated as steerable democratic preferences versus non-steerable rights floors?
3. Should decision-drift measure model drift over time, across providers, across prompts, or all three?
4. Is BSA enough for the first UK demo, or should BES be included immediately?
5. How should the demo communicate uncertainty and source quality without becoming too academic?

## Provisional Recommendation

Lead with BSA + decision-drift. Keep WVS/EVS as a baseline appendix.

The sovereign AI pitch becomes stronger, more current, and easier for a UK policymaker to understand.
