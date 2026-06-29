# Logprobs Research Direction: sharper scoring + nudging toward agreement

Purpose: extend Democracy Bench from *measuring* a model's option distribution to *analysing
the full logprob distribution* and *moving that distribution toward a public target* — while
proving the rights floor still holds. This is the researcher-flagged direction: push on token
log-probabilities for sharper scoring, and treat logit steering as an alignment lever.

This builds directly on existing code. It does **not** replace the forced-choice, survey-grounded
design — logprobs make the same `representation = 1 − TV(model, public)` measurement sharper and
add a continuous steering signal on top of it.

## Where we already are

The measurement seam is built; the steering-in-logprob-space seam is not.

- `src/alignment/instrument/measure.py`
  - `option_logprob_vector(top_logprobs, n_options)` — first generated token's logprobs → a
    probability vector over the option numbers. Fails closed if no option-number token is present.
  - `elicit_item_logprobs(logprob_fn, item, n_orders)` — scores an item directly from logprobs,
    averaging over option orderings to cancel position bias. No temperature, no sampling.
  - `openrouter_logprob_fn(model)` — a real `LogprobFn` over OpenRouter (`logprobs: true`,
    `top_logprobs`, `temperature: 0`, `max_tokens: 1`). Fails closed when a provider returns none.
  - `mlx_elicitor(model)` — local open weights on Apple Silicon (the substrate that makes true
    logit/activation steering possible).
- `src/alignment/instrument/scorers.py`
  - `total_variation`, `representation_score = 1 − TV`, `wasserstein1_ordinal`, `tracking`,
    bootstrap CIs. "Agreement" = high representation = low TV against the public target.
- `src/alignment/steer/` — Tier 1 (persona label) and Tier 2 (inject the actual distribution)
  produce a `conditioning` string prepended to the prompt. These are the prompt-level steering rungs.

So today: we can read option logprobs from API models and score them by TV. We cannot yet (a)
use the *full* distribution as a richer instrument, or (b) *move* the logprob mass and quantify
the move.

## Two research questions

- **RQ1 — Sharper scoring.** What does the full first-token logprob distribution tell us that a
  sampled/argmax distribution cannot?
- **RQ2 — Nudge toward agreement.** Can we move logprob mass toward the public target, how cheaply,
  and does the rights floor survive the nudge?

The unifying idea: logprobs are the common currency for measuring how far each intervention rung
(context → decode → activations → weights) moves a model toward agreement, and whether the floor
holds at every rung.

## Substrate decision

**Both, API-breadth first.** RQ1 and the cheap RQ2 rungs (1–2) run on OpenRouter across the
existing multi-model panel; the headline RQ2 rungs (3–5) need local open weights via `mlx_elicitor`.

- API path (OpenRouter): logprobs are read-only; `logit_bias` gives coarse, output-token-level
  write access. Broad model coverage, fast. Covers RQ1 fully + RQ2 rungs 1–2.
- Local path (MLX/HF): full logit and activation access → true logit steering, activation steering,
  LoRA. Fewer/smaller models, slower. Required for RQ2 rungs 3–5 and the headline logit-steering claim.

## RQ1 — Logprob analysis (sharpens the existing instrument)

Add these to `scorers.py` alongside the TV/Wasserstein scorers, and log the full first-token option
vector per item on the OpenRouter path.

1. **KL / NLL scoring, not just TV.** Add `KL(public ‖ model)` and the NLL of public responses
   under the model. The logprob-native distance: how surprised the model is by how the public
   actually answered. Sharper and more sensitive to *where* mass sits than TV. Report alongside
   `representation_score`, not instead of it (TV stays the headline for continuity with prior runs).

2. **Entropy gap — does the model reproduce the public's *dispersion*?** `H(model) − H(public)`.
   A model can match the public mean (good TV) yet pile all mass on one option when the public is
   genuinely split. This is representativeness of *uncertainty*, a metric values-benchmarks rarely
   make — a candidate headline claim.

3. **Logprob-space variance as the instrument.** NEXT_EXPERIMENT_DESIGN warns that repeated
   sampling turns the temperature setting into the measurement target. The variance of the logprob
   vector under paraphrase/reorder is a cleaner robustness signal than sampled-count noise. The
   paraphrase and order rotation already exist (`elicit_item`, `elicit_item_logprobs`).

4. **Position bias, quantified.** `elicit_item_logprobs` already averages over orders to cancel
   bias; logprobs let us *measure* the per-option-token bias magnitude rather than only cancel it.

5. **Steering trace (bridge to RQ2).** Log-mass on the public-preferred option *before* and *after*
   Tier-1/Tier-2 conditioning. The nudge becomes a continuous quantity, `Δ log p(target)`, not a
   discrete distribution shift.

## RQ2 — Nudge toward agreement (the steering ladder)

Cheapest, always-runs rung first; most invasive last — mirroring the existing fallback ladder.
Each rung is a different answer to "where does alignment live," measured in the same logprob currency.

| Rung | Lever | Substrate | Status |
|---|---|---|---|
| 1 | Prompt steering (Tier 1/2) | any | have — measure it in logprob space |
| 2 | Logit bias on option tokens | API (`logit_bias`) | new, cheap, doable now |
| 3 | Controlled / reweighted decoding | local weights | new |
| 4 | Activation steering (diff-of-means agreement vector) | local weights | new — the headline |
| 5 | LoRA fine-tune to a KL target | local weights | existing Tier-3 stretch |

