"""Panel B (AMD-PB-01) — activation, isolation from v7, and the usage-calibrated counter.

The binding property this file protects is NEGATIVE: importing or exercising `panel_b` must
never change a v7 run. Every test therefore asserts the v7 value both before activation and
after `deactivate()`, and the fixture deactivates unconditionally so a failure mid-test cannot
leak Panel B constants into the rest of the suite.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from alignment.q2_v7 import canary as C
from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import ledger as L
from alignment.q2_v7 import panel_b as PB
from alignment.q2_v7 import study_run as SR

ROOT = Path(__file__).resolve().parents[1]
GLM = "z-ai/glm-5.3"
SOL = "openai/gpt-5.6-sol"

# The v7 values this module must leave alone.
V7_PANEL = ("qwen/qwen3.5-397b-a17b", "deepseek/deepseek-v4-pro")
V7_STOP = 8.50
V7_SNAPSHOT_PATH = "out/q2_stage2_endpoint_snapshot/manifest.json"


@pytest.fixture(autouse=True)
def _never_leak_panel_b():
    """Panel B is off before every test and off after every test, however the test ends."""
    PB.deactivate()
    yield
    PB.deactivate()


@pytest.fixture
def _no_env(monkeypatch):
    monkeypatch.delenv("Q2_PANEL", raising=False)
    return monkeypatch


# =======================================================================================
# v7 is untouched unless Panel B is explicitly activated
# =======================================================================================

def _assert_v7_constants():
    assert G.PANEL_ORDER == V7_PANEL
    assert set(G.FALLBACK_SEQUENCES) == set(V7_PANEL)
    assert G.FALLBACK_SEQUENCE is G.FALLBACK_SEQUENCES or dict(G.FALLBACK_SEQUENCE) == dict(
        G.FALLBACK_SEQUENCES)
    assert G.GLOBAL_STUDY_STOP == pytest.approx(V7_STOP)
    assert G.APPROVED_FALLBACK_AMENDMENTS == frozenset()
    assert L.HARD_STOP_USD == pytest.approx(V7_STOP)
    assert E.SNAPSHOT_PATH == V7_SNAPSHOT_PATH
    assert E.SNAPSHOT_SHA256 == (
        "d9a5d0e061bf222ee7d12bd056c0f7ccaeadfab16db47da1fcf581d52dd3a72b")
    assert E.PROVIDER_DEFAULT_SAMPLING_MODELS == frozenset()
    assert C.PANEL_ORDER == V7_PANEL
    assert set(C.FALLBACK_SEQUENCES) == set(V7_PANEL)
    assert C.DEFAULT_RUN_DIR.name == "q2_stage2_v7_canary"
    assert len(C.PRIOR_RECORD_DIRS) == 4
    assert len(C.PRIOR_DIAGNOSTIC_COMPONENTS) == 3
    assert SR.DEFAULT_RUN_DIR.name == "q2_stage2_v7_study"
    assert dict(SR.FALLBACK_AMENDMENT_BY_MODEL) == {}
    assert SR.USAGE_CALIBRATED_MODELS == frozenset()


def test_importing_panel_b_changes_nothing():
    assert PB.is_active() is False
    _assert_v7_constants()


def test_deactivate_restores_every_v7_constant():
    PB.activate()
    assert PB.is_active() is True
    PB.deactivate()
    assert PB.is_active() is False
    _assert_v7_constants()


def test_activate_is_idempotent_and_still_restores_v7():
    PB.activate()
    PB.activate()
    PB.activate()
    assert G.PANEL_ORDER == PB.PANEL_B_ORDER
    PB.deactivate()
    PB.deactivate()
    _assert_v7_constants()


# =======================================================================================
# Activation rebinds every listed attribute
# =======================================================================================

def test_activation_rebinds_every_listed_attribute():
    PB.activate()
    assert G.PANEL_ORDER == (GLM, SOL)
    assert dict(G.FALLBACK_SEQUENCES) == {GLM: ("reka/fp8",), SOL: ("openai",)}
    assert dict(G.FALLBACK_SEQUENCE) == dict(G.FALLBACK_SEQUENCES)
    assert G.GLOBAL_STUDY_STOP == pytest.approx(11.00)
    assert G.APPROVED_FALLBACK_AMENDMENTS == frozenset({"AMD-PB-01"})
    assert G.ENDPOINT_SNAPSHOT.name == "manifest.json"
    assert "panel_b_snapshot" in str(G.ENDPOINT_SNAPSHOT)

    assert E.SNAPSHOT_PATH == "out/q2_stage2_panel_b_snapshot/manifest.json"
    assert E.SNAPSHOT_SHA256 == PB.SNAPSHOT_SHA256_B
    assert E.PROVIDER_DEFAULT_SAMPLING_MODELS == frozenset({SOL})

    assert L.HARD_STOP_USD == pytest.approx(11.00)

    assert C.PANEL_ORDER == (GLM, SOL)
    assert dict(C.FALLBACK_SEQUENCES) == dict(G.FALLBACK_SEQUENCES)
    assert C.DEFAULT_RUN_DIR.name == "q2_stage2_panel_b_canary"
    assert C.PRIOR_RECORD_DIRS == (C.DEFAULT_RUN_DIR / "raw",)
    assert C.PRIOR_DIAGNOSTIC_COMPONENTS == ()

    assert SR.DEFAULT_RUN_DIR.name == "q2_stage2_panel_b_run"
    assert dict(SR.FALLBACK_AMENDMENT_BY_MODEL) == {SOL: "AMD-PB-01"}
    assert SR.USAGE_CALIBRATED_MODELS == frozenset({SOL})


def test_panel_b_prior_spend_never_reconciles_a_v7_record():
    """AMD-PB-01 (3): the two ledgers are disjoint, so no v7 raw dir may appear here."""
    PB.activate()
    for directory in C.PRIOR_RECORD_DIRS:
        assert "panel_b" in str(directory)


def test_frozen_sequence_follows_the_active_panel():
    with pytest.raises(G.SpecViolation):
        G.frozen_sequence(GLM)
    PB.activate()
    assert G.frozen_sequence(GLM) == ("reka/fp8",)
    assert G.frozen_sequence(SOL) == ("openai",)
    with pytest.raises(G.SpecViolation):
        G.frozen_sequence(V7_PANEL[0])


# =======================================================================================
# AMD-PB-01 (1): the omitted sampling parameters
# =======================================================================================

MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_sampling_parameters_are_sent_for_every_model_when_panel_b_is_off():
    for model, tag in ((SOL, "openai"), (GLM, "reka/fp8"), (V7_PANEL[0], "fireworks")):
        body = E.build_sampling_request(model, tag, MSGS)
        assert body["temperature"] == E.TEMPERATURE
        assert body["top_p"] == E.TOP_P


def test_sampling_parameters_are_omitted_only_for_sol_and_only_when_active():
    PB.activate()
    sol = E.build_sampling_request(SOL, "openai", MSGS)
    assert "temperature" not in sol and "top_p" not in sol
    # nothing else is dropped: the envelope is otherwise the frozen v7 one
    assert sol["max_tokens"] == G.MAX_TOKENS
    assert sol["usage"] == {"include": True}

    glm = E.build_sampling_request(GLM, "reka/fp8", MSGS)
    assert glm["temperature"] == E.TEMPERATURE and glm["top_p"] == E.TOP_P

    PB.deactivate()
    again = E.build_sampling_request(SOL, "openai", MSGS)
    assert again["temperature"] == E.TEMPERATURE and again["top_p"] == E.TOP_P


# =======================================================================================
# AMD-PB-01 (2): the amendment-gated fixed-overhead projection
# =======================================================================================

def _fallback_projection(amendment):
    """A minimal CostProjection labelled as the non-C2 fallback."""
    return G.CostProjection(
        model=SOL,
        endpoint_tag="openai",
        n_requests=0,
        draws_per_request=G.DRAWS_PER_COORDINATE,
        price_prompt_per_token=0.0,
        price_completion_per_token=0.0,
        rows=(),
        projected_input_tokens_total=0,
        projected_input_cost=0.0,
        completion_allowance=G.MAX_TOKENS,
        projected_completion_cost=0.0,
        reconciled_prior_gate_spend=0.0,
        retry_reserve=0.0,
        total=0.0,
        stop=11.0,
        fits=True,
        serialization_method=G.SERIALIZATION_FIXED_OVERHEAD,
        fixed_overhead_fallback_signed_amendment=amendment,
    )


def test_fixed_overhead_projection_is_refused_without_an_amendment():
    for active in (False, True):
        if active:
            PB.activate()
        with pytest.raises(G.MissingChatTemplate):
            G.require_frozen_c2_serialization(_fallback_projection(None))
        PB.deactivate()


def test_amd_pb_01_is_accepted_only_while_panel_b_is_active():
    with pytest.raises(G.MissingChatTemplate):
        G.require_frozen_c2_serialization(_fallback_projection("AMD-PB-01"))
    PB.activate()
    G.require_frozen_c2_serialization(_fallback_projection("AMD-PB-01"))   # no raise
    # an unsigned/unknown amendment is still refused while Panel B is active
    with pytest.raises(G.MissingChatTemplate):
        G.require_frozen_c2_serialization(_fallback_projection("AMD-NOT-SIGNED"))
    PB.deactivate()
    with pytest.raises(G.MissingChatTemplate):
        G.require_frozen_c2_serialization(_fallback_projection("AMD-PB-01"))


# =======================================================================================
# AMD-PB-01 (2): the usage-calibrated counter
# =======================================================================================

def _put_walk_envelope(run_dir: Path, *, model=SOL, prompt_tokens=40, status=200,
                       timestamp="2026-09-22T00:00:00Z", draw_id="draw-a",
                       messages=None, usage=None):
    store = SR.walk_store(run_dir)
    messages = messages if messages is not None else [
        {"role": "system", "content": "abcdefghij"},      # 10 chars
        {"role": "user", "content": "klmnopqrs"},         # 9 chars; + 1 newline = 20
    ]
    env = L.RawEnvelope(
        draw_id=draw_id,
        request_sha256="a" * 64,
        draw_index=0,
        request_body={"model": model, "messages": messages},
        request_headers={},
        response_body={},
        response_headers={},
        http_status=status,
        generation_id=None,
        timestamp=timestamp,
        usage=({"prompt_tokens": prompt_tokens} if usage is None else usage),
        cost_usd=0.0,
        cost_status="returned",
        openrouter_metadata=None,
        bucket="gate",
        model=model,
        provider="openai",
        stage="gate",
    )
    store.put(env)
    return store


def test_usage_calibrated_counter_math(tmp_path):
    _put_walk_envelope(tmp_path, prompt_tokens=40)          # 40 tokens / 20 chars = 2.0
    counter = PB.usage_calibrated_counter(SOL, run_dir=tmp_path)
    assert counter("x" * 7) == 14
    assert counter("") == 0
    ident = counter.identity()
    assert ident["tokens_per_character"] == pytest.approx(2.0)
    assert ident["signed_amendment"] == "AMD-PB-01"
    assert ident["prompt_tokens"] == 40 and ident["characters"] == 20


def test_usage_calibrated_counter_rounds_up(tmp_path):
    _put_walk_envelope(tmp_path, prompt_tokens=7)           # 7 / 20 = 0.35
    counter = PB.usage_calibrated_counter(SOL, run_dir=tmp_path)
    assert counter("x" * 10) == math.ceil(10 * 0.35) == 4


def test_usage_calibrated_counter_is_lazy(tmp_path):
    """Construction must not touch the run dir: the walk has not run yet at build time."""
    counter = PB.usage_calibrated_counter(SOL, run_dir=tmp_path / "not-yet")
    with pytest.raises(SR.StudyRunError):
        counter("anything")


def test_usage_calibrated_counter_takes_the_latest_envelope(tmp_path):
    _put_walk_envelope(tmp_path, prompt_tokens=40, timestamp="2026-09-22T00:00:00Z",
                       draw_id="draw-old")
    _put_walk_envelope(tmp_path, prompt_tokens=60, timestamp="2026-09-22T06:00:00Z",
                       draw_id="draw-new")
    assert PB.usage_calibrated_counter(SOL, run_dir=tmp_path)("x" * 10) == 30


@pytest.mark.parametrize("kwargs", [
    {"status": 429},                                   # not a success
    {"model": GLM},                                    # a different model
    {"usage": {}},                                     # no prompt_tokens
    {"usage": {"prompt_tokens": None}},                # unusable prompt_tokens
])
def test_usage_calibrated_counter_fails_closed(tmp_path, kwargs):
    _put_walk_envelope(tmp_path, **kwargs)
    counter = PB.usage_calibrated_counter(SOL, run_dir=tmp_path)
    with pytest.raises(SR.StudyRunError):
        counter("abc")


def test_usage_calibrated_counter_fails_closed_on_an_empty_run_dir(tmp_path):
    with pytest.raises(SR.StudyRunError):
        PB.usage_calibrated_counter(SOL, run_dir=tmp_path)("abc")


def test_pinned_tokenizer_routes_sol_to_the_calibrated_counter(tmp_path):
    _put_walk_envelope(tmp_path, prompt_tokens=40)
    PB.activate()
    counter = SR.pinned_tokenizer(SOL, None, tmp_path / "unused-tokenizer-dir",
                                  run_dir=tmp_path)
    assert isinstance(counter, PB.UsageCalibratedCounter)
    assert not isinstance(counter, G.PinnedTokenizer)   # so the projection is LABELLED fallback
    assert counter("x" * 5) == 10


def test_pinned_tokenizer_refuses_a_calibrated_model_with_no_run_dir(tmp_path):
    PB.activate()
    with pytest.raises(SR.StudyRunError):
        SR.pinned_tokenizer(SOL, None, tmp_path)


# =======================================================================================
# The committed Panel B snapshot
# =======================================================================================

def test_panel_b_snapshot_loads_and_its_sha_matches():
    PB.activate()
    snapshot = E.load_snapshot(ROOT / E.SNAPSHOT_PATH)
    assert snapshot.sha256 == PB.SNAPSHOT_SHA256_B
    assert set(snapshot.candidates) == {(GLM, "reka/fp8"), (SOL, "openai")}
    assert snapshot.candidates[(GLM, "reka/fp8")].quantization == "fp8"
    # the closed model pins no tokenizer files; GLM pins three
    assert (snapshot.tokenizers[SOL].get("files") or {}) == {}
    assert len(snapshot.tokenizers[GLM]["files"]) == 3


def test_the_v7_snapshot_is_refused_under_the_panel_b_binding():
    """The SHA binding is what keeps the two panels from reading each other's manifest."""
    PB.activate()
    with pytest.raises(E.SnapshotError):
        E.load_snapshot(ROOT / V7_SNAPSHOT_PATH)


