"""No-network tests for the Q2 Stage-2 v7.2 frozen envelope (alignment.q2_v7.envelope).

Covers the runner deltas the freeze requires before any paid call
(paper/Q2_STAGE2_HOSTED_DESIGN.md — "v7 amendment", "v7.1 revision" R-V7-1..R-V7-7, and
"v7.2 closure" C1..C4):

  A. exact frozen sampling body (temp/top_p/max_tokens/reasoning-off/no-seed/provider/usage)
  B. frozen headers, including X-OpenRouter-Cache:false on every draw (R-V7-7)
  C. committed endpoint snapshot parsed and SHA-256-bound (C1)
  D. frozen C1 provider-audit proof — passes on a good response, fails on every named defect,
     and does NOT require any response field to equal the variant tag
  E. R-V7-1 reasoning-off proof — exactly zero reasoning tokens, no payload, usage present

Nothing here touches the network: every response is a hand-built dict modelled on the real
envelopes persisted under out/q2_stage2_canary/.
"""
from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from alignment.q2_v7 import envelope as E

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / E.SNAPSHOT_PATH

QWEN = "qwen/qwen3.5-397b-a17b"
DEEPSEEK = "deepseek/deepseek-v4-pro"

MESSAGES = [
    {"role": "system", "content": "You are answering a survey."},
    {"role": "user", "content": "Pick one option (1-4). Reply with the number only."},
]


# --------------------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def snap() -> E.Snapshot:
    return E.load_snapshot(SNAPSHOT)


def good_response(*, model=QWEN, display="DigitalOcean",
                  upstream="qwen/qwen3.5-397b-a17b-20260216",
                  reasoning_tokens=0, attempt=1, strategy="direct", is_byok=False,
                  available=None, summary=None) -> dict:
    """A realistic OpenRouter 200 response, modelled on the shape actually returned in
    out/q2_stage2_canary/openweight_logprob/*.json. Note it contains NO field anywhere that
    equals a variant tag such as 'parasail/fp8' — only display names."""
    if available is None:
        available = [{"provider": display, "model": upstream, "selected": True}]
    if summary is None:
        summary = f"available={len(available)}, selected={display}"
    return {
        "id": "gen-1784808120-xzNVmceMnt17NTNAdrEL",
        "object": "chat.completion",
        "created": 1784808120,
        "model": model,
        "provider": display,
        "choices": [{"index": 0, "finish_reason": "length",
                     "message": {"role": "assistant", "content": "3"}}],
        "usage": {
            "prompt_tokens": 77,
            "completion_tokens": 1,
            "total_tokens": 78,
            "cost": 4.9245e-05,
            "is_byok": False,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens,
                                          "image_tokens": 0, "audio_tokens": 0},
        },
        "openrouter_metadata": {
            "requested": model,
            "strategy": strategy,
            "region": "LHR",
            "summary": summary,
            "attempt": attempt,
            "is_byok": is_byok,
            "endpoints": {"total": 11, "available": available},
        },
    }


# ============================================================ A. frozen sampling request

def test_sampling_request_exact_shape():
    """The whole body, key for key — this is the byte-level freeze."""
    body = E.build_sampling_request(QWEN, "parasail/fp8", MESSAGES)
    assert body == {
        "model": QWEN,
        "messages": [
            {"role": "system", "content": "You are answering a survey."},
            {"role": "user", "content": "Pick one option (1-4). Reply with the number only."},
        ],
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 4,
        "reasoning": {"effort": "none"},
        "provider": {"only": ["parasail/fp8"], "allow_fallbacks": False,
                     "require_parameters": True},
        "usage": {"include": True},
    }


def test_sampling_request_has_no_seed_key_at_all():
    """R-V7-1/v6: draws must be independent, so `seed` is ABSENT — not null, not 0."""
    body = E.build_sampling_request(QWEN, "alibaba", MESSAGES)
    assert "seed" not in body
    assert "seed" not in json.dumps(body)


def test_sampling_request_has_no_stop_sequences_or_logprob_keys():
    body = E.build_sampling_request(DEEPSEEK, "deepseek", MESSAGES)
    for banned in ("stop", "stop_sequences", "logprobs", "top_logprobs", "stream"):
        assert banned not in body


def test_reasoning_off_uses_documented_effort_none_form():
    """R-V7-1 replaced the draft's undocumented {"enabled": false} with {"effort": "none"}."""
    body = E.build_sampling_request(QWEN, "alibaba", MESSAGES)
    assert body["reasoning"] == {"effort": "none"}
    assert "enabled" not in body["reasoning"]


