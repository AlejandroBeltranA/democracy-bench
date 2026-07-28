"""No-network tests for the Q2 Stage-2 v7.2 study runner (`alignment.q2_v7.study_run`).

The v7.2 code review's lesson is that a green helper-level suite does not establish a safe
live runner: every defect it found (R-C1--R-C6) was in ORCHESTRATION. These tests therefore
drive the real stage functions against a real on-disk `EnvelopeStore` and a fake transport,
asserting the frozen counts, the deterministic walk, smoke reuse, the parse gates, the hard
stop, restart, and the manifest binding.

NETWORK: none. `FakeTransport` replaces the HTTP seam entirely; the pinned tokenizer is an
injected word counter; sleeps and the clock are injected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest

from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import identity as I
from alignment.q2_v7 import ledger as L
from alignment.q2_v7 import study_run as S

MODEL = "qwen/qwen3.5-397b-a17b"
SEQUENCE = G.FALLBACK_SEQUENCES[MODEL]          # alibaba -> digitalocean -> streamlake -> parasail/fp8
PRIMARY_TAG = SEQUENCE[0]
KEY = "test-key-not-a-real-credential"

PROBE_IDS = [
    "pol_ai_due_process", "pol_surveillance", "pol_ai_predictive_policing",
    "pol_ai_nhs_triage", "pol_protest", "pol_speech", "pol_privacy", "pol_detention",
    "pol_asylum", "pol_press", "pol_assembly", "pol_data",
]


# =======================================================================================
# Fakes — the transport, the renderer, and the tokenizer
# =======================================================================================

class FakeTransport:
    """Returns queued or scripted (status, headers, body) triples and counts every call."""

    def __init__(self, default=None, script=None):
        self.default = default
        self.script = list(script or [])
        self.calls = 0
        self.bodies: list[dict] = []
        self.headers: list[dict] = []
        self.by_tag: dict[str, int] = {}

    def post(self, body, headers, timeout=60.0):
        self.calls += 1
        self.bodies.append(json.loads(json.dumps(body)))
        self.headers.append(dict(headers))
        tag = (body.get("provider") or {}).get("only", ["?"])[0]
        self.by_tag[tag] = self.by_tag.get(tag, 0) + 1
        if self.script:
            item = self.script.pop(0)
        elif callable(self.default):
            item = self.default(body, self.calls)
        else:
            item = self.default
        status, hdrs, payload = item
        return status, hdrs, json.dumps(payload)


@dataclass(frozen=True)
class FakeRequest:
    """Mirrors the frozen `study_render.StudyRequest` contract."""
    cell_id: str
    probe_id: str
    order_idx: int
    body: dict
    request_sha256: str
    rendered: G.RenderedRequest


def _make_request(model: str, tag: str, cell_id: str, probe_id: str,
                  order_idx: int) -> FakeRequest:
    messages = [
        {"role": "system", "content": f"cell={cell_id}"},
        {"role": "user", "content": f"probe={probe_id} order={order_idx}\nPick one option."},
    ]
    body = E.build_sampling_request(model, tag, messages)
    sha = E.canonical_request_sha256(body)
    rendered = G.render_request(cell_id, probe_id, order_idx, body)
    assert rendered.request_sha256 == sha
    return FakeRequest(cell_id=cell_id, probe_id=probe_id, order_idx=order_idx, body=body,
                       request_sha256=sha, rendered=rendered)


def fake_study_grid(model: str = MODEL, tag: str = PRIMARY_TAG,
                    probe_ids=tuple(PROBE_IDS)) -> list[FakeRequest]:
    """528 requests over the frozen 11 cells x 12 probes x 4 orders."""
    return [_make_request(model, tag, coord.cell_id, coord.probe_id, coord.order_idx)
            for coord in I.enumerate_coordinates(list(probe_ids))]


def fake_smoke_grid(model: str = MODEL, tag: str = PRIMARY_TAG) -> list[FakeRequest]:
    """The 48 frozen smoke coordinates, rendered IDENTICALLY to their place in the 528."""
    return [_make_request(model, tag, coord.cell_id, coord.probe_id, coord.order_idx)
            for coord in I.enumerate_smoke_coordinates()]


def word_tokenizer(text: str) -> int:
    return max(1, len(text.split()))


@lru_cache(maxsize=1)
def real_snapshot() -> E.Snapshot:
    return E.load_snapshot(S.ROOT / E.SNAPSHOT_PATH)


@pytest.fixture()
def snapshot():
    return real_snapshot()


@pytest.fixture()
def run_dir(tmp_path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    return d


def empty_ledger(hard_stop: float = L.HARD_STOP_USD, manifest=None) -> L.V7Ledger:
    rec = L.ReconciliationResult(reconciled_usd=0.0, record_count=0)
    return L.V7Ledger(reconciliation=rec, hard_stop_usd=hard_stop, manifest=manifest)


# =======================================================================================
# Canned wire responses
# =======================================================================================

def ok_body(content="2", cost=1e-06, reasoning_tokens=0, completion_tokens=1,
            tag=PRIMARY_TAG, model=MODEL, snapshot=None):
    provider = "Alibaba"
    upstream = "qwen/qwen3.5-397b-a17b-20260216"
    if snapshot is not None:
        cand = snapshot.candidate(model, tag)
        provider, upstream = cand.provider_name, cand.upstream_model
    return {
        "id": f"gen-{tag}",
        "model": model,
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": 53, "completion_tokens": completion_tokens,
                  "total_tokens": 53 + completion_tokens, "cost": cost,
                  "completion_tokens_details": {"reasoning_tokens": reasoning_tokens}},
        "openrouter_metadata": {
            "requested": model, "strategy": "direct", "attempt": 1, "is_byok": False,
            "summary": f"available=1, selected={provider}",
            "endpoints": {"total": 1, "available": [
                {"provider": provider, "model": upstream, "selected": True}]},
        },
    }


def ok(tag=PRIMARY_TAG, snapshot=None, **kw):
    return (200, {}, ok_body(tag=tag, snapshot=snapshot, **kw))


def hard_404(tag=PRIMARY_TAG):
    return (404, {}, {"error": {"code": 404, "message": "no endpoints matching data policy"},
                      "openrouter_metadata": {"requested": MODEL, "strategy": "direct",
                                              "attempt": 0, "is_byok": False}})


def rate_limited(retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return (429, headers, {"error": {"code": 429, "message": "rate limited"}})


def byok_body(tag=PRIMARY_TAG, snapshot=None):
    body = ok_body(tag=tag, snapshot=snapshot)
    body["openrouter_metadata"]["is_byok"] = True
    return (200, {}, body)


def _walk_kwargs(snapshot, store, ledger, transport, **overrides):
    kwargs = dict(
        model=MODEL, key=KEY, snapshot=snapshot, store=store, ledger=ledger,
        transport=transport, requests_for=lambda tag: fake_study_grid(tag=tag),
        tokenizer=word_tokenizer, retry_reserve_usd=0.01,
        observed_billed_completion_tokens=(), sleep=lambda _s: None,
        clock=_stub_clock(), max_attempts=G.MAX_ATTEMPTS)
    kwargs.update(overrides)
    return kwargs


def _stub_clock():
    counter = {"t": 0.0}

    def clock() -> float:
        counter["t"] += 0.001
        return counter["t"]

    return clock


# =======================================================================================
# 1. The deterministic endpoint promotion walk
# =======================================================================================

def test_walk_promotes_the_first_passing_candidate_and_never_probes_a_later_one(
        snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport))
    assert result.promoted_tag == PRIMARY_TAG
    assert result.probed_tags == (PRIMARY_TAG,)          # no later endpoint was probed at all
    assert transport.by_tag == {PRIMARY_TAG: 1}
    assert not result.excluded


def test_walk_probes_candidates_in_the_frozen_sequence_order(snapshot, run_dir):
    """The second candidate is reached only after the first fails, and no later one is."""
    transport = FakeTransport(default=lambda body, n: (
        hard_404() if (body["provider"]["only"][0] == SEQUENCE[0])
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport))
    assert result.probed_tags == (SEQUENCE[0], SEQUENCE[1])
    assert result.promoted_tag == SEQUENCE[1]
    assert SEQUENCE[2] not in transport.by_tag


def test_walk_advances_past_a_hard_4xx_immediately_without_retrying(snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: (
        hard_404() if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport))
    assert transport.by_tag[SEQUENCE[0]] == 1           # one attempt, no retries
    first = result.probes[0]
    assert first.terminal_reason == "hard_4xx"
    assert first.attempts_made == 1


def test_walk_advances_past_a_429_only_after_the_retry_policy_is_exhausted(snapshot, run_dir):
    """C3: five attempts = one initial attempt plus four retries."""
    sleeps: list[float] = []
    transport = FakeTransport(default=lambda body, n: (
        rate_limited() if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport, sleep=sleeps.append))
    assert transport.by_tag[SEQUENCE[0]] == G.MAX_ATTEMPTS == 5
    assert sleeps == [2.0, 4.0, 8.0, 16.0]             # base 2 s, cap 60 s, four retries
    assert result.probes[0].terminal_reason == "attempts_exhausted"
    assert result.promoted_tag == SEQUENCE[1]


def test_walk_stops_retrying_a_429_when_retry_after_exceeds_the_window(snapshot, run_dir):
    """C3: `Retry-After` is honoured only when the wait fits the 10-minute window."""
    sleeps: list[float] = []
    transport = FakeTransport(default=lambda body, n: (
        rate_limited(retry_after=10_000) if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport, sleep=sleeps.append))
    assert transport.by_tag[SEQUENCE[0]] == 1          # no further request was sent
    assert sleeps == []                                 # and nothing slept past the window
    assert result.probes[0].terminal_reason == "window_exhausted"


def test_walk_rejects_byok_as_an_availability_failure_and_never_retries_it(snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: (
        byok_body(SEQUENCE[0], snapshot) if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport))
    assert transport.by_tag[SEQUENCE[0]] == 1
    assert result.probes[0].terminal_reason == "byok"
    assert any("is_byok" in f for f in result.decision.attempts[0].envelope_failures)
    assert result.promoted_tag == SEQUENCE[1]


def test_walk_fails_a_candidate_that_returns_positive_reasoning_tokens(snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: (
        ok(SEQUENCE[0], snapshot, reasoning_tokens=7)
        if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport))
    failures = result.decision.attempts[0].reasoning_failures
    assert any("reasoning_tokens" in f for f in failures)
    assert result.promoted_tag == SEQUENCE[1]


def test_walk_fails_a_candidate_whose_reply_does_not_parse(snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: (
        ok(SEQUENCE[0], snapshot, content="I choose 3")
        if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot)))
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport))
    assert any("parsed_leading_digit" in f
               for f in result.decision.attempts[0].reasoning_failures)
    assert result.promoted_tag == SEQUENCE[1]


def test_walk_fails_a_candidate_whose_full_grid_projection_exceeds_the_stop(snapshot, run_dir):
    """Criterion (c): the projection, not a single-call multiplication, decides."""
    transport = FakeTransport(default=lambda body, n: ok(body["provider"]["only"][0],
                                                         snapshot))

    def fat_tokenizer(text: str) -> int:
        return 100_000

    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport, tokenizer=fat_tokenizer))
    assert result.excluded
    assert all(a.cost_failure and "exceeds" in a.cost_failure for a in result.decision.attempts)
    assert transport.by_tag[SEQUENCE[-1]] == 1          # every candidate was still walked


def test_no_candidate_passing_is_an_exclusion_with_no_reduced_design_substitute(
        snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: hard_404())
    result = S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                       transport, run_dir=run_dir))
    assert result.excluded
    assert result.promoted_tag is None
    assert result.decision.substitute is None
    record = json.loads(S.walk_record_path(run_dir, MODEL).read_text())
    assert record["reduced_cell_substitute"] is None
    assert record["reduced_s_substitute"] is None
    assert record["reduced_designs_retired"] is True
    with pytest.raises(G.SpecViolation):
        G.reduced_design_substitute()
    # And no later stage can resurrect the model.
    with pytest.raises(S.CapabilityExclusion):
        S.load_promotion(run_dir, MODEL)


def test_walk_persists_and_books_every_returned_attempt(snapshot, run_dir):
    """R-C3: each attempt gets its own draw identity, envelope, derived record and booking."""
    store = S.walk_store(run_dir)
    ledger = empty_ledger()
    transport = FakeTransport(default=lambda body, n: (
        rate_limited() if body["provider"]["only"][0] == SEQUENCE[0]
        else ok(body["provider"]["only"][0], snapshot, cost=3e-06)))
    S.run_walk(**_walk_kwargs(snapshot, store, ledger, transport))
    # five 429 attempts (no cost) + one successful probe (cost booked)
    assert len(store.envelopes()) == G.MAX_ATTEMPTS + 1
    assert len(store.derived_records()) == G.MAX_ATTEMPTS + 1
    assert ledger.run_usd == pytest.approx(3e-06)


def test_walk_sends_the_exact_frozen_envelope(snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(), transport))
    body = transport.bodies[0]
    assert body["reasoning"] == {"effort": "none"}
    assert body["max_tokens"] == 4
    assert body["temperature"] == 1.0 and body["top_p"] == 1.0
    assert "seed" not in body and "stop" not in body and "logprobs" not in body
    assert body["provider"] == {"only": [PRIMARY_TAG], "allow_fallbacks": False,
                                "require_parameters": True}
    assert transport.headers[0]["X-OpenRouter-Cache"] == "false"


def test_walk_probe_is_synthetic_and_carries_no_study_content(snapshot, run_dir):
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(), transport))
    contents = " ".join(m["content"] for m in transport.bodies[0]["messages"]).lower()
    for banned in ("rights", "survey", "united kingdom", "policy", "protest"):
        assert banned not in contents


def test_walk_refuses_a_model_outside_the_frozen_panel(snapshot, run_dir):
    with pytest.raises(G.SpecViolation):
        S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), empty_ledger(),
                                  FakeTransport(default=hard_404()), model="acme/whatever"))


def test_panel_order_is_frozen_qwen_then_deepseek():
    assert G.PANEL_ORDER == ("qwen/qwen3.5-397b-a17b", "deepseek/deepseek-v4-pro")


# =======================================================================================
# 2. The full-grid projection artifact
# =======================================================================================

def test_projection_covers_all_528_requests_and_counts_the_smoke_once(snapshot, run_dir):
    requests = fake_study_grid()
    candidate = S.gate_candidates(snapshot, MODEL)[f"{MODEL}::{PRIMARY_TAG}"]
    projection = S.build_projection(model=MODEL, candidate=candidate, requests=requests,
                                    tokenizer=word_tokenizer, ledger=empty_ledger(),
                                    retry_reserve_usd=0.05,
                                    observed_billed_completion_tokens=[3])
    assert projection.n_requests == 528
    assert projection.total_draws == 13_200
    assert projection.completion_allowance == 4          # never below the frozen max_tokens
    assert projection.smoke_draws_inside_grid == 240 and projection.smoke_counted_once
    assert projection.fits

    path = S.write_projection(run_dir, projection)
    artifact = S.read_projection(path)
    assert len(artifact["rows"]) == 528
    assert len({r["request_sha256"] for r in artifact["rows"]}) == 528
    for key in ("completion_allowance", "reconciled_prior_gate_spend", "retry_reserve",
                "total", "endpoint_prices", "projected_input_tokens_total"):
        assert key in artifact
    # An artifact that decided a promotion is immutable evidence.
    assert S.write_projection(run_dir, projection) == path


def test_projection_uses_the_observed_canary_completion_allowance(snapshot):
    candidate = S.gate_candidates(snapshot, MODEL)[f"{MODEL}::{PRIMARY_TAG}"]
    projection = S.build_projection(model=MODEL, candidate=candidate,
                                    requests=fake_study_grid(), tokenizer=word_tokenizer,
                                    ledger=empty_ledger(), retry_reserve_usd=0.0,
                                    observed_billed_completion_tokens=[2, 9, 4])
    assert projection.completion_allowance == 9


def test_worst_case_lookup_refuses_an_unpriced_request(snapshot):
    candidate = S.gate_candidates(snapshot, MODEL)[f"{MODEL}::{PRIMARY_TAG}"]
    projection = S.build_projection(model=MODEL, candidate=candidate,
                                    requests=fake_study_grid(), tokenizer=word_tokenizer,
                                    ledger=empty_ledger(), retry_reserve_usd=0.0)
    lookup = S.worst_case_lookup(projection)
    assert lookup(projection.rows[0].request_sha256) > 0
    with pytest.raises(S.StudyRunError):
        lookup("0" * 64)


# =======================================================================================
# 3. Frozen counts
# =======================================================================================

def test_the_grid_is_exactly_528_unique_coordinates():
    requests = fake_study_grid()
    assert len(requests) == 528
    assert len({r.request_sha256 for r in requests}) == 528
    assert len({(r.cell_id, r.probe_id, r.order_idx) for r in requests}) == 528


def test_counts_are_exactly_13200_240_and_12960():
    requests = fake_study_grid()
    full = S.plan_full_draws(requests)
    smoke = S.plan_smoke_draws(fake_smoke_grid())
    assert len(full) == 13_200
    assert len(smoke) == 240
    smoke_ids = {I.draw_id(r.request_sha256, i) for r, i in smoke}
    full_ids = {I.draw_id(r.request_sha256, i) for r, i in full}
    assert len(full_ids) == 13_200
    assert smoke_ids < full_ids                       # the smoke is INSIDE the grid
    assert len(full_ids - smoke_ids) == 12_960


def test_draw_identity_excludes_the_stage_label():
    """R-V7-7: the smoke/full stage label never enters identity, which is what makes the
    240 smoke draws the first five of the 25 rather than a second payment."""
    smoke = fake_smoke_grid()[0]
    match = [r for r in fake_study_grid()
             if (r.cell_id, r.probe_id, r.order_idx) ==
             (smoke.cell_id, smoke.probe_id, smoke.order_idx)]
    assert len(match) == 1
    assert match[0].request_sha256 == smoke.request_sha256
    for index in range(I.SMOKE_DRAWS_PER_COORDINATE):
        assert I.draw_id(smoke.request_sha256, index) == I.draw_id(match[0].request_sha256,
                                                                   index)


def test_plans_refuse_a_partial_grid():
    with pytest.raises(I.CountMismatch):
        S.plan_full_draws(fake_study_grid()[:527])
    with pytest.raises(I.CountMismatch):
        S.plan_smoke_draws(fake_smoke_grid()[:47])


# =======================================================================================
# 4. Manifest binding
# =======================================================================================

@pytest.fixture()
def binding():
    return S.DesignBinding(
        design_sha256="a" * 64, item_bank_sha256="b" * 64, payload_sha256="c" * 64,
        guard_sha256="d" * 64, runner_revision="test-rev")


def test_manifest_binds_13200_identities_528_hashes_and_the_snapshot(snapshot, binding):
    requests = fake_study_grid()
    manifest = S.build_study_manifest(model=MODEL, endpoint_tag=PRIMARY_TAG,
                                      requests=requests, probe_ids=PROBE_IDS,
                                      snapshot_sha256=snapshot.sha256, binding=binding)
    assert manifest.n_draws == 13_200
    assert manifest.n_coordinates == 528
    assert set(manifest.request_sha256s) == {r.request_sha256 for r in requests}
    assert manifest.body["endpoint_snapshot_sha256"] == snapshot.sha256
    assert manifest.body["endpoint_slug"] == PRIMARY_TAG
    assert manifest.body["runner_revision"] == "test-rev"
    assert manifest.body["design_sha256"] == "a" * 64
    assert manifest.body["item_bank_sha256"] == "b" * 64


def test_manifest_resumes_only_on_byte_identical_bytes(run_dir, snapshot, binding):
    requests = fake_study_grid()
    manifest = S.build_study_manifest(model=MODEL, endpoint_tag=PRIMARY_TAG,
                                      requests=requests, probe_ids=PROBE_IDS,
                                      snapshot_sha256=snapshot.sha256, binding=binding)
    first = S.write_study_manifest(run_dir, MODEL, manifest)
    assert first.created and first.may_run
    again = S.write_study_manifest(run_dir, MODEL, manifest)
    assert again.resumed and not again.created


def test_manifest_mismatch_refuses_to_resume(run_dir, snapshot, binding):
    manifest = S.build_study_manifest(model=MODEL, endpoint_tag=PRIMARY_TAG,
                                      requests=fake_study_grid(), probe_ids=PROBE_IDS,
                                      snapshot_sha256=snapshot.sha256, binding=binding)
    S.write_study_manifest(run_dir, MODEL, manifest)
    other = S.build_study_manifest(
        model=MODEL, endpoint_tag=SEQUENCE[1],
        requests=fake_study_grid(tag=SEQUENCE[1]), probe_ids=PROBE_IDS,
        snapshot_sha256=snapshot.sha256, binding=binding)
    with pytest.raises(I.ManifestMismatch):
        S.write_study_manifest(run_dir, MODEL, other)
    # The stored manifest is never rewritten or repaired.
    assert S.manifest_path(run_dir, MODEL).read_bytes() == manifest.raw


def test_manifest_refuses_a_grid_that_is_not_528_coordinates(snapshot, binding):
    with pytest.raises(I.CountMismatch):
        S.build_study_manifest(model=MODEL, endpoint_tag=PRIMARY_TAG,
                               requests=fake_study_grid()[:500], probe_ids=PROBE_IDS,
                               snapshot_sha256=snapshot.sha256, binding=binding)


def test_default_binding_is_deterministic():
    assert S.default_binding() == S.default_binding()


# =======================================================================================
# 5. The smoke: execution, reuse, and the promotion gate
# =======================================================================================

def _worst_case(_sha: str) -> float:
    return 1e-05


def _run_smoke(run_dir, transport, ledger=None, requests=None, snapshot=None, **kw):
    return S.run_smoke(model=MODEL, tag=PRIMARY_TAG, key=KEY,
                       smoke_requests=requests if requests is not None else fake_smoke_grid(),
                       store=S.study_store(run_dir), ledger=ledger or empty_ledger(),
                       transport=transport, worst_case_usd=_worst_case,
                       snapshot=snapshot if snapshot is not None else real_snapshot(),
                       sleep=lambda _s: None, clock=_stub_clock(), **kw)


def test_smoke_executes_exactly_240_draws(run_dir, snapshot):
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    report = _run_smoke(run_dir, transport)
    assert report.run.n_attempted == 240
    assert report.run.n_sent == 240 and report.run.n_reused == 0
    assert transport.calls == 240
    assert report.promoted
    assert len({o.draw_id for o in report.run.outcomes}) == 240


def test_smoke_draws_are_reused_and_never_repaid(run_dir, snapshot):
    first = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    _run_smoke(run_dir, first)
    second = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    report = _run_smoke(run_dir, second)
    assert second.calls == 0                          # transport untouched for persisted draws
    assert report.run.n_reused == 240 and report.run.n_sent == 0
    assert all(o.reused for o in report.run.outcomes)
    assert report.promoted


def test_a_persisted_failure_stays_a_failure_on_restart(run_dir, snapshot):
    """R-C1: the existence of a file is never evidence of success."""
    def script(body, n):
        return hard_404() if n == 1 else ok(PRIMARY_TAG, snapshot)

    first = FakeTransport(default=script)
    _run_smoke(run_dir, first)
    second = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    report = _run_smoke(run_dir, second)
    assert second.calls == 0
    failed = [o for o in report.run.outcomes if o.http_status != 200]
    assert len(failed) == 1
    assert failed[0].reused and not failed[0].parse_ok
    assert "http_error" in failed[0].failures


def test_replay_refuses_an_envelope_whose_request_hash_moved(run_dir, snapshot):
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    _run_smoke(run_dir, transport)
    smoke = fake_smoke_grid()
    tampered = [FakeRequest(cell_id=smoke[0].cell_id, probe_id=smoke[0].probe_id,
                            order_idx=smoke[0].order_idx, body=smoke[0].body,
                            request_sha256="f" * 64, rendered=smoke[0].rendered),
                *smoke[1:]]
    store = S.study_store(run_dir)
    envelope = store.get(I.draw_id(smoke[0].request_sha256, 0))
    with pytest.raises(S.StudyRunError):
        S._replay(tampered[0], 0, envelope, store)


def test_smoke_gate_rejects_a_coordinate_below_four_of_five(run_dir, snapshot):
    """Every coordinate must reach >= 4/5 parseable."""
    target = fake_smoke_grid()[0]

    def script(body, n):
        sha = E.canonical_request_sha256(body)
        if sha == target.request_sha256 and n % 5 in (1, 2):
            return ok(PRIMARY_TAG, snapshot, content="I pick three")
        return ok(PRIMARY_TAG, snapshot)

    report = _run_smoke(run_dir, FakeTransport(default=script))
    assert not report.promoted
    assert any("parseable" in f for f in report.gate.failures)
    with pytest.raises(S.MeasurementValidityFailure):
        S.require_smoke_promotion(report)


def test_smoke_gate_rejects_a_coordinate_with_no_parseable_reply(run_dir, snapshot):
    target = fake_smoke_grid()[3]

    def script(body, n):
        sha = E.canonical_request_sha256(body)
        if sha == target.request_sha256:
            return ok(PRIMARY_TAG, snapshot, content="")
        return ok(PRIMARY_TAG, snapshot)

    report = _run_smoke(run_dir, FakeTransport(default=script))
    assert not report.promoted
    assert any("no parseable reply" in f for f in report.gate.failures)


def test_smoke_gate_rejects_an_overall_rate_of_094():
    """0.94 overall (226/240) fails the frozen 0.95 floor even with every coordinate >= 4/5."""
    outcomes = []
    smoke = fake_smoke_grid()
    unparseable_left = 14
    for request in smoke:
        for index in range(5):
            bad = index == 0 and unparseable_left > 0
            if bad:
                unparseable_left -= 1
            outcomes.append(S.DrawOutcome(
                cell_id=request.cell_id, probe_id=request.probe_id,
                order_idx=request.order_idx, draw_index=index,
                draw_id=I.draw_id(request.request_sha256, index),
                request_sha256=request.request_sha256, http_status=200,
                parse_ok=not bad, parse_reason="not_anchored" if bad else "ok",
                choice=None if bad else 1, cost_usd=1e-06, reused=False,
                failures=("parse:not_anchored",) if bad else ()))
    report = S.smoke_promotion_gate(outcomes)
    assert report.overall_parse_rate == pytest.approx(226 / 240)
    assert report.overall_parse_rate < 0.95
    assert not report.promoted
    assert any("overall smoke parse rate" in f for f in report.failures)
    # ...and every coordinate still cleared 4/5, so ONLY the overall rule rejected it.
    assert all(n >= 4 for n in report.parseable_by_coordinate.values())


def test_smoke_gate_rejects_a_short_run(run_dir):
    assert not S.smoke_promotion_gate([]).promoted


def test_smoke_never_emits_a_headline(run_dir, snapshot):
    report = _run_smoke(run_dir, FakeTransport(default=lambda body, n: ok(PRIMARY_TAG,
                                                                          snapshot)))
    assert report.emit_headline is False


def test_smoke_writes_linked_derived_records(run_dir, snapshot):
    _run_smoke(run_dir, FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot)))
    store = S.study_store(run_dir)
    assert len(store.envelopes()) == 240
    derived = store.derived_records()
    assert len(derived) == 240
    for record in derived:
        assert store.get(record.draw_id) is not None
        assert record.raw_sha256 == store.get(record.draw_id).content_sha256()
    assert len(L.estimand_eligible_draw_ids(store)) == 240


def test_every_study_draw_carries_the_c1_provider_audit(run_dir, snapshot):
    """The frozen proof is written for "a study response", so it runs on EVERY draw — not
    only on the handful of synthetic promotion-walk probes."""
    def wrong_provider(body, n):
        response = ok_body(tag=PRIMARY_TAG, snapshot=snapshot)
        response["openrouter_metadata"]["endpoints"]["available"][0]["provider"] = "Impostor"
        return (200, {}, response)

    report = _run_smoke(run_dir, FakeTransport(default=wrong_provider))
    assert not report.promoted
    outcome = report.run.outcomes[0]
    assert outcome.http_status == 200                    # the wire was fine...
    assert any("display_name_mismatch" in f for f in outcome.failures)   # ...routing was not
    assert L.estimand_eligible_draw_ids(S.study_store(run_dir)) == []


def test_the_per_draw_audit_fails_closed_without_the_committed_snapshot(snapshot):
    """No snapshot means no bound proof, and an unprovable draw is never estimand-eligible."""
    good = ok_body(tag=PRIMARY_TAG, snapshot=snapshot)
    assert S.audit_failures(good, model=MODEL, tag=PRIMARY_TAG, snapshot=snapshot) == ()
    assert S.audit_failures(good, model=MODEL, tag=PRIMARY_TAG, snapshot=None) != ()


def test_the_per_draw_audit_rejects_positive_reasoning_tokens(snapshot):
    body = ok_body(tag=PRIMARY_TAG, snapshot=snapshot, reasoning_tokens=5)
    failures = S.audit_failures(body, model=MODEL, tag=PRIMARY_TAG, snapshot=snapshot)
    assert any("reasoning_tokens_not_zero" in f for f in failures)


def test_smoke_books_every_returned_cost(run_dir, snapshot):
    ledger = empty_ledger()
    _run_smoke(run_dir, FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot,
                                                                 cost=2e-06)),
               ledger=ledger)
    assert ledger.run_usd == pytest.approx(240 * 2e-06)


# =======================================================================================
# 6. The full run: reuse, counts, completeness, the hard stop, restart
# =======================================================================================

def _run_full(run_dir, transport, ledger=None, worst_case=_worst_case, requests=None,
              snapshot=None):
    return S.run_full(model=MODEL, tag=PRIMARY_TAG, key=KEY,
                      requests=requests if requests is not None else fake_study_grid(),
                      probe_ids=PROBE_IDS, store=S.study_store(run_dir),
                      ledger=ledger or empty_ledger(), transport=transport,
                      worst_case_usd=worst_case,
                      snapshot=snapshot if snapshot is not None else real_snapshot(),
                      sleep=lambda _s: None, clock=_stub_clock())


def test_full_run_attempts_13200_reuses_240_and_sends_12960(run_dir, snapshot):
    smoke_transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    _run_smoke(run_dir, smoke_transport)
    assert smoke_transport.calls == 240

    full_transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot))
    report = _run_full(run_dir, full_transport)
    assert report.run.n_attempted == 13_200
    assert report.run.n_reused == 240                # smoke draws replayed, never repaid
    assert report.run.n_sent == 12_960
    assert full_transport.calls == 12_960
    assert report.completeness is not None and report.completeness.complete
    assert report.complete and report.emit_headline
    assert not report.run.halted


def test_full_run_halts_before_a_call_that_would_breach_the_hard_stop(run_dir, snapshot):
    """"Finish current model" NEVER overrides the $8.50 stop."""
    ledger = empty_ledger(hard_stop=0.001)
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot, cost=1e-04))
    report = _run_full(run_dir, transport, ledger=ledger, worst_case=lambda _s: 1e-04)
    assert report.run.halted
    assert report.run.n_attempted < 13_200
    assert report.model_incomplete
    assert report.emit_headline is False
    assert report.completeness is None               # no completeness, hence no headline
    assert ledger.total_spent_usd <= ledger.hard_stop_usd
    assert transport.calls == report.run.n_sent


def test_hard_stop_halt_is_recorded_and_reports_no_headline(run_dir, snapshot):
    ledger = empty_ledger(hard_stop=0.0005)
    transport = FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot, cost=1e-04))
    report = S.run_full(model=MODEL, tag=PRIMARY_TAG, key=KEY, requests=fake_study_grid(),
                        probe_ids=PROBE_IDS, store=S.study_store(run_dir), ledger=ledger,
                        transport=transport, worst_case_usd=lambda _s: 1e-04,
                        run_dir=run_dir, snapshot=snapshot, sleep=lambda _s: None,
                        clock=_stub_clock())
    record = json.loads(S.full_record_path(run_dir, MODEL).read_text())
    assert record["halted"] is True
    assert record["emit_headline"] is False
    assert record["model_incomplete"] is True
    assert record["expected_attempted"] == 13_200
    assert "hard stop" in record["halt_reason"]
    assert report.run.halted


def test_restart_rebuilds_cumulative_spend_before_the_first_budget_check(run_dir, snapshot):
    """R-C2: a restarted process resumes at the cumulative spend, never at zero."""
    ledger = empty_ledger()
    _run_smoke(run_dir, FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot,
                                                                 cost=5e-06)),
               ledger=ledger)
    spent = ledger.run_usd
    assert spent == pytest.approx(240 * 5e-06)

    requests = fake_study_grid()
    study_ids = [I.draw_id(r.request_sha256, i) for r in requests
                 for i in range(I.DRAWS_PER_COORDINATE)]
    rebuilt = S.open_ledger(run_dir, model=MODEL, endpoint=PRIMARY_TAG,
                            study_draw_ids=study_ids)
    assert rebuilt.run_usd == pytest.approx(spent)
    assert rebuilt.total_spent_usd == pytest.approx(spent)


def test_open_ledger_includes_walk_spend_under_the_same_stop(run_dir, snapshot):
    walk_ledger = empty_ledger()
    S.run_walk(**_walk_kwargs(snapshot, S.walk_store(run_dir), walk_ledger,
                              FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot,
                                                                       cost=7e-06))))
    rebuilt = S.open_ledger(run_dir, model=MODEL, endpoint=PRIMARY_TAG)
    assert rebuilt.run_usd == pytest.approx(7e-06)
    assert rebuilt.hard_stop_usd == 8.50


def test_open_ledger_carries_prior_reconciled_spend(run_dir):
    rec = L.ReconciliationResult(reconciled_usd=0.031, record_count=3,
                                 components=(L.FORCE_OVERWRITTEN_CANARY,))
    ledger = S.open_ledger(run_dir, model=MODEL, reconciliation=rec)
    assert ledger.prior_usd == pytest.approx(0.031 + L.FORCE_OVERWRITTEN_CANARY.upper_bound_usd)
    assert ledger.is_exact is False


def test_open_ledger_refuses_a_record_outside_the_authorised_identities(run_dir, snapshot):
    _run_smoke(run_dir, FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot)))
    with pytest.raises(L.ManifestBindingError):
        S.open_ledger(run_dir, model=MODEL, endpoint=PRIMARY_TAG, study_draw_ids=())


def test_completeness_gate_rejects_19_of_25_in_one_coordinate():
    """R-V7-3: >= 20/25 parseable in EVERY order."""
    requests = fake_study_grid()
    thin = requests[0]
    draws = []
    for request in requests:
        for index in range(25):
            bad = request.request_sha256 == thin.request_sha256 and index >= 19
            draws.append(G.SamplingDraw(cell_id=request.cell_id, probe_id=request.probe_id,
                                        order_idx=request.order_idx, draw_index=index,
                                        choice=None if bad else 1))
    report = G.completeness_gate(draws, expected_probe_ids=PROBE_IDS)
    assert not report.complete
    assert report.valid_counts[(thin.cell_id, thin.probe_id, thin.order_idx)] == 19
    assert any("below 20/25" in f for f in report.failures)


def test_completeness_gate_rejects_094_overall():
    requests = fake_study_grid()
    draws = []
    # 792 of 13,200 unparseable == 0.94 overall, spread so EVERY coordinate still clears
    # 20/25 — only the overall rule may reject this run.
    remaining = int(round(13_200 * 0.06))
    for position, request in enumerate(requests):
        unparseable = 2 if position < 264 else 1
        for index in range(25):
            bad = remaining > 0 and index >= 25 - unparseable
            if bad:
                remaining -= 1
            draws.append(G.SamplingDraw(cell_id=request.cell_id, probe_id=request.probe_id,
                                        order_idx=request.order_idx, draw_index=index,
                                        choice=None if bad else 2))
    report = G.completeness_gate(draws, expected_probe_ids=PROBE_IDS)
    assert report.overall_parse_rate == pytest.approx(0.94)
    assert not report.complete
    assert any("overall parse rate" in f for f in report.failures)


def test_full_run_report_emits_no_headline_when_incomplete(run_dir):
    report = S.FullRunReport(model=MODEL, endpoint=PRIMARY_TAG,
                             run=S.PlanRun(outcomes=(), halted=True, halt_reason="stop",
                                           n_sent=0, n_reused=0),
                             completeness=None)
    assert report.model_incomplete and not report.emit_headline
    assert report.as_record()["emit_headline"] is False


def test_full_run_refuses_a_grid_that_is_not_528(run_dir, snapshot):
    with pytest.raises(I.CountMismatch):
        _run_full(run_dir, FakeTransport(default=lambda body, n: ok(PRIMARY_TAG, snapshot)),
                  requests=fake_study_grid()[:10])


# =======================================================================================
# 7. The CLI
# =======================================================================================

def test_cli_refuses_without_the_paid_spend_flag(monkeypatch, capsys, run_dir):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    code = S.main(["walk", "--model", MODEL, "--run-dir", str(run_dir)])
    assert code == 2
    assert "--i-have-authorized-paid-spend" in capsys.readouterr().err


def test_cli_refuses_without_an_api_key(monkeypatch, capsys, run_dir):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    code = S.main(["walk", "--model", MODEL, "--run-dir", str(run_dir),
                   "--i-have-authorized-paid-spend"])
    assert code == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_cli_refuses_a_model_outside_the_frozen_panel(monkeypatch, capsys, run_dir):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    code = S.main(["walk", "--model", "acme/whatever", "--run-dir", str(run_dir),
                   "--i-have-authorized-paid-spend"])
    assert code == 2
    assert "frozen v7 panel" in capsys.readouterr().err


def test_cli_requires_the_pinned_tokenizer_for_the_projection_stages(monkeypatch, capsys,
                                                                     run_dir):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    code = S.main(["walk", "--model", MODEL, "--run-dir", str(run_dir),
                   "--i-have-authorized-paid-spend"])
    assert code == 2
    assert "--tokenizer-dir" in capsys.readouterr().err


def test_cli_rejects_an_unknown_stage(run_dir):
    with pytest.raises(SystemExit) as excinfo:
        S.main(["headline", "--model", MODEL, "--run-dir", str(run_dir)])
    assert excinfo.value.code == 2


def test_cli_runs_exactly_one_stage_and_never_auto_advances(monkeypatch, run_dir):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    called: list[str] = []
    monkeypatch.setattr(S, "_DISPATCH", {
        name: (lambda *a, _n=name, **k: called.append(_n) or 0) for name in S.STAGES})
    for stage in S.STAGES:
        called.clear()
        assert S.main([stage, "--model", MODEL, "--run-dir", str(run_dir),
                       "--i-have-authorized-paid-spend", "--tokenizer-dir",
                       str(run_dir)]) == 0
        assert called == [stage]                     # exactly one stage, no successor


def test_cli_stage_names_are_the_four_frozen_steps():
    assert S.STAGES == ("walk", "project", "smoke", "full")
    assert set(S._DISPATCH) == set(S.STAGES)


def test_usage_line_documents_the_required_acknowledgement():
    assert "--i-have-authorized-paid-spend" in S.USAGE
    assert "{walk,project,smoke,full}" in S.USAGE


# =======================================================================================
# 8. Conformance with the real renderer, when it is present
# =======================================================================================

def test_real_renderer_matches_the_frozen_counts_and_coordinates(snapshot):
    render = pytest.importorskip("alignment.q2_v7.study_render")
    probe_ids = render.probe_ids_for("ENG")
    grid = render.render_study_grid(MODEL, PRIMARY_TAG, probe_ids)
    smoke = render.render_smoke_grid(MODEL, PRIMARY_TAG, probe_ids)
    assert len(grid) == 528 and len(smoke) == 48
    by_coordinate = {(r.cell_id, r.probe_id, r.order_idx): r.request_sha256 for r in grid}
    assert len(by_coordinate) == 528
    for request in smoke:
        key = (request.cell_id, request.probe_id, request.order_idx)
        assert by_coordinate[key] == request.request_sha256      # smoke IS inside the grid
    assert len(S.plan_full_draws(grid)) == 13_200
    assert len(S.plan_smoke_draws(smoke)) == 240
