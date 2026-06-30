"""Steering rung 4: activation steering on a local open model (logprobs research direction, RQ2 / Phase 2).

Phase 1 showed the cheapest rung — one shared logit-bias on the *output* — does not generalise: the
model's misses are idiosyncratic per item, not a single global tilt. This rung reaches *inside* the
model instead. As the model processes a forced-choice question it carries a residual stream (a vector
per token at each layer); we

  1. find a "public-agreement" DIRECTION in that stream as the diff-of-means between the model run as
     itself (default) and run told to answer as the median UK adult (persona) — `capture_direction`;
  2. add `alpha · direction` back into the stream at one layer while the model answers, with no prompt
     — `LayerTap` in steer mode;
  3. sweep `alpha` and re-measure on BOTH axes (representation on contestable items, rights-floor
     protective mass) — `dose_response` — to locate the safe operating point.

Because the model rebuilds its residual stream per question, one direction expresses differently on
each — the per-item adaptivity a global output bias cannot have. This only works on weights we run
ourselves: it needs a local MLX model, not an API. The *measurement* reuses Phase 1 exactly — the same
first-token option logprobs and `option_logprob_vector` — so default/steered numbers are comparable.

MLX imports live inside the functions so the pure helpers (diff_of_means, pick_operating_point) and this
module import without mlx installed.
"""
from __future__ import annotations

import numpy as np

from alignment.instrument import measure as M
from alignment.steer import tier1_prompt as T1

DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
PERSONA_COUNTRY, PERSONA_YEAR = "GBR", 2024


# ---- pure helpers (no mlx) -----------------------------------------------------------

def diff_of_means(default_acts: np.ndarray, persona_acts: np.ndarray) -> np.ndarray:
    """The steering direction: mean(persona) − mean(default) over captured residual-stream vectors.
    Both arrays are [n_items, d_model]; returns a [d_model] direction (the average shift the persona
    instruction induces in the model's internal state)."""
    d = np.asarray(default_acts, float)
    p = np.asarray(persona_acts, float)
    if d.shape != p.shape or d.ndim != 2:
        raise ValueError(f"need matching [n,d] arrays, got {d.shape} vs {p.shape}")
    return p.mean(axis=0) - d.mean(axis=0)


def pick_operating_point(curve: list[dict], floor_min: float = 0.5) -> dict:
    """From a dose-response curve (each row: alpha, representation, floor_mass), pick the alpha with the
    highest representation whose floor protective-mass still holds (>= floor_min). The "safe operating
    point": as much agreement gain as we can buy without cracking the rights floor.

    Returns {baseline_representation, best, improved, floor_limited}. `best` is the chosen row;
    `improved` = it beats the alpha=0 baseline; `floor_limited` = a higher-rep alpha existed but was
    rejected for breaching the floor."""
    rows = [r for r in curve if r.get("representation") is not None]
    if not rows:
        raise ValueError("no dose-response rows with a valid representation (model broke at every alpha)")
    base = min(rows, key=lambda r: abs(r["alpha"]))            # alpha closest to 0
    safe = [r for r in rows if r.get("floor_mass") is None or r["floor_mass"] >= floor_min]
    best = max(safe, key=lambda r: r["representation"]) if safe else base
    unsafe_better = any(r["representation"] > best["representation"] and
                        r.get("floor_mass") is not None and r["floor_mass"] < floor_min
                        for r in rows)
    return {
        "baseline_representation": base["representation"],
        "best": best,
        "improved": best["representation"] > base["representation"] + 1e-9,
        "floor_limited": bool(unsafe_better),
    }


# ---- mlx engine ----------------------------------------------------------------------

def load_model(name: str = DEFAULT_MODEL):
    """Load an MLX model + tokenizer (raises a clear error if mlx-lm isn't installed)."""
    if not M.mlx_available():
        raise RuntimeError("mlx-lm not available — `pip install mlx-lm` (Apple Silicon only)")
    from mlx_lm import load
    return load(name)


def _chat_ids(tok, user: str, system: str = M.SURVEY_SYSTEM):
    """Token ids for a chat-formatted (system, user) turn, ready for the model's forward pass."""
    import mlx.core as mx
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": user}]
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True)
    if isinstance(ids, str):                       # some wrappers return text, not ids
        ids = tok.encode(ids)
    return mx.array([list(ids)])