def test_glm_takes_the_ordinary_frozen_c2_path():
    PB.activate()
    snapshot = E.load_snapshot(ROOT / E.SNAPSHOT_PATH)
    tokenizer = SR.pinned_tokenizer(GLM, snapshot, ROOT / "out" / "q2_stage2_tokenizers" / "glm")
    assert isinstance(tokenizer, G.PinnedTokenizer)
    assert tokenizer.has_exact_serialization is True
    assert tokenizer.serialization_method in G.FROZEN_C2_SERIALIZATIONS


# =======================================================================================
# Environment selection
# =======================================================================================

def test_env_var_activates_panel_b(monkeypatch):
    monkeypatch.setenv("Q2_PANEL", "B")
    assert PB.activate_from_env() is True
    assert PB.is_active() is True
    assert G.PANEL_ORDER == (GLM, SOL)


@pytest.mark.parametrize("value", ["b", " B ", "B"])
def test_env_var_is_case_and_space_insensitive(monkeypatch, value):
    monkeypatch.setenv("Q2_PANEL", value)
    assert PB.activate_from_env() is True


@pytest.mark.parametrize("value", ["", "A", "v7", "BB", "panel-b"])
def test_any_other_env_value_leaves_v7_alone(monkeypatch, value):
    monkeypatch.setenv("Q2_PANEL", value)
    assert PB.activate_from_env() is False
    assert PB.is_active() is False
    _assert_v7_constants()


def test_unset_env_leaves_v7_alone(_no_env):
    assert PB.activate_from_env() is False
    _assert_v7_constants()


def test_activate_from_env_accepts_an_explicit_mapping():
    assert PB.activate_from_env({"Q2_PANEL": "B"}) is True
    assert G.PANEL_ORDER == (GLM, SOL)
