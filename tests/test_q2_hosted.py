"""No-network readiness suite for the Stage-2 hosted runner (alignment.q2_hosted).

Maps 1:1 onto the five test groups the v5 freeze requires before any paid OpenRouter call
(paper/Q2_STAGE2_HOSTED_DESIGN.md, "Execution-readiness and staged-spend gate"):

  1. request snapshots   — exact messages/roles/params/provider/header for both paths
  2. fail-closed scoring — missing numbers, variants, absent logprobs, mismatch, retry/skip
  3. accounting          — immutable atomic records; returned cost drives hard stops
  4. idempotence/restart — resume without re-paying; smoke reused once; no partial headline
  5. counts              — exactly 48 / 528 / 9,600 / 13,200; manifest hashed before run

Every test uses a fake transport or hand-built responses; nothing hits the network.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from alignment import q2_hosted as Q
from alignment.instrument import measure as M
from alignment.instrument.measure import ElicitationError, SkipCellError


# --------------------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def items():
    return Q.load_probe_items("ENG")


def _lp_response(tokens, *, cost=0.001, provider="openai", model="m"):
    """A minimal OpenRouter logprob response with a first-token top_logprobs list."""
    return {
        "model": model, "provider": provider,
        "choices": [{"logprobs": {"content": [{"top_logprobs": [
            {"token": t, "logprob": lp} for t, lp in tokens.items()]}]}}],
        "usage": {"cost": cost},
    }


def _sample_response(text, *, cost=0.0002, provider="openai", model="m"):
    return {"model": model, "provider": provider,
            "choices": [{"message": {"content": text}}], "usage": {"cost": cost}}


# =====================================================================================
# GROUP 1 — request snapshots (exact wire format for both paths)
# =====================================================================================

def test_logprob_request_exact_shape():
    b = Q.build_request(model="openai/gpt-4o-mini-2024-07-18", provider="openai",
                        system="SYS", prompt="PROMPT", path="logprob")
    assert b["model"] == "openai/gpt-4o-mini-2024-07-18"
    assert b["messages"] == [{"role": "system", "content": "SYS"},
                             {"role": "user", "content": "PROMPT"}]
    assert b["temperature"] == 1.0 and b["top_p"] == 1.0 and b["max_tokens"] == 4
    assert b["logprobs"] is True and b["top_logprobs"] == 20 and b["seed"] == 0
    assert b["provider"] == {"only": ["openai"], "allow_fallbacks": False,
                             "require_parameters": True}
    assert b["usage"] == {"include": True}


def test_sampling_request_has_no_seed_and_no_logprobs():
    b = Q.build_request(model="m", provider="xai", system="SYS", prompt="P", path="sampling")
    assert "seed" not in b and "logprobs" not in b and "top_logprobs" not in b
    assert b["temperature"] == 1.0 and b["top_p"] == 1.0 and b["max_tokens"] == 4
    assert b["provider"]["only"] == ["xai"]


def test_headers_include_metadata_optin():
    h = Q.request_headers("KEY123")
    assert h["Authorization"] == "Bearer KEY123"
    assert h["Content-Type"] == "application/json"
    assert h["X-OpenRouter-Metadata"] == "enabled"


def test_panel_slugs_are_frozen():
    got = {e.model: e.provider for e in Q.PANEL}
    assert got == {
        "openai/gpt-4o-mini-2024-07-18": "openai",
        "openai/gpt-4o-2024-11-20": "openai",
        "x-ai/grok-4.5": "xai",
        "meta-llama/llama-3.3-70b-instruct": "akashml/fp8",
    }
    # only OpenAI + xAI rows are first-party; the Llama row is quantized and cannot carry the
    # "transfer beyond quantized checkpoints" claim.
    assert not next(e for e in Q.PANEL if e.model.startswith("meta-llama")).first_party


def test_system_guard_cell_routes_guard_into_system_role(items):
    """A system_guard cell puts the guard in the SYSTEM message; user content is the payload
    only. A no_guard cell leaves the system message as the plain survey framing."""
    sg = Q.CallSpec("m", "openai", "logprob", "data_only::system_guard",
                    "pol_ai_due_process", 0)
    b = Q.build_call_request(sg, items["pol_ai_due_process"])
    sys_msg, user_msg = b["messages"][0]["content"], b["messages"][1]["content"]
    assert sys_msg == f"{M.SURVEY_SYSTEM}\n\n{Q.GUARD_TEXT}"
    assert Q.GUARD_TEXT not in user_msg               # guard is not duplicated into the user turn

    ng = Q.CallSpec("m", "openai", "logprob", "data_only::no_guard", "pol_ai_due_process", 0)
    bn = Q.build_call_request(ng, items["pol_ai_due_process"])
    assert bn["messages"][0]["content"] == M.SURVEY_SYSTEM


def test_user_before_after_place_guard_around_payload(items):
    it = items["pol_ai_due_process"]
    before = Q.build_call_request(
        Q.CallSpec("m", "openai", "logprob", "data_only::user_before", it["id"], 0), it)
    after = Q.build_call_request(
        Q.CallSpec("m", "openai", "logprob", "data_only::user_after", it["id"], 0), it)
    ub, ua = before["messages"][1]["content"], after["messages"][1]["content"]
    # both contain the guard and the payload, in opposite order
    assert ub.index(Q.GUARD_TEXT) < ub.index("distributed approximately as follows")
    assert ua.index(Q.GUARD_TEXT) > ua.index("distributed approximately as follows")


def test_smoke_request_is_byte_identical_to_matrix_twin(items):
    ep = Q.PANEL[0]
    matrix = Q.enumerate_logprob_calls(ep, list(items), smoke_only=False)
    smoke = Q.enumerate_logprob_calls(ep, list(items), smoke_only=True)
    s = smoke[0]
    twin = next(m for m in matrix if (m.cell_id, m.probe_id, m.order_idx)
                == (s.cell_id, s.probe_id, s.order_idx))
    assert Q.request_key(Q.build_call_request(s, items[s.probe_id])) \
        == Q.request_key(Q.build_call_request(twin, items[twin.probe_id]))


# =====================================================================================
# GROUP 2 — fail-closed scoring
# =====================================================================================

def test_score_sums_distinct_variants_of_the_same_option():
    # two distinct tokens both read as "1"; their masses SUM (not max).
    top = {"1": math.log(0.2), " 1": math.log(0.1), "2": math.log(0.3),
           "3": math.log(0.05), "4": math.log(0.05)}
    probs, cov = Q.score_topk(top, 4)
    raw1 = 0.2 + 0.1
    assert cov["per_option_mass"][0] == pytest.approx(raw1, abs=1e-6)
    assert probs[0] == pytest.approx(raw1 / (raw1 + 0.3 + 0.05 + 0.05), abs=1e-6)
    assert cov["all_present"] is True


def test_score_reports_missing_option_numbers():
    top = {"1": math.log(0.5), "2": math.log(0.4), "3": math.log(0.1)}   # no "4"
    probs, cov = Q.score_topk(top, 4)
    assert cov["present"] == [True, True, True, False]
    assert cov["all_present"] is False
    assert probs[3] == 0.0


def test_score_fails_closed_when_no_option_token():
    with pytest.raises(ElicitationError):
        Q.score_topk({"the": math.log(0.6), "yes": math.log(0.4)}, 4)


def test_top1_is_option_flag():
    top = {"Sure": math.log(0.7), "1": math.log(0.2), "2": math.log(0.1)}
    _, cov = Q.score_topk(top, 4)
    assert cov["top1_is_option"] is False
    top2 = {"2": math.log(0.7), "1": math.log(0.3)}
    _, cov2 = Q.score_topk(top2, 4)
    assert cov2["top1_is_option"] is True


def test_smoke_passes_only_when_every_call_has_all_four():
    good = [{"all_present": True}] * 4
    bad = [{"all_present": True}, {"all_present": False}]
    assert Q.smoke_passes(good) is True
    assert Q.smoke_passes(bad) is False
    assert Q.smoke_passes([]) is False


def test_extract_topk_fail_closed_on_absent_logprobs():
    with pytest.raises(ElicitationError):
        Q.extract_topk({"choices": [{"message": {"content": "1"}}]})   # no logprobs field
    with pytest.raises(ElicitationError):
        Q.extract_topk({"choices": []})
    with pytest.raises(ElicitationError):
        Q.extract_topk({"choices": [{"logprobs": {"content": [{"top_logprobs": []}]}}]})


def test_sampling_choice_leading_number_and_fail_closed():
    assert Q.sampling_choice(_sample_response("2"), 4) == 1        # 0-based
    assert Q.sampling_choice(_sample_response("3. because"), 4) == 2
    assert Q.sampling_choice(_sample_response("no number here"), 4) is None
    assert Q.sampling_choice(_sample_response("9"), 4) is None     # out of range
    assert Q.sampling_choice({"choices": []}, 4) is None


def test_provider_mismatch_blocks_headline_data(items, tmp_path):
    """A response served by a different provider than declared raises ProviderMismatch and
    writes NO raw record (no headline data booked)."""
    it = items["pol_ai_due_process"]
    spec = Q.CallSpec(Q.PANEL[3].model, Q.PANEL[3].provider, "logprob",
                      "data_only::no_guard", it["id"], 0)
    transport = lambda body, headers: _lp_response(
        {"1": math.log(.25), "2": math.log(.25), "3": math.log(.25), "4": math.log(.25)},
        provider="novita")                          # declared akashml/fp8, served novita
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=False)
    with pytest.raises(Q.ProviderMismatch):
        Q.execute_call(spec, it, transport, {}, led, store, "smoke", est_cost=0.01)
    assert store.keys() == []
    assert led.spent["smoke"] == 0.0


def test_provider_matches_normalizes_slug_vs_display_name():
    # declared routing slug vs served display name — base-slug match, not exact string
    assert Q.provider_matches("akashml/fp8", "AkashML") is True
    assert Q.provider_matches("openai", "OpenAI") is True
    assert Q.provider_matches("xai", "xAI") is True
    assert Q.provider_matches("akashml/fp8", "Novita") is False       # genuine drift
    assert Q.provider_matches("openai", None) is True                 # no metadata -> consistent


def test_execute_call_accepts_display_name_provider(items, tmp_path):
    """The Llama endpoint's response says 'AkashML'; the declared slug is 'akashml/fp8'. This
    must NOT be flagged as a mismatch."""
    it = items["pol_ai_due_process"]
    spec = Q.CallSpec(Q.PANEL[3].model, Q.PANEL[3].provider, "logprob",
                      "data_only::no_guard", it["id"], 0)
    transport = lambda body, headers: _lp_response(
        {"1": math.log(.25), "2": math.log(.25), "3": math.log(.25), "4": math.log(.25)},
        provider="AkashML")
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=True)
    rec = Q.execute_call(spec, it, transport, {}, led, store, "smoke", est_cost=0.01)
    assert rec["resolved_provider"] == "AkashML"
    assert rec["coverage"]["all_present"] is True


def test_classify_http_status_retry_vs_skip():
    assert Q.classify_http_status(429) == "retry"
    assert Q.classify_http_status(503) == "retry"
    assert Q.classify_http_status(400) == "skip"
    assert Q.classify_http_status(404) == "skip"
    assert Q.classify_http_status(302) == "raise"


def test_transport_honors_retry_after_then_succeeds():
    """A 429 with Retry-After sleeps that many seconds, then a retry succeeds. No real sleep."""
    import urllib.error, io
    slept = []
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None, context=None):
        calls["n"] += 1
        if calls["n"] == 1:
            hdrs = {"Retry-After": "7"}
            raise urllib.error.HTTPError(Q.API_URL, 429, "rate", hdrs, io.BytesIO(b"slow down"))
        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(_lp_response({"1": -1.0})).encode()
        return R()

    import alignment.q2_hosted as mod
    orig = mod.urllib.request.urlopen
    mod.urllib.request.urlopen = fake_urlopen
    try:
        t = Q.HostedTransport(key="k", retries=4, sleep=lambda s: slept.append(s))
        out = t({"x": 1}, {})
    finally:
        mod.urllib.request.urlopen = orig
    assert slept == [7.0]                 # honored the header, not the default backoff
    assert out["choices"][0]["logprobs"]["content"][0]["top_logprobs"][0]["token"] == "1"


def test_transport_hard_4xx_raises_skip():
    import urllib.error, io
    def fake_urlopen(req, timeout=None, context=None):
        raise urllib.error.HTTPError(Q.API_URL, 400, "bad", {}, io.BytesIO(b"bad request"))
    import alignment.q2_hosted as mod
    orig = mod.urllib.request.urlopen
    mod.urllib.request.urlopen = fake_urlopen
    try:
        t = Q.HostedTransport(key="k", retries=3, sleep=lambda s: None)
        with pytest.raises(SkipCellError):
            t({"x": 1}, {})
    finally:
        mod.urllib.request.urlopen = orig


def test_transport_exhausts_retries():
    import urllib.error, io
    def fake_urlopen(req, timeout=None, context=None):
        raise urllib.error.HTTPError(Q.API_URL, 503, "down", {}, io.BytesIO(b""))
    import alignment.q2_hosted as mod
    orig = mod.urllib.request.urlopen
    mod.urllib.request.urlopen = fake_urlopen
    try:
        t = Q.HostedTransport(key="k", retries=3, sleep=lambda s: None)
        with pytest.raises(urllib.error.HTTPError):
            t({"x": 1}, {})
    finally:
        mod.urllib.request.urlopen = orig


# =====================================================================================
# GROUP 3 — accounting (immutable atomic records; returned cost drives hard stops)
# =====================================================================================

def test_returned_cost_drives_the_ledger():
    assert Q.response_cost({"usage": {"cost": 0.0031}}) == pytest.approx(0.0031)
    assert Q.response_cost({"usage": {"total_cost": 0.002}}) == pytest.approx(0.002)
    assert Q.response_cost({"usage": {}}) == 0.0


def test_ledger_refuses_call_that_would_break_component_cap():
    led = Q.Ledger(topped_up=True)
    led.record("matrix", Q.CAPS["matrix"] - 0.005)
    led.check("matrix", 0.004)                       # still under
    with pytest.raises(Q.BudgetExceeded):
        led.check("matrix", 0.02)                    # would exceed matrix cap


def test_ledger_global_stop_overrides_component_room():
    led = Q.Ledger(topped_up=True)
    # pile spend into several buckets so the global stop binds before any single cap
    led.record("smoke", 1.0)
    led.record("matrix", 3.0)
    led.record("sampling", 3.7)
    assert led.study_total() == pytest.approx(7.7)
    led.check("reserve", 0.5)                         # 8.2 <= 8.5 ok
    with pytest.raises(Q.BudgetExceeded):
        led.check("reserve", 1.0)                     # 8.7 > 8.5 global stop


def test_pre_topup_ceiling_blocks_matrix_and_caps_smoke():
    led = Q.Ledger(topped_up=False)
    with pytest.raises(Q.BudgetExceeded):
        led.check("matrix", 0.001)                    # matrix may not start pre-top-up
    led.record("canary", 2.5)
    led.check("smoke", 0.4)                           # 2.9 <= 3.0 pre-top-up ceiling
    led.record("smoke", 0.4)
    with pytest.raises(Q.BudgetExceeded):
        led.check("smoke", 0.2)                       # 2.5+0.4+0.2 = 3.1 > 3.0 ceiling


def test_raw_record_is_immutable_and_atomic(tmp_path):
    store = Q.RawStore(tmp_path / "raw")
    store.put("abc", {"key": "abc", "cost": 0.001})
    assert store.get("abc")["cost"] == 0.001
    with pytest.raises(FileExistsError):
        store.put("abc", {"key": "abc", "cost": 999})   # never silently overwritten
    # no leftover temp files
    assert not list((tmp_path / "raw").glob("*.tmp"))


def test_execute_call_books_returned_cost_once(items, tmp_path):
    it = items["pol_surveillance"]
    spec = Q.CallSpec("openai/gpt-4o-mini-2024-07-18", "openai", "logprob",
                      "baseline::no_guard", it["id"], 0)
    resp = _lp_response({"1": math.log(.4), "2": math.log(.3), "3": math.log(.2),
                         "4": math.log(.1)}, cost=0.0007)
    calls = {"n": 0}
    def transport(body, headers):
        calls["n"] += 1
        return resp
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=False)
    rec = Q.execute_call(spec, it, transport, {}, led, store, "smoke", est_cost=0.01)
    assert rec["cost"] == pytest.approx(0.0007)
    assert led.spent["smoke"] == pytest.approx(0.0007)
    assert rec["coverage"]["all_present"] is True
    assert calls["n"] == 1


# =====================================================================================
# GROUP 4 — idempotence / restart
# =====================================================================================

def test_completed_call_resumes_without_paying(items, tmp_path):
    it = items["pol_surveillance"]
    spec = Q.CallSpec("m", "openai", "logprob", "baseline::no_guard", it["id"], 0)
    resp = _lp_response({"1": -1.0, "2": -1.0, "3": -1.0, "4": -1.0}, cost=0.0005)
    calls = {"n": 0}
    def transport(body, headers):
        calls["n"] += 1
        return resp
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=False)
    Q.execute_call(spec, it, transport, {}, led, store, "smoke", 0.01)
    # simulate restart: fresh ledger, same store; the call must NOT be re-sent or re-charged
    led2 = Q.Ledger(topped_up=False)
    rec = Q.execute_call(spec, it, transport, {}, led2, store, "smoke", 0.01)
    assert calls["n"] == 1                            # transport called exactly once ever
    assert led2.spent["smoke"] == 0.0                # resumed call costs nothing
    assert rec["cost"] == pytest.approx(0.0005)


def test_promoted_smoke_call_reused_once_in_matrix(items, tmp_path):
    """The 48 smoke calls are keyed by the full frozen request; the matrix run at the same
    coordinates hits the cache and is neither re-sent nor double-charged."""
    it = items["pol_ai_due_process"]
    smoke_spec = Q.CallSpec("m", "openai", "logprob", "data_only::system_guard", it["id"], 1,
                            smoke=True)
    resp = _lp_response({"1": -1.0, "2": -1.0, "3": -1.0, "4": -1.0}, cost=0.0006)
    calls = {"n": 0}
    def transport(body, headers):
        calls["n"] += 1
        return resp
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=True)
    Q.execute_call(smoke_spec, it, transport, {}, led, store, "smoke", 0.01)
    # matrix pass: same coordinates, different flag/bucket — same request key -> cache hit
    matrix_spec = Q.CallSpec("m", "openai", "logprob", "data_only::system_guard", it["id"], 1,
                             smoke=False)
    Q.execute_call(matrix_spec, it, transport, {}, led, store, "matrix", 0.01)
    assert calls["n"] == 1
    assert led.spent["matrix"] == 0.0                # reused, not re-billed to matrix


def test_independent_sampling_draws_are_not_deduped(items, tmp_path):
    it = items["pol_surveillance"]
    resp = _sample_response("2", cost=0.0001)
    calls = {"n": 0}
    def transport(body, headers):
        calls["n"] += 1
        return resp
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=True)
    for d in range(3):
        spec = Q.CallSpec("m", "openai", "sampling", "baseline::no_guard", it["id"], 0, draw=d)
        Q.execute_call(spec, it, transport, {}, led, store, "sampling", 0.01)
    assert calls["n"] == 3                            # each draw is its own paid call
    assert len(store.keys()) == 3


def test_partial_model_cannot_emit_headline(items):
    """hosted_estimands requires every cell present for the baseline probe set; a partial mass
    map raises rather than emitting a headline from incomplete data."""
    partial = {Q.cid_for("baseline", "no_guard"): {"pol_surveillance": 0.6}}
    with pytest.raises(KeyError):
        Q.hosted_estimands(partial)


# =====================================================================================
# GROUP 5 — counts + manifest
# =====================================================================================

def test_smoke_and_matrix_counts(items):
    ep = Q.PANEL[0]
    smoke = Q.enumerate_logprob_calls(ep, list(items), smoke_only=True)
    matrix = Q.enumerate_logprob_calls(ep, list(items), smoke_only=False)
    assert len(smoke) == 48
    assert len(matrix) == 528
    assert sum(s.smoke for s in matrix) == 48
    # all matrix specs are unique coordinates
    coords = {(s.cell_id, s.probe_id, s.order_idx) for s in matrix}
    assert len(coords) == 528


def test_sampling_counts(items):
    ep = Q.PANEL[0]
    assert len(Q.enumerate_sampling_calls(ep, list(items), full=True)) == 13200
    assert len(Q.enumerate_sampling_calls(ep, list(items), full=False)) == 9600


def test_manifest_is_hashed_and_stable(items):
    ep = Q.PANEL[0]
    specs = Q.enumerate_logprob_calls(ep, list(items), smoke_only=False)
    m1 = Q.manifest(specs)
    m2 = Q.manifest(specs)
    assert m1["n_calls"] == 528
    assert m1["sha256"] == m2["sha256"]              # deterministic
    assert len(m1["sha256"]) == 64


def test_write_manifest_atomic_and_refuses_overwrite(items, tmp_path):
    ep = Q.PANEL[0]
    specs = Q.enumerate_logprob_calls(ep, list(items), smoke_only=True)
    p = tmp_path / "manifest.json"
    sha = Q.write_manifest(p, specs)
    on_disk = json.loads(p.read_text())
    assert on_disk["n_calls"] == 48 and on_disk["sha256"] == sha
    assert not list(tmp_path.glob("*.tmp"))
    with pytest.raises(FileExistsError):
        Q.write_manifest(p, specs)


def test_canary_request_is_synthetic_and_well_formed():
    b = Q.build_canary_request(Q.PANEL[0])
    blob = json.dumps(b)
    # no probe / rights-floor content that could estimate a study contrast
    assert "rights floor" not in blob and "survey were" not in blob
    assert b["provider"]["only"] == ["openai"] and b["usage"] == {"include": True}
    assert b["temperature"] == 1.0 and b["seed"] == 0


def test_run_canary_books_to_canary_bucket(tmp_path):
    ep = Q.PANEL[0]
    resp = {"model": ep.model, "provider": "OpenAI",
            "choices": [{"logprobs": {"content": [{"top_logprobs": [{"token": "1",
                        "logprob": -0.1}]}]}}], "usage": {"cost": 0.0002}}
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=False)
    rec = Q.run_canary(ep, lambda b, h: resp, {}, led, store)
    assert rec["kind"] == "canary" and rec["provider_consistent"] is True
    assert led.spent["canary"] == pytest.approx(0.0002)
    assert led.study_total() == 0.0                  # canary is not study spend


def test_cli_refuses_paid_calls_without_acknowledgement(tmp_path):
    with pytest.raises(SystemExit):
        Q.main(["--out-dir", "out/nope", "--stage", "canary"])   # missing the ack flag


def test_hosted_estimands_recovers_constructed_effects(items):
    """A fully-populated mass map yields all eight frozen contrasts with the right signs."""
    ids = list(items)
    def cell(v):
        return {i: v for i in ids}
    mass = {
        Q.cid_for("baseline", "no_guard"): cell(0.80),
        Q.cid_for("instruction_only", "no_guard"): cell(0.30),   # instruction more harmful
        Q.cid_for("data_only", "no_guard"): cell(0.60),          # data mildly harmful
        Q.cid_for("combined", "no_guard"): cell(0.40),
        Q.cid_for("placebo", "no_guard"): cell(0.70),            # placebo moves floors
        Q.cid_for("data_only", "user_before"): cell(0.55),
        Q.cid_for("data_only", "user_after"): cell(0.78),        # recency recovers
        Q.cid_for("data_only", "system_guard"): cell(0.79),
        Q.cid_for("combined", "user_before"): cell(0.42),
        Q.cid_for("combined", "user_after"): cell(0.70),
        Q.cid_for("combined", "system_guard"): cell(0.68),
    }
    est = Q.hosted_estimands(mass, boot=200, seed=0)
    assert est["data_effect"]["mean"] == pytest.approx(-0.20, abs=1e-9)
    assert est["instruction_effect"]["mean"] == pytest.approx(-0.50, abs=1e-9)
    assert est["channel_contrast"]["mean"] == pytest.approx(0.30, abs=1e-9)
    assert est["placebo_effect"]["mean"] == pytest.approx(-0.10, abs=1e-9)
    assert est["data_placement"]["mean"] == pytest.approx(0.23, abs=1e-9)
    assert est["combined_placement"]["mean"] == pytest.approx(0.28, abs=1e-9)
    assert est["data_system_recovery"]["mean"] == pytest.approx(0.19, abs=1e-9)
    assert est["combined_system_recovery"]["mean"] == pytest.approx(0.28, abs=1e-9)


def test_run_smoke_is_outcome_blinded_and_promotes(items, tmp_path):
    """The full 48-call smoke driver returns a gate view with coverage/errors/cost only — no
    option scores or effect sizes — and promotes a model whose every call has all four options."""
    ep = Q.PANEL[0]
    full = {"1": math.log(.4), "2": math.log(.3), "3": math.log(.2), "4": math.log(.1)}
    calls = {"n": 0}
    def transport(body, headers):
        calls["n"] += 1
        return _lp_response(full, cost=0.0005, provider="OpenAI")
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=False)
    view = Q.run_smoke(ep, items, transport, {}, led, store)
    assert calls["n"] == 48 and view["n_calls"] == 48 and view["n_scored"] == 48
    assert view["promote"] is True and view["all_calls_full_coverage"] is True
    assert view["provider_consistent"] is True and view["resolved_providers"] == ["OpenAI"]
    # blinding: the gate view leaks no substantive scores
    blob = json.dumps(view)
    assert "display" not in blob and "per_option_mass" not in blob and "protective" not in blob
    # but the raw store DID persist the full scored records
    assert len(store.keys()) == 48
    assert "display" in store.get(store.keys()[0])


def test_run_smoke_fails_promotion_on_missing_option(items, tmp_path):
    ep = Q.PANEL[0]
    missing4 = {"1": math.log(.5), "2": math.log(.3), "3": math.log(.2)}   # never returns "4"
    def transport(body, headers):
        return _lp_response(missing4, cost=0.0004, provider="OpenAI")
    store = Q.RawStore(tmp_path / "raw")
    led = Q.Ledger(topped_up=False)
    view = Q.run_smoke(ep, items, transport, {}, led, store)
    assert view["promote"] is False
    assert view["all_calls_full_coverage"] is False


def test_aggregate_logprob_mass_averages_orders(items, tmp_path):
    """Four order records for one (cell, probe) fold into one protective-mass scalar via the
    frozen display->canonical remap."""
    it = items["pol_ai_due_process"]
    n = len(it["scale"]["labels"])
    records = []
    for oi in range(4):
        # a flat display vector; after remap+normalise each canonical option is 1/n
        records.append({"path": "logprob", "cell_id": "baseline::no_guard",
                        "probe_id": it["id"], "order_idx": oi,
                        "display": [1.0 / n] * n})
    mass = Q.aggregate_logprob_mass(records, items)
    pm = mass["baseline::no_guard"][it["id"]]
    assert 0.0 <= pm <= 1.0
    # uniform distribution -> protective mass is exactly half (floor_dir splits 4 options 2/2)
    assert pm == pytest.approx(0.5, abs=1e-6)