def test_temperature_and_top_p_frozen_on_every_candidate(snap):
    """R-V7-1: both are frozen on ALL nine candidates; they are never conditionally omitted."""
    for (model, tag) in snap.candidates:
        body = E.build_sampling_request(model, tag, MESSAGES)
        assert body["temperature"] == 1.0
        assert body["top_p"] == 1.0
        assert body["max_tokens"] == 4


def test_provider_block_is_single_tag_no_fallbacks_require_parameters():
    body = E.build_sampling_request(DEEPSEEK, "streamlake/fp8", MESSAGES)
    assert body["provider"] == {"only": ["streamlake/fp8"], "allow_fallbacks": False,
                                "require_parameters": True}


def test_usage_include_true_so_returned_cost_drives_the_ledger():
    assert E.build_sampling_request(QWEN, "alibaba", MESSAGES)["usage"] == {"include": True}


def test_request_body_does_not_alias_caller_messages():
    msgs = [{"role": "user", "content": "hi"}]
    body = E.build_sampling_request(QWEN, "alibaba", msgs)
    msgs[0]["content"] = "MUTATED"
    assert body["messages"][0]["content"] == "hi"


@pytest.mark.parametrize("bad", [
    [],                                             # empty
    [{"role": "user"}],                             # no content
    [{"role": "tool", "content": "x"}],             # unsupported role
    [{"role": "user", "content": 3}],               # non-string content
    [{"role": "user", "content": "x", "name": "n"}],  # undeclared key
    "not a list",
])
def test_malformed_messages_fail_closed(bad):
    with pytest.raises(E.EnvelopeError):
        E.build_sampling_request(QWEN, "alibaba", bad)


@pytest.mark.parametrize("model,tag", [("", "alibaba"), (QWEN, ""), (QWEN, "   ")])
def test_blank_model_or_tag_fails_closed(model, tag):
    with pytest.raises(E.EnvelopeError):
        E.build_sampling_request(model, tag, MESSAGES)


def test_canonical_hash_is_stable_and_key_order_independent():
    body = E.build_sampling_request(QWEN, "alibaba", MESSAGES)
    shuffled = {k: body[k] for k in reversed(list(body))}
    assert E.canonical_request_sha256(body) == E.canonical_request_sha256(shuffled)
    assert (E.canonical_request_sha256(body)
            != E.canonical_request_sha256(E.build_sampling_request(QWEN, "digitalocean",
                                                                   MESSAGES)))


# ============================================================ B. frozen headers

def test_headers_exact():
    h = E.request_headers("sk-or-TESTKEY")
    assert h == {
        "Authorization": "Bearer sk-or-TESTKEY",
        "Content-Type": "application/json",
        "X-OpenRouter-Metadata": "enabled",
        "X-OpenRouter-Cache": "false",
    }


def test_cache_header_present_and_false_on_every_draw():
    """R-V7-7: X-OpenRouter-Cache:false on EVERY draw, so 25 draws never collapse to one."""
    for _ in range(3):
        assert E.request_headers("k")["X-OpenRouter-Cache"] == "false"


def test_headers_carry_the_key_only_in_authorization():
    h = E.request_headers("sk-or-SECRET")
    hits = [k for k, v in h.items() if "SECRET" in str(v)]
    assert hits == ["Authorization"]


@pytest.mark.parametrize("bad", ["", "   ", None, 123])
def test_blank_key_fails_closed(bad):
    with pytest.raises(E.EnvelopeError):
        E.request_headers(bad)


# ============================================================ C. committed snapshot (C1)

def test_snapshot_binds_to_the_frozen_sha256(snap):
    assert snap.sha256 == E.SNAPSHOT_SHA256
    assert snap.sha256 == hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()


def test_snapshot_has_all_nine_bound_candidates(snap):
    assert len(snap.candidates) == 9
    assert set(snap.tags_for(QWEN)) == {"alibaba", "digitalocean", "streamlake", "parasail/fp8"}
    assert set(snap.tags_for(DEEPSEEK)) == {"deepseek", "fireworks", "novita/fp8",
                                            "parasail/fp8", "streamlake/fp8"}


def test_snapshot_tag_to_display_name_mapping(snap):
    assert snap.display_name(QWEN, "digitalocean") == "DigitalOcean"
    assert snap.display_name(QWEN, "parasail/fp8") == "Parasail"
    assert snap.display_name(DEEPSEEK, "streamlake/fp8") == "StreamLake"
    assert snap.display_name(DEEPSEEK, "deepseek") == "DeepSeek"


