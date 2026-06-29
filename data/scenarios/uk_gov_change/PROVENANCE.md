# UK government-change scenario — data provenance

⚠️ **Every vector in this directory is SYNTHETIC and illustrative.** It exists to drive the
"government changes → re-align the AI, but hold the floor" demo beat end-to-end before real
data lands. Do not present any number or direction here as real. Replace at Gate 2
(`gates/GATE2_manifesto_data.md`).

Vectors are per-item probability distributions over the item's 4-point scale (same order as
`data/wvs_items.jsonl` labels), keyed by WVS var.

| File | Layer | Real source (Gate 2) |
|---|---|---|
| `mandate_outgoing.json` | the outgoing government's implied stance | outgoing manifesto / programme, human-coded |
| `mandate_incoming.json` | the incoming government's implied stance | incoming manifesto or King's Speech / Programme for Government, human-coded |
| `public_recent.json` | post-change public opinion (where mappable) | Pew (Q235 analog) / BES (Q240) / latest poll near demo day |

## The illustrative story these numbers tell

- **Q240 (left–right, contestable):** outgoing mandate sits centre-right; incoming sits
  centre-left — a clear, demonstrable shift the model should track when re-aligned.
- **Q250 (importance of democracy, contestable):** incoming mandate emphasises democratic
  renewal (slightly higher) — a mild positive shift.
- **Q235 (strong leader bypassing parliament, FLOOR):** both mandates are strongly
  pro-parliament, as any real programme would be. This item is **never steered** toward a
  mandate; it is only checked for floor integrity. The demo line is: "we re-aligned policy
  to the new mandate, but we never moved the floor — and here is the model still holding it."

## Honesty note for the leadership-vs-election case

If the new PM arrives by party leadership change (no general election), there is no manifesto
and no electoral result — the mandate is the leadership platform + King's Speech, and "the
public didn't vote for this" is itself the point that makes the floor matter. See
`gates/GATE2_manifesto_data.md`.
