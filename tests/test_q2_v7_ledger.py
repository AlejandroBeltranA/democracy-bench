"""No-network tests for the Stage-2 v7 audit ledger (src/alignment/q2_v7/ledger.py).

Covers R-E1, R-E2, R-E3, R-E5 (paper/Q2_STAGE2_RUNNER_REVIEW.md) and R-V7-6
(paper/Q2_STAGE2_HOSTED_DESIGN.md, "v7.1 revision" / "v7.2 closure").

NOTHING here touches the network. Every response is a literal dict.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alignment.q2_v7.ledger import (EPS, FORCE_OVERWRITTEN_CANARY, HARD_STOP_USD,
                                    CostAccountingError, DerivedRecord, DoubleBookingError,
                                    DrawIdentity, EnvelopeExistsError, EnvelopeStore,
                                    HardStopExceeded, ManifestBindingError, ModelProjection,
                                    NonReconciledComponent, RawEnvelope, ReconciliationError,
                                    ReconciliationResult, RunManifest, V7Ledger,
                                    build_envelope, canonical_sha256,
                                    estimand_eligible_draw_ids, is_cache_hit,
                                    reconcile_prior_spend, reconstruct_ledger, record_response,
                                    record_validation, redact_headers, redact_request_body,
                                    returned_cost)

# ---------------------------------------------------------------------------------------
# fixtures / builders
# ---------------------------------------------------------------------------------------

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

QWEN = "qwen/qwen3.5-397b-a17b"
DEEPSEEK = "deepseek/deepseek-v4-pro"


def _request(text: str = "Answer with a single digit.") -> dict:
    return {
        "model": QWEN,
        "messages": [{"role": "system", "content": "You are a helpful assistant."},
                     {"role": "user", "content": text}],
        "max_tokens": 4,
        "temperature": 1.0,
        "top_p": 1.0,
        "reasoning": {"effort": "none"},
        "provider": {"only": ["alibaba"], "allow_fallbacks": False,
                     "require_parameters": True},
        "usage": {"include": True},
    }


def _headers() -> dict:
    return {
        "Authorization": "Bearer sk-or-v1-SUPERSECRET",
        "Content-Type": "application/json",
        "X-OpenRouter-Metadata": "enabled",
        "X-OpenRouter-Cache": "false",
    }


def _response(cost: float | None = 0.0004, *, content: str = "3",
              provider: str = "Alibaba", cached: bool = False) -> dict:
    usage: dict = {"prompt_tokens": 218, "completion_tokens": 1, "reasoning_tokens": 0}
    if cost is not None:
        usage["cost"] = cost
    if cached:
        usage["cache_hit"] = True
    return {
        "id": "gen-01HVQWEN",
        "model": QWEN,
        "choices": [{"message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": usage,
        "openrouter_metadata": {"requested": QWEN, "strategy": "direct", "attempt": 1,
                                "is_byok": False,
                                "endpoints": {"available": [{"provider_name": provider}]},
                                "selected": {"provider_name": provider}},
    }


def _resp_headers() -> dict:
    return {"X-Generation-Id": "gen-01HVQWEN", "Content-Type": "application/json"}


def _manifest(*draw_ids: str) -> RunManifest:
    return RunManifest.from_draw_ids(draw_ids, model=QWEN, endpoint="alibaba")


def _fresh_ledger(manifest: RunManifest, *, prior: float = 0.0,
                  components=()) -> V7Ledger:
    rec = ReconciliationResult(reconciled_usd=prior, record_count=0, components=tuple(components))
    return V7Ledger(reconciliation=rec, manifest=manifest)


def _post(store, ledger, draw, *, cost=0.0004, content="3", status=200,
          bucket="study", stage="study", provider="alibaba"):
    return record_response(store=store, ledger=ledger, draw=draw,
                           request_body=_request(), request_headers=_headers(),
                           response_body=_response(cost, content=content),
                           response_headers=_resp_headers(), http_status=status,
                           bucket=bucket, model=QWEN, provider=provider, stage=stage,
                           timestamp="2026-07-28T00:00:00Z")


# =======================================================================================
# R-E5 — redaction and envelope completeness
# =======================================================================================

def test_credential_headers_are_redacted_and_everything_else_kept():
    red = redact_headers(_headers())
    assert red["Authorization"] == "REDACTED"
    assert "SUPERSECRET" not in json.dumps(red)
    assert red["X-OpenRouter-Cache"] == "false"
    assert red["X-OpenRouter-Metadata"] == "enabled"


def test_request_body_redaction_keeps_messages_and_provider_block():
    body = dict(_request(), api_key="sk-or-v1-SUPERSECRET")
    red = redact_request_body(body)
    assert red["api_key"] == "REDACTED"
    assert red["messages"] == body["messages"]
    assert red["provider"] == {"only": ["alibaba"], "allow_fallbacks": False,
                               "require_parameters": True}
    assert red["reasoning"] == {"effort": "none"}


def test_envelope_carries_every_required_audit_field(tmp_path: Path):
    draw = DrawIdentity(SHA_A, 0)
    env = build_envelope(draw=draw, request_body=_request(), request_headers=_headers(),
                         response_body=_response(0.0004), response_headers=_resp_headers(),
                         http_status=200, bucket="study", model=QWEN, provider="alibaba",
                         stage="study")
    assert env.draw_id == f"{SHA_A}#0"
    assert env.request_body["messages"][1]["content"].startswith("Answer")
    assert env.request_headers["Authorization"] == "REDACTED"
    assert env.response_body["choices"][0]["message"]["content"] == "3"
    assert env.response_headers["X-Generation-Id"] == "gen-01HVQWEN"
    assert env.http_status == 200
    assert env.generation_id == "gen-01HVQWEN"
    assert env.timestamp
    assert env.usage["prompt_tokens"] == 218
    assert env.cost_usd == pytest.approx(0.0004)
    assert env.openrouter_metadata["strategy"] == "direct"
    assert env.model == QWEN and env.provider == "alibaba"


def test_persisted_envelope_round_trips_and_secret_is_not_on_disk(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    ledger = _fresh_ledger(_manifest(f"{SHA_A}#0"))
    call = _post(store, ledger, DrawIdentity(SHA_A, 0))
    text = call.path.read_text()
    assert "SUPERSECRET" not in text
    back = RawEnvelope.from_dict(json.loads(text))
    assert back == call.envelope
    assert back.content_sha256() == call.envelope.content_sha256()


def test_atomic_write_leaves_no_temp_files(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    ledger = _fresh_ledger(_manifest(f"{SHA_A}#0"))
    _post(store, ledger, DrawIdentity(SHA_A, 0))
    assert list(store.raw_dir.glob("*.tmp")) == []


# =======================================================================================
# R-E1 — persist BEFORE validation/scoring; refuse to overwrite
# =======================================================================================

def test_envelope_is_persisted_before_the_cost_gate_can_fail(tmp_path: Path):
    """A paid response with no returned cost still leaves a complete durable envelope."""
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))

    with pytest.raises(CostAccountingError):
        _post(store, ledger, draw, cost=None)

    assert store.has(draw.draw_id), "paid response was discarded — R-E1 violation"
    env = store.get(draw.draw_id)
    assert env.cost_status == "missing" and env.cost_usd is None
    assert env.response_body["choices"][0]["message"]["content"] == "3"
    assert env.generation_id == "gen-01HVQWEN"      # reconciliation hook survives
    assert ledger.run_usd == 0.0, "nothing may be booked when cost is unknown"


def test_store_refuses_to_overwrite_an_existing_record(tmp_path: Path):
    """The R-E5/S-F6 failure that already destroyed one canary envelope. No --force exists."""
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))
    _post(store, ledger, draw, cost=0.0004, content="3")
    before = store.raw_path(draw.draw_id).read_text()

    replacement = build_envelope(draw=draw, request_body=_request(),
                                 request_headers=_headers(),
                                 response_body=_response(0.0009, content="1"),
                                 response_headers=_resp_headers(), http_status=200,
                                 bucket="study", model=QWEN, provider="alibaba", stage="study")
    with pytest.raises(EnvelopeExistsError):
        store.put(replacement)

    assert store.raw_path(draw.draw_id).read_text() == before
    assert store.get(draw.draw_id).cost_usd == pytest.approx(0.0004)
    assert not hasattr(store, "force")


def test_derived_record_also_refuses_overwrite(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))
    call = _post(store, ledger, draw)
    record_validation(store, call.envelope, valid=True)
    with pytest.raises(EnvelopeExistsError):
        record_validation(store, call.envelope, valid=False, failures=("rewrite",))


def test_filename_content_mismatch_is_rejected(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))
    call = _post(store, ledger, draw)
    tampered = dict(json.loads(call.path.read_text()), draw_id=f"{SHA_B}#0")
    call.path.write_text(json.dumps(tampered))
    with pytest.raises(ManifestBindingError):
        store.envelopes()


# =======================================================================================
# R-E2 — cost fails closed
# =======================================================================================

@pytest.mark.parametrize("usage", [
    {},                              # no cost at all
    {"cost": None},
    {"cost": "not-a-number"},
    {"cost": float("nan")},
    {"cost": float("inf")},
    {"cost": -0.0001},               # negative
])
def test_returned_cost_raises_instead_of_booking_zero(usage):
    with pytest.raises(CostAccountingError):
        returned_cost({"usage": usage})


def test_returned_cost_accepts_total_cost_alias():
    assert returned_cost({"usage": {"total_cost": 0.00062}}) == pytest.approx(0.00062)


def test_legitimate_cache_hit_zero_cost_is_booked_not_raised(tmp_path: Path):
    resp = _response(None, cached=True)
    assert is_cache_hit(resp)
    assert returned_cost(resp) == 0.0

    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))
    env = build_envelope(draw=draw, request_body=_request(), request_headers=_headers(),
                         response_body=resp, response_headers=_resp_headers(),
                         http_status=200, bucket="study", model=QWEN, provider="alibaba",
                         stage="study")
    store.put(env)
    assert env.cost_status == "cache_hit_zero"
    assert ledger.book_envelope(env) == 0.0


def test_paid_but_invalid_response_is_still_booked_and_retained(tmp_path: Path):
    """R-E1.2/R-E1.4: a provider mismatch excludes the call from the headline but never
    erases its audit record or its cost."""
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))

    call = _post(store, ledger, draw, cost=0.0007, content="I think option three")
    derived = record_validation(store, call.envelope, valid=False,
                                failures=("provider_mismatch", "unparseable_leading_digit"))

    assert ledger.total_spent_usd == pytest.approx(0.0007), "invalid call must still be charged"
    assert store.has(draw.draw_id), "invalid call must keep its audit record"
    assert derived.excluded_from_estimands is True
    assert derived.raw_sha256 == call.envelope.content_sha256()
    assert estimand_eligible_draw_ids(store) == []


def test_valid_call_is_estimand_eligible_but_unvalidated_call_is_not(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0", f"{SHA_B}#0")
    ledger = _fresh_ledger(manifest)
    good = _post(store, ledger, DrawIdentity(SHA_A, 0))
    _post(store, ledger, DrawIdentity(SHA_B, 0))          # never validated
    record_validation(store, good.envelope, valid=True)
    assert estimand_eligible_draw_ids(store) == [f"{SHA_A}#0"]


def test_double_booking_the_same_draw_is_refused(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    ledger = _fresh_ledger(_manifest(draw.draw_id))
    call = _post(store, ledger, draw)
    with pytest.raises(DoubleBookingError):
        ledger.book_envelope(call.envelope)


# =======================================================================================
# R-E3 — restart reconstruction
# =======================================================================================

def test_restart_rebuilds_cumulative_spend_and_does_not_reset_to_zero(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0", f"{SHA_B}#0")
    first = _fresh_ledger(manifest)
    _post(store, first, DrawIdentity(SHA_A, 0), cost=0.0004)
    _post(store, first, DrawIdentity(SHA_B, 0), cost=0.0006)
    assert first.run_usd == pytest.approx(0.0010)

    # process dies; a brand-new process starts and reconstructs BEFORE any budget check
    restarted = reconstruct_ledger(EnvelopeStore(tmp_path / "run"), manifest=manifest)
    assert restarted.run_usd == pytest.approx(0.0010), "restart must NOT reset cumulative spend"
    assert restarted.total_spent_usd == pytest.approx(0.0010)
    assert restarted.booked_draw_ids() == [f"{SHA_A}#0", f"{SHA_B}#0"]


def test_restart_after_one_valid_and_one_invalid_but_paid_call(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0", f"{SHA_B}#0")
    ledger = _fresh_ledger(manifest)
    good = _post(store, ledger, DrawIdentity(SHA_A, 0), cost=0.0004)
    bad = _post(store, ledger, DrawIdentity(SHA_B, 0), cost=0.0002, content="nonsense")
    record_validation(store, good.envelope, valid=True)
    record_validation(store, bad.envelope, valid=False, failures=("provider_mismatch",))

    restarted = reconstruct_ledger(EnvelopeStore(tmp_path / "run"), manifest=manifest)
    assert restarted.run_usd == pytest.approx(0.0006), "invalid-but-paid spend must survive restart"
    assert estimand_eligible_draw_ids(EnvelopeStore(tmp_path / "run")) == [f"{SHA_A}#0"]


def test_restart_carries_prior_reconciled_spend_into_the_budget_check(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0")
    ledger = _fresh_ledger(manifest)
    _post(store, ledger, DrawIdentity(SHA_A, 0), cost=0.0004)

    prior = ReconciliationResult(reconciled_usd=0.0325, record_count=7)
    restarted = reconstruct_ledger(EnvelopeStore(tmp_path / "run"), manifest=manifest,
                                   reconciliation=prior)
    assert restarted.prior_usd == pytest.approx(0.0325)
    assert restarted.total_spent_usd == pytest.approx(0.0329)


def test_restart_rejects_a_record_outside_the_frozen_manifest(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0", f"{SHA_B}#0")
    ledger = _fresh_ledger(manifest)
    _post(store, ledger, DrawIdentity(SHA_A, 0))

    stray = build_envelope(draw=DrawIdentity(SHA_C, 0), request_body=_request(),
                           request_headers=_headers(), response_body=_response(0.0004),
                           response_headers=_resp_headers(), http_status=200,
                           bucket="study", model=QWEN, provider="alibaba", stage="study")
    store.put(stray)

    with pytest.raises(ManifestBindingError):
        reconstruct_ledger(EnvelopeStore(tmp_path / "run"), manifest=manifest)


def test_booking_a_draw_outside_the_manifest_is_refused(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    ledger = _fresh_ledger(_manifest(f"{SHA_A}#0"))
    with pytest.raises(ManifestBindingError):
        _post(store, ledger, DrawIdentity(SHA_B, 0))


def test_restart_fails_closed_on_a_persisted_record_with_no_cost(tmp_path: Path):
    store = EnvelopeStore(tmp_path / "run")
    draw = DrawIdentity(SHA_A, 0)
    manifest = _manifest(draw.draw_id)
    with pytest.raises(CostAccountingError):
        _post(store, _fresh_ledger(manifest), draw, cost=None)

    with pytest.raises(CostAccountingError):
        reconstruct_ledger(EnvelopeStore(tmp_path / "run"), manifest=manifest)


def test_draw_identity_excludes_the_stage_label_so_smoke_draws_are_reused():
    smoke = DrawIdentity(SHA_A, 0)
    full = DrawIdentity(SHA_A, 0)
    assert smoke.draw_id == full.draw_id
    assert DrawIdentity.parse(smoke.draw_id) == smoke
    assert DrawIdentity(SHA_A, 5).draw_id != smoke.draw_id


# =======================================================================================
# R-V7-6 — prior-spend reconciliation
# =======================================================================================

def _write_prior(dirpath: Path, name: str, obj: dict) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(json.dumps(obj))


def test_reconciliation_from_persisted_records_is_exact_when_nothing_is_missing(tmp_path: Path):
    gate = tmp_path / "gate_run"
    _write_prior(gate, "a.json", {"key": "a", "cost": 0.0200})
    _write_prior(gate, "b.json", {"key": "b", "usage": {"cost": 0.0110}})
    _write_prior(gate, "c.json", {"key": "c", "cost_usd": 0.0005})

    result = reconcile_prior_spend([gate])
    assert result.record_count == 3
    assert result.reconciled_usd == pytest.approx(0.0315)
    assert result.non_reconciled_usd == 0.0
    assert result.total_usd == pytest.approx(0.0315)
    assert result.is_exact is True


def test_reconciliation_marks_the_force_overwritten_canary_non_reconciled(tmp_path: Path):
    """The --force-overwritten round-2 llama@digitalocean envelope cannot be recovered: it is
    debited at a documented conservative UPPER bound and the total is NOT exact."""
    canary = tmp_path / "openweight_canary"
    _write_prior(canary, "r1.json", {"cost": 0.000646})
    _write_prior(canary, "r2.json", {"cost": 0.000194})

    result = reconcile_prior_spend([canary], non_reconciled=[FORCE_OVERWRITTEN_CANARY])

    assert result.reconciled_usd == pytest.approx(0.000840)
    assert result.non_reconciled_usd == pytest.approx(0.0000207)
    assert result.total_usd == pytest.approx(0.0008607)
    assert result.is_exact is False, "a non-reconciled component may never be called exact"
    assert result.components[0].label.startswith("openweight_logprob_canary_round2")
    assert "--force" in result.components[0].reason
    assert result.to_dict()["is_exact"] is False


def test_non_reconciled_upper_bound_flows_into_the_hard_stop(tmp_path: Path):
    canary = tmp_path / "canary"
    _write_prior(canary, "r1.json", {"cost": 0.000840})
    result = reconcile_prior_spend([canary], non_reconciled=[FORCE_OVERWRITTEN_CANARY])
    ledger = V7Ledger(reconciliation=result, manifest=_manifest())
    assert ledger.prior_usd == pytest.approx(result.total_usd)
    assert ledger.is_exact is False
    assert ledger.audit_summary()["is_exact"] is False


def test_reconciliation_fails_closed_on_a_record_with_no_recoverable_cost(tmp_path: Path):
    gate = tmp_path / "gate_run"
    _write_prior(gate, "a.json", {"key": "a", "cost": 0.02})
    _write_prior(gate, "b.json", {"key": "b", "usage": {"prompt_tokens": 10}})
    with pytest.raises(ReconciliationError):
        reconcile_prior_spend([gate])


def test_reconciliation_refuses_a_missing_directory(tmp_path: Path):
    with pytest.raises(ReconciliationError):
        reconcile_prior_spend([tmp_path / "nope"])


def test_non_reconciled_component_rejects_a_non_finite_bound():
    with pytest.raises(ValueError):
        NonReconciledComponent(label="x", upper_bound_usd=float("nan"), reason="")


# =======================================================================================
# R-V7-6 — the unified $8.50 hard stop
# =======================================================================================

def test_hard_stop_is_the_single_frozen_figure():
    assert HARD_STOP_USD == 8.50


def test_all_buckets_count_against_the_one_stop(tmp_path: Path):
    """v7 supersedes v5's separate-canary treatment: canaries, diagnostics, and study calls
    all debit the same $8.50."""
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0", f"{SHA_B}#0", f"{SHA_C}#0")
    ledger = _fresh_ledger(manifest)
    _post(store, ledger, DrawIdentity(SHA_A, 0), cost=0.001, bucket="canary", stage="canary")
    _post(store, ledger, DrawIdentity(SHA_B, 0), cost=0.002, bucket="diagnostic",
          stage="diagnostic")
    _post(store, ledger, DrawIdentity(SHA_C, 0), cost=0.003, bucket="study", stage="study")

    assert ledger.total_spent_usd == pytest.approx(0.006)
    assert ledger.spend_by_bucket() == pytest.approx(
        {"canary": 0.001, "diagnostic": 0.002, "study": 0.003})
    assert ledger.remaining_usd == pytest.approx(8.494)


def test_pre_call_check_refuses_a_request_at_the_cap_boundary():
    ledger = _fresh_ledger(_manifest(), prior=8.499)
    ledger.check_before_call(0.001)                        # exactly $8.50 — permitted
    assert ledger.may_start_call(0.001) is True
    with pytest.raises(HardStopExceeded):
        ledger.check_before_call(0.0011)                   # would breach
    assert ledger.may_start_call(0.0011) is False


def test_pre_call_check_rejects_a_nonsense_estimate():
    ledger = _fresh_ledger(_manifest())
    with pytest.raises(ValueError):
        ledger.check_before_call(-0.01)
    with pytest.raises(ValueError):
        ledger.check_before_call(float("inf"))


# =======================================================================================
# R-V7-6 — may_start_model / finish-current-model never overrides the stop
# =======================================================================================

def _projection(model: str, total: float, reserve: float = 0.0) -> ModelProjection:
    return ModelProjection(model=model, endpoint="alibaba" if model == QWEN else "deepseek",
                           projected_input_cost_usd=total, projected_completion_cost_usd=0.0,
                           retry_reserve_usd=reserve)


def test_may_start_model_blocks_deepseek_when_only_qwen_fits(tmp_path: Path):
    """The cut rule may prevent starting DeepSeek; it can never authorize a partial run."""
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0")
    ledger = _fresh_ledger(manifest, prior=0.0325)
    qwen = _projection(QWEN, 4.20, reserve=0.30)
    deepseek = _projection(DEEPSEEK, 4.20, reserve=0.30)

    started = ledger.start_model(qwen)
    assert started.allowed is True
    assert ledger.current_model == QWEN

    # Qwen actually runs and bills its full projected cost.
    _post(store, ledger, DrawIdentity(SHA_A, 0), cost=4.50)
    ledger.mark_model_complete()
    assert ledger.total_spent_usd == pytest.approx(0.0325 + 4.50)

    decision = ledger.may_start_model(deepseek)
    assert decision.allowed is False
    assert decision.budget_excluded is True
    assert decision.projected_total_usd == pytest.approx(0.0325 + 4.50 + 4.50)
    assert "budget exclusion" in decision.reason
    assert "reduced-cell" in decision.reason
    with pytest.raises(HardStopExceeded):
        ledger.start_model(deepseek)


def test_may_start_model_requires_the_reserve_to_fit_too():
    ledger = _fresh_ledger(_manifest(), prior=4.00)
    assert ledger.may_start_model(_projection(QWEN, 4.50, reserve=0.0)).allowed is True
    assert ledger.may_start_model(_projection(QWEN, 4.50, reserve=0.01)).allowed is False


def test_may_start_model_permits_exactly_the_boundary():
    ledger = _fresh_ledger(_manifest(), prior=0.50)
    decision = ledger.may_start_model(_projection(QWEN, 7.00, reserve=1.00))
    assert decision.allowed is True
    assert decision.projected_total_usd == pytest.approx(8.50)
    assert decision.headroom_usd == pytest.approx(0.0, abs=1e-9)


def test_mid_model_cost_drift_halts_before_the_next_call_with_no_headline(tmp_path: Path):
    """Realized cost drifted above the projection; the run halts mid-model rather than
    'finishing the current model'. The model is reported incomplete and emits no headline."""
    store = EnvelopeStore(tmp_path / "run")
    manifest = _manifest(f"{SHA_A}#0")
    ledger = _fresh_ledger(manifest, prior=8.40)
    ledger.start_model(_projection(QWEN, 0.09, reserve=0.01))   # projection fits exactly

    ok = ledger.must_halt_before_next_call(0.001)
    assert ok.halt is False

    # one call bills far above projection
    _post(store, ledger, DrawIdentity(SHA_A, 0), cost=0.0995)

    decision = ledger.must_halt_before_next_call(0.001)
    assert decision.halt is True
    assert decision.model == QWEN
    assert decision.model_incomplete is True
    assert decision.emit_headline is False
    assert "hard stop" in decision.reason
    with pytest.raises(HardStopExceeded):
        ledger.check_before_call(0.001)


def test_halt_triggers_when_realized_spend_already_exceeds_the_stop():
    ledger = _fresh_ledger(_manifest(), prior=8.51)
    ledger.current_model = QWEN
    decision = ledger.must_halt_before_next_call(0.0)
    assert decision.halt is True
    assert decision.emit_headline is False
    assert "already exceeds" in decision.reason


def test_no_halt_and_headline_allowed_once_the_model_is_complete():
    ledger = _fresh_ledger(_manifest(), prior=1.00)
    ledger.start_model(_projection(QWEN, 4.00, reserve=0.10))
    assert ledger.must_halt_before_next_call(0.001).emit_headline is False  # still in flight
    ledger.mark_model_complete()
    decision = ledger.must_halt_before_next_call(0.001)
    assert decision.halt is False
    assert decision.model_incomplete is False
    assert decision.emit_headline is True


def test_halt_check_rejects_a_nonsense_next_call_estimate():
    ledger = _fresh_ledger(_manifest())
    with pytest.raises(ValueError):
        ledger.must_halt_before_next_call(-1.0)


# =======================================================================================
# manifest identity
# =======================================================================================

def test_manifest_hash_changes_with_the_bound_draw_set():
    a = RunManifest.from_draw_ids([f"{SHA_A}#0"], model=QWEN, endpoint="alibaba")
    b = RunManifest.from_draw_ids([f"{SHA_A}#0", f"{SHA_A}#1"], model=QWEN, endpoint="alibaba")
    c = RunManifest.from_draw_ids([f"{SHA_A}#0"], model=QWEN, endpoint="digitalocean")
    assert len({a.manifest_sha256, b.manifest_sha256, c.manifest_sha256}) == 3
    assert a.contains(f"{SHA_A}#0") and not a.contains(f"{SHA_A}#1")


def test_draw_identity_validates_its_inputs():
    with pytest.raises(ValueError):
        DrawIdentity("short", 0)
    with pytest.raises(ValueError):
        DrawIdentity(SHA_A, -1)
    with pytest.raises(ValueError):
        DrawIdentity.parse("no-hash-marker")


def test_canonical_sha256_is_key_order_independent():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