def test_snapshot_keys_by_model_and_tag_because_tags_are_not_unique(snap):
    """`parasail/fp8` exists under BOTH models with different upstream ids; a flat tag->name
    map would silently accept a cross-model routing error."""
    q = snap.candidate(QWEN, "parasail/fp8")
    d = snap.candidate(DEEPSEEK, "parasail/fp8")
    assert q.provider_name == d.provider_name == "Parasail"
    assert q.upstream_model != d.upstream_model


def test_snapshot_quantization_and_prices(snap):
    assert snap.quantization(QWEN, "alibaba") == "unknown"
    assert snap.quantization(DEEPSEEK, "novita/fp8") == "fp8"
    prompt, completion = snap.prices(QWEN, "digitalocean")
    assert prompt == Decimal("0.000000385")
    assert completion == Decimal("0.00000245")
    assert snap.candidate(DEEPSEEK, "deepseek").price_prompt_per_million == Decimal("0.435")


def test_snapshot_upstream_model_parsed_from_endpoint_name(snap):
    c = snap.candidate(QWEN, "digitalocean")
    assert c.endpoint_name == "DigitalOcean | qwen/qwen3.5-397b-a17b-20260216"
    assert c.upstream_model == "qwen/qwen3.5-397b-a17b-20260216"


def test_snapshot_exposes_raw_file_hashes_and_tokenizers(snap):
    assert snap.raw_file_sha256["qwen_qwen3.5-397b-a17b_endpoints.json"].startswith("75f6ac9d")
    assert snap.tokenizers[QWEN]["revision"] == "8472618112abcbd45acbcdc58436aff4233c23f7"
    assert len(snap.sources) == 2


def test_snapshot_fails_closed_on_sha_mismatch():
    with pytest.raises(E.SnapshotError, match="SHA-256 mismatch"):
        E.load_snapshot(SNAPSHOT, expected_sha256="00" * 32)


def test_snapshot_fails_closed_when_verification_is_skipped():
    with pytest.raises(E.SnapshotError):
        E.load_snapshot(SNAPSHOT, expected_sha256=None)


def test_snapshot_fails_closed_on_tampered_file(tmp_path):
    doc = json.loads(SNAPSHOT.read_text())
    doc["candidates"][0]["provider_name"] = "Attacker"
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(E.SnapshotError):
        E.load_snapshot(p)


def test_snapshot_fails_closed_on_missing_file(tmp_path):
    with pytest.raises(E.SnapshotError):
        E.load_snapshot(tmp_path / "nope.json")


def test_snapshot_rejects_duplicate_candidates(tmp_path):
    doc = json.loads(SNAPSHOT.read_text())
    doc["candidates"].append(copy.deepcopy(doc["candidates"][0]))
    p = tmp_path / "m.json"
    p.write_bytes(json.dumps(doc).encode())
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(E.SnapshotError, match="duplicate"):
        E.load_snapshot(p, expected_sha256=sha)


def test_snapshot_rejects_endpoint_name_provider_disagreement(tmp_path):
    doc = json.loads(SNAPSHOT.read_text())
    doc["candidates"][0]["endpoint_name"] = "SomeoneElse | qwen/qwen3.5-397b-a17b-20260216"
    p = tmp_path / "m.json"
    p.write_bytes(json.dumps(doc).encode())
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(E.SnapshotError, match="provider_name"):
        E.load_snapshot(p, expected_sha256=sha)


def test_unknown_candidate_fails_closed(snap):
    with pytest.raises(E.SnapshotError):
        snap.candidate(QWEN, "deepseek")  # right tag, wrong model


# ============================================================ D. frozen C1 provider audit

def test_audit_passes_on_a_good_response(snap):
    res = E.verify_provider_audit(good_response(), QWEN, "digitalocean", snap)
    assert res.ok, res.failures
    assert res.failures == ()
    assert res.selected_provider == "DigitalOcean"
    assert res.returned_upstream_model == "qwen/qwen3.5-397b-a17b-20260216"
    assert res.attempt == 1 and res.strategy == "direct" and res.is_byok is False
    assert res.available_count == 1
    assert bool(res) is True
    assert res.raise_for_status() is res


def test_audit_does_not_require_any_field_to_equal_the_variant_tag(snap):
    """C1: 'Do not require a response field to equal the variant tag if the API does not
    return such a field.' The whole response mentions 'Parasail', never 'parasail/fp8'."""
    resp = good_response(model=DEEPSEEK, display="Parasail",
                         upstream="deepseek/deepseek-v4-pro-20260423")
    assert "parasail/fp8" not in json.dumps(resp)
    res = E.verify_provider_audit(resp, DEEPSEEK, "parasail/fp8", snap)
    assert res.ok, res.failures


