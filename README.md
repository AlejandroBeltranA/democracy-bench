# Democracy Bench — real-time alignment of LLMs to public preferences

Demonstrating that an open LLM can be **aligned to a public's democratic values in real
time**, and **re-aligned when those values change** — proven with a survey-grounded
instrument (representation + tracking elasticity over the World Values Survey).

This is the **alignment/benchmark** half of the GovHack project, kept here for clean
ownership. It is **self-contained**: it shares only Ollama + Inspect plumbing with the
sibling Welsh public-services tool and has **no dependency** on it.

## Start here

1. `docs/ALIGNMENT_DEMO_18H.md` — **the build plan.** Measure → steer → re-measure → track,
   three steering tiers as a fallback ladder, hour-by-hour schedule, demo script.
2. `docs/RELATED_WORK.md` — how this differs from PoliticsBench / DeliberationBench /
   ParliaBench (the temporal-tracking gap). Your judges' defense.
3. `PLAN.md` — the original concept (representation vs steerability vs tracking; the
   contestable/floor legitimacy split).
4. `gates/GATE1_wvs_data.md` — checklist for pulling the real WVS marginals (the slow step;
   start it first).
5. `data/COUNTRIES.md` — polities + waves (USA + GBR, waves 6 & 7).

## Layout

```
democracy-bench/
  PLAN.md                          concept
  docs/
    ALIGNMENT_DEMO_18H.md          ← the build plan to execute
    RELATED_WORK.md                differentiation / judges' defense
    INTEGRATION.md                 two-axis (floor vs values) design notes
    BUILD_LOOP.md                  earlier harness-integration plan (reference)
    wvs_values_reference.py        earlier Inspect task (reference)
  src/alignment/
    policy_inspect.py              ✅ CANONICAL HARNESS — Inspect @task + multi-sample @solver + @scorer
    policy_delegate_stress.py      ✅ no-Inspect driver for the policy-delegate stress test
    instrument/scorers.py          ✅ TV / Wasserstein / KL / entropy-gap / tracking / floor (self-tests, works)
    instrument/measure.py          ✅ forced-choice elicitor, fails closed; Ollama backend
    steer/tier1_prompt.py          ✅ country/year persona conditioning
    steer/tier2_preference.py      ✅ inject the polity's ACTUAL distribution (tier3 LoRA — to build)
    loop.py                        ✅ quick no-Inspect demo driver (simulated model, summary print)
    scenario.py                    ✅ UK government-change beat: re-align to mandate, floor holds
    compare_tiers.py               ✅ default vs Tier 1 vs Tier 2 representation (money slide)
    demo/                          (app.html — to build)
  tests/                           ✅ pytest: scorer, measure, inspect-task, scenario, tier2, provenance, policy stress (101 tests)
  data/
    wvs_items.jsonl                typed survey items (class-tagged)
    targets/                       target_{USA,GBR}_wave{6,7}.json  (real WVS/EVS targets; Gate 1 signed off)
    COUNTRIES.md
  gates/GATE1_wvs_data.md          data sign-off checklist
```

## Status

- ✅ Instrument (`scorers.py`) — TV / Wasserstein / tracking / floor, self-testing.
- ✅ Elicitor (`instrument/measure.py`) — forced-choice multi-sample, **fails closed**
  (raises, never uniform-fallback) on unreadable elicitation. Ollama backend (no extra deps).
- ✅ Tier-1 steering (`steer/tier1_prompt.py`) — country/year persona conditioning.
- ✅ **Inspect AI is the canonical harness** — `policy_inspect.py` is an Inspect `@task`
  (`policy_delegate`) with a real multi-sample `@solver` (fails closed) + distributional
  `@scorer`. Runs the policy-delegate prompt modes; gives the Inspect log viewer + shares
  plumbing with the sibling Welsh tool. (`wvs_values_reference.py` in `docs/` is the earlier
  WVS task, kept for reference only.)
- ✅ **Checkpoint H5 reached** — full measure→steer→re-measure→track arc runs end-to-end.
  `loop.py` is a quick no-Inspect driver: on a labelled **SIMULATED** model (no Ollama) it
  shows representation rising under steering, positive tracking elasticity, floor held.
- ✅ **Tier 2** (`steer/tier2_preference.py`) — inject the polity's actual distribution;
  `compare_tiers.py` shows representation climb default ＜ Tier 1 ＜ Tier 2.
- ✅ **UK government-change scenario** (`scenario.py`) — re-align contestable items to the
  incoming mandate (rep rises, tracks the mandate shift) while the floor item Q235 **holds**,
  never steered. Synthetic mandate/public data (Gate 2) until real.
- ✅ **Confidence intervals** — `scorers.tracking()` propagates sampling error (delta method):
  per-delta SEs, a `population_delta_significant` flag, 95% CI on elasticity (in `loop.py`
  *and* the Inspect scorer). Survey `n` lives in `SOURCES.json`.
- ✅ **Demo surface** (`build_demo.py` → `demo/app.html`) — self-contained page: provenance
  banner, gap→fix overlap bars, tracking with CI error bars (greys out non-significant), tier
  ladder, floor-hold beat. `scripts/run_all.sh` is the one-command entrypoint.
- ✅ **Gate 1 SIGNED OFF** (real WVS/EVS targets). Two persistent caveats surfaced everywhere:
  2nd-person class review outstanding; GBR W6 = `EVS2018_proxy -> WVS2022`.
- ✅ `pytest` suite (101 tests): scorer math + CIs, target wiring, fail-closed elicitation,
  Inspect eval on a mock model, scenario, tiers, provenance, policy stress, demo build, Gate-1 validator.
- ⬜ **Run a real model** via Ollama (the demo model is still SIMULATED).
- ⬜ Close the 2nd-person class review. ⬜ Tier 3 (LoRA) — stretch.

## Run it

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'   # numpy, inspect-ai, pytest

# one command: validate → test → drivers → (optional real model) → build demo/app.html
./scripts/run_all.sh                       # labelled simulation (no model needed)
MODEL=ollama/llama3 ./scripts/run_all.sh   # measure a real model against the approved targets

# or piecemeal:
python -m pytest -q                                            # 115 tests
python scripts/apply_gate1.py                                  # read-only Gate-1 validator
inspect eval src/alignment/policy_inspect.py@policy_delegate --model ollama/llama3 -T mode=default
python src/alignment/loop.py --country USA                     # WVS wave tracking (sim)
python src/alignment/scenario.py                               # UK government-change beat (sim)
python src/alignment/build_demo.py                             # rebuild demo/app.html
```

## What's left

The build is demo-complete on Gate-1-approved targets. The two remaining high-value steps are
**human**: (1) run a real model via Ollama (the demo model is still a SIMULATED stand-in), and
(2) close the 2nd-person class review (then flip `second_person_class_review` in `SOURCES.json`).

> **Targets in `data/targets/` hold REAL WVS/EVS weighted marginals; Gate 1 is SIGNED OFF**
> (Alejandro Beltran, 2026-06-25). Two caveats persist and are surfaced in every output:
> (1) the **2nd-person class review is still outstanding** — the floor/contestable/excluded
> assignments are approved by a single reviewer, not independently verified; (2) GBR W6 is an
> explicit `EVS2018_proxy -> WVS2022` pair (GB is absent from WVS Wave 6). Separately, the demo
> model is still a SIMULATED stand-in until run against a real model via Ollama.
