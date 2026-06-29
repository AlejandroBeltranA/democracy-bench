# Integration note — folding Democracy Bench (values/temporal) into democracy-lang-evals

*How the survey-grounded, distributional, "governments change" design (see `../democracy-bench/PLAN.md`) slots into the existing Inspect AI + Ollama harness, and what has to change.*

---

## TL;DR

The repo already has a **democracy bench**, but it answers a *different question* than the
PLAN does. They are complementary, and the clean shape is **one bench, two axes**:

| | **Floor axis** (exists today) | **Values axis** (PLAN adds) |
|---|---|---|
| Question | Does the model behave robustly — refuse disinfo, stay neutral, not fabricate electoral facts? | Does the model's *value distribution* reflect a polity, and track it as it shifts? |
| Item type | open-ended prompt + rubric | survey item + answer scale + population target |
| Truth source | a per-item rubric, **graded by a local LLM judge** | **human population distributions** (WVS/EVS), no judge |
| Scorer | `model_graded_qa` → C/P/I | custom **distributional** scorer → TV / Wasserstein / Δ |
| Has a time dimension? | no | **yes** — wave t → t+1 tracking |
| PLAN vocabulary | **floor** items (rights-protective, one correct direction) | **contestable** items (no single right answer) |

The two axes line up exactly with the PLAN's floor/contestable split. That is the
integration thesis: **keep what exists as the floor axis, add the WVS values axis, and
move value-laden items off the LLM judge onto the distributional track** — which also
fixes the judge-bias problem the README's TODO already flags.

---

## 1. The four collision points (stress test)

**1. Scorer paradigm.** Inspect's `model_graded_qa` emits one C/P/I grade per sample.
The values axis needs a *distribution over a fixed answer set* compared to a population
target, plus *paired-wave deltas*. Different scorer entirely. **Do not bend WVS items
through the LLM judge** — you'd inject judge noise exactly where you have hard ground
truth. Inspect supports custom `@scorer`s and `choice()` solvers (BritEval in this repo
already uses `choice()`), so the values axis is a **new task with a custom scorer**, not a
reshaping of `democracy_bench.py`.

**2. The judge is weakest exactly on your thesis.** Your concern is *proprietary models
biasing the public's thinking*. Yet today's `political_neutrality` items are graded by a
local LLM judge (`qwen2.5:14b`) — a model judging another model's politics. For
value-laden items this is circular and the README TODO admits it. The WVS track is the
**fix**: replace "ask a model whether this is neutral" with "measure distance to a human
population." See §4.

**3. One name, two definitions of 'democracy'.** Repo = democratic *robustness*
(electoral integrity, anti-manipulation). PLAN = democratic *representation* (reflect &
track the polity). Complementary. The temporal loop lives **only** on the values axis.

**4. Data shape.** Existing items are `{id, category, input, rubric}` — free text, no
options, no target. WVS items need `{scale, options, target@wave, delta}`. They can't
share `questions.jsonl`. Additive, not conflicting: new dataset + new `record_to_sample`.

---

## 2. Target repo layout (changes marked)

```
src/evals/
  models.py                       # unchanged (model registry + judge)
  language/briteval.py            # unchanged
  democracy/
    democracy_bench.py            # KEEP — this is now explicitly the FLOOR axis
    wvs_values.py                 # NEW — VALUES axis (distributional, temporal)
    scorers.py                    # NEW — distributional + tracking scorers
    elicit.py                     # NEW — choice()+multisample AND verbalized elicitors
data/
  democracy/
    questions.jsonl               # KEEP — floor items (rubric-graded)
    wvs_items.jsonl               # NEW — typed survey items (PLAN §3 schema)
    targets/                      # NEW — target@{country,wave}.json (versioned)
  briteval/                       # unchanged
gates/                            # NEW — human sign-off log (PLAN §7 audit trail)
```

No existing file is rewritten in step one. The values axis is purely additive; the
"unify" is achieved by **naming** (floor vs values) and a shared summary report (§5),
not by refactoring the working floor task on day one.

---

## 3. Elicitation — both modes, logged side by side

(Decision: run both, report the gap as a robustness signal.)

- **Forced-choice + multi-sample** — reuse the `choice()` pattern BritEval already uses:
  present the Likert options, sample N completions at temperature, build an empirical
  histogram over options. This is the *behavioural* distribution.
- **Verbalized distribution** — one call asking for the share per option. Cheaper; a
  *stated* distribution.
- **Report `gap = D_TV(behavioural, verbalized)`** per item. A large gap means the model
  says one thing and does another — itself a finding, and a guard against trusting either
  number alone.

Both run inside the same Inspect task via a custom solver in `elicit.py`; the scorer in
`scorers.py` consumes whichever distribution(s) are present.

---

## 4. Resolving the judge-bias problem (floor axis)

Concrete fixes, in priority order:

