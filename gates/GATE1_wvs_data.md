# Gate 1 — WVS data acquisition & target build

**Purpose.** Produce the population targets the values axis scores against, and get a
human sign-off that (a) the item set + class assignments are right and (b) the wave→wave
deltas are real signal, not noise. Nothing downstream (elicitation, scoring) means
anything until this gate is passed with *real* numbers replacing the synthetic stubs.

**Output of this gate:** real `data/targets/target_{USA,GBR}_wave{6,7}.json`
+ a completed sign-off block at the bottom of this file.

---

## Recommendation: which data form

**Use aggregated marginals for the MVP. Keep microdata as the reproducibility upgrade.**

| | Aggregated marginals (RECOMMENDED for MVP) | Per-country microdata |
|---|---|---|
| Source | WVS **Online** analysis/cross-tabs, or Welzel/WVS published aggregates | Registered WVS-6 + WVS-7 country files (SPSS/CSV) |
| Effort | low — read weighted % per option off the tool | higher — load file, apply survey weight, tabulate |
| Weights | applied by the tool (verify it's the weighted view) | you apply `W_WEIGHT` / country weight yourself |
| Auditability | weaker — must record exact filters | strong — script is the record |
| Licensing | lightest | microdata redistribution restricted (don't commit raw files) |
| When to prefer | the demo, ~30 items × 2 countries × 2 waves | if a marginal looks wrong, esp. **GBR W7 boost samples** |

**Decision rule:** pull aggregated marginals for everything; if any GBR Wave-7 item's
weighted marginal looks inconsistent (boost-sample skew for Scotland/Wales/NI), recompute
*that item* from GB microdata. Record which items, if any, used the microdata fallback.

---

## Step 0 — Register (do this first; can have a wait)

1. Create a WVS account at worldvaluessurvey.org (and/or GESIS) — needed for both the
   online tool's full access and any microdata download.
2. Note the **citation requirement**: WVS must be cited; microdata must **not** be
   redistributed. We commit only derived target JSON + citations, never raw WVS files.
3. Add the raw microdata directory to `.gitignore` if you download any microdata
   (`data/wvs_raw/` or the current `data/wvs microdata/` path).

> This step is the slow one — start it in parallel with the harness/elicit.py work.

---

## Step 1 — Confirm the item set & variables (human)

For each of the ~30 items in `wvs_items.jsonl`:

- [ ] The `source.var` code (e.g. `Q235`) exists in **both** Wave 6 and Wave 7 (some
      variable codes changed between waves — verify against the codebook, not memory).
- [ ] The answer scale + `scale.labels` **order** matches the codebook's coding.
      ⚠️ Option order must match the target vector order — a flipped scale silently
      inverts tracking direction.
- [ ] The `class` (floor | contestable) is correct, and `floor_dir` is set for floor items.

**Sign-off here is the legitimacy decision** (contestable vs floor). Have a second person
review the class assignments for partisan slant before proceeding.

---

## Step 2 — Pull marginals (per item × country × wave)

For each available (var, country ∈ {USA, GBR}, wave ∈ {6, 7}):

1. In the WVS Online tool, select the country, the wave/dataset, and the variable.
2. Switch to the **weighted** view (confirm the weight is applied — unweighted % is a
   common trap).
3. Read the percentage for each substantive option, in the **same order** as
   `scale.labels`.
4. Handle non-response: record "Don't know / No answer" mass separately. For the MVP,
   **renormalize over substantive options** (document this choice); keep the DK/NA share
   in a note so a refusal channel can be added later.
5. Record `n` (weighted or unweighted base) and the exact tool filters used.

Note: WVS Wave 6 does not include a Great Britain/UK sample. `GBR wave6` is therefore an
explicit EVS proxy baseline: EVS Trend File ZA7503 v3.0.0, Great Britain 2018
(`S003=826`, `S002EVS=5`, `S025=8262018`, weight `S017`). Do not report GBR tracking as
plain WVS Wave 6 -> Wave 7; report it as `EVS2018_proxy -> WVS2022`.

Write each country/wave file as:

```json
{ "Q235": [p1, p2, p3, p4], "Q240": [...], "Q182": [...] }
```

Probabilities (not percentages) summing to ~1.0, option order = `scale.labels` order.

---

## Step 3 — Validate before sign-off (mechanical)

Run the existing wiring check (no model needed) to confirm files parse, every item's var
resolves in every country/wave, and the deltas look like real signal:

```bash
python3 - <<'PY'
import json, numpy as np, importlib.util
spec=importlib.util.spec_from_file_location("s","src/alignment/instrument/scorers.py")
S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
items=[json.loads(l) for l in open("data/wvs_items.jsonl")]
for c in ["USA","GBR"]:
    t6=json.load(open(f"data/targets/target_{c}_wave6.json"))
    t7=json.load(open(f"data/targets/target_{c}_wave7.json"))
    print(f"\n{c}")
    for it in items:
        v=it["source"]["var"]
        for w,t in [(6,t6),(7,t7)]:
            assert v in t, f"{v} missing in {c} wave{w}"
            s=sum(t[v]); assert abs(s-1)<0.02, f"{c} w{w} {v} sums to {s:.3f}"
        d=S._mean_position(np.array(t7[v]))-S._mean_position(np.array(t6[v]))
        print(f"  {it['id']:26s} pop_Δ(mean-pos)={d:+.3f}")
PY
```

Sanity checks:
- [ ] Every target vector sums to ~1.0 (the assert catches gross errors).
- [ ] Deltas have plausible sign/size (e.g. emancipative items like `Q182` should drift
      toward "justifiable" in most Western polities over 2010s).
- [ ] No vector is uniform-by-accident (a copy/paste miss).

---

## Step 4 — Sign-off (human, fill in)

```
Gate 1 sign-off
  Date: 25/06/2026
  Reviewer(s): Alejandro Beltran
  Data form used:     mixed
  Microdata fallback used for items:   GBR W6 = EVS2018 microdata (GESIS ZA7503, weight S017); USA/GBR W7 = WVS country CSV (W_WEIGHT); USA W6 = WVS Online weighted (no microdata weight available)
  Item set version (git sha):   2026-06-25 · 3 items (Q235, Q240, Q250) · data/wvs_items.jsonl (repo not under git)
  Class assignments reviewed by 2nd person:   no
  Deltas judged real (not noise):             yes 
  Notes / caveats:   GBR W6 is an EVS2018 proxy (EVS2018_proxy -> WVS2022), NOT WVS Wave 6. USA W6 from WVS Online weighted view (country CSV lacks a weight column). Q240/Q250 are WVS 1-10 items bucketed to 4 bins (see source.bucket_10_to_4). Q182 excluded from the demo. 2nd-person class review still outstanding.
  APPROVED to proceed to elicitation + scoring:   yes 
```

Commit this completed file as the audit record. Only after `APPROVED: yes` do real
scores from `wvs_values` mean anything.

---

## Citations to carry through to outputs

- Haerpfer, C. et al. (eds.) *World Values Survey: Round Seven* (WVS-7) — country files
  for USA (2017) and Great Britain (2022).
- *World Values Survey: Round Six* (WVS-6, 2010–2014) — USA (2011). Great Britain/UK is
  not available in WVS Wave 6.
- EVS (2022): *EVS Trend File 1981-2017*. GESIS Data Archive, Cologne. ZA7503 Data file
  Version 3.0.0, DOI: `10.4232/1.14021` — Great Britain 2018 proxy baseline.
- Cite the exact dataset versions/DOIs used (record them in the sign-off notes).