The two genuinely novel rungs:

- **Rung 2 — logit-bias calibration (API).** OpenRouter/OpenAI expose `logit_bias`. Solve for the
  per-item bias vector on the option-number tokens that makes the normalized option logprobs match
  the public distribution — a small convex calibration. Claim: "we can calibrate a frontier API
  model's option logprobs to a public target via a logit-bias vector." The honest test is **held-out
  generalization** (a bias fit on items A–C applied to D–F), not fit on the calibrated item — the
  same inject-then-score-against trap as the Tier-2 honesty caveat.

- **Rung 4 — activation steering (local).** On an MLX open model, extract a "public-agreement"
  direction as the diff-of-means between default and persona-conditioned activations, then add it at
  decode time. This is logit-steering-as-alignment-lever. Sweep the steering coefficient and plot a
  **dose-response curve on both axes** (representation gain vs. floor margin). The safe operating
  point is where representation rises and the floor margin does not shrink.

## The guardrail that makes this a safety result

Every rung is scored on **both** axes:

- contestable items → representation / agreement gain;
- floor items → `log p(protective) − log p(violating)` margin must **not** shrink under steering.

A bias/steering vector that improves agreement *and* erodes the floor is a "bad nudge" in the
existing taxonomy (NEXT_EXPERIMENT_DESIGN). The dose-response curve makes the trade-off visible.
Demo beat: a continuous nudge slider sliding the logprob bars toward the public distribution while
the floor bar stays put.

## Logprob-native metrics to add

- `kl_public_model` — KL(public ‖ model); the NLL of public responses under the model.
- `entropy_gap` — H(model) − H(public); does the model reproduce public dispersion.
- `delta_logp_target` — Δ log p(public-preferred option) before vs after a steer; the continuous nudge.
- `steering_efficiency` — representation gain per unit intervention strength (bias magnitude or
  steering coefficient).
- `floor_logprob_margin` — log p(protective) − log p(violating); must not shrink under any steer.
- dose–response / monotonicity — sweep steering strength; plot representation and floor margin vs
  strength to locate the safe operating point.

Keep `total_variation` / `representation_score` as the headline for continuity; the logprob metrics
are the sharper secondary layer.

## Confounds and guardrails (bake in from day one)

- Not all providers return logprobs or honor `logit_bias`; fail closed (the existing
  `ElicitationError` pattern) rather than degrade silently.
- **Tokenization** breaks multi-token option numbers ("10" = "1" + "0"). Cap items at ≤ 9 options
  or use single-letter labels so each option is one token. `option_logprob_vector` already strips
  surrounding punctuation/whitespace; verify it against the real tokenizer.
- Verify the *first generated token* is the answer token, not formatting/whitespace.
- `logit_bias` is global per-token, not per-position — valid only with `max_tokens: 1` (which the
  logprob path already uses).
- Tier-2 and logit-bias both inject-then-score-against the target — the interesting number is
  **held-out** generalization, not fit on the calibrated item.
- Activation steering can degrade coherence/capability — measure off-task quality, not only the
  target metric.
- Public agreement is **not** a virtue on floor items — the two-axis evaluation is non-negotiable.

## Phasing

- **Phase 0 (~1–2 days, API).** Logprob analysis layer: add KL/NLL/entropy-gap to `scorers.py`, log
  the full first-token option vector per item over the existing OpenRouter panel. Answers RQ1, no new
  infra.
- **Phase 1 (API).** Logit-bias calibration: solve per-item bias vectors to match the target, test
  held-out generalization, check the floor margin. First "move the logprobs" result.
- **Phase 2 (local).** Activation steering on one MLX model: diff-of-means agreement vector,
  dose-response sweep on both axes. The headline logit-steering lever.
- **Phase 3 (stretch, local).** LoRA fine-tune to a KL target; compare where alignment "sticks"
  (context vs decode vs activations vs weights). Ties to the existing Tier-3 stretch.

Each phase yields a defensible claim and a demo beat.

## Claims this design can support

- "We can score how well a model reproduces not just the public's central tendency but its
  *dispersion* (entropy gap) — and some representative-on-average models are over/under-confident."
- "A frontier model's option logprobs can be calibrated to a public target with a per-item
  logit-bias vector, and the calibration partially generalizes to held-out items."
- "Activation steering moves an open model toward public agreement continuously, with a measurable
  safe operating point beyond which the rights floor erodes."
- "Alignment can be moved at the context, decode, activation, or weight level — logprobs measure how
  far each rung moves agreement and whether the floor holds."

Avoid (out of scope for this evidence):

- "Agreement with the public is always good" (false on floor items by construction).
- "Logit steering proves values live in the weights" (rungs 1–4 are runtime, not weight-level).

## Success criteria

A logprob run is presentation-grade only if:

- KL/NLL/entropy-gap are reported alongside TV, with the full first-token option vector logged;
- every steering rung is evaluated on **both** axes (representation gain + floor margin);
- logit-bias / Tier-2 results report **held-out** generalization, not fit on the calibrated item;
- activation-steering results include a dose-response curve and an identified safe operating point;
- providers that return no logprobs fail closed, never a fabricated vector;
- option sets are single-token (≤ 9 options or letter labels) and the first-token assumption is verified;
- run metadata records substrate (API vs local), model id, intervention type and strength.