def test_audit_passes_when_summary_omits_the_selected_clause(snap):
    """Some real responses carry only 'available=1' with no 'selected=' clause."""
    res = E.verify_provider_audit(good_response(summary="available=1"), QWEN, "digitalocean",
                                  snap)
    assert res.ok, res.failures


def test_audit_fails_on_missing_metadata(snap):
    """Reverses the old q2_hosted bug where provider_matches(x, None) returned True: absence
    of routing evidence is never proof of correct routing."""
    resp = good_response()
    resp.pop("openrouter_metadata")
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert res.failures == ("missing_openrouter_metadata",)
    with pytest.raises(E.ProviderAuditError):
        res.raise_for_status()


def test_audit_fails_when_metadata_is_not_a_mapping(snap):
    resp = good_response()
    resp["openrouter_metadata"] = "enabled"
    assert not E.verify_provider_audit(resp, QWEN, "digitalocean", snap).ok


def test_audit_fails_on_fallback_occurred(snap):
    resp = good_response()
    resp["openrouter_metadata"]["fallback"] = True
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("fallback_occurred") for f in res.failures)


def test_audit_fails_on_non_direct_strategy(snap):
    res = E.verify_provider_audit(good_response(strategy="fallback"), QWEN, "digitalocean",
                                  snap)
    assert not res.ok
    assert any(f.startswith("strategy_not_direct") for f in res.failures)


@pytest.mark.parametrize("attempt", [0, 2, 3, None, "1", True])
def test_audit_fails_when_attempt_is_not_one(snap, attempt):
    res = E.verify_provider_audit(good_response(attempt=attempt), QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("attempt_not_one") for f in res.failures)


@pytest.mark.parametrize("byok", [True, None, "false"])
def test_audit_fails_on_byok(snap, byok):
    """R-V7-5: BYOK spend escapes the returned-cost ledger, so the $8.50 stop would be
    incomplete. A BYOK-only endpoint is an availability failure."""
    res = E.verify_provider_audit(good_response(is_byok=byok), QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("is_byok_not_false") for f in res.failures)


def test_audit_fails_on_wrong_requested_model(snap):
    resp = good_response()
    resp["openrouter_metadata"]["requested"] = DEEPSEEK
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("requested_model_mismatch") for f in res.failures)


def test_audit_fails_on_wrong_top_level_model(snap):
    resp = good_response()
    resp["model"] = "qwen/qwen3.5-72b"
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("response_model_mismatch") for f in res.failures)


def test_audit_fails_on_returned_upstream_model_mismatch(snap):
    """The datable upstream id must match the snapshot's bound endpoint (R-V7-4)."""
    resp = good_response(upstream="qwen/qwen3.5-397b-a17b-20251101")
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("returned_model_mismatch") for f in res.failures)


def test_audit_fails_on_display_name_mismatch(snap):
    """Requested digitalocean, served by Alibaba."""
    resp = good_response(display="Alibaba")
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("display_name_mismatch") for f in res.failures)


def test_audit_fails_when_display_name_matches_a_different_models_tag(snap):
    """StreamLake serves both `streamlake` (Qwen) and `streamlake/fp8` (DeepSeek); the display
    name alone must not be allowed to satisfy the wrong (model, tag) binding."""
    resp = good_response(model=QWEN, display="StreamLake",
                         upstream="qwen/qwen3.5-397b-a17b-20260216")
    ok = E.verify_provider_audit(resp, QWEN, "streamlake", snap)
    assert ok.ok, ok.failures
    bad = E.verify_provider_audit(resp, DEEPSEEK, "streamlake/fp8", snap)
    assert not bad.ok


def test_audit_fails_on_more_than_one_available_candidate(snap):
    resp = good_response(available=[
        {"provider": "DigitalOcean", "model": "qwen/qwen3.5-397b-a17b-20260216",
         "selected": True},
        {"provider": "Alibaba", "model": "qwen/qwen3.5-397b-a17b-20260216", "selected": False},
    ])
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("available_candidates_not_one") for f in res.failures)
    assert res.available_count == 2


def test_audit_fails_when_the_sole_candidate_is_not_selected(snap):
    """The real 429 shape: one available endpoint, selected=false, nothing served."""
    resp = good_response(available=[{"provider": "DigitalOcean",
                                     "model": "qwen/qwen3.5-397b-a17b-20260216",
                                     "selected": False}])
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert "sole_candidate_not_selected" in res.failures


def test_audit_fails_when_available_list_is_missing(snap):
    resp = good_response()
    resp["openrouter_metadata"]["endpoints"] = {"total": 11}
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert "missing_available_candidates" in res.failures


