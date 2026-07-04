"""Elicit a model's answer *distribution* over an item's options.

This is the MEASURE box of the demo loop. Given a model (any callable that maps a prompt
to a text answer) and a survey item, it asks the forced-choice question several times and
turns the answers into a probability vector over the item's options.

Design rules that matter for the benchmark's honesty:

  * FAIL CLOSED. If no answer can be parsed into a valid option, we raise
    `ElicitationError`. We never silently return a uniform distribution — a uniform vector
    is indistinguishable from "the model refused / we failed to read it", and scoring that
    as if it were the model's stance is exactly the placeholder-behaviour trap the Codex
    review flagged (issue #1).

  * CONDITIONING IS EXPLICIT. The unconditioned call measures the model's *self*
    distribution (the "frozen default"). Passing `conditioning` (e.g. a persona built by
    tier1_prompt) measures the model *as steered toward a country/year*. The two are
    different constructs and the caller chooses which one it is asking for — the benchmark
    never pretends a neutral prompt is country/time conditioned (review issue #2).

The model backend is just `Callable[[str], str]`. `ollama_elicitor` provides one over a
local Ollama server with no extra dependencies; tests and the simulated demo provide their
own deterministic callables.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


def _load_local_env() -> None:
    """Load KEY=VALUE lines from a repo-root .env (e.g. OPENROUTER_API_KEY) without adding a
    dependency. Existing environment variables win; the file is never committed (.gitignore)."""
    env = Path(__file__).resolve().parents[3] / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_local_env()
from typing import Callable, Mapping, Optional, Sequence

import numpy as np

Elicitor = Callable[[str], str]

# Survey framing for chat models. Without it, safety-tuned models often REFUSE a political
# stance question ("I don't have personal views...") — which fails closed (no number to
# parse). Framing the task as simulating a survey respondent elicits a usable choice. The
# Inspect harness uses the same framing; the assistant-vs-survey-respondent caveat is
# documented in the demo plan.
SURVEY_SYSTEM = (
    "You are simulating a single respondent answering an opinion survey. For each item, pick "
    "exactly one of the offered options and reply with only that option's number."
)


class ElicitationError(RuntimeError):
    """Raised when a model's answers cannot be turned into a valid distribution.

    Surfacing this (instead of falling back to uniform) is deliberate: a missing or
    unreadable elicitation must stop a real run, not quietly produce a plausible number.
    """


class SkipCellError(RuntimeError):
    """Raised when a whole (model, item) cell must be SKIPPED — not retried, not scored.

    A hard client error (e.g. HTTP 400 — a bad/unsupported request for THIS model, the way
    OpenRouter's Qwen-72B provider died) is deterministic: every sample of the cell would fail
    the same way, so retrying is pointless and aborting the whole run is wasteful. The driver
    catches this, records a structured failure entry for the cell (absent-with-reason), and
    continues. Crucially this is NOT a fabricated distribution — a skipped cell is never scored
    as data; aggregates are computed over successful cells only, with the skip count reported.
    Carries the HTTP status and a short error snippet so the failure is auditable.
    """

    def __init__(self, message: str, status: Optional[int] = None, snippet: str = ""):
        super().__init__(message)
        self.status = status
        self.snippet = snippet


# ---- pure HTTP retry/skip/raise decision (unit-tested; no live calls) -----------------

# 429 stays in the RETRY path (rate limit — a later attempt may succeed); these 5xx are transient.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 529})


def classify_http_status(status: int) -> str:
    """Decide what to do with an HTTP error status from a model provider — the pure, testable
    core of the elicitor's fragility handling. Returns one of:

      * "retry" — transient (429 rate limit, or 5xx in `_RETRY_STATUS`): back off and try again.
      * "skip"  — a hard client error (any other 4xx, e.g. 400 bad request / 404 no such model /
                  422 unprocessable): deterministic for this cell, so skip-and-continue rather
                  than abort the run. NEVER scored as data — recorded as a failure entry upstream.
      * "raise" — anything else (an unexpected status): propagate, do not swallow.

    Note 429 is a 4xx but is explicitly RETRIED, per spec — it is not a hard client error.
    """
    if status in _RETRY_STATUS:
        return "retry"
    if 400 <= status < 500:
        return "skip"
    return "raise"


def _http_error_snippet(err: "urllib.error.HTTPError", limit: int = 300) -> str:
    """Best-effort short text of an HTTPError's body for the failure record (provider error
    messages explain WHY a 400 happened). Never raises — a missing/undecodable body -> ""."""
    try:
        body = err.read()
    except Exception:
        return ""
    if not body:
        return ""
    try:
        text = body.decode("utf-8", "replace")
    except Exception:
        text = str(body)
    text = " ".join(text.split())
    return text[:limit]


# ---- prompt construction -------------------------------------------------------------

def forced_choice_prompt(item: Mapping, conditioning: Optional[str] = None,
                         order: Optional[Sequence[int]] = None,
                         collect_rationale: bool = False,
                         prompt_text: Optional[str] = None) -> str:
    """Render an item as a numbered forced-choice question.

    `conditioning`, if given, is prepended verbatim (this is where a tier-1 persona or a
    tier-2 injected distribution goes). With no conditioning the question is neutral —
    that measures the model's own stance. `order` is a permutation of canonical option
    indices giving the DISPLAY order (for position-bias debiasing); default = canonical.

    `prompt_text` overrides the item's canonical wording, used to present a PARAPHRASE while
    keeping the same options and scoring. `collect_rationale` switches the answer instruction
    so the model gives the option number FIRST and then a brief reason — the scorer still reads
    only the leading number (see `split_choice_reason`); the reason is stored as a diagnostic
    and never affects the distribution.
    """
    labels: Sequence[str] = item["scale"]["labels"]
    order = list(range(len(labels))) if order is None else list(order)
    options = "\n".join(f"  {i + 1}. {labels[c]}" for i, c in enumerate(order))
    question = item["prompt_text"] if prompt_text is None else prompt_text
    if collect_rationale:
        instr = (
            f"First answer with the single number (1-{len(labels)}) of the option that best "
            f"matches. Then, after the number, give a brief one-sentence reason."
        )
    else:
        instr = (
            f"Answer with the single number (1-{len(labels)}) of the option that best matches. "
            f"Reply with only the number."
        )
    body = f"{question}\n\n{options}\n\n{instr}"
    return f"{conditioning.strip()}\n\n{body}" if conditioning else body


# ---- answer parsing ------------------------------------------------------------------

def parse_choice(text: str, n_options: int) -> Optional[int]:
    """Parse a model answer into a 0-based option index, or None if unreadable.

    Accepts a leading/standalone integer in [1, n_options]. Returns None (not a guess) on
    anything ambiguous — None answers are dropped, and if *all* answers are None the
    distribution fails closed upstream.
    """
    if text is None:
        return None
    m = re.search(r"-?\d+", text)
    if not m:
        return None
    val = int(m.group())
    if 1 <= val <= n_options:
        return val - 1
    return None


def split_choice_reason(text: str, n_options: int) -> tuple[Optional[int], Optional[str]]:
    """Parse a rationale-mode answer into (option_index, reason_text).

    Scoring reads ONLY the leading option number (same rule as `parse_choice`). The reason is
    the raw answer text, stored verbatim for error analysis — it never affects the distribution.
    """
    idx = parse_choice(text, n_options)
    reason = text.strip() if text and text.strip() else None
    return idx, reason


# ---- elicitation ---------------------------------------------------------------------

def distribution_from_answers(
    answers: Sequence[str], n_options: int, min_valid: int = 1, item_id: str = "?"
) -> np.ndarray:
    """Turn raw model answers into a probability vector — the shared fail-closed core.

    Used by both the synchronous elicitor and the async Inspect solver so the "never
    fabricate a distribution" guarantee lives in exactly one place. Raises
    ElicitationError if fewer than `min_valid` answers parse into a valid option.
    """
    counts: Counter = Counter()
    valid = 0
    for a in answers:
        idx = parse_choice(a, n_options)
        if idx is not None:
            counts[idx] += 1
            valid += 1
    if valid < min_valid:
        raise ElicitationError(
            f"item {item_id}: only {valid}/{len(answers)} answers parsed into a valid "
            f"option (need >= {min_valid}). Refusing to fabricate a distribution."
        )
    return np.array([counts.get(i, 0) for i in range(n_options)], dtype=float) / valid


def distribution_from_indices(indices: Sequence[Optional[int]], n_options: int,
                             min_valid: int = 1, item_id: str = "?") -> np.ndarray:
    """Build a probability vector from already-mapped canonical option indices (None = a
    failed/unparseable answer). Same fail-closed guarantee as distribution_from_answers."""
    counts: Counter = Counter()
    valid = 0
    for idx in indices:
        if idx is not None:
            counts[idx] += 1
            valid += 1
    if valid < min_valid:
        raise ElicitationError(
            f"item {item_id}: only {valid}/{len(indices)} answers parsed into a valid "
            f"option (need >= {min_valid}). Refusing to fabricate a distribution.")
    return np.array([counts.get(i, 0) for i in range(n_options)], dtype=float) / valid


# ---- rich elicitation result (distribution + per-sample diagnostics) -----------------

@dataclass
class SampleRecord:
    """One forced-choice sample and everything needed to audit it after the fact."""
    raw: str
    order: list                     # display order of canonical option indices
    display_choice: Optional[int]   # parsed DISPLAY position (0-based), None if unreadable
    canonical: Optional[int]        # display position mapped back to the canonical option
    paraphrase_id: int              # which wording was shown (0 = canonical)
    reason: Optional[str] = None    # raw rationale text, only when collect_rationale


@dataclass
class Elicitation:
    """The fail-closed distribution plus the diagnostics behind it: parse counts, raw answers,
    option order, paraphrase ids, and rationales. Lets a surprising result be told apart from
    parse loss, a paraphrase artifact, or low-sample noise — the assurance gap the next-
    experiment design flags as the top priority."""
    item_id: str
    n_options: int
    distribution: np.ndarray
    samples: list
    valid: int
    invalid: int

    @property
    def parse_rate(self) -> float:
        total = self.valid + self.invalid
        return self.valid / total if total else 0.0

    def diagnostics(self, include_raw: bool = True) -> dict:
        """A JSON-serialisable per-record block for a run artifact."""
        d = {
            "n_options": self.n_options,
            "valid": self.valid,
            "invalid": self.invalid,
            "parse_rate": round(self.parse_rate, 4),
            "n_paraphrases": len({s.paraphrase_id for s in self.samples}),
        }
        if include_raw:
            d["samples"] = [
                {
                    "raw": s.raw, "order": s.order, "canonical": s.canonical,
                    "paraphrase_id": s.paraphrase_id,
                    **({"reason": s.reason} if s.reason is not None else {}),
                }
                for s in self.samples
            ]
        return d


def _paraphrase_pool(item: Mapping, paraphrases: Optional[Sequence[str]]) -> list:
    """Canonical wording first, then any paraphrases (explicit arg wins over item-carried)."""
    extra = list(paraphrases) if paraphrases is not None else list(item.get("paraphrases", []))
    return [item["prompt_text"], *extra]


def elicit_item(
    elicitor: Elicitor,
    item: Mapping,
    n_samples: int = 16,
    conditioning: Optional[str] = None,
    min_valid: int = 1,
    shuffle: bool = False,
    seed: Optional[int] = None,
    collect_rationale: bool = False,
    paraphrases: Optional[Sequence[str]] = None,
    max_workers: int = 1,
) -> Elicitation:
    """Sample the model `n_samples` times and return a full `Elicitation`.

    Variation across samples comes from option-order (when `shuffle`) and paraphrase rotation
    (when paraphrases are available) — deliberately NOT only temperature, which would make the
    sampler setting the measurement target. With `collect_rationale` the model is asked for the
    option number then a brief reason; only the number is scored, the reason is kept as a
    diagnostic. Fails closed (raises ElicitationError) if too few answers parse.

    `max_workers` > 1 issues the (independent, network-bound) sample calls through a thread pool
    — the per-sample option order and paraphrase are planned FIRST, sequentially, so the RNG draw
    sequence (and therefore the result) is identical to the serial path. Use it only for I/O-bound
    network elicitors; the default (1) keeps the deterministic serial behaviour for simulations.
    """
    labels = item["scale"]["labels"]
    n = len(labels)
    rng = np.random.default_rng(seed)
    pool = _paraphrase_pool(item, paraphrases)
    # plan every sample deterministically (all RNG draws happen here, in order)
    plan = []
    for k in range(n_samples):
        order = list(rng.permutation(n)) if shuffle else list(range(n))
        pid = k % len(pool)
        prompt = forced_choice_prompt(item, conditioning, order,
                                      collect_rationale=collect_rationale, prompt_text=pool[pid])
        plan.append((order, pid, prompt))

    prompts = [p for _, _, p in plan]
    if max_workers > 1 and n_samples > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            raws = list(ex.map(elicitor, prompts))   # ex.map preserves input order
    else:
        raws = [elicitor(p) for p in prompts]

    records: list = []
    indices: list[Optional[int]] = []
    for (order, pid, _), raw in zip(plan, raws):
        disp = parse_choice(raw, n)
        canon = int(order[disp]) if disp is not None else None
        indices.append(canon)
        records.append(SampleRecord(
            raw=raw, order=[int(o) for o in order], display_choice=disp, canonical=canon,
            paraphrase_id=pid, reason=(raw.strip() or None) if collect_rationale else None))
    dist = distribution_from_indices(indices, n, min_valid, item.get("id", "?"))
    valid = sum(1 for c in indices if c is not None)
    return Elicitation(item.get("id", "?"), n, dist, records, valid, len(indices) - valid)


def elicit_item_distribution(
    elicitor: Elicitor,
    item: Mapping,
    n_samples: int = 16,
    conditioning: Optional[str] = None,
    min_valid: int = 1,
    shuffle: bool = False,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Sample the model `n_samples` times and return a probability vector over the options.

    Thin wrapper over `elicit_item` that returns only the distribution (the diagnostics are
    discarded). With `shuffle=True`, each sample presents the options in a random order and the
    chosen DISPLAY position is mapped back to its canonical option — averaging out a model's
    first-option / position bias. Raises ElicitationError if too few answers parse — never a
    uniform fallback.
    """
    return elicit_item(elicitor, item, n_samples, conditioning, min_valid, shuffle, seed).distribution


