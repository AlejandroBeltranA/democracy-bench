"""No-network tests for the LIVE canary orchestration (`alignment.q2_v7.canary`).

Sol's v7.2 code review (R-C1--R-C6) found that a green helper-level suite does not
establish a safe live runner: the defects were all in orchestration, not in the pure
helpers. These tests therefore drive `run_one`/`_evaluate` directly with a fake transport
and a real on-disk store, including the committed HTTP-404 restart case.

NETWORK: none. `FakeTransport` replaces the HTTP seam entirely.
"""
from __future__ import annotations

import json

import pytest

from alignment.q2_v7 import canary as C
from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import ledger as L

MODEL = "qwen/qwen3.5-397b-a17b"
TAG = "alibaba"


class FakeTransport:
    """Returns queued (status, headers, body) triples; records how often it was called."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def post(self, body, headers, timeout=60.0):
        self.calls += 1
        status, hdrs, payload = self._responses.pop(0)
        return status, hdrs, json.dumps(payload) if not isinstance(payload, str) else payload


@pytest.fixture()
def snapshot():
    return E.load_snapshot(C.ROOT / E.SNAPSHOT_PATH)


@pytest.fixture()
def store(tmp_path):
    return L.EnvelopeStore(tmp_path / "run")


def _ledger():
    rec = L.reconcile_prior_spend([], non_reconciled=[])
    return L.V7Ledger(reconciliation=rec)


def _ok_response(content="2", cost=2.3e-05, reasoning_tokens=0):
    return {
        "id": "gen-abc",
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": 53, "completion_tokens": 1, "total_tokens": 54,
                  "cost": cost,
                  "completion_tokens_details": {"reasoning_tokens": reasoning_tokens}},
        "openrouter_metadata": {
            "requested": MODEL, "strategy": "direct", "attempt": 1, "is_byok": False,
            "endpoints": {"total": 1, "available": [
                {"provider": "Alibaba", "model": "qwen/qwen3.5-397b-a17b-20260216",
                 "selected": True}]},
        },
    }


def _router_404():
    return {"error": {"code": 404, "message": "No endpoints available matching your "
                                              "guardrail restrictions and data policy"},
            "openrouter_metadata": {"requested": "deepseek/deepseek-v4-pro",
                                    "strategy": "direct", "attempt": 0, "is_byok": False}}


# --- R-C1: a persisted record is replayed with its REAL verdict ----------------------

def test_persisted_404_stays_a_failure_on_restart(store, snapshot):
    """The committed DeepSeek case: before the fix, existence of a file was reported as
    HTTP 200 / audit ok / reasoning ok, fabricating a capability success."""
    t = FakeTransport((404, {}, _router_404()))
    first = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                      store=store, ledger=_ledger(), transport=t)
    assert first.http_status == 404 and not first.passed

    replay_transport = FakeTransport()          # any call would IndexError
    second = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                       store=store, ledger=_ledger(), transport=replay_transport)
    assert replay_transport.calls == 0, "a persisted draw must never be repaid"
    assert second.reused is True
    assert second.http_status == 404, "replay must carry the REAL status, not 200"
    assert second.passed is False, "a persisted failure must not become a success"


def test_persisted_success_replays_real_verdict(store, snapshot):
    t = FakeTransport((200, {}, _ok_response()))
    first = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                      store=store, ledger=_ledger(), transport=t)
    assert first.passed and first.cost_usd == pytest.approx(2.3e-05)

    replay = FakeTransport()
    second = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                       store=store, ledger=_ledger(), transport=replay)
    assert replay.calls == 0
    assert second.reused and second.passed
    assert second.http_status == 200
    assert second.cost_usd == pytest.approx(2.3e-05)


# --- R-C3: accounting is independent of validity ------------------------------------

def test_paid_but_invalid_response_is_still_persisted_and_booked(store, snapshot):
    """A 200 that fails the provider audit must not escape the ledger."""
    bad = _ok_response()
    bad["openrouter_metadata"]["is_byok"] = True          # audit must fail
    led = _ledger()
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=led, transport=FakeTransport((200, {}, bad)))
    assert not r.passed
    assert r.cost_usd == pytest.approx(2.3e-05)
    assert led.run_usd == pytest.approx(2.3e-05), "invalid-but-paid must still be booked"
    assert store.get(r_draw(MODEL, TAG)) is not None


def r_draw(model, tag):
    return C.planned_draw(model, tag)[1].draw_id


def test_missing_cost_on_a_200_fails_closed_but_persists(store, snapshot):
    resp = _ok_response()
    resp["usage"].pop("cost")
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=_ledger(),
                  transport=FakeTransport((200, {}, resp)))
    assert r.error and "CostAccountingError" in r.error
    assert store.get(r_draw(MODEL, TAG)) is not None, "envelope must be durable first"


def test_router_404_is_unbilled_not_an_accounting_failure(store, snapshot):
    """A router-level rejection provably never reached a provider: book 0.0 explicitly."""
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=_ledger(),
                  transport=FakeTransport((404, {}, _router_404())))
    env = store.get(r_draw(MODEL, TAG))
    assert env.cost_status == "unbilled_rejection"
    assert env.cost_usd == 0.0
    assert not r.passed


# --- S-F2 ---------------------------------------------------------------------------

def test_response_cache_hit_is_rejected(store, snapshot):
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=_ledger(),
                  transport=FakeTransport(
                      (200, {"X-OpenRouter-Cache-Status": "HIT"}, _ok_response())))
    assert r.error and "CacheHitRejected" in r.error
    assert not r.passed


# --- R-C6: the ANSWER must parse under the frozen anchored rule ----------------------

@pytest.mark.parametrize("content,why", [
    ("", "empty"),
    (None, "null"),
    ("I choose 2", "prose before the digit"),
    ("22", "multiple digits"),
    ("5", "out of range"),
    ("two", "non-numeric"),
    ("3", "valid digit but not the requested option"),
])
def test_canary_fails_when_the_answer_does_not_parse(store, snapshot, content, why):
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=_ledger(),
                  transport=FakeTransport((200, {}, _ok_response(content=content))))
    assert not r.parse_ok, f"should reject: {why}"
    assert not r.passed, f"passed despite unparseable content: {why}"


@pytest.mark.parametrize("content", ["2", " 2 ", "2.", "(2)"])
def test_canary_accepts_the_frozen_valid_forms(store, snapshot, content):
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=_ledger(),
                  transport=FakeTransport((200, {}, _ok_response(content=content))))
    assert r.parse_ok and r.passed


# --- R-V7-1 --------------------------------------------------------------------------

def test_positive_reasoning_tokens_fail_the_canary(store, snapshot):
    r = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot,
                  store=store, ledger=_ledger(),
                  transport=FakeTransport(
                      (200, {}, _ok_response(reasoning_tokens=249))))
    assert not r.reasoning_ok and not r.passed


# --- integrity -----------------------------------------------------------------------

def test_request_hash_mismatch_on_replay_raises(store, snapshot, monkeypatch):
    C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
              ledger=_ledger(), transport=FakeTransport((200, {}, _ok_response())))
    draw_id = r_draw(MODEL, TAG)
    raw = json.loads(store.raw_path(draw_id).read_text())
    raw["request_sha256"] = "f" * 64
    store.raw_path(draw_id).write_text(json.dumps(raw))
    with pytest.raises(C.CanaryError, match="request hash"):
        C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                  ledger=_ledger(), transport=FakeTransport())