def test_audit_fails_on_error_payload(snap):
    resp = good_response()
    resp["error"] = {"message": "Provider returned error", "code": 429}
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert "error_in_response" in res.failures


def test_audit_fails_on_summary_contradiction(snap):
    resp = good_response(summary="available=3, selected=Alibaba")
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("summary_available_not_one") for f in res.failures)
    assert any(f.startswith("summary_selected_mismatch") for f in res.failures)


def test_audit_fails_on_top_level_provider_disagreement(snap):
    resp = good_response()
    resp["provider"] = "Parasail"
    res = E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert not res.ok
    assert any(f.startswith("response_provider_mismatch") for f in res.failures)


def test_audit_of_unbound_candidate_raises(snap):
    with pytest.raises(E.SnapshotError):
        E.verify_provider_audit(good_response(), QWEN, "openai", snap)


def test_audit_is_pure(snap):
    resp = good_response()
    before = copy.deepcopy(resp)
    E.verify_provider_audit(resp, QWEN, "digitalocean", snap)
    assert resp == before


# ============================================================ E. R-V7-1 reasoning-off proof

def test_reasoning_off_passes_on_zero_tokens():
    res = E.verify_reasoning_off(good_response(reasoning_tokens=0))
    assert res.ok, res.failures
    assert res.reasoning_tokens == 0
    assert res.completion_tokens == 1
    assert res.raise_for_status() is res


@pytest.mark.parametrize("n", [1, 7, 249])
def test_reasoning_off_fails_on_positive_reasoning_tokens(n):
    """R-V7-1 froze EXACTLY 0, superseding v7's 'approximately 0' wording. 7 and 249 are the
    counts actually observed on these endpoints in the open-weight canary."""
    res = E.verify_reasoning_off(good_response(reasoning_tokens=n))
    assert not res.ok
    assert f"reasoning_tokens_not_zero:{n}" in res.failures
    with pytest.raises(E.ReasoningError):
        res.raise_for_status()


def test_reasoning_off_fails_on_missing_usage():
    resp = good_response()
    resp.pop("usage")
    res = E.verify_reasoning_off(resp)
    assert not res.ok
    assert "missing_usage" in res.failures


def test_reasoning_off_fails_on_missing_completion_tokens_details():
    resp = good_response()
    resp["usage"].pop("completion_tokens_details")
    res = E.verify_reasoning_off(resp)
    assert not res.ok
    assert "missing_completion_tokens_details" in res.failures


def test_reasoning_off_fails_when_reasoning_tokens_absent():
    """An unreported count is not a zero count."""
    resp = good_response()
    resp["usage"]["completion_tokens_details"].pop("reasoning_tokens")
    res = E.verify_reasoning_off(resp)
    assert not res.ok
    assert any(f.startswith("missing_reasoning_tokens") for f in res.failures)
    assert res.reasoning_tokens is None


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens", "total_tokens"])
def test_reasoning_off_fails_on_missing_required_usage_field(field):
    resp = good_response()
    resp["usage"].pop(field)
    res = E.verify_reasoning_off(resp)
    assert not res.ok
    assert f"missing_usage_field:{field}" in res.failures


@pytest.mark.parametrize("key", ["reasoning", "reasoning_content", "reasoning_details"])
def test_reasoning_off_fails_on_reasoning_payload_in_message(key):
    resp = good_response()
    resp["choices"][0]["message"][key] = "let me think about this"
    res = E.verify_reasoning_off(resp)
    assert not res.ok
    assert any(f.startswith("reasoning_payload") for f in res.failures)


def test_reasoning_off_fails_on_reasoning_payload_on_the_choice():
    resp = good_response()
    resp["choices"][0]["reasoning"] = [{"text": "hidden"}]
    assert not E.verify_reasoning_off(resp).ok


def test_reasoning_off_tolerates_empty_reasoning_fields():
    """Providers commonly emit reasoning=None/'' when reasoning is genuinely off."""
    resp = good_response()
    resp["choices"][0]["message"]["reasoning"] = None
    resp["choices"][0]["message"]["reasoning_details"] = []
    assert E.verify_reasoning_off(resp).ok


def test_reasoning_off_is_pure():
    resp = good_response()
    before = copy.deepcopy(resp)
    E.verify_reasoning_off(resp)
    assert resp == before


# ============================================================ no-network guarantee

def test_module_makes_no_network_calls():
    """Static guard: the envelope module imports no HTTP machinery and issues no request."""
    src = (REPO / "src" / "alignment" / "q2_v7" / "envelope.py").read_text()
    for banned in ("urllib.request", "urlopen", "import requests", "http.client", "socket"):
        assert banned not in src