# ---- logprob scoring: score each option directly, no temperature sampling ------------
#
# Repeated forced-choice sampling turns the *temperature setting* into the measurement target
# (the design's words). Where a provider exposes token logprobs we can do better: ask for the
# first token, read the probability mass on each option NUMBER token, and normalise. The result
# is the model's own option likelihood, not a Monte-Carlo estimate of it. `LogprobFn` is the
# injectable seam — the network backend provides a real one; tests provide a fake.

LogprobFn = Callable[[str, int], np.ndarray]   # (prompt, n_options) -> prob over DISPLAY positions


def option_logprob_vector(top_logprobs: Mapping[str, float], n_options: int) -> np.ndarray:
    """Turn a {token: logprob} map of the FIRST generated token into a probability vector over
    the option numbers 1..n_options. A token counts for option k if, stripped of surrounding
    whitespace/punctuation, it reads as that number (e.g. '2', ' 2', '2.', '(2'). Fails closed
    (raises ElicitationError) if no option-number token is present — never a uniform fallback."""
    probs = np.zeros(n_options, dtype=float)
    found = False
    for i in range(n_options):
        num = str(i + 1)
        best: Optional[float] = None
        for tok, lp in top_logprobs.items():
            if tok.strip().strip(".)(:") == num:
                best = lp if best is None else max(best, lp)
        if best is not None:
            probs[i] = float(np.exp(best))
            found = True
    if not found:
        raise ElicitationError(
            "no option-number token found in logprobs; refusing to fabricate a distribution")
    return probs / probs.sum()


