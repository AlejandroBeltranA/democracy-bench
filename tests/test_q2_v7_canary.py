"""No-network tests for the LIVE canary orchestration (`alignment.q2_v7.canary`).

Sol's v7.2 code review (R-C1--R-C6) found that a green helper-level suite does not
establish a safe live runner: the defects were all in orchestration, not in the pure
helpers. These tests therefore drive `run_one`/`_evaluate` directly with a fake transport
and a real on-disk store, including the committed HTTP-404 restart case.

NETWORK: none. `FakeTransport` replaces the HTTP seam entirely.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass

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


# =====================================================================================
# PS-5 — canary derived records are bound to the FULL envelope hash and verified on reuse
# =====================================================================================

def _seed(store, snapshot, response=None, status=200, headers=None):
    """One persisted canary draw, written by the real code path."""
    payload = _ok_response() if response is None else response
    result = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                       ledger=_ledger(),
                       transport=FakeTransport((status, headers or {}, payload)))
    draw_id = r_draw(MODEL, TAG)
    return result, draw_id, store.get(draw_id), store.get_derived(draw_id)


def _rewrite_derived(store, draw_id, /, **changes):
    """Overwrite a derived record in place (the store itself refuses overwrites)."""
    obj = json.loads((store.derived_dir / f"{draw_id.replace('#', '__')}.json").read_text())
    obj.update(changes)
    (store.derived_dir / f"{draw_id.replace('#', '__')}.json").write_text(json.dumps(obj))


def test_derived_record_is_bound_to_the_full_envelope_hash(store, snapshot):
    """PS-5 core: the binding is `content_sha256()`, NOT `canonical_sha256(response_body)`."""
    _, draw_id, env, derived = _seed(store, snapshot)
    assert derived is not None
    assert derived.raw_sha256 == env.content_sha256()
    assert derived.raw_sha256 != L.canonical_sha256(env.response_body or {}), (
        "the pre-PS-5 body-only binding must no longer be produced")


@dataclass
class _StubStudyRequest:
    """Minimal `study_run.StudyRequestLike` — only these fields are read by `_replay`."""
    cell_id: str
    probe_id: str
    order_idx: int
    body: dict
    request_sha256: str


def test_canary_pair_round_trips_through_the_study_replay_binding_check(store, snapshot):
    """The canary and study replay must not drift apart again: a real canary
    envelope/derived pair is fed to `study_run._replay`, which is the code that rejects a
    mismatched binding for the study."""
    from alignment.q2_v7 import study_run as SR

    _, draw_id, env, derived = _seed(store, snapshot)
    body, draw = C.planned_draw(MODEL, TAG)
    request = _StubStudyRequest(cell_id="c", probe_id="p", order_idx=0, body=body,
                                request_sha256=draw.request_sha256)

    outcome = SR._replay(request, 0, env, store)       # must NOT raise
    assert outcome.reused is True
    assert outcome.http_status == 200
    assert outcome.parse_ok is True
    assert outcome.failures == ()

    # And the OLD binding is exactly what that check rejects.
    _rewrite_derived(store, draw_id,
                     raw_sha256=L.canonical_sha256(env.response_body or {}))
    with pytest.raises(SR.StudyRunError, match="bound to raw hash"):
        SR._replay(request, 0, env, store)


def test_replay_requires_the_derived_record_to_exist(store, snapshot):
    _, draw_id, env, derived = _seed(store, snapshot)
    (store.derived_dir / f"{draw_id.replace('#', '__')}.json").unlink()

    replay = FakeTransport()                           # any call would IndexError
    with pytest.raises(C.CanaryError, match="no linked derived"):
        C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                  ledger=_ledger(), transport=replay)
    assert replay.calls == 0, "failing closed must never re-pay for the draw"


def test_replay_rejects_a_tampered_derived_record(store, snapshot):
    """The derived record is edited to claim a different raw hash."""
    _seed(store, snapshot)
    draw_id = r_draw(MODEL, TAG)
    _rewrite_derived(store, draw_id, raw_sha256="a" * 64)

    replay = FakeTransport()
    with pytest.raises(C.CanaryError, match="bound to raw hash"):
        C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                  ledger=_ledger(), transport=replay)
    assert replay.calls == 0


def test_replay_rejects_a_tampered_envelope(store, snapshot):
    """The envelope is edited (leaving the request hash intact) so it no longer hashes to
    the value its derived record is bound to."""
    _seed(store, snapshot)
    draw_id = r_draw(MODEL, TAG)
    path = store.raw_path(draw_id)
    raw = json.loads(path.read_text())
    raw["cost_usd"] = 0.0                              # cheaper paid record, same request
    path.write_text(json.dumps(raw))

    replay = FakeTransport()
    with pytest.raises(C.CanaryError, match="bound to raw hash"):
        C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                  ledger=_ledger(), transport=replay)
    assert replay.calls == 0


def test_replay_rejects_a_derived_record_filed_under_another_draw(store, snapshot):
    _seed(store, snapshot)
    draw_id = r_draw(MODEL, TAG)
    _rewrite_derived(store, draw_id, draw_id="deadbeef#0")
    with pytest.raises(C.CanaryError, match="filename/content mismatch"):
        C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                  ledger=_ledger(), transport=FakeTransport())


def test_a_persisted_invalid_verdict_stays_invalid_on_replay(store, snapshot):
    """A record whose derived verdict says INVALID must not be resurrected by a re-parse
    that happens to succeed."""
    result, draw_id, env, derived = _seed(store, snapshot)
    assert result.passed and derived.valid
    _rewrite_derived(store, draw_id, valid=False, excluded_from_estimands=True,
                     failures=["audit:provider_mismatch"])

    replay = FakeTransport()
    second = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                       ledger=_ledger(), transport=replay)
    assert replay.calls == 0
    assert second.reused is True
    assert second.parse_ok is True, "the re-parse itself still succeeds..."
    assert second.passed is False, "...but the persisted invalid verdict wins"
    assert "excluded_by_derived_record" in (second.error or "")
    assert "audit:provider_mismatch" in (second.error or "")


def test_conforming_pair_replays_cleanly_with_zero_transport_calls(store, snapshot):
    first, draw_id, env, derived = _seed(store, snapshot)
    assert first.passed and not first.reused

    replay = FakeTransport()
    second = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                       ledger=_ledger(), transport=replay)
    assert replay.calls == 0, "a persisted draw must never be repaid"
    assert second.reused and second.passed
    assert second.http_status == 200
    assert second.cost_usd == pytest.approx(2.3e-05)
    # nothing was mutated by the replay
    assert store.get_derived(draw_id) == derived
    assert store.get(draw_id) == env


def test_a_persisted_failure_keeps_its_failing_derived_record_on_replay(store, snapshot):
    """The committed DeepSeek 404 shape: the derived record written on the paid attempt is
    itself invalid, and replay honours it."""
    _, draw_id, env, derived = _seed(store, snapshot, response=_router_404(), status=404)
    assert derived is not None and derived.valid is False
    assert derived.raw_sha256 == env.content_sha256()

    second = C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=store,
                       ledger=_ledger(), transport=FakeTransport())
    assert second.reused and not second.passed and second.http_status == 404


# --- legacy committed artifacts (written under the OLD binding) ----------------------

LEGACY_DIRS = [
    ("q2_stage2_v7_canary", "no derived records at all", "no linked derived"),
    ("q2_stage2_v7_canary_postprivacy", "derived bound to the response body only",
     "bound to raw hash"),
]


@pytest.mark.parametrize("name,why,match", LEGACY_DIRS,
                         ids=[d[0] for d in LEGACY_DIRS])
def test_legacy_canary_artifacts_are_not_usable_as_a_passing_reuse(tmp_path, snapshot,
                                                                   name, why, match):
    """The committed pre-PS-5 records are immutable audit history. They are never deleted
    or rewritten, but their binding cannot be verified, so replaying them FAILS CLOSED and
    the operator must re-authorize a fresh paid canary ({why})."""
    src = C.ROOT / "out" / name
    if not src.exists():                               # pragma: no cover - artifact removed
        pytest.skip(f"legacy artifact dir {name} is not present")
    work = tmp_path / name
    shutil.copytree(src, work)
    legacy = L.EnvelopeStore(work)

    # The committed draw identities still reproduce exactly from the frozen prompt.
    assert legacy.get(C.planned_draw(MODEL, TAG)[1].draw_id) is not None

    replay = FakeTransport()
    with pytest.raises(C.CanaryError, match=match):
        C.run_one(model=MODEL, tag=TAG, key="k", snapshot=snapshot, store=legacy,
                  ledger=_ledger(), transport=replay)
    assert replay.calls == 0, "a fail-closed legacy replay must not re-pay"

    # The originals are untouched by this test.
    assert (src / "raw").exists()