def install_tap(model, layer_idx: int):
    """Wrap decoder block `layer_idx` with a LayerTap (for capture + steering). Returns (tap, restore)
    where restore() puts the original block back. The residual stream is the block's output."""
    import mlx.nn as nn
    import mlx.core as mx

    base = model.model
    inner = base.layers[layer_idx]

    class LayerTap(nn.Module):
        def __init__(self, block):
            super().__init__()
            self.inner = block
            self.capture = False
            self.captured = None          # last-token residual of the most recent forward (np [d])
            self.steer_vec = None         # mx.array [d] or None
            self.steer_alpha = 0.0

        def __getattr__(self, name):
            # the parent model reads block attributes (e.g. `use_sliding`) off the layer before
            # calling it — delegate anything we don't define to the wrapped block (`inner` from the
            # enclosing install_tap scope; mlx stores submodules outside __dict__).
            try:
                return super().__getattr__(name)
            except AttributeError:
                if hasattr(inner, name):
                    return getattr(inner, name)
                raise

        def __call__(self, x, mask=None, cache=None):
            out = self.inner(x, mask, cache)
            if self.steer_vec is not None and self.steer_alpha:
                out = out + (self.steer_alpha * self.steer_vec).astype(out.dtype)
            if self.capture:
                last = out[:, -1, :]
                mx.eval(last)
                self.captured = np.array(last)[0].astype(np.float64)
            return out

    tap = LayerTap(inner)
    base.layers[layer_idx] = tap

    def restore():
        base.layers[layer_idx] = inner
    return tap, restore


def mlx_logprob_fn(model, tok, top_k: int = 40):
    """A Phase-1-compatible LogprobFn over the local model: one forward pass, read the last position's
    logits, keep the top-k tokens, and hand them to `option_logprob_vector` (same scoring as the API
    path). Steering is whatever the installed tap currently holds — set it before calling."""
    import mlx.core as mx

    def fn(prompt: str, n: int) -> np.ndarray:
        ids = _chat_ids(tok, prompt)
        logits = model(ids)
        row = np.array(logits[0, -1]).astype(np.float64)
        row = row - (row.max() + np.log(np.exp(row - row.max()).sum()))   # log-softmax
        top = np.argpartition(row, -top_k)[-top_k:]
        top_logprobs = {tok.decode([int(i)]): float(row[int(i)]) for i in top}
        return M.option_logprob_vector(top_logprobs, n)

    return fn


def capture_direction(model, tok, tap, items: list, country: str = PERSONA_COUNTRY,
                      year=PERSONA_YEAR) -> np.ndarray:
    """Diff-of-means public-agreement direction at the tap's layer: for each item capture the last-token
    residual under the bare question (default) and under the median-UK-adult persona, then average the
    (persona − default) shift. One forward per condition per item (canonical option order)."""
    persona = T1.persona(country, year)
    defs, pers = [], []
    tap.steer_vec = None
    tap.capture = True
    for it in items:
        mlx_logprob_fn(model, tok)(M.forced_choice_prompt(it, None), len(it["scale"]["labels"]))
        defs.append(tap.captured)
        mlx_logprob_fn(model, tok)(M.forced_choice_prompt(it, persona), len(it["scale"]["labels"]))
        pers.append(tap.captured)
    tap.capture = False
    return diff_of_means(np.array(defs), np.array(pers))


def steered_distribution(model, tok, tap, item, vector, alpha: float,
                         n_orders: int = 2, seed: int = 0) -> np.ndarray:
    """Order-averaged option distribution for one item with the steering vector applied at strength
    `alpha` (alpha=0 → the model's default). Reuses `elicit_item_logprobs` for position-bias averaging.
    Raises ElicitationError when steering has pushed the model off-distribution (no option token in the
    top logprobs) — the caller treats that as the coherence-breakdown ceiling, not a crash."""
    import mlx.core as mx
    tap.steer_vec = None if vector is None else mx.array(np.asarray(vector, np.float32))
    tap.steer_alpha = float(alpha)
    try:
        return M.elicit_item_logprobs(mlx_logprob_fn(model, tok), item, conditioning=None,
                                      n_orders=n_orders, seed=seed)
    finally:
        tap.steer_alpha = 0.0


def dose_response(model, tok, tap, contestable: list, floors: list, vector,
                  alphas: list, n_orders: int = 2, seed: int = 0) -> list[dict]:
    """Sweep steering strength and measure BOTH axes at each alpha: mean representation on contestable
    items (vs their public targets) and mean rights-floor protective mass. Items where steering broke
    the model (no option token) are counted as `broke`, not faked — at high alpha that count is itself
    the coherence-ceiling signal. `contestable`/`floors` are StressItem-like (`.item`, `.public`)."""
    from alignment.instrument import scorers as S
    from alignment import drift

    def measure_group(group, score_fn):
        vals, broke = [], 0
        for si in group:
            try:
                d = steered_distribution(model, tok, tap, si.item, vector, a, n_orders, seed)
            except M.ElicitationError:
                broke += 1
                continue
            vals.append(score_fn(si, d))
        return vals, broke

    curve = []
    for a in alphas:
        reps, broke_c = measure_group(contestable, lambda si, d: S.representation_score(d, si.public))
        masses, broke_f = measure_group(floors, lambda si, d: drift.protective_mass(d, si.item["floor_dir"]))
        curve.append({
            "alpha": float(a),
            "representation": float(np.mean(reps)) if reps else None,
            "floor_mass": float(np.mean(masses)) if masses else None,
            "n_contestable_ok": len(reps), "n_contestable_broke": broke_c,
            "n_floor_ok": len(masses), "n_floor_broke": broke_f,
        })
    return curve
