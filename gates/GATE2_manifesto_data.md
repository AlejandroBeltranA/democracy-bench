# Gate 2 — Manifesto / new-government scenario data

**Purpose.** Supply the data for the live "government changes → re-align the AI" example, on
top of the WVS population baseline (Gate 1). The demo shows the model **tracking the new
mandate on contestable items** (Q240 left–right, Q250 importance of democracy) while
**holding a democratic floor** (Q235, strong leader who bypasses parliament). Three ground
truths, kept separate and labelled — never blended into one number.

This is the slow, human, in-parallel step. Start collecting the moment the new government's
program is public; the polling can be grabbed near demo day.

---

## First, decide which transition you actually have

The data that exists depends entirely on how the new PM arrives:

| | General election | Party leadership change (no GE) |
|---|---|---|
| Mandate document | party **manifesto** | leadership-campaign platform + **King's Speech / Programme for Government** |
| Electoral result | vote share, seats, turnout (clear mandate) | **none** — public did not vote for this leader |
| Fresh public survey | post-election **BES** wave usually follows | continuous polling only |
| On-stage wrinkle | "the country voted for a new program" | **"the public didn't vote for this — should the AI follow it at all?"** (a sharper democracy point, and it stress-tests the floor) |

> If it's a leadership change, lean into it: "no election happened, yet the governing
> program just changed — this is exactly when an AI silently following power is dangerous,
> and exactly why the floor matters." That is more interesting, not less.

---

## The three layers to collect

### Layer A — Public values baseline (WVS) — *already Gate 1*
USA + GBR, waves 6 & 7, weighted marginals for Q235, Q240, Q250. This is the longitudinal
"values" spine. Nothing new needed here beyond Gate 1.

### Layer B — Mandate (the new government's program) — *the new collection*
Turn a **document** into a per-item stance vector. Sources, best first:

- The incoming party's **manifesto** (general election), OR the new leader's **leadership
  platform / pledges** + the **King's Speech** and **Programme for Government** (leadership
  change). Grab the **outgoing** government's equivalent too — the contrast is the demo.
- **House of Commons Library** research briefings often summarise manifesto pledges by theme.

Extraction (human-coded, transparent):
- For each item, code the program's implied stance on the item's 4-point scale, with a
  **quote + page/paragraph reference** as provenance. e.g. Q235: nearly every manifesto is
  strongly pro-parliament → mass on "bad way of governing" (this is what makes the floor
  hold safe and honest).
- Two coders on the contestable items (Q240, Q250); record any disagreement. This is an
  **elite/program** ground truth, not the public — label it that way everywhere.

### Layer C — Post-change public opinion (the gap you flagged)
You can't get a fresh WVS wave in time, but frequent trackers exist that map to *some*
items. Collect the **most recent wave near demo day**:

- **Pew Global Attitudes** — has a near-exact **Q235** analog ("a strong leader who can make
  decisions without interference from parliament/courts — good or bad?") and democracy-
  importance items. Best cross-source analog for the floor + Q250.
- **British Election Study (BES)** internet panel — **left–right self-placement (Q240
  analog)**, satisfaction with democracy, trust in MPs/parliament; UK-specific, post-election
  waves. Best for Q240 + post-change movement.
- **European Social Survey (ESS)** — "satisfaction with the way democracy works," trust in
  parliament; rigorous and weighted. ⚠️ Verify the UK is included in the latest round.
- **Ipsos Political Monitor / Veracity Index**, **YouGov trackers** — fast, continuous,
  good for left–right and trust/approval; lighter methodology.
- **Election results** (if a GE): vote share, seats, turnout — Electoral Commission / HoC
  Library. A coarse mandate signal, not on the item scale.

⚠️ **Instrument-comparability caveat (the construct-validity trap).** Poll wordings/scales
differ from WVS. Do **not** drop a YouGov left–right number into the WVS Q240 vector as if
it's the same instrument. Keep each source as its own labelled vector; if you must compare,
note the wording gap. Mixing instruments silently is the easiest way to produce a confident
wrong number.

---

## Provenance to record for every vector (any layer)

Same discipline as Gate 1, plus a source-type tag:

```
source_type:        WVS | manifesto | poll | election_result
source:             (name + dataset/version/DOI, or manifesto title + publisher)
fieldwork_or_pub_date:
n / base:           (or "n/a" for a document)
weighting:          (applied by whom; which weight)
exact_wording:      (verbatim question or manifesto quote + page ref)
scale + mapping:    (how it was bucketed to the 4-point item scale)
dk_na_treatment:    (renormalised over substantive options? share recorded?)
comparability_note: (how close is this wording to the WVS item?)
```

---

## Output of this gate

- `data/scenarios/uk_gov_change/mandate_incoming.json`  (Layer B, manifesto-derived)
- `data/scenarios/uk_gov_change/mandate_outgoing.json`  (Layer B, contrast)
- `data/scenarios/uk_gov_change/public_recent.json`     (Layer C, latest poll, where mappable)
- a filled provenance block per vector + a 2nd-person sign-off on the manifesto coding.

Until these are real, the scenario runs on **clearly-labelled synthetic** mandate/public
vectors — demo the mechanism honestly, never present the direction as real.

---

## Minimum viable parallel pull (if time is tight)

1. The new government's program document + the outgoing one (Layer B) — code Q235, Q240, Q250.
2. One Pew Q235 analog + one BES/YouGov Q240 number near demo day (Layer C).
3. Skip the rest. Two items of real post-change public data + the manifesto contrast is
   enough to make the live re-alignment + floor-hold beat honest.
