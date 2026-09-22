"""Panel B (AMD-PB-01) — activation, isolation from v7, and the usage-calibrated counter.

The binding property this file protects is NEGATIVE: importing or exercising `panel_b` must
never change a v7 run. Every test therefore asserts the v7 value both before activation and
after `deactivate()`, and the fixture deactivates unconditionally so a failure mid-test cannot
leak Panel B constants into the rest of the suite.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from alignment.q2_v7 import canary as C
from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import ledger as L
from alignment.q2_v7 import panel_b as PB
from alignment.q2_v7 import study_run as SR

ROOT = Path(__file__).resolve().parents[1]
GLM = "z-ai/glm-5.2"
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
    assert dict(G.FALLBACK_SEQUENCES) == {GLM: ("novita/fp8",), SOL: ("openai",)}
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
    assert C.PRIOR_DIAGNOSTIC_COMPONENTS == PB.PRIOR_DIAGNOSTIC_COMPONENTS_B
    assert sum(c.upper_bound_usd for c in C.PRIOR_DIAGNOSTIC_COMPONENTS) < 0.001

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
    assert G.frozen_sequence(GLM) == ("novita/fp8",)
    assert G.frozen_sequence(SOL) == ("openai",)
    with pytest.raises(G.SpecViolation):
        G.frozen_sequence(V7_PANEL[0])


# =======================================================================================
# AMD-PB-01 (1): the omitted sampling parameters
# =======================================================================================

MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_sampling_parameters_are_sent_for_every_model_when_panel_b_is_off():
    for model, tag in ((SOL, "openai"), (GLM, "novita/fp8"), (V7_PANEL[0], "fireworks")):
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

    glm = E.build_sampling_request(GLM, "novita/fp8", MSGS)
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


def _enc():
    import tiktoken
    return tiktoken.get_encoding("o200k_base")


#: The default fixture payload: "abcdefghij" + "\n" + "klmnopqrs".
DEFAULT_PAYLOAD = "abcdefghij\nklmnopqrs"


def _payload_tokens(text=DEFAULT_PAYLOAD):
    return len(_enc().encode(text))


def test_usage_calibrated_counter_counts_with_o200k_base(tmp_path):
    """The count IS tiktoken o200k_base on the text — no ratio, no scaling."""
    # framing must sit in [0, chat_template_overhead(2)] = [0, 32]
    _put_walk_envelope(tmp_path, prompt_tokens=_payload_tokens() + 10)
    counter = PB.usage_calibrated_counter(SOL, run_dir=tmp_path)
    enc = _enc()
    for text in ("", "x" * 7, "The Member for Ashford asked about the funding formula.",
                 "abcdefghij\nklmnopqrs"):
        assert counter(text) == len(enc.encode(text))


def test_usage_calibrated_counter_identity(tmp_path):
    import tiktoken
    payload = _payload_tokens()
    _put_walk_envelope(tmp_path, prompt_tokens=payload + 10, draw_id="draw-1",
                       timestamp="2026-09-22T06:00:00Z")
    ident = PB.usage_calibrated_counter(SOL, run_dir=tmp_path).identity()
    assert ident["method"] == "tiktoken_content_count_plus_fixed_overhead"
    assert ident["encoding"] == "o200k_base"
    assert ident["tiktoken_version"] == tiktoken.__version__
    assert ident["amendment"] == "AMD-PB-01"
    assert ident["calibration_draw_id"] == "draw-1"
    assert ident["calibration_timestamp"] == "2026-09-22T06:00:00Z"
    assert ident["probe_prompt_tokens"] == payload + 10
    assert ident["probe_payload_tokens"] == payload
    assert ident["provider_framing_tokens"] == 10
    assert ident["framing_cap_tokens"] == G.chat_template_overhead(2) == 32
    assert "tokens_per_character" not in ident


def test_usage_calibrated_counter_is_lazy(tmp_path):
    """Construction must not touch the run dir: the walk has not run yet at build time."""
    counter = PB.usage_calibrated_counter(SOL, run_dir=tmp_path / "not-yet")
    with pytest.raises(SR.StudyRunError):
        counter("anything")


def test_usage_calibrated_counter_takes_the_latest_envelope(tmp_path):
    """The framing check reads the LATEST usable probe, not the first one written."""
    payload = _payload_tokens()
    _put_walk_envelope(tmp_path, prompt_tokens=payload + 31,
                       timestamp="2026-09-22T00:00:00Z", draw_id="draw-old")
    _put_walk_envelope(tmp_path, prompt_tokens=payload + 7,
                       timestamp="2026-09-22T06:00:00Z", draw_id="draw-new")
    ident = PB.usage_calibrated_counter(SOL, run_dir=tmp_path).identity()
    assert ident["calibration_draw_id"] == "draw-new"
    assert ident["provider_framing_tokens"] == 7


def test_usage_calibrated_counter_fails_closed_on_negative_framing(tmp_path):
    """Billed fewer prompt tokens than the public encoding counts: not conservative."""
    _put_walk_envelope(tmp_path, prompt_tokens=_payload_tokens() - 1)
    with pytest.raises(SR.StudyRunError, match="NEGATIVE"):
        PB.usage_calibrated_counter(SOL, run_dir=tmp_path)("abc")


def test_usage_calibrated_counter_fails_closed_above_the_overhead_cap(tmp_path):
    """Real framing above gate.chat_template_overhead(n) would understate the grid."""
    cap = G.chat_template_overhead(2)
    _put_walk_envelope(tmp_path, prompt_tokens=_payload_tokens() + cap + 1)
    with pytest.raises(SR.StudyRunError, match="framing"):
        PB.usage_calibrated_counter(SOL, run_dir=tmp_path)("abc")
    # exactly at the cap is still allowed
    _put_walk_envelope(tmp_path, prompt_tokens=_payload_tokens() + cap,
                       timestamp="2026-09-23T00:00:00Z", draw_id="draw-at-cap")
    assert PB.usage_calibrated_counter(SOL, run_dir=tmp_path)("abc") == len(
        _enc().encode("abc"))


def test_the_framing_cap_follows_the_message_count(tmp_path):
    """A three-message probe is capped at chat_template_overhead(3), not (2)."""
    msgs = [{"role": "system", "content": "abc"},
            {"role": "user", "content": "def"},
            {"role": "user", "content": "ghi"}]
    payload = _payload_tokens("abc\ndef\nghi")
    _put_walk_envelope(tmp_path, messages=msgs,
                       prompt_tokens=payload + G.chat_template_overhead(3))
    ident = PB.usage_calibrated_counter(SOL, run_dir=tmp_path).identity()
    assert ident["framing_cap_tokens"] == G.chat_template_overhead(3) == 44


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
    _put_walk_envelope(tmp_path, prompt_tokens=_payload_tokens() + 10)
    PB.activate()
    counter = SR.pinned_tokenizer(SOL, None, tmp_path / "unused-tokenizer-dir",
                                  run_dir=tmp_path)
    assert isinstance(counter, PB.UsageCalibratedCounter)
    assert not isinstance(counter, G.PinnedTokenizer)   # so the projection is LABELLED fallback
    assert counter("x" * 5) == len(_enc().encode("x" * 5))


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
    assert set(snapshot.candidates) == {(GLM, "novita/fp8"), (SOL, "openai")}
    assert snapshot.candidates[(GLM, "novita/fp8")].quantization == "fp8"
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
    tokenizer = SR.pinned_tokenizer(GLM, snapshot, ROOT / "out" / "q2_stage2_tokenizers" / "glm52")
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


def test_activate_also_rebinds_a_python_dash_m_main_alias(monkeypatch, tmp_path):
    """`python -m alignment.q2_v7.canary` runs canary.py as `__main__`, a second module
    object. Activation must reach that running copy, not only the imported one."""
    import sys
    import types
    from alignment.q2_v7 import canary as C
    from alignment.q2_v7 import panel_b

    panel_b.deactivate()
    fake_main = types.ModuleType("__main__")
    fake_main.__file__ = C.__file__
    fake_main.DEFAULT_RUN_DIR = C.DEFAULT_RUN_DIR
    fake_main.PANEL_ORDER = C.PANEL_ORDER
    monkeypatch.setitem(sys.modules, "__main__", fake_main)
    try:
        panel_b.activate()
        assert fake_main.DEFAULT_RUN_DIR == panel_b.CANARY_RUN_DIR_B
        assert fake_main.PANEL_ORDER == panel_b.PANEL_B_ORDER
    finally:
        panel_b.deactivate()
    assert fake_main.DEFAULT_RUN_DIR == C.DEFAULT_RUN_DIR
    assert fake_main.PANEL_ORDER == C.PANEL_ORDER


# --------------------------------------------------------------------------------------
# AMD-PB-02 — variant B2 (Sol-only re-run with a bounded framing-token tolerance)
# --------------------------------------------------------------------------------------

def _probe(tag, billed, reasoning_tokens=0, payload=False):
    from alignment.q2_v7 import gate as G
    return G.EndpointProbeResult(tag=tag, http_status=200, reasoning_tokens=reasoning_tokens,
                                 has_reasoning_payload=payload, usage_fields_present=True,
                                 parsed_leading_digit=2, billed_completion_tokens=billed)


def test_v7_keeps_the_strict_billed_token_rule():
    from alignment.q2_v7 import gate as G
    from alignment.q2_v7 import panel_b
    panel_b.deactivate()
    assert G.FRAMING_TOKEN_TOLERANCE_BY_TAG == {}
    assert any("exceeds max_tokens" in f for f in G.audit_reasoning_off(_probe("openai", 5)))
    assert G.audit_reasoning_off(_probe("openai", 4)) == ()


def test_variant_b_does_not_tolerate_framing_tokens():
    from alignment.q2_v7 import gate as G
    from alignment.q2_v7 import panel_b
    panel_b.deactivate()
    panel_b.activate("B")
    try:
        assert any("exceeds" in f for f in G.audit_reasoning_off(_probe("openai", 5)))
    finally:
        panel_b.deactivate()


def test_variant_b2_tolerates_bounded_framing_tokens_only_with_reasoning_off():
    from alignment.q2_v7 import gate as G
    from alignment.q2_v7 import ledger as L
    from alignment.q2_v7 import panel_b
    panel_b.deactivate()
    panel_b.activate("B2")
    try:
        assert panel_b.active_variant() == "B2"
        assert G.PANEL_ORDER == ("openai/gpt-5.6-sol",)
        assert G.GLOBAL_STUDY_STOP == pytest.approx(8.40)
        assert L.HARD_STOP_USD == pytest.approx(8.40)
        assert G.audit_reasoning_off(_probe("openai", 5)) == ()
        assert G.audit_reasoning_off(_probe("openai", 4 + 8)) == ()
        assert any("exceeds" in f for f in G.audit_reasoning_off(_probe("openai", 4 + 9)))
        # the tolerance is keyed by tag: GLM's endpoint stays strict
        assert any("exceeds" in f for f in G.audit_reasoning_off(_probe("novita/fp8", 5)))
        # and it never applies when reasoning is not demonstrably off
        fails = G.audit_reasoning_off(_probe("openai", 5, reasoning_tokens=1))
        assert any("exceeds" in f for f in fails) and any("reasoning_tokens" in f for f in fails)
        fails = G.audit_reasoning_off(_probe("openai", 5, payload=True))
        assert any("exceeds" in f for f in fails)
    finally:
        panel_b.deactivate()
    assert G.FRAMING_TOKEN_TOLERANCE_BY_TAG == {}
    assert G.GLOBAL_STUDY_STOP == pytest.approx(8.50)


def test_b2_env_activation_and_variant_switch_guard(monkeypatch):
    from alignment.q2_v7 import panel_b
    panel_b.deactivate()
    assert panel_b.activate_from_env({"Q2_PANEL": "b2"}) is True
    try:
        assert panel_b.active_variant() == "B2"
        with pytest.raises(RuntimeError):
            panel_b.activate("B")
    finally:
        panel_b.deactivate()
    assert panel_b.activate_from_env({"Q2_PANEL": ""}) is False
