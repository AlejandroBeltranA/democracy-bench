"""Tests for the Q2 Stage-2 v7.2 outcome-blinding interlock, and for the unified
dated-upstream-model rule that closes the two-audits deviation.

Two frozen requirements are under test:

1. **The promotion-and-funding blinding interlock** (v7 "Outcome-blinding interlock", as
   revised by R-V7-7). No substantive outcome becomes visible until BOTH the endpoint-
   promotion decision and the funding decision are recorded; headline aggregation refuses
   to run until both records exist. The interlock is PROCEDURAL: raw persisted responses
   necessarily contain substantive answers and are not claimed to be sealed. What is
   mechanised is that the runner/gate reports never display or aggregate them, and that
   aggregation refuses to start.

2. **R-V7-4 "resolved model/version evidence"** — one rule, applied identically by
   `envelope.verify_provider_audit` and `gate.audit_envelope`: the returned evidence must
   resolve to the candidate's DATED upstream checkpoint id. The version-free catalog slug
   is not version evidence, and a different dated checkpoint fails both paths.

NO NETWORK. Every fixture is a local dict or the committed snapshot file on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import interlock as I
from alignment.q2_v7 import ledger as L

QWEN = "qwen/qwen3.5-397b-a17b"
TAG = "alibaba"
MANIFEST = "b" * 64
OTHER_MANIFEST = "c" * 64

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "out" / "q2_stage2_endpoint_snapshot" / "manifest.json"


@pytest.fixture(scope="module")
def snap_candidate():
    return E.load_snapshot(SNAPSHOT).candidate(QWEN, TAG)


# =======================================================================================
# 1. The immutable, persisted records
# =======================================================================================

def test_promotion_record_round_trips_and_binds_to_the_manifest(tmp_path):
    rec = I.record_promotion(
        tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG,
        promoted_endpoint_name="Alibaba | qwen/qwen3.5-397b-a17b-20260216",
        projection_total_usd=3.21, recorded_by="operator")
    assert rec.recorded_utc.endswith("Z") and len(rec.recorded_utc) == 20
    assert rec.promoted_upstream_model == "qwen/qwen3.5-397b-a17b-20260216"

    path = I.promotion_record_path(tmp_path)
    assert path.exists()
    stored = json.loads(path.read_text())
    assert stored["schema"] == I.PROMOTION_SCHEMA
    assert stored["manifest_sha256"] == MANIFEST
    assert stored["promoted_tag"] == TAG
    assert stored["projection_total_usd"] == pytest.approx(3.21)
    assert stored["binding_sha256"] == rec.binding_sha256

    assert I.load_promotion_record(tmp_path) == rec


def test_funding_record_round_trips_and_binds_to_the_manifest(tmp_path):
    rec = I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True,
                           decision="topped up", available_usd=8.50, hard_stop_usd=8.50,
                           reconciled_prior_usd=0.031)
    stored = json.loads(I.funding_record_path(tmp_path).read_text())
    assert stored["schema"] == I.FUNDING_SCHEMA
    assert stored["authorized"] is True
    assert stored["manifest_sha256"] == MANIFEST
    assert I.load_funding_record(tmp_path) == rec


def test_binding_digest_changes_with_the_manifest():
    """The hash BINDS the decision to one run: the same decision under another manifest is
    a different record, so a record cannot be silently reused across runs."""
    a = I.PromotionRecord(model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG,
                          recorded_utc="2026-07-28T00:00:00Z")
    b = I.PromotionRecord(model=QWEN, manifest_sha256=OTHER_MANIFEST, promoted_tag=TAG,
                          recorded_utc="2026-07-28T00:00:00Z")
    assert a.binding_sha256 != b.binding_sha256


@pytest.mark.parametrize("field,value", [
    ("promoted_tag", "digitalocean"),
    ("projection_total_usd", 99.0),
    ("manifest_sha256", OTHER_MANIFEST),
    ("excluded", True),
])
def test_an_edited_promotion_record_fails_to_load(tmp_path, field, value):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG,
                       projection_total_usd=1.0)
    path = I.promotion_record_path(tmp_path)
    doc = json.loads(path.read_text())
    doc[field] = value
    path.chmod(0o644)
    path.write_text(json.dumps(doc))
    with pytest.raises(I.RecordBindingError):
        I.load_promotion_record(tmp_path)


def test_records_are_write_once(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    with pytest.raises(I.RecordExistsError):
        I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST,
                           promoted_tag="digitalocean")
    I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True)
    with pytest.raises(I.RecordExistsError):
        I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=False)
    # the first decision survives
    assert I.load_promotion_record(tmp_path).promoted_tag == TAG
    assert I.load_funding_record(tmp_path).authorized is True


def test_a_record_must_be_bound_to_a_manifest(tmp_path):
    with pytest.raises(I.RecordBindingError):
        I.record_promotion(tmp_path, model=QWEN, manifest_sha256="", promoted_tag=TAG)
    with pytest.raises(I.RecordBindingError):
        I.record_funding(tmp_path, manifest_sha256="", authorized=True)


def test_an_exclusion_is_also_a_recorded_promotion_decision(tmp_path):
    rec = I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST,
                             excluded=True, exclusion_reason="budget")
    assert rec.excluded is True and rec.promoted_tag is None
    assert I.load_promotion_record(tmp_path).exclusion_reason == "budget"


# =======================================================================================
# 2. interlock_state / require_headline_permitted
# =======================================================================================

def test_state_reports_neither_record_on_a_fresh_run(tmp_path):
    st = I.interlock_state(tmp_path)
    assert st.promotion_recorded is False and st.funding_recorded is False
    assert st.missing == ("promotion", "funding")
    assert st.headline_permitted is False


def test_state_reports_a_partially_recorded_interlock(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    st = I.interlock_state(tmp_path)
    assert st.promotion_recorded is True and st.funding_recorded is False
    assert st.missing == ("funding",)
    assert st.headline_permitted is False


def test_state_permits_the_headline_only_once_both_records_exist(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True)
    st = I.interlock_state(tmp_path, MANIFEST)
    assert st.headline_permitted is True and st.ok is True
    assert st.missing == () and st.binding_failures == ()
    assert st.as_dict()["headline_permitted"] is True


@pytest.mark.parametrize("write_promotion,write_funding", [
    (False, False), (True, False), (False, True),
])
def test_headline_aggregation_refuses_to_run_until_both_records_exist(
        tmp_path, write_promotion, write_funding):
    if write_promotion:
        I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    if write_funding:
        I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True)
    with pytest.raises(I.HeadlineBlocked) as exc:
        I.require_headline_permitted(tmp_path)
    assert "refuses to run" in str(exc.value)


def test_require_headline_permitted_returns_the_state_when_both_exist(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True)
    st = I.require_headline_permitted(tmp_path, MANIFEST)
    assert isinstance(st, I.InterlockState) and st.headline_permitted


def test_records_bound_to_another_manifest_do_not_unblock_the_headline(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=OTHER_MANIFEST,
                       promoted_tag=TAG)
    I.record_funding(tmp_path, manifest_sha256=OTHER_MANIFEST, authorized=True)
    st = I.interlock_state(tmp_path, MANIFEST)
    assert st.headline_permitted is False and len(st.binding_failures) == 2
    with pytest.raises(I.HeadlineBlocked):
        I.require_headline_permitted(tmp_path, MANIFEST)


def test_a_tampered_record_leaves_the_headline_blocked(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True)
    path = I.promotion_record_path(tmp_path)
    path.chmod(0o644)
    path.write_text('{"schema": "q2_v7.promotion_record.v1"}')
    st = I.interlock_state(tmp_path)
    assert st.headline_permitted is False
    with pytest.raises(I.HeadlineBlocked):
        I.require_headline_permitted(tmp_path)


# =======================================================================================
# 2b. PF-1 — the PS-1 staged-authorization records that actually paid for the run
# =======================================================================================
#
# `study_run` writes `interlock/promotion_record_<model>.json` per panel model plus one
# `interlock/funding_record_panel.json`. Headline extraction must CONSUME AND VALIDATE those
# records — not ask an operator to re-record a second, weaker pair of decisions that could
# diverge from the ones that authorized the paid draws. Every fixture below is either the
# real committed panel run directory (read-only) or a copy of it under tmp_path.

PANEL_RUN = REPO / "out" / "q2_stage2_v7_run_panel"
DEEPSEEK = "deepseek/deepseek-v4-pro"
PANEL_MODELS = (QWEN, DEEPSEEK)


def _panel_manifest_sha(run_dir: Path, model: str) -> str:
    """The recomputed extraction manifest digest for one panel model."""
    from alignment.q2_v7 import identity as ID
    body = json.loads((run_dir / f"manifest_{model.replace('/', '__')}.json").read_text())
    return ID.canonical_sha256(body)


def _sign(doc: dict) -> dict:
    """Re-sign a record the way BOTH writers do, recomputed here from first principles:
    sha256 over the canonical payload with `binding_sha256` removed. A tamper case that is
    re-signed is cryptographically VALID — it must still be refused on its content."""
    import hashlib
    payload = {k: v for k, v in doc.items() if k != "binding_sha256"}
    out = dict(payload)
    out["binding_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return out


@pytest.fixture
def panel(tmp_path):
    """A WRITABLE copy of the immutable paid panel run's authorization evidence.

    `out/q2_stage2_v7_run_panel/` is paid evidence and is never mutated by a test; only the
    files a tamper case needs are copied, and the copies are made writable."""
    import shutil
    run = tmp_path / "run"
    (run / I.INTERLOCK_DIRNAME).mkdir(parents=True)
    for src in sorted((PANEL_RUN / I.INTERLOCK_DIRNAME).glob("*.json")):
        dst = run / I.INTERLOCK_DIRNAME / src.name
        shutil.copyfile(src, dst)
        dst.chmod(0o644)
    for model in PANEL_MODELS:
        name = f"manifest_{model.replace('/', '__')}.json"
        shutil.copyfile(PANEL_RUN / name, run / name)
    return run


@pytest.mark.parametrize("model", PANEL_MODELS)
def test_the_real_paid_panel_run_unblocks_the_headline_for_each_model(model):
    """PF-1 regression, against the untouched committed run directory.

    Before the fix this reported `promotion_recorded: false, funding_recorded: false,
    missing: [promotion, funding]` — a complete, fully paid 13,200-draw run refused at
    headline extraction because only the legacy singular filenames were looked for."""
    st = I.require_headline_permitted(
        PANEL_RUN, _panel_manifest_sha(PANEL_RUN, model), model)
    assert st.scheme == I.SCHEME_PS1 and st.model == model
    assert st.promotion_recorded and st.funding_recorded
    assert st.missing == () and st.binding_failures == ()
    assert st.ps1_promotion["model"] == model and st.ps1_funding["authorized"] is True
    # and it does so WITHOUT any legacy singular record present
    assert not I.promotion_record_path(PANEL_RUN).exists()
    assert not I.funding_record_path(PANEL_RUN).exists()


def test_the_ps1_names_and_schemas_track_the_runner_that_writes_them():
    """The one place the two modules could silently drift apart is pinned here."""
    from alignment.q2_v7 import study_run as S
    assert I.PS1_PROMOTION_SCHEMA == S.AUTHORIZATION_PROMOTION_SCHEMA
    assert I.PS1_FUNDING_SCHEMA == S.AUTHORIZATION_FUNDING_SCHEMA
    assert I.PS1_FUNDING_RECORD_FILENAME == S.FUNDING_AUTHORIZATION_FILENAME
    for model in PANEL_MODELS:
        assert I.ps1_promotion_record_path(PANEL_RUN, model) == \
            S.promotion_authorization_path(PANEL_RUN, model)
    assert I.ps1_funding_record_path(PANEL_RUN) == S.funding_authorization_path(PANEL_RUN)


@pytest.mark.parametrize("model", PANEL_MODELS)
def test_a_missing_promotion_record_for_this_model_blocks(panel, model):
    I.ps1_promotion_record_path(panel, model).unlink()
    st = I.interlock_state(panel, _panel_manifest_sha(panel, model), model)
    assert st.promotion_recorded is False and st.headline_permitted is False
    assert "promotion" in " ".join(st.binding_failures)
    with pytest.raises(I.HeadlineBlocked):
        I.require_headline_permitted(panel, _panel_manifest_sha(panel, model), model)


def test_a_missing_panel_funding_record_blocks(panel):
    I.ps1_funding_record_path(panel).unlink()
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.funding_recorded is False and st.headline_permitted is False
    with pytest.raises(I.HeadlineBlocked):
        I.require_headline_permitted(panel, _panel_manifest_sha(panel, QWEN), QWEN)


@pytest.mark.parametrize("field,value", [
    ("promoted_tag", "digitalocean"),
    ("manifest_sha256", "f" * 64),
    ("projection_artifact_sha256", "f" * 64),
    ("excluded", True),
    ("model", DEEPSEEK),
])
def test_an_edited_promotion_record_blocks(panel, field, value):
    """Editing WITHOUT re-signing breaks `binding_sha256`, so the record fails to load."""
    path = I.ps1_promotion_record_path(panel, QWEN)
    doc = json.loads(path.read_text())
    doc[field] = value
    path.write_text(json.dumps(doc))
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False
    assert "binding_sha256" in " ".join(st.binding_failures)


def test_an_edited_funding_record_blocks(panel):
    path = I.ps1_funding_record_path(panel)
    doc = json.loads(path.read_text())
    doc["authorized"] = True
    doc["hard_stop_usd"] = 9999.0
    path.write_text(json.dumps(doc))
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False
    assert "binding_sha256" in " ".join(st.binding_failures)


def test_a_cross_model_promotion_record_blocks(panel):
    """DeepSeek's decision moved onto Qwen's filename. The move keeps `binding_sha256`
    valid — the record is intact — so only the model check can catch it."""
    import shutil
    shutil.copyfile(I.ps1_promotion_record_path(panel, DEEPSEEK),
                    I.ps1_promotion_record_path(panel, QWEN))
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False
    assert any("not 'qwen/qwen3.5-397b-a17b'" in f for f in st.binding_failures)


def test_another_models_manifest_does_not_unblock_this_model(panel):
    """Qwen's promotion record does not authorize a headline over DeepSeek's manifest."""
    st = I.interlock_state(panel, _panel_manifest_sha(panel, DEEPSEEK), QWEN)
    assert st.headline_permitted is False
    assert any("recomputed extraction manifest" in f for f in st.binding_failures)


def test_a_stale_manifest_blocks(panel):
    st = I.interlock_state(panel, "a" * 64, QWEN)
    assert st.headline_permitted is False
    assert any("not the recomputed extraction manifest" in f for f in st.binding_failures)


def test_a_staged_authorization_is_never_accepted_unbound(panel):
    """Without a recomputed manifest digest to check against, there is nothing binding the
    record to THIS extraction — so it is refused rather than waved through."""
    st = I.interlock_state(panel, None, QWEN)
    assert st.headline_permitted is False
    assert any("without the recomputed run manifest digest" in f
               for f in st.binding_failures)


def test_a_panel_run_refuses_to_guess_which_model_is_being_extracted(panel):
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN))
    assert st.headline_permitted is False
    assert any("refusing to guess" in f for f in st.binding_failures)


def test_a_refused_funding_decision_blocks(panel):
    """`authorized=False` is a validly recorded REFUSAL, correctly signed. It must not
    unblock anything — the legacy `interlock_state` never checked this field at all."""
    path = I.ps1_funding_record_path(panel)
    doc = _sign({**json.loads(path.read_text()), "authorized": False,
                 "decision": "refused: out of budget"})
    path.write_text(json.dumps(doc))
    assert I.load_ps1_funding_record(panel)["authorized"] is False    # signature is valid
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False
    assert any("REFUSES this run" in f for f in st.binding_failures)


@pytest.mark.parametrize("field", [
    "manifest_sha256", "projection_artifact_sha256", "promotion_binding_sha256",
    "endpoint_tag",
])
def test_an_internally_inconsistent_funding_record_blocks(panel, field):
    """A correctly signed funding record whose Qwen row disagrees with the Qwen promotion
    record it claims to fund. The signature proves only that nobody edited it afterwards —
    it says nothing about whether the two decisions agree."""
    path = I.ps1_funding_record_path(panel)
    doc = json.loads(path.read_text())
    for row in doc["models"]:
        if row["model"] == QWEN:
            row[field] = "digitalocean" if field == "endpoint_tag" else "e" * 64
    path.write_text(json.dumps(_sign(doc)))
    assert I.load_ps1_funding_record(panel) is not None               # signature is valid
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False and st.binding_failures
    # the OTHER panel model is untouched and still authorized
    assert I.interlock_state(panel, _panel_manifest_sha(panel, DEEPSEEK),
                             DEEPSEEK).headline_permitted is True


def test_a_funding_record_that_does_not_cover_this_model_blocks(panel):
    path = I.ps1_funding_record_path(panel)
    doc = json.loads(path.read_text())
    doc["models"] = [r for r in doc["models"] if r["model"] != QWEN]
    path.write_text(json.dumps(_sign(doc)))
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False
    assert any("does not cover" in f for f in st.binding_failures)


def test_an_excluded_model_has_no_headline(panel):
    path = I.ps1_promotion_record_path(panel, QWEN)
    doc = _sign({**json.loads(path.read_text()), "excluded": True,
                 "exclusion_reason": "budget"})
    path.write_text(json.dumps(doc))
    st = I.interlock_state(panel, _panel_manifest_sha(panel, QWEN), QWEN)
    assert st.headline_permitted is False
    assert any("EXCLUDES" in f for f in st.binding_failures)


def test_valid_ps1_records_need_no_legacy_records_but_legacy_cannot_rescue_them(panel):
    """Backward compatibility runs one way only. The legacy singular records are not
    required when PS-1 records are present (that was PF-1), and — because presence, not
    validity, selects the scheme — they cannot be used to launder a broken PS-1 record."""
    sha = _panel_manifest_sha(panel, QWEN)
    assert I.interlock_state(panel, sha, QWEN).headline_permitted is True

    I.record_promotion(panel, model=QWEN, manifest_sha256=sha, promoted_tag=TAG)
    I.record_funding(panel, manifest_sha256=sha, authorized=True)
    assert I.interlock_state(panel, sha, QWEN).scheme == I.SCHEME_PS1

    I.ps1_promotion_record_path(panel, QWEN).unlink()
    st = I.interlock_state(panel, sha, QWEN)
    assert st.scheme == I.SCHEME_PS1 and st.headline_permitted is False


def test_the_legacy_scheme_is_untouched_when_no_ps1_record_exists(tmp_path):
    I.record_promotion(tmp_path, model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    I.record_funding(tmp_path, manifest_sha256=MANIFEST, authorized=True)
    st = I.interlock_state(tmp_path, MANIFEST, QWEN)
    assert st.scheme == I.SCHEME_LEGACY and st.headline_permitted is True
    # a legacy record for another model is still refused when the model is named
    blocked = I.interlock_state(tmp_path, MANIFEST, DEEPSEEK)
    assert blocked.headline_permitted is False


def test_the_pure_predicate_reads_a_ps1_record_pair():
    promotion = I.load_ps1_promotion_record(PANEL_RUN, QWEN)
    funding = I.load_ps1_funding_record(PANEL_RUN)
    assert I.blinding_interlock(promotion, funding) is True
    assert I.blinding_interlock(promotion, {**funding, "authorized": False}) is False


# =======================================================================================
# 3. The pure `blinding_interlock` predicate
# =======================================================================================

def test_blinding_interlock_refuses_until_both_decisions_are_recorded():
    assert I.blinding_interlock(None, None) is False
    assert I.blinding_interlock({"promoted_tag": TAG}, None) is False
    assert I.blinding_interlock(None, {"authorized": True}) is False
    assert I.blinding_interlock({}, {}) is False
    assert I.blinding_interlock({"promoted_tag": TAG}, {"authorized": True}) is True


def test_a_funding_refusal_does_not_unblock_the_headline():
    assert I.blinding_interlock({"promoted_tag": TAG}, {"authorized": False}) is False


def test_blinding_interlock_accepts_the_persisted_dataclasses():
    p = I.PromotionRecord(model=QWEN, manifest_sha256=MANIFEST, promoted_tag=TAG)
    f = I.FundingRecord(manifest_sha256=MANIFEST, authorized=True)
    assert I.blinding_interlock(p, f) is True
    assert I.blinding_interlock(p, I.FundingRecord(manifest_sha256=MANIFEST,
                                                  authorized=False)) is False
    excluded = I.PromotionRecord(model=QWEN, manifest_sha256=MANIFEST, excluded=True,
                                 exclusion_reason="budget")
    assert I.blinding_interlock(excluded, f) is True


def test_the_predicate_is_reachable_from_the_package_and_the_gate():
    """The interlock must be discoverable where aggregation code looks for it."""
    import alignment.q2_v7 as PKG
    assert PKG.blinding_interlock is I.blinding_interlock
    assert G.blinding_interlock is I.blinding_interlock
    assert G.require_headline_permitted is I.require_headline_permitted


# =======================================================================================
# 4. The outcome-blinded operator view
# =======================================================================================

MARKER = "ZQXJ-substantive-answer-marker"


def _env(draw_index: int, reply, *, status: int = 200, cost=0.00002,
         cost_status: str = "returned", provider: str = "Alibaba",
         upstream: str = "qwen/qwen3.5-397b-a17b-20260216") -> dict:
    """A raw-envelope-shaped dict whose reply is a REAL answer."""
    return {
        "draw_id": f"{'a' * 64}#{draw_index}",
        "request_sha256": "a" * 64,
        "draw_index": draw_index,
        "http_status": status,
        "model": QWEN,
        "provider": provider,
        "cost_usd": cost,
        "cost_status": cost_status,
        "usage": {"prompt_tokens": 100, "completion_tokens": 1, "total_tokens": 101},
        "openrouter_metadata": {
            "requested": QWEN, "strategy": "direct", "attempt": 1, "is_byok": False,
            "endpoints": {"available": [{"provider": provider, "model": upstream,
                                         "selected": True}]},
        },
        "response_body": {"choices": [{"message": {"role": "assistant",
                                                   "content": reply}}]},
        "response_headers": {},
        "stage": "smoke",
        "bucket": "study",
    }


def test_gate_view_exposes_only_the_permitted_sections():
    view = I.gate_view([_env(i, "3") for i in range(5)])
    assert set(view) == set(I.GATE_VIEW_SECTIONS) | {
        "schema", "blinded", "blinding", "blinding_rule"}
    assert view["blinded"] is True and view["blinding"] == "procedural"
    assert view["request_integrity"]["n_envelopes"] == 5
    assert view["parse_coverage"]["n_parseable"] == 5
    assert view["cost"]["cumulative_usd"] == pytest.approx(5 * 0.00002)
    assert view["usage"]["prompt_tokens"] == 500
    assert view["resolved_provider"] == [
        {"model": QWEN, "provider": "Alibaba",
         "upstream_model": "qwen/qwen3.5-397b-a17b-20260216", "n": 5}]


def test_gate_view_carries_no_substantive_answer_content_for_real_answers():
    """Fed envelopes whose replies are REAL answers, the operator view contains no answer.

    Checked three ways: no substantive key survives the structural check, no reply string
    appears anywhere in the serialised view, and — the decisive one — two runs whose answers
    are entirely different but whose parse outcomes agree produce IDENTICAL views. A view
    that leaked a choice frequency, contrast, direction, or effect size could not do that.
    """
    all_one = [_env(i, "1") for i in range(25)]
    all_four = [_env(i, "4") for i in range(25)]
    split = [_env(i, "1" if i < 13 else "4") for i in range(25)]

    a = I.gate_view(all_one)
    b = I.gate_view(all_four)
    c = I.gate_view(split)
    assert a == b == c, (
        "the outcome-blinded view must be a function of non-substantive facts only; "
        "distinguishing all-1 from all-4 from a 13/12 split is a choice frequency"
    )

    blob = json.dumps(a)
    for reply in ("\"1\"", "\"4\""):
        assert reply not in blob
    I.assert_outcome_blinded(a)


def test_gate_view_never_echoes_reply_text():
    prose = [_env(i, f"I choose 3 because {MARKER}") for i in range(4)]
    view = I.gate_view(prose)
    assert MARKER not in json.dumps(view)
    # the prose is still COUNTED as unparseable -- coverage is permitted, content is not
    assert view["parse_coverage"]["n_parseable"] == 0
    assert view["parse_coverage"]["unparseable"]["not_anchored"] == 4
    assert view["parse_coverage"]["parse_rate"] == pytest.approx(0.0)


def test_gate_view_reports_parse_coverage_without_reporting_the_options():
    envs = ([_env(i, "2") for i in range(18)]
            + [_env(i, "") for i in range(18, 20)]
            + [_env(i, "9") for i in range(20, 22)]
            + [_env(i, "the third one") for i in range(22, 25)])
    view = I.gate_view(envs, expected_draws=25)
    cov = view["parse_coverage"]
    assert cov["n_responses"] == 25 and cov["n_parseable"] == 18
    assert cov["parse_rate"] == pytest.approx(18 / 25)
    assert cov["coverage_rate"] == pytest.approx(1.0)
    assert cov["unparseable"] == {"empty": 2, "not_anchored": 3, "out_of_range": 2}
    # `out_of_range` names the failure mode, never the digit that caused it
    assert "9" not in json.dumps(cov)


def test_gate_view_reports_request_integrity_errors_usage_and_cumulative_cost():
    envs = [_env(0, "1"), _env(0, "1"),                                  # duplicate draw id
            _env(2, None, status=429, cost=None, cost_status="missing"),
            _env(3, "2", cost=0.0, cost_status="cache_hit_zero")]
    view = I.gate_view(envs, prior_usd=0.031)
    ri = view["request_integrity"]
    assert ri["n_envelopes"] == 4 and ri["n_unique_draw_ids"] == 3
    assert ri["n_duplicate_draw_ids"] == 1 and ri["n_unique_request_sha256"] == 1
    err = view["errors"]
    assert err["n_http_ok"] == 3 and err["n_http_error"] == 1
    assert err["status_counts"] == {"200": 3, "429": 1}
    assert err["n_cache_hit"] == 1 and err["n_missing_cost"] == 1
    assert view["cost"]["prior_usd"] == pytest.approx(0.031)
    assert view["cost"]["cumulative_usd"] == pytest.approx(0.031 + 0.00002 * 2)
    assert view["cost"]["n_costed"] == 3


def test_gate_view_accepts_the_real_raw_envelope_artifact():
    raw = L.RawEnvelope(
        draw_id=f"{'a' * 64}#0", request_sha256="a" * 64, draw_index=0,
        request_body={}, request_headers={},
        response_body={"choices": [{"message": {"content": "3"}}]},
        response_headers={}, http_status=200, generation_id="gen-1",
        timestamp="2026-07-28T00:00:00Z",
        usage={"prompt_tokens": 100, "completion_tokens": 1, "total_tokens": 101},
        cost_usd=0.00002, cost_status="returned",
        openrouter_metadata={"endpoints": {"available": [
            {"provider": "Alibaba", "model": "qwen/qwen3.5-397b-a17b-20260216",
             "selected": True}]}},
        bucket="study", model=QWEN, provider="Alibaba", stage="smoke")
    view = I.gate_view([raw])
    assert view["parse_coverage"]["n_parseable"] == 1
    assert view["cost"]["returned_usd"] == pytest.approx(0.00002)
    assert "3" not in json.dumps(view["parse_coverage"]["unparseable"])


def test_gate_view_of_an_empty_run_is_well_defined():
    view = I.gate_view([])
    assert view["parse_coverage"]["parse_rate"] is None
    assert view["cost"]["cumulative_usd"] == 0.0
    I.assert_outcome_blinded(view)


@pytest.mark.parametrize("section,payload", [
    ("choice_frequencies", {"1": 12, "4": 13}),
    ("contrasts", {"evidence_in_context": 0.21}),
    ("effect_size", 0.3),
    ("headline", {"protective_mass": 0.5}),
])
def test_assert_outcome_blinded_rejects_a_view_carrying_an_outcome(section, payload):
    view = I.gate_view([_env(0, "3")])
    view[section] = payload
    with pytest.raises(I.BlindingViolation):
        I.assert_outcome_blinded(view)


def test_assert_outcome_blinded_rejects_a_nested_outcome_key():
    view = I.gate_view([_env(0, "3")])
    view["parse_coverage"]["choice_counts"] = {"3": 1}
    with pytest.raises(I.BlindingViolation) as exc:
        I.assert_outcome_blinded(view)
    assert "parse_coverage.choice_counts" in str(exc.value)


# =======================================================================================
# 5. R-V7-4: ONE dated-upstream-model rule, applied identically by both audit paths
# =======================================================================================

def _gate_candidate(sc) -> G.EndpointCandidate:
    return G.EndpointCandidate(
        model=sc.model, tag=sc.tag, provider_name=sc.provider_name,
        endpoint_name=sc.endpoint_name, quantization=sc.quantization,
        price_prompt_per_token=float(sc.price_prompt_per_token),
        price_completion_per_token=float(sc.price_completion_per_token))


def _envelope_path(sc, evidence) -> E.AuditResult:
    """The `envelope.verify_provider_audit` verdict for one piece of model evidence."""
    response = {
        "openrouter_metadata": {
            "requested": sc.model, "strategy": "direct", "attempt": 1, "is_byok": False,
            "endpoints": {"available": [{"provider": sc.provider_name, "model": evidence,
                                         "selected": True}]},
        },
    }
    return E.verify_provider_audit(response, sc.model, sc.tag,
                                   E.load_snapshot(SNAPSHOT))


def _gate_path(sc, evidence) -> tuple[str, ...]:
    """The `gate.audit_envelope` verdict for the same piece of model evidence."""
    probe = G.EndpointProbeResult(
        tag=sc.tag, http_status=200, requested_provider_only=(sc.tag,),
        n_candidates_available=1, selected_provider_name=sc.provider_name,
        requested_model=sc.model, returned_model_evidence=evidence, strategy="direct",
        attempt=1, fallback_occurred=False, is_byok=False, reasoning_tokens=0,
        has_reasoning_payload=False, usage_fields_present=True, parsed_leading_digit=3,
        billed_completion_tokens=1)
    return G.audit_envelope(probe, _gate_candidate(sc))


def test_the_gate_candidate_exposes_the_dated_upstream_model(snap_candidate):
    cand = _gate_candidate(snap_candidate)
    assert cand.upstream_model == snap_candidate.upstream_model
    assert cand.upstream_model == "qwen/qwen3.5-397b-a17b-20260216"
    assert cand.upstream_model != cand.model, "the catalog slug carries no version"


@pytest.mark.parametrize("evidence_kind", ["bare_upstream", "endpoint_name"])
def test_correct_dated_evidence_passes_both_paths(snap_candidate, evidence_kind):
    evidence = (snap_candidate.upstream_model if evidence_kind == "bare_upstream"
                else snap_candidate.endpoint_name)
    assert _envelope_path(snap_candidate, evidence).ok is True
    assert _gate_path(snap_candidate, evidence) == ()


@pytest.mark.parametrize("evidence,why", [
    ("qwen/qwen3.5-397b-a17b-19700101", "a DIFFERENT dated checkpoint"),
    ("qwen/qwen3.5-397b-a17b-20260215", "an off-by-one-day checkpoint"),
    ("Alibaba | qwen/qwen3.5-397b-a17b-19700101", "a different checkpoint, endpoint form"),
    ("qwen/qwen3.5-397b-a17b", "the version-free catalog slug: no version evidence at all"),
    ("Alibaba | qwen/qwen3.5-397b-a17b", "the slug behind an endpoint-name prefix"),
    ("DigitalOcean | qwen/qwen3.5-397b-a17b-20260216", "the right checkpoint, wrong provider"),
    (None, "no evidence"),
    ("", "empty evidence"),
])
def test_a_different_dated_checkpoint_fails_both_paths_identically(
        snap_candidate, evidence, why):
    """R-V7-4: the gate's old rule accepted the bare `candidate.model`, so a provider
    serving a different dated checkpoint could satisfy 'resolved model/version evidence'
    simply by returning the version-free slug. Both paths now refuse, with the same code."""
    env_result = _envelope_path(snap_candidate, evidence)
    gate_failures = _gate_path(snap_candidate, evidence)

    assert env_result.ok is False, why
    assert gate_failures, why
    assert any(f.startswith("returned_model_mismatch") for f in env_result.failures), why
    assert any("returned_model_mismatch" in f for f in gate_failures), why
    assert any("returned_model_evidence" in f for f in gate_failures), (
        "the gate keeps its historical failure vocabulary while delegating the rule")


@pytest.mark.parametrize("evidence", [
    "qwen/qwen3.5-397b-a17b",
    "qwen/qwen3.5-397b-a17b-19700101",
    None,
])
def test_both_paths_agree_on_every_evidence_value(snap_candidate, evidence):
    """The two audits must never disagree: that divergence WAS the deviation."""
    env_ok = _envelope_path(snap_candidate, evidence).ok
    gate_ok = not _gate_path(snap_candidate, evidence)
    assert env_ok == gate_ok


def test_gate_audit_delegates_rather_than_restating_the_proof():
    """`gate.audit_envelope` must not carry its own copy of the C1 provider proof."""
    src = (REPO / "src" / "alignment" / "q2_v7" / "gate.py").read_text()
    body = src.split("def audit_envelope(", 1)[1].split("\ndef ", 1)[0]
    assert "verify_provider_audit" in body, (
        "audit_envelope must delegate the C1 proof to envelope.verify_provider_audit"
    )
    for restated in ("candidate.provider_name", "candidate.endpoint_name", "!= 'direct'"):
        assert restated not in body, (
            f"audit_envelope still restates the proof locally ({restated!r})"
        )


def test_resolved_model_evidence_normalisation_rules():
    dated = "qwen/qwen3.5-397b-a17b-20260216"
    assert E.resolved_model_evidence(dated) == dated
    assert E.resolved_model_evidence(f"Alibaba | {dated}") == dated
    assert E.resolved_model_evidence(f"Alibaba | {dated}", "Alibaba") == dated
    assert E.resolved_model_evidence(f"Alibaba | {dated}", "DigitalOcean") is None
    assert E.resolved_model_evidence(None) is None
    assert E.resolved_model_evidence("") is None
    assert E.resolved_model_evidence("   ") is None
    assert E.resolved_model_evidence(123) is None
    assert E.resolved_model_evidence("Alibaba | ") is None


# =======================================================================================
# Cross-cutting: no network anywhere in this suite or in the module under test.
# =======================================================================================

def test_this_suite_and_the_interlock_module_make_no_network_call():
    forbidden = ["urlopen", "urllib.request", "requests.post", "requests.get", "httpx.",
                 "http.client", "socket.socket", "from_pretrained", "hf_hub_download"]
    for path in (Path(__file__), REPO / "src" / "alignment" / "q2_v7" / "interlock.py"):
        src = path.read_text()
        for token in forbidden:
            # skip this test's own literal list
            hits = [ln for ln in src.splitlines()
                    if token in ln and "forbidden" not in ln and '"' + token not in ln]
            assert not hits, f"{path.name}: {token!r} must not appear: {hits[:2]}"
