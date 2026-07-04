"""Tests for the elicitor — especially the fail-closed guarantee (no uniform fallback)."""
import json

import numpy as np
import pytest

from alignment.instrument import measure as M

ITEM = {"id": "t", "prompt_text": "Q?", "scale": {"labels": ["a", "b", "c", "d"]}}


def test_parse_choice_valid_and_invalid():
    assert M.parse_choice("3", 4) == 2
    assert M.parse_choice("I choose 1.", 4) == 0
    assert M.parse_choice("banana", 4) is None
    assert M.parse_choice("9", 4) is None  # out of range -> None, not clamped
    assert M.parse_choice(None, 4) is None


def test_distribution_recovers_frequencies():
    # 75% "3", 25% "4"
    seq = iter(["3"] * 6 + ["4"] * 2)
    dist = M.elicit_item_distribution(lambda _p: next(seq), ITEM, n_samples=8)
    assert dist == pytest.approx([0.0, 0.0, 0.75, 0.25])
    assert dist.sum() == pytest.approx(1.0)


def test_fails_closed_on_unreadable_answers():
    # the whole point: garbage must raise, NOT silently become uniform
    with pytest.raises(M.ElicitationError):
        M.elicit_item_distribution(lambda _p: "banana", ITEM, n_samples=8)


def test_fails_closed_respects_min_valid():
    # one valid answer out of many, but min_valid=5 required -> raise
    seq = iter(["3"] + ["nope"] * 9)
    with pytest.raises(M.ElicitationError):
        M.elicit_item_distribution(lambda _p: next(seq), ITEM, n_samples=10, min_valid=5)


def test_shuffle_debiases_first_option_position_bias():
    # a model with PURE position bias: it always picks the first DISPLAYED option ("1"),
    # regardless of meaning — exactly what a small model does.
    always_first = lambda _p: "1"
    # without shuffle, that concentrates entirely on canonical option 0 (the artifact):
    biased = M.elicit_item_distribution(always_first, ITEM, n_samples=40, shuffle=False)
    assert biased[0] == 1.0
    # with shuffle, the first slot lands on each canonical option ~equally -> spread out:
    debiased = M.elicit_item_distribution(always_first, ITEM, n_samples=400, shuffle=True, seed=0)
    assert debiased[0] < 0.45, "debiasing should spread first-option bias off option 0"
    assert max(debiased) < 0.45, f"expected ~uniform, got {debiased}"


def test_shuffle_preserves_a_genuine_preference():
    # a model that genuinely always prefers label 'c' (by content, wherever it appears)
    labels = ITEM["scale"]["labels"]
    def prefers_c(prompt: str) -> str:
        # find which displayed number maps to 'c'
        for line in prompt.splitlines():
            line = line.strip()
            if line[:2] in ("1.", "2.", "3.", "4.") and line.endswith(" c"):
                return line[0]
        return "1"
    dist = M.elicit_item_distribution(prefers_c, ITEM, n_samples=200, shuffle=True, seed=1)
    assert dist[labels.index("c")] > 0.95   # genuine preference survives shuffling


def test_conditioning_is_prepended():
    prompt = M.forced_choice_prompt(ITEM, conditioning="ACT AS X")
    assert prompt.startswith("ACT AS X")
    assert "Q?" in prompt
    # unconditioned prompt does not carry a persona
    assert not M.forced_choice_prompt(ITEM).startswith("ACT AS X")


# ---- HTTP retry/skip/raise decision (pure; no live calls) ----------------------------

@pytest.mark.parametrize("status", [429, 500, 502, 503, 529])
def test_classify_http_status_retry(status):
    # 429 (rate limit) explicitly stays in the RETRY path even though it is a 4xx; 5xx transient.
    assert M.classify_http_status(status) == "retry"


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_classify_http_status_skip_hard_4xx(status):
    # a hard client error (400 = the Qwen-72B death) is deterministic for the cell -> skip.
    assert M.classify_http_status(status) == "skip"


@pytest.mark.parametrize("status", [200, 301, 504, 599])
def test_classify_http_status_raise_unexpected(status):
    # anything that is neither retryable nor a hard 4xx propagates (e.g. a 5xx not in the retry set).
    assert M.classify_http_status(status) == "raise"


def test_classify_429_is_retry_not_skip():
    # the spec's sharp edge: 429 is a 4xx but must NOT be treated as a hard client error.
    assert M.classify_http_status(429) == "retry"
    assert M.classify_http_status(400) == "skip"


# ---- openrouter elicitor: 400 -> SkipCellError, 429 -> retried (mocked transport) -----

class _FakeHTTPError(Exception):
    """Stands in for urllib.error.HTTPError: carries .code and a readable body, no network."""
    def __init__(self, code, body=b""):
        super().__init__(f"HTTP {code}")
        self.code = code
        self._body = body

    def read(self):
        return self._body


def _install_fake_transport(monkeypatch, responder):
    """Patch measure.urllib so the OpenRouter elicitor's _call hits `responder(req)` instead of a
    real socket. `responder` may return a bytes body (success) or raise _FakeHTTPError."""
    monkeypatch.setattr(M.urllib.error, "HTTPError", _FakeHTTPError, raising=True)
    monkeypatch.setattr(M.time, "sleep", lambda *_a, **_k: None)  # no real backoff waits

    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, *a, **k):
        return _Resp(responder(req))

    monkeypatch.setattr(M.urllib.request, "urlopen", fake_urlopen)


def test_openrouter_elicitor_400_raises_skipcell(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def responder(_req):
        raise _FakeHTTPError(400, body=b'{"error":{"message":"provider does not support this model"}}')

    _install_fake_transport(monkeypatch, responder)
    elic = M.openrouter_elicitor("qwen/qwen-2.5-72b-instruct", retries=6)
    with pytest.raises(M.SkipCellError) as ei:
        elic("pick 1 or 2")
    assert ei.value.status == 400
    assert "provider does not support" in ei.value.snippet  # error snippet is captured for the record


def test_openrouter_elicitor_429_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = {"n": 0}

    def responder(_req):
        calls["n"] += 1
        if calls["n"] < 3:                       # 429 twice, then succeed -> proves retry path
            raise _FakeHTTPError(429)
        return json.dumps({"choices": [{"message": {"content": "2"}}]}).encode()

    _install_fake_transport(monkeypatch, responder)
    elic = M.openrouter_elicitor("openai/gpt-4o-mini", retries=6)
    assert elic("pick 1 or 2") == "2"
    assert calls["n"] == 3                        # two retries then success (429 never skips)


def test_openrouter_elicitor_500_still_retries(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = {"n": 0}

    def responder(_req):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _FakeHTTPError(500)
        return json.dumps({"choices": [{"message": {"content": "1"}}]}).encode()

    _install_fake_transport(monkeypatch, responder)
    elic = M.openrouter_elicitor("openai/gpt-4o-mini", retries=6)
    assert elic("q") == "1"
    assert calls["n"] == 2