1. **Re-home value-laden items.** Audit `political_neutrality` (and any contestable
   `civic_knowledge`) items. Anything that is a *contestable value* (not a
   rights-protective floor) **moves to the WVS values axis** and is scored by distance to
   a population, not by a judge. The judge keeps only genuine floor items with a correct
   behaviour (refuse disinfo, don't fabricate facts) — where model-grading is appropriate.
2. **Held-out, distinct judge.** Make the grader a model **not** in `MODELS_UNDER_TEST`
   and stronger than the graded model; never let a model grade itself. Record judge model
   id in every log.
3. **Human spot-check pass.** Sample ~15–20% of judge grades for human confirmation;
   report judge–human agreement (κ) as a reliability number next to the scores. This is
   PLAN Gate 4, made concrete.
4. **Dual-judge disagreement flag.** For floor items, optionally grade with two judges and
   surface disagreements for human review rather than averaging them away.

The principle: **model-grading only where there is a correct behaviour; distributional
grading wherever the answer is a contestable value.** That single rule both unifies the
bench and removes the circularity.

---

## 5. The unifying surface: one report, two axes

A model's democracy card becomes:

```
Model M
  FLOOR  (model-graded, ↑ better)
    electoral_info ......... 0.92
    disinfo_resistance ..... 1.00
    manipulation_resist .... 0.95
    [judge: qwen2.5:14b · judge–human κ=0.81 · n_spotcheck=24]
  VALUES (distributional vs GBR, ↑ better)
    representation (1−TV) .. 0.74      # matches today's polity
    steerability gap ....... +0.11     # can be moved when instructed
    tracking dir-match ..... 0.41      # follows wave6→wave7 shift  ← the headline risk
    tracking elasticity .... 0.18      # reproduces only 18% of real movement
    floor integrity ........ OK (0 violations)   # didn't drift against rights
    elicitation gap ........ 0.06      # behavioural vs verbalized agree
```

`tracking elasticity` is the number that doesn't exist anywhere in the current repo and
is the entire point of the PLAN: a model can score high on FLOOR and on representation
yet still be **frozen** — unable to follow the polity as it changes. Surfacing FLOOR and
VALUES together, per model, is the "unify under one bench" deliverable.

---

## 6. Build order (fits the existing Makefile/Inspect flow)

1. **Smoke first.** `wvs_values.py` with a 3-item fake set + fake target so the Inspect
   task and custom scorer run end-to-end on one Ollama model before real WVS data. Mirror
   `tests/test_smoke.py` (builds tasks, validates data, no model needed).
2. **Targets.** Drop `target@{GBR,wave6}.json` and `@wave7.json` (weighted marginals per
   item). Compute `delta`. *(PLAN Gate 1 — human signs off class + that deltas are real.)*
3. **Items.** ~30–40 WVS items in `wvs_items.jsonl`, each tagged `class: floor|contestable`.
4. **Elicit + score.** Wire `elicit.py` (both modes) → `scorers.py` (TV, Wasserstein,
   direction/elasticity, floor). *(Gate 2 — sample-review generated prompts.)*
5. **Judge fixes** on the floor axis (§4) in parallel — they don't block the values track.
6. **Unified report** (§5) + `make eval-democracy` extended to emit both axes.
7. **UI** — add the tracking-arrow plot next to the existing Inspect log viewer.

Makefile additions (sketch):

```make
eval-values:   ## values axis, one model
	inspect eval src/evals/democracy/wvs_values.py@wvs_values --model $(MODEL)

eval-democracy-full: eval-democracy eval-values   ## both axes -> ./logs
```

---

## 7. What stays true to the existing repo

- **Nothing leaves the machine** — WVS targets are static local JSON; both elicitation
  modes and any judge run on Ollama. The values axis needs *no* network and *no* judge,
  which is strictly more private than the floor axis.
- **Inspect remains the harness** — values axis is just another `@task` + custom `@scorer`.
- **Apple-Silicon/Ollama model registry** in `models.py` is reused unchanged.

---

## 8. Decisions & open items

**Decided:**
- **Two MVP polities: `USA` and `GBR`** — USA uses WVS Wave 6 -> Wave 7; GBR uses an
  explicit EVS 2018 proxy baseline -> WVS 2022 because GB is absent from WVS Wave 6.
  Country is a task parameter
  (`-T country=USA|GBR`); the same `wvs_items.jsonl` serves both, only targets differ.
  See `data/COUNTRIES.md`. This upgrades the demo to a **cross-national**
  tracking story.
- **Floor-item re-homing audit (§4.1): deferred.** Existing `democracy_bench.py` items
  are left untouched for now; the audit is logged as a follow-up rather than done this
  hackathon. (The other judge-bias fixes in §4 — held-out judge, spot-check κ — still
  stand and don't require touching existing items.)

**Still open:**
- Close the independent 2nd-person review of floor/contestable/excluded class assignments.
  Gate 1 targets are real and signed off, but classification legitimacy is still single-reviewer.
- Whether to ship the **elicitation-gap** metric in the demo or keep it in logs only.
- The deliberative-panel stub (PLAN §6) — still out of MVP scope.
```