def elicit_item_logprobs(
    logprob_fn: LogprobFn,
    item: Mapping,
    conditioning: Optional[str] = None,
    n_orders: int = 4,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Score an item's options directly from logprobs, averaging over `n_orders` option orderings
    to cancel position bias. `logprob_fn(prompt, n)` returns a probability vector over the DISPLAY
    positions; each is mapped back to canonical options and averaged. No temperature, no sampling."""
    labels = item["scale"]["labels"]
    n = len(labels)
    rng = np.random.default_rng(seed)
    orders = [list(range(n))]
    for _ in range(max(0, n_orders - 1)):
        orders.append([int(x) for x in rng.permutation(n)])
    acc = np.zeros(n, dtype=float)
    for order in orders:
        disp = logprob_fn(forced_choice_prompt(item, conditioning, order), n)
        for disp_pos, canon_idx in enumerate(order):
            acc[canon_idx] += float(disp[disp_pos])
    return acc / acc.sum()


def measure(
    elicitor: Elicitor,
    items: Sequence[Mapping],
    n_samples: int = 16,
    conditioning: Optional[str] = None,
    shuffle: bool = False,
    seed: Optional[int] = None,
) -> dict[str, np.ndarray]:
    """Elicit a distribution for every item. Fails closed on the first unreadable item.
    `shuffle` enables option-order debiasing (on for real models, off for the simulation)."""
    return {
        it["id"]: elicit_item_distribution(elicitor, it, n_samples, conditioning,
                                           shuffle=shuffle, seed=seed)
        for it in items
    }


def measure_detailed(
    elicitor: Elicitor,
    items: Sequence[Mapping],
    n_samples: int = 16,
    conditioning: Optional[str] = None,
    shuffle: bool = False,
    seed: Optional[int] = None,
    collect_rationale: bool = False,
) -> dict[str, "Elicitation"]:
    """Like `measure`, but returns a full `Elicitation` (distribution + diagnostics) per item.

    Each item's own `paraphrases` (if present) are rotated through automatically, so a driver
    gets paraphrase-varied sampling and parse/rationale diagnostics with no extra wiring."""
    return {
        it["id"]: elicit_item(elicitor, it, n_samples, conditioning, shuffle=shuffle, seed=seed,
                              collect_rationale=collect_rationale, paraphrases=it.get("paraphrases"))
        for it in items
    }


# ---- a real backend: local Ollama (no extra deps) ------------------------------------

def ollama_elicitor(
    model: str,
    host: str = "http://localhost:11434",
    temperature: float = 0.8,
    timeout: float = 60.0,
    system: str = SURVEY_SYSTEM,
    max_tokens: int = 16,
) -> Elicitor:
    """Return an Elicitor backed by a local Ollama server's /api/generate endpoint.

    Uses urllib so the instrument has no hard runtime dependency on an LLM client. A
    non-zero temperature is intentional: forced-choice multi-sampling needs sampling
    variance to recover a distribution rather than a single argmax.

    Accepts either a bare Ollama name ("llama3") or an Inspect-style "ollama/llama3" — the
    provider prefix is stripped — so the same MODEL string works for the drivers and the
    Inspect harness (run_all.sh passes one value to both).
    """
    if model.startswith("ollama/"):
        model = model[len("ollama/"):]

    def _call(prompt: str) -> str:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(
            f"{host}/api/generate", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("response", "")

    return _call


def ollama_available(host: str = "http://localhost:11434", timeout: float = 2.0) -> bool:
    """True if a local Ollama server answers — lets callers pick a real vs simulated run."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---- a real backend: OpenRouter (one key -> many frontier + open providers) -----------

try:  # macOS python.org builds lack CA certs for urllib HTTPS; certifi fixes it
    import ssl as _ssl
    import certifi as _certifi
    _SSL_CTX = _ssl.create_default_context(cafile=_certifi.where())
except Exception:
    _SSL_CTX = None


def openrouter_available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def openrouter_elicitor(model: str, temperature: float = 0.8, max_tokens: int = 16,
                        timeout: float = 60.0, system: str = SURVEY_SYSTEM,
                        retries: int = 6, backoff: float = 3.0) -> Elicitor:
    """Elicitor over OpenRouter's chat API — runs drift across many providers (GPT, Claude,
    Gemini, Llama, Qwen, ...) with one key. `model` is an OpenRouter id like 'openai/gpt-4o-mini'
    or 'meta-llama/llama-3.1-8b-instruct'. Needs OPENROUTER_API_KEY. (HTTP pattern adapted from
    the sibling decision-drift project.)"""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set — export it to use OpenRouter models")

    def _call(prompt: str) -> str:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions", data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                    data = json.loads(resp.read())
                return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""
            except urllib.error.HTTPError as e:
                action = classify_http_status(e.code)
                # 429 = rate limit, 5xx = transient: back off and retry (until attempts run out).
                if action == "retry" and attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                # a hard 4xx (e.g. 400 — Qwen-72B's death) is deterministic for this cell: signal
                # skip-and-continue so the driver records a failure entry instead of aborting.
                if action == "skip":
                    raise SkipCellError(
                        f"{model}: HTTP {e.code} (hard client error) — skipping cell",
                        status=e.code, snippet=_http_error_snippet(e)) from e
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise
        return ""

    return _call


# ---- a real backend: OpenRouter option logprobs (direct scoring, no sampling) ---------

def openrouter_logprob_fn(model: str, top_logprobs: int = 20, timeout: float = 60.0,
                          system: str = SURVEY_SYSTEM, retries: int = 6,
                          backoff: float = 3.0) -> LogprobFn:
    """A `LogprobFn` over OpenRouter: requests the first token with `logprobs`, returns the
    probability vector over the displayed option numbers (via `option_logprob_vector`).

    Temperature is 0 and max_tokens is 1 — we read the model's option likelihood directly rather
    than sampling it. Not every model/provider returns logprobs; if the response carries none,
    this fails closed (ElicitationError) so a run never silently degrades to a fabricated vector.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set — export it to use OpenRouter logprobs")

    def _fn(prompt: str, n_options: int) -> np.ndarray:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 1,
            "logprobs": True,
            "top_logprobs": top_logprobs,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions", data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as e:
                action = classify_http_status(e.code)
                if action == "retry" and attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                if action == "skip":
                    raise SkipCellError(
                        f"{model}: HTTP {e.code} (hard client error) — skipping cell",
                        status=e.code, snippet=_http_error_snippet(e)) from e
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise
        else:
            raise ElicitationError(f"{model}: no logprob response after {retries} attempts")
        content = (((data.get("choices") or [{}])[0].get("logprobs") or {}).get("content") or [])
        if not content:
            raise ElicitationError(
                f"{model}: provider returned no token logprobs (model may not expose them)")
        top = {e["token"]: e["logprob"] for e in (content[0].get("top_logprobs") or [])}
        if not top:
            raise ElicitationError(f"{model}: empty top_logprobs in response")
        return option_logprob_vector(top, n_options)

    return _fn


# ---- a real backend: local MLX on Apple Silicon (no server, in-process) ---------------

def mlx_available() -> bool:
    try:
        import mlx_lm  # noqa: F401
        return True
    except Exception:
        return False


def mlx_elicitor(model: str, temperature: float = 0.8, max_tokens: int = 16,
                 system: str = SURVEY_SYSTEM) -> Elicitor:
    """Return an Elicitor backed by mlx-lm running a local open model on Apple Silicon.

    Loads the model once; each call applies the chat template (with the survey-framing
    system message, so the model answers instead of refusing) and samples at non-zero
    temperature (needed so forced-choice multi-sampling recovers a distribution, not an
    argmax). Accepts an HF repo id like 'mlx-community/Llama-3.2-3B-Instruct-4bit'.
    """
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler

    _model, _tok = load(model)
    sampler = make_sampler(temp=temperature)
    has_chat = bool(getattr(_tok, "chat_template", None))

    def _call(prompt: str) -> str:
        if has_chat:
            msgs = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
            text = _tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        else:
            # BASE model (no chat template, e.g. BritLLM/Caernarfon): completion-style cue so
            # it emits an option number instead of continuing prose.
            text = f"{system}\n\n{prompt}\n\nAnswer (the option number only): "
        return generate(_model, _tok, prompt=text, max_tokens=max_tokens,
                        sampler=sampler, verbose=False)

    return _call


def real_elicitor(model: str | None, max_tokens: int = 16):
    """Route a --model string to a real backend, or None when no model is requested.

    'ollama/...' -> Ollama HTTP; anything else (e.g. an HF/MLX repo id) -> local MLX.
    Raises if a model is requested but its backend isn't available, so a real run never
    silently degrades to the simulation. Returns (elicitor, label) or None. `max_tokens`
    is raised by callers that collect a rationale (the bare-number default is 16).
    """
    if not model:
        return None
    if model.startswith("ollama/"):
        if ollama_available():
            return ollama_elicitor(model, max_tokens=max_tokens), f"ollama:{model}"
        raise RuntimeError(f"{model}: no Ollama server on localhost:11434")
    if model.startswith("openrouter/"):
        name = model[len("openrouter/"):]
        return openrouter_elicitor(name, max_tokens=max_tokens), f"openrouter:{name}"
    if mlx_available():
        return mlx_elicitor(model, max_tokens=max_tokens), f"mlx:{model}"
    raise RuntimeError(
        f"{model}: not an 'ollama/...' or 'openrouter/...' name and mlx-lm is unavailable "
        f"(pip install mlx-lm, Apple Silicon only)")


if __name__ == "__main__":
    # self-test with a deterministic fake model (no Ollama needed): a model that answers
    # "3" 70% of the time and "4" 30% of the time, cycling deterministically.
    item = {
        "id": "demo", "prompt_text": "Test?",
        "scale": {"labels": ["a", "b", "c", "d"]},
    }
    seq = iter(["3", "3", "3", "3", "3", "3", "3", "4", "4", "4"] * 2)
    dist = elicit_item_distribution(lambda _p: next(seq), item, n_samples=20)
    print("elicited:", np.round(dist, 3).tolist())

    # fail-closed check: a model that only ever says "banana" must raise, not return uniform.
    try:
        elicit_item_distribution(lambda _p: "banana", item, n_samples=8)
        print("FAIL: should have raised ElicitationError")
    except ElicitationError as e:
        print("fail-closed OK:", str(e)[:60], "...")
