"""Q2 Stage-2 v7.2 executable study sequence — the integrated live runner.

The v7.2 code review's "Implementation-scope gap" section names exactly what this module is:
the one executable path that renders the frozen grid, walks the endpoint sequence, projects
the full-grid cost, executes the outcome-blinded smoke, reuses those draws inside the full
13,200-draw design, and enforces restart and the hard stop throughout.

Seven separately callable, separately testable stages (nothing ever auto-advances):

1. `run_walk`      — the deterministic endpoint promotion walk (ONE synthetic, non-study
                     capability probe per candidate, in frozen sequence order).
2. `run_projection`— the C2 documented-tokenizer full-grid projection artifact, written under a
                     CONTENT-ADDRESSED identity and pinned by a write-once binding record.
3. `record_promotion_authorization` / `record_funding_authorization` — the frozen staged
                     authorization (v7 "Staged authorization" 4). NO paid call.
4. `run_smoke`     — the 240 outcome-blinded smoke draws (48 coordinates x draw indices 0-4).
5. `smoke_promotion_gate` — the frozen measurement-validity gate on those 240 draws.
6. `run_full`      — the remaining 12,960 draws (240 + 12,960 = 13,200 attempted per model),
                     reusing every persisted smoke draw and never repaying it.
7. `build_study_manifest` / `write_study_manifest` — the R-V7-7 manifest binding, plus
                     `open_ledger`, which reconstructs cumulative spend BEFORE the first
                     budget check (R-C2).

Frozen invariants this module refuses to break:

* draw identity is `request SHA-256 + immutable draw index` and NOTHING else — the smoke/full
  stage label never enters identity, which is precisely why smoke draws 0-4 ARE the first five
  of the 25 and are replayed from their records rather than repaid (R-V7-7, R-C1);
* every returned response is persisted FIRST and booked SECOND, whatever its status, audit,
  parse or cache outcome (R-C3), through `ledger.record_response`;
* a persisted failure stays a failure; the existence of a file is never evidence of success
  (R-C1);
* there is NO reduced-cell and NO reduced-S substitute: a model that cannot pass the walk or
  cannot fit the $8.50 stop is reported as a capability/budget exclusion;
* "finish current model" NEVER overrides the $8.50 hard stop: the run halts BEFORE the call
  that would breach it, the model is reported incomplete, and no headline is emitted;
* every wire attempt that returned a response is persisted and booked BEFORE the retry policy
  is allowed to decide anything, and exactly ONE terminal sampling outcome per draw enters the
  13,200-draw study store (PS-4);
* no paid study call is constructed, let alone sent, until the model's promotion authorization
  and the panel's funding authorization are on disk, validate, and match this exact model,
  endpoint, manifest, snapshot and projection artifact (PS-1).

NETWORK: the HTTP transport is an INJECTED seam (`SingleAttemptTransport` is the only live
implementation and is constructed solely by `main`). Every stage function takes the transport
as an argument, so the whole module is exercised with no network in
`tests/test_q2_v7_study_run.py`.

Usage (each stage is invoked separately; no stage ever starts its successor):

    python -m alignment.q2_v7.study_run {walk,project,authorize,smoke,full} \
        --model MODEL --run-dir DIR --i-have-authorized-paid-spend
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from alignment.q2_v7 import canary as C
from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import identity as I
from alignment.q2_v7 import interlock as K
from alignment.q2_v7 import ledger as L

ROOT = Path(__file__).resolve().parents[3]
API_URL = "https://openrouter.ai/api/v1/chat/completions"
DESIGN_DOC = ROOT / "paper" / "Q2_STAGE2_HOSTED_DESIGN.md"
DEFAULT_RUN_DIR = ROOT / "out" / "q2_stage2_v7_study"
V7_CANARY_RAW = ROOT / "out" / "q2_stage2_v7_canary" / "raw"

STAGES: tuple[str, ...] = ("walk", "project", "authorize", "smoke", "full")

#: Reporting labels only — ALL buckets share the single $8.50 stop (R-V7-6).
WALK_STAGE, WALK_BUCKET = "gate", "gate"
SMOKE_STAGE, SMOKE_BUCKET = "smoke", "smoke"
FULL_STAGE, FULL_BUCKET = "study", "study"

#: Sub-directory holding the append-only per-wire-attempt records (PS-4). It is deliberately
#: SEPARATE from the study store so the study store keeps exactly one terminal sampling
#: outcome per manifest-bound draw (the 13,200 count never changes).
ATTEMPT_DIRNAME = "study_attempts"

#: Draw-index base for attempt identities. A sampling draw index is 0-24; an attempt index is
#: `BASE + draw_index * max_attempts + attempt`, so an attempt identity can never collide with
#: a manifest-bound sampling draw identity, and every attempt of every draw is distinct.
ATTEMPT_DRAW_INDEX_BASE = 1000
assert ATTEMPT_DRAW_INDEX_BASE > I.DRAWS_PER_COORDINATE

#: Worst case debited against the stop before one synthetic capability probe. The probe is a
#: two-message, four-token call; a cent is orders of magnitude above its realised cost.
PROBE_WORST_CASE_USD = 0.01

#: Separately quantified retry reserve (C2 `total` term). Overridable per run; never zero by
#: default, because a projection with no reserve can authorise a run it cannot finish.
DEFAULT_RETRY_RESERVE_USD = 0.25

USAGE = ("python -m alignment.q2_v7.study_run {walk,project,authorize,smoke,full} "
         "--model MODEL --run-dir DIR --i-have-authorized-paid-spend")


# =======================================================================================
# Errors — every failure mode is fail-closed and loud.
# =======================================================================================

class StudyRunError(RuntimeError):
    """Fail-closed runner failure."""


class HardStopReached(StudyRunError):
    """A wire call was refused because it would breach the $8.50 hard stop (PS-7).

    Raised from inside the retry ladder so the ladder terminates WITHOUT sending, rather than
    letting a retry spend past a stop its predecessor was legitimately allowed under.
    """


class CapabilityExclusion(StudyRunError):
    """No endpoint in the model's frozen sequence passed (a)+(b)+(c).

    There is NO reduced-cell and NO reduced-S substitute: the model is reported as a
    capability/budget exclusion and nothing further is executed for it.
    """


class MeasurementValidityFailure(StudyRunError):
    """The 240-draw smoke did not clear the frozen promotion gate. No headline is emitted."""


class HardStopHalt(StudyRunError):
    """The $8.50 stop would be breached by the next call."""


class ProjectionIntegrityError(StudyRunError):
    """A projection artifact is absent, unbound, edited, or does not describe this run (PS-3).

    Every paid study call is priced from a projection artifact. An artifact that cannot be
    proved — byte-for-byte — to be the one the promotion decision was taken on is never used
    to authorise a payment.
    """


class AuthorizationError(StudyRunError):
    """The frozen staged authorization for a paid study stage is absent or does not apply.

    Raised BEFORE any transport is constructed, so a missing, refused, malformed, stale,
    cross-model, or wrong-manifest authorization record produces exactly ZERO wire calls
    (PS-1).
    """


# =======================================================================================
# The rendered-grid contract (implemented by `alignment.q2_v7.study_render`)
# =======================================================================================

class StudyRequestLike(Protocol):
    """One of the 528 rendered cell-probe-order requests."""
    cell_id: str
    probe_id: str
    order_idx: int
    body: dict
    request_sha256: str
    rendered: G.RenderedRequest


def _render_module():
    """Import the renderer lazily so this module imports (and tests run) without it."""
    try:
        from alignment.q2_v7 import study_render          # noqa: WPS433 (deliberate)
    except ImportError as exc:                             # pragma: no cover - operator path
        raise StudyRunError(
            "alignment.q2_v7.study_render is required to render the frozen 528-request "
            f"grid: {exc}") from None
    return study_render


def render_study_grid(model: str, tag: str, probe_ids: Sequence[str]) -> list[Any]:
    """The 528 unique cell-probe-order requests for one model at one endpoint."""
    return _render_module().render_study_grid(model, tag, probe_ids)


def render_smoke_grid(model: str, tag: str, probe_ids: Sequence[str]) -> list[Any]:
    """The 48 outcome-blinded smoke coordinates for one model at one endpoint."""
    return _render_module().render_smoke_grid(model, tag, probe_ids)


def probe_ids_for(primary: str = "ENG") -> list[str]:
    """The 12 frozen floor probes, in frozen order."""
    return _render_module().probe_ids_for(primary)


# =======================================================================================
# Transport seam — ONE attempt per call; the C3 retry policy lives in `gate`
# =======================================================================================

class Transport(Protocol):
    def post(self, body: Mapping[str, Any], headers: Mapping[str, str],
             timeout: float = 60.0) -> tuple[int, Mapping[str, str], str]:
        ...


@dataclass
class SingleAttemptTransport:
    """The live transport: exactly ONE HTTP attempt per call, no retries of its own.

    `alignment.q2_v7.canary.LiveTransport` embeds the C3 retry ladder inside the transport.
    Here the ladder is driven by the FROZEN `gate.execute_with_retries` instead, so the policy
    that decides when the walk advances is the frozen one, its bookkeeping (`RetryResult`) is
    recorded on the probe result, and every individual attempt gets its own draw identity,
    persistence and booking. Retrying inside the transport would hide paid attempts from the
    ledger.
    """
    ca_file: Optional[str] = None
    statuses: list[int] = field(default_factory=list)

    def _opener(self):
        if self.ca_file:
            import ssl
            ctx = ssl.create_default_context(cafile=self.ca_file)
            return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        return urllib.request.build_opener()

    def post(self, body: Mapping[str, Any], headers: Mapping[str, str],
             timeout: float = 60.0) -> tuple[int, dict, str]:
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST")
        for name, value in headers.items():
            req.add_header(name, value)
        try:
            with self._opener().open(req, timeout=timeout) as resp:
                self.statuses.append(resp.status)
                return resp.status, dict(resp.headers), resp.read().decode()
        except urllib.error.HTTPError as exc:
            self.statuses.append(exc.code)
            return exc.code, dict(exc.headers), exc.read().decode()
        except Exception as exc:                                # transport-level failure
            self.statuses.append(0)
            # 503 keeps it inside the frozen transient class without inventing a wire status.
            return 503, {}, json.dumps({"error": {"message": f"{type(exc).__name__}: {exc}"}})


class StudyDraw(L.DrawIdentity):
    """Draw identity = canonical request SHA-256 + immutable draw index, serialised by
    `identity.draw_id`.

    `ledger.DrawIdentity` renders the same two components as `<sha>#<n>` while
    `identity.draw_id` renders `<sha>#draw<n>`, and the R-V7-7 manifest binds the LATTER. A
    run whose persisted records used the ledger spelling could never be bound by its own
    manifest, so the runner overrides the rendering — not the identity, which is unchanged —
    to the one the manifest, the reuse check, and the spec all use.
    """

    @property
    def draw_id(self) -> str:
        return I.draw_id(self.request_sha256, self.draw_index)


@dataclass(frozen=True)
class WireResult:
    """One returned HTTP response, parsed but not yet judged."""
    status: int
    headers: dict
    body: dict


def _post_once(transport: Transport, body: Mapping[str, Any],
               headers: Mapping[str, str]) -> WireResult:
    status, resp_headers, raw = transport.post(body, headers)
    if isinstance(raw, Mapping):
        parsed: Any = dict(raw)
    else:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = {"_unparseable_body": raw}
    if not isinstance(parsed, Mapping):
        parsed = {"_unparseable_body": raw}
    return WireResult(int(status), dict(resp_headers or {}), dict(parsed))


def _retry_after_seconds(headers: Mapping[str, Any]) -> Optional[float]:
    for name, value in (headers or {}).items():
        if str(name).lower() == "retry-after":
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return None
    return None


def _metadata(body: Mapping[str, Any]) -> Mapping[str, Any]:
    meta = body.get("openrouter_metadata")
    return meta if isinstance(meta, Mapping) else {}


def _is_byok(body: Mapping[str, Any]) -> bool:
    """R-V7-5: `is_byok == true` is an availability failure, never retried, never promoted."""
    return _metadata(body).get("is_byok") is True


def _message_content(body: Mapping[str, Any]) -> Optional[str]:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    message = first.get("message")
    if not isinstance(message, Mapping):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _billed_completion_tokens(body: Mapping[str, Any]) -> Optional[int]:
    usage = body.get("usage")
    if not isinstance(usage, Mapping):
        return None
    value = usage.get("completion_tokens")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# =======================================================================================
# Persist-then-book (R-C3) — the ONLY path by which a returned response enters the run
# =======================================================================================

def _record_and_book(*, store: L.EnvelopeStore, ledger: L.V7Ledger, draw: StudyDraw,
                     request_body: Mapping[str, Any], request_headers: Mapping[str, str],
                     wire: WireResult, bucket: str, model: str, provider: str,
                     stage: str) -> tuple[Optional[float], tuple[str, ...],
                                          Optional[L.RawEnvelope]]:
    """Persist the immutable envelope, then book any finite returned cost.

    Ordering is the point: validity is a SEPARATE question from accounting, so a non-200, a
    cache hit, or an audit failure never prevents the response from being persisted and its
    returned cost from being booked (R-C3).
    """
    failures: list[str] = []
    cost: Optional[float] = None
    envelope: Optional[L.RawEnvelope] = None
    try:
        recorded = L.record_response(
            store=store, ledger=ledger, draw=draw, request_body=request_body,
            request_headers=request_headers, response_body=wire.body,
            response_headers=wire.headers, http_status=wire.status, bucket=bucket,
            model=model, provider=provider, stage=stage)
        cost = recorded.booked_cost_usd
        envelope = recorded.envelope
    except L.CostAccountingError as exc:
        # The envelope is durable; the call must be reconciled through its generation id and
        # is never booked as free.
        failures.append(f"cost_unreconciled:{exc}")
        envelope = store.get(draw.draw_id)
    except L.LedgerError as exc:
        failures.append(f"{type(exc).__name__}:{exc}")
        envelope = store.get(draw.draw_id)

    try:
        L.reject_cache_hit(wire.body, wire.headers)
    except L.CacheHitRejected:
        failures.append("cache_hit_excluded")
    return cost, tuple(failures), envelope


def _write_derived(store: L.EnvelopeStore, envelope: Optional[L.RawEnvelope], *, valid: bool,
                   failures: Sequence[str]) -> Optional[L.DerivedRecord]:
    """Write the SEPARATE, linked derived validation record for a persisted envelope."""
    if envelope is None:                                  # persistence itself failed
        return None
    existing = store.get_derived(envelope.draw_id)
    if existing is not None:
        return existing
    return L.record_validation(store, envelope, valid=valid, failures=tuple(failures))


# =======================================================================================
# Stage 1 — the deterministic endpoint promotion walk
# =======================================================================================

def walk_probe_messages() -> list[dict]:
    """The SYNTHETIC, non-study capability probe.

    Deliberately contentless — no probe item, no payload, no guard, no option order — so it
    cannot estimate any frozen contrast and viewing its reply reveals no outcome. Reused
    verbatim from the signed canary so the walk probes exactly the envelope the canary
    validated.
    """
    return C.canary_messages()


def walk_request_body(model: str, tag: str) -> dict:
    """The exact frozen sampling envelope for one candidate's capability probe."""
    return E.build_sampling_request(model, tag, walk_probe_messages())


def walk_draw_ids(model: str, max_attempts: int = G.MAX_ATTEMPTS) -> tuple[str, ...]:
    """Every draw identity the walk is authorised to pay for.

    One synthetic probe request per candidate, with up to `max_attempts` attempts; each attempt
    is an independent draw of that synthetic request and therefore carries its own immutable
    draw index, its own persisted envelope, and its own booked cost.
    """
    ids: list[str] = []
    for tag in G.frozen_sequence(model):
        sha = E.canonical_request_sha256(walk_request_body(model, tag))
        ids.extend(I.draw_id(sha, index) for index in range(max_attempts))
    return tuple(ids)


@dataclass(frozen=True)
class ProbeRecord:
    """The audit view of one candidate's capability probe (no substantive outcome)."""
    tag: str
    http_status: int
    terminal_reason: str
    attempts_made: int
    draw_ids: tuple[str, ...]
    booked_cost_usd: float
    envelope_audit_failures: tuple[str, ...]
    reasoning_failures: tuple[str, ...]
    parsed_option: Optional[int]
    reasoning_tokens: Optional[int]
    billed_completion_tokens: Optional[int]

    def as_record(self) -> dict:
        return {
            "tag": self.tag,
            "http_status": self.http_status,
            "terminal_reason": self.terminal_reason,
            "attempts_made": self.attempts_made,
            "draw_ids": list(self.draw_ids),
            "booked_cost_usd": self.booked_cost_usd,
            "envelope_audit_failures": list(self.envelope_audit_failures),
            "reasoning_failures": list(self.reasoning_failures),
            "parsed_option": self.parsed_option,
            "reasoning_tokens": self.reasoning_tokens,
            "billed_completion_tokens": self.billed_completion_tokens,
        }


@dataclass(frozen=True)
class WalkResult:
    model: str
    decision: G.PromotionDecision
    probes: tuple[ProbeRecord, ...]
    record_path: Optional[Path] = None

    @property
    def promoted_tag(self) -> Optional[str]:
        return self.decision.promoted_tag

    @property
    def excluded(self) -> bool:
        return self.decision.excluded

    @property
    def probed_tags(self) -> tuple[str, ...]:
        return self.decision.probed_tags

    def as_record(self) -> dict:
        record = self.decision.as_record()
        record.update({
            "artifact": "Q2 Stage-2 v7.2 endpoint promotion walk",
            "probes": [p.as_record() for p in self.probes],
            "promoted_projection_total": (self.decision.promoted_projection.total
                                          if self.decision.promoted_projection else None),
            # v7 requirement 4: there is no substitute design of any kind.
            "reduced_cell_substitute": None,
            "reduced_s_substitute": None,
        })
        return record


def gate_candidates(snapshot: E.Snapshot,
                    model: Optional[str] = None) -> dict[str, G.EndpointCandidate]:
    """Project the committed snapshot (C1) onto the gate's candidate rows.

    `endpoint_name` carries the snapshot's DATABLE UPSTREAM identifier (e.g.
    `qwen/qwen3.5-397b-a17b-20260216`), because that is the model evidence OpenRouter actually
    returns and the evidence `gate.audit_envelope` compares against; the human-readable
    "Provider | model" string adds nothing the audit can check.
    """
    out: dict[str, G.EndpointCandidate] = {}
    for (candidate_model, tag), cand in snapshot.candidates.items():
        if model is not None and candidate_model != model:
            continue
        out[f"{candidate_model}::{tag}"] = G.EndpointCandidate(
            model=candidate_model,
            tag=tag,
            provider_name=cand.provider_name,
            endpoint_name=cand.upstream_model,
            quantization=cand.quantization,
            price_prompt_per_token=float(cand.price_prompt_per_token),
            price_completion_per_token=float(cand.price_completion_per_token),
        )
    return out


def _probe_result(tag: str, wire: WireResult, *, model: str, snapshot: E.Snapshot,
                  request_body: Mapping[str, Any],
                  retry: G.RetryResult) -> tuple[G.EndpointProbeResult, E.AuditResult,
                                                 E.ReasoningResult, Optional[int]]:
    """Derive the frozen (a)+(b) evidence from ONE returned probe response. No fabrication."""
    audit = E.verify_provider_audit(wire.body, model, tag, snapshot)
    reasoning = E.verify_reasoning_off(wire.body)
    meta = _metadata(wire.body)
    parsed = I.parse_option(_message_content(wire.body))
    attempt = meta.get("attempt")
    result = G.EndpointProbeResult(
        tag=tag,
        http_status=wire.status,
        requested_provider_only=tuple((request_body.get("provider") or {}).get("only") or ()),
        n_candidates_available=int(audit.available_count or 0),
        selected_provider_name=audit.selected_provider,
        requested_model=audit.requested_model,
        returned_model_evidence=audit.returned_upstream_model,
        strategy=audit.strategy,
        attempt=(attempt if isinstance(attempt, int) and not isinstance(attempt, bool)
                 else None),
        fallback_occurred=any(bool(meta.get(k)) for k in E.FALLBACK_EVIDENCE_KEYS),
        # gate requires `is_byok is False`; anything else (True, missing, non-bool) fails.
        is_byok=(meta.get("is_byok") is not False),
        reasoning_tokens=reasoning.reasoning_tokens,
        has_reasoning_payload=any(f.startswith("reasoning_payload")
                                  for f in reasoning.failures),
        usage_fields_present=not any(f.startswith("missing_usage")
                                     for f in reasoning.failures),
        parsed_leading_digit=parsed.option,
        billed_completion_tokens=_billed_completion_tokens(wire.body),
        retry=retry,
    )
    return result, audit, reasoning, parsed.option


def run_walk(*, model: str, key: str, snapshot: E.Snapshot, store: L.EnvelopeStore,
             ledger: L.V7Ledger, transport: Transport,
             requests_for: Callable[[str], Sequence[StudyRequestLike]],
             tokenizer: G.Tokenizer,
             retry_reserve_usd: float = DEFAULT_RETRY_RESERVE_USD,
             observed_billed_completion_tokens: Sequence[int] = (),
             projection_dir: Optional[Path] = None,
             run_dir: Optional[Path] = None,
             sleep: G.Sleeper = time.sleep,
             clock: G.Clock = time.monotonic,
             max_attempts: int = G.MAX_ATTEMPTS) -> WalkResult:
    """Walk the model's FROZEN fallback sequence and promote the FIRST endpoint satisfying
    (a) exact-envelope HTTP 200 resolving to the declared slug under the C1 provider-audit
    proof, (b) reasoning-off honored with reasoning tokens EXACTLY 0 and a parseable leading
    digit, and (c) a full-grid projection over all 528 requests fitting the $8.50 stop.

    Hard 4xx skips immediately; 429/408/5xx exhaust the frozen C3 retry policy (one initial
    attempt plus four retries) before the walk advances; `is_byok == true` is an availability
    failure. If no candidate passes, the model is a capability/budget exclusion — there is NO
    reduced-cell and NO reduced-S substitute.
    """
    candidates = gate_candidates(snapshot, model)
    headers = E.request_headers(key)
    probes: dict[str, ProbeRecord] = {}
    envelope_audit_ok: dict[str, bool] = {}

    def probe(tag: str) -> G.EndpointProbeResult:
        body = walk_request_body(model, tag)
        sha = E.canonical_request_sha256(body)
        wires: list[WireResult] = []
        draw_ids: list[str] = []
        booked = 0.0

        def send() -> G.AttemptOutcome:
            nonlocal booked
            index = len(wires)
            draw = StudyDraw(request_sha256=sha, draw_index=index)
            ledger.check_before_call(PROBE_WORST_CASE_USD,
                                     label=f"walk:{model}@{tag}#draw{index}")
            wire = _post_once(transport, body, headers)
            wires.append(wire)
            draw_ids.append(draw.draw_id)
            cost, failures, envelope = _record_and_book(
                store=store, ledger=ledger, draw=draw, request_body=body,
                request_headers=headers, wire=wire, bucket=WALK_BUCKET, model=model,
                provider=tag, stage=WALK_STAGE)
            if cost:
                booked += cost
            _write_derived(store, envelope,
                           valid=(wire.status == 200 and not failures),
                           failures=(*failures,
                                     *(("http_error",) if wire.status != 200 else ())))
            return G.AttemptOutcome(status=wire.status,
                                    retry_after_s=_retry_after_seconds(wire.headers),
                                    is_byok=_is_byok(wire.body),
                                    payload=wire.body)

        retry = G.execute_with_retries(send, sleep=sleep, clock=clock,
                                       max_attempts=max_attempts)
        terminal = wires[-1]
        result, audit, reasoning, parsed = _probe_result(
            tag, terminal, model=model, snapshot=snapshot, request_body=body, retry=retry)
        envelope_audit_ok[tag] = bool(audit.ok)
        probes[tag] = ProbeRecord(
            tag=tag, http_status=terminal.status, terminal_reason=retry.terminal_reason,
            attempts_made=retry.attempts_made, draw_ids=tuple(draw_ids),
            booked_cost_usd=booked,
            envelope_audit_failures=tuple(audit.failures),
            reasoning_failures=tuple(reasoning.failures),
            parsed_option=parsed, reasoning_tokens=reasoning.reasoning_tokens,
            billed_completion_tokens=_billed_completion_tokens(terminal.body))
        return result

    def project(candidate: G.EndpointCandidate) -> G.CostProjection:
        observed = [*observed_billed_completion_tokens]
        billed = probes[candidate.tag].billed_completion_tokens if candidate.tag in probes \
            else None
        if billed is not None:
            observed.append(billed)
        projection = build_projection(
            model=model, candidate=candidate, requests=requests_for(candidate.tag),
            tokenizer=tokenizer, ledger=ledger, retry_reserve_usd=retry_reserve_usd,
            observed_billed_completion_tokens=observed)
        if projection_dir is not None:
            write_projection(projection_dir, projection)
        return projection

    decision = G.promotion_walk(model=model, probe=probe, project=project,
                                candidates=candidates)

    # The gate's (a) audit and the envelope module's C1 proof check the same frozen facts. If
    # they ever disagree on the PROMOTED endpoint that is a runner defect, not a finding: fail
    # closed rather than promote on a half-verified proof.
    if decision.promoted_tag and not envelope_audit_ok.get(decision.promoted_tag, False):
        raise StudyRunError(
            f"promoted {decision.promoted_tag!r} passed the gate audit but failed the C1 "
            f"provider-audit proof: {probes[decision.promoted_tag].envelope_audit_failures}")

    ordered = tuple(probes[a.tag] for a in decision.attempts)
    result = WalkResult(model=model, decision=decision, probes=ordered)
    if run_dir is not None:
        path = walk_record_path(run_dir, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.as_record(), sort_keys=True, indent=1))
        result = WalkResult(model=model, decision=decision, probes=ordered, record_path=path)
    return result


def _safe_model(model: str) -> str:
    return model.replace("/", "__")


def walk_record_path(run_dir: Path | str, model: str) -> Path:
    return Path(run_dir) / f"walk_{_safe_model(model)}.json"


def load_promotion(run_dir: Path | str, model: str) -> str:
    """The promoted endpoint tag recorded by the walk stage.

    Later stages read the RECORDED decision rather than re-deriving it: no stage auto-advances,
    and a model recorded as an exclusion can never be resurrected by a later invocation.
    """
    path = walk_record_path(run_dir, model)
    if not path.exists():
        raise StudyRunError(
            f"no promotion record at {path} — run the `walk` stage for {model} first")
    record = json.loads(path.read_text())
    if record.get("excluded") or not record.get("promoted_tag"):
        raise CapabilityExclusion(
            f"{model} is a capability/budget exclusion "
            f"({record.get('exclusion_reason')}); there is no reduced-cell and no reduced-S "
            f"substitute, so no smoke and no study run may be executed for it")
    return str(record["promoted_tag"])


# =======================================================================================
# Stage 2 — the full-grid projection artifact (C2 / S-F5)
# =======================================================================================

def build_projection(*, model: str, candidate: G.EndpointCandidate,
                     requests: Sequence[StudyRequestLike], tokenizer: G.Tokenizer,
                     ledger: L.V7Ledger, retry_reserve_usd: float,
                     observed_billed_completion_tokens: Sequence[int] = ()
                     ) -> G.CostProjection:
    """The frozen C2 projection over ALL 528 rendered requests for one candidate.

    The 240 smoke draws are counted ONCE — they are already the first five draws of 48 of these
    528 coordinates, so there is deliberately no separate smoke term.
    """
    allowance = G.completion_allowance(list(observed_billed_completion_tokens))
    return G.project_full_grid(
        model=model,
        candidate=candidate,
        requests=[r.rendered for r in requests],
        tokenizer=tokenizer,
        completion_allowance_tokens=allowance,
        reconciled_prior_gate_spend=ledger.total_spent_usd,
        retry_reserve=float(retry_reserve_usd),
    )


#: The canonical serialization `gate.write_projection_artifact` uses. Recomputed here so the
#: artifact can be content-addressed and byte-compared without re-writing it.
def projection_bytes(projection: G.CostProjection) -> bytes:
    return json.dumps(projection.as_artifact(), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def projection_sha256(projection: G.CostProjection) -> str:
    return hashlib.sha256(projection_bytes(projection)).hexdigest()


def _safe_tag(tag: str) -> str:
    return tag.replace("/", "__")


def projection_path(projection_dir: Path | str, projection: G.CostProjection) -> Path:
    """The CONTENT-ADDRESSED artifact path (PS-3.4).

    The v7.2 pre-smoke re-audit found that a single `projection_<model>__<tag>.json` name made
    a corrected projection indistinguishable from the stale heuristic one it replaced: rerunning
    `project` silently kept the old file. The digest is therefore part of the filename, so an
    artifact computed by a different method, at different prices, or over a different request
    set can never occupy the identity of the one that decided a promotion. Which of several
    artifacts a paid stage may use is decided by the write-once binding record below, never by
    a filename glob.
    """
    digest = projection_sha256(projection)
    return (Path(projection_dir) /
            f"projection_{_safe_model(projection.model)}__{_safe_tag(projection.endpoint_tag)}"
            f"__sha256-{digest[:16]}.json")


def write_projection(projection_dir: Path | str, projection: G.CostProjection) -> Path:
    """Persist the per-candidate cost artifact, IMMUTABLE BY CONTENT (PS-3.1).

    Identical bytes at the same content-addressed identity resume silently — that is what makes
    the stage restartable. Different bytes at the same identity RAISE: the previous
    implementation returned an existing same-name artifact without ever comparing it, so a
    stale projection could price every paid call in the run.
    """
    path = projection_path(projection_dir, projection)
    body = projection_bytes(projection)
    if path.exists():
        existing = path.read_bytes()
        if existing != body:
            raise ProjectionIntegrityError(
                f"projection artifact {path} exists with different bytes (sha256 "
                f"{hashlib.sha256(existing).hexdigest()[:12]} on disk vs "
                f"{hashlib.sha256(body).hexdigest()[:12]} recomputed) — refusing to reuse or "
                f"replace immutable cost evidence")
        return path
    G.write_projection_artifact(path, projection)
    return path


def read_projection(path: Path | str) -> dict:
    """Read one projection artifact, with the MINIMUM structural check.

    This is the raw reader. It is never sufficient to authorise a payment: every smoke/full
    invocation goes through `verify_projection`, which checks the artifact against the
    snapshot, the manifest, the pinned tokenizer identity, all 528 request hashes, the prices,
    and every arithmetic total.
    """
    obj = json.loads(Path(path).read_text())
    if not isinstance(obj, Mapping):
        raise ProjectionIntegrityError(f"{path}: projection artifact is not a JSON object")
    if not isinstance(obj.get("rows"), list):
        raise ProjectionIntegrityError(f"{path}: projection artifact carries no rows")
    return dict(obj)


# ---------------------------------------------------------------------------------------
# The write-once projection binding record — the LOGICAL identity of "the projection this
# model+endpoint runs on". PS-3.2: it is what the authorization records bind.
# ---------------------------------------------------------------------------------------

PROJECTION_BINDING_SCHEMA = "q2_v7.study_run.projection_binding.v1"


def projection_binding_path(run_dir: Path | str, model: str, tag: str) -> Path:
    return Path(run_dir) / f"projection_binding_{_safe_model(model)}__{_safe_tag(tag)}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _binding_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over a record's canonical payload — the same idiom `interlock` uses.

    Every field a later stage relies on is inside the payload, so an edited record fails to
    load rather than silently authorising a different run.
    """
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


#: Fields that record WHO/WHEN, not WHAT was decided. They are covered by `binding_sha256`
#: (so they cannot be edited after the fact) but are excluded from the write-once comparison,
#: exactly as `identity.write_or_resume_manifest` resumes on identical content: re-invoking a
#: stage must be a no-op, and a wall-clock second is not a different decision.
_VOLATILE_RECORD_FIELDS: tuple[str, ...] = ("recorded_utc", "recorded_by")


def _decision_content(record: Mapping[str, Any]) -> dict:
    return {k: v for k, v in record.items()
            if k != "binding_sha256" and k not in _VOLATILE_RECORD_FIELDS}


def _write_once_record(path: Path, payload: Mapping[str, Any], *,
                       error: type[StudyRunError]) -> dict:
    """Persist one write-once record atomically. Identical decision content resumes; different
    decision content raises. A decision record is evidence — there is no `--force`."""
    body = dict(payload)
    body["binding_sha256"] = _binding_digest(payload)
    text = _canonical(body)
    if path.exists():
        stored = json.loads(path.read_text())
        if _decision_content(stored) != _decision_content(body):
            raise error(
                f"{path} already records a DIFFERENT decision — a recorded decision is "
                f"immutable evidence and is never rewritten. Move the superseded record aside "
                f"deliberately (and re-review it) before recording a new one.")
        return dict(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o444)
    except OSError:                                    # pragma: no cover - platform-dependent
        pass
    return body


def _read_once_record(path: Path, schema: str, *, error: type[StudyRunError]) -> dict:
    if not path.exists():
        raise error(f"no record at {path}")
    try:
        obj = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise error(f"{path}: unreadable record ({exc})") from None
    if not isinstance(obj, Mapping):
        raise error(f"{path}: record is not a JSON object")
    if obj.get("schema") != schema:
        raise error(f"{path}: wrong schema {obj.get('schema')!r}, expected {schema!r}")
    stored = obj.get("binding_sha256")
    payload = {k: v for k, v in obj.items() if k != "binding_sha256"}
    if not isinstance(stored, str) or stored != _binding_digest(payload):
        raise error(
            f"{path}: binding_sha256 does not match the record payload — the record was "
            f"edited after it was written, or moved onto another run")
    return dict(obj)


def _tokenizer_identity(snapshot: E.Snapshot, model: str) -> dict:
    """The pinned tokenizer identity C2 requires: repo id, exact revision, and file hashes."""
    spec = snapshot.tokenizers.get(model)
    if not isinstance(spec, Mapping):
        raise ProjectionIntegrityError(
            f"the committed snapshot pins no tokenizer for {model!r}; C2 cannot be reproduced")
    return {
        "repo_id": str(spec.get("repo_id") or ""),
        "revision": str(spec.get("revision") or ""),
        "files": {str(k): str(v) for k, v in sorted((spec.get("files") or {}).items())},
    }


def request_set_sha256(request_sha256s: Sequence[str]) -> str:
    """A canonical digest over the SET of request hashes the projection priced."""
    return I.canonical_sha256(sorted(set(request_sha256s)))


def write_projection_binding(run_dir: Path | str, projection: G.CostProjection, *,
                             snapshot: E.Snapshot, manifest: I.Manifest,
                             artifact_path: Path, recorded_by: str = "") -> dict:
    """Pin ONE projection artifact as the projection this model+endpoint is priced from.

    Write-once. Re-running `project` after correcting the C2 method produces a different
    artifact digest and therefore a different record body, which RAISES here rather than
    silently swapping the artifact that prices 13,200 paid calls (PS-3.1/PS-3.4).
    """
    artifact_path = Path(artifact_path)
    body = artifact_path.read_bytes()
    payload = {
        "schema": PROJECTION_BINDING_SCHEMA,
        "model": projection.model,
        "endpoint_tag": projection.endpoint_tag,
        "artifact_filename": artifact_path.name,
        "artifact_sha256": hashlib.sha256(body).hexdigest(),
        "endpoint_snapshot_sha256": snapshot.sha256,
        "manifest_sha256": manifest.sha256,
        "tokenizer": _tokenizer_identity(snapshot, projection.model),
        "n_requests": int(projection.n_requests),
        "draws_per_request": int(projection.draws_per_request),
        "completion_allowance": int(projection.completion_allowance),
        "price_prompt_per_token": float(projection.price_prompt_per_token),
        "price_completion_per_token": float(projection.price_completion_per_token),
        "request_set_sha256": request_set_sha256([r.request_sha256 for r in projection.rows]),
        "projected_input_tokens_total": int(projection.projected_input_tokens_total),
        "projected_input_cost": float(projection.projected_input_cost),
        "projected_completion_cost": float(projection.projected_completion_cost),
        "reconciled_prior_gate_spend": float(projection.reconciled_prior_gate_spend),
        "retry_reserve": float(projection.retry_reserve),
        "total": float(projection.total),
        "stop": float(projection.stop),
        "fits": bool(projection.fits),
        "recorded_utc": _utc_now(),
        "recorded_by": recorded_by,
    }
    path = projection_binding_path(run_dir, projection.model, projection.endpoint_tag)
    return _write_once_record(path, payload, error=ProjectionIntegrityError)


def load_projection_binding(run_dir: Path | str, model: str, tag: str) -> dict:
    return _read_once_record(projection_binding_path(run_dir, model, tag),
                             PROJECTION_BINDING_SCHEMA, error=ProjectionIntegrityError)


def _close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)


def verify_projection(run_dir: Path | str, *, model: str, tag: str, snapshot: E.Snapshot,
                      manifest: I.Manifest,
                      requests: Sequence[StudyRequestLike]) -> tuple[dict, str]:
    """Validate the bound projection artifact END TO END, BEFORE any transport exists (PS-3.3).

    Checks, in order: the binding record loads and is unedited; it names this model, this
    endpoint, this committed snapshot, this manifest and this pinned tokenizer; the artifact on
    disk hashes to the bound digest; the artifact's own model/endpoint/prices agree with the
    snapshot candidate; all 528 rows are unique in both hash and coordinate and exactly cover
    the rendered grid and the manifest; and every arithmetic total re-derives from the rows
    under the frozen C2 formula, fits the $8.50 stop, and matches the binding record.

    Returns `(artifact, artifact_sha256)`; raises `ProjectionIntegrityError` otherwise.
    """
    run_dir = Path(run_dir)
    binding = load_projection_binding(run_dir, model, tag)

    def fail(msg: str) -> None:
        raise ProjectionIntegrityError(
            f"projection binding {projection_binding_path(run_dir, model, tag).name}: {msg}")

    if binding.get("model") != model:
        fail(f"bound to model {binding.get('model')!r}, not {model!r}")
    if binding.get("endpoint_tag") != tag:
        fail(f"bound to endpoint {binding.get('endpoint_tag')!r}, not the promoted {tag!r}")
    if binding.get("endpoint_snapshot_sha256") != snapshot.sha256:
        fail(f"bound to endpoint snapshot {binding.get('endpoint_snapshot_sha256')!r}, not the "
             f"committed {snapshot.sha256!r}")
    if binding.get("manifest_sha256") != manifest.sha256:
        fail(f"bound to manifest {str(binding.get('manifest_sha256'))[:12]}, not this run's "
             f"{manifest.sha256[:12]}")
    if binding.get("tokenizer") != _tokenizer_identity(snapshot, model):
        fail("the pinned tokenizer identity (repo/revision/file hashes) has changed since the "
             "projection was recorded; C2 is no longer reproducible from it")

    artifact_path = run_dir / str(binding.get("artifact_filename") or "")
    if not artifact_path.exists():
        fail(f"the bound artifact {binding.get('artifact_filename')!r} is absent")
    raw = artifact_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != binding.get("artifact_sha256"):
        fail(f"the bound artifact hashes to {digest[:12]} but the record binds "
             f"{str(binding.get('artifact_sha256'))[:12]} — the artifact was edited")
    artifact = read_projection(artifact_path)

    if artifact.get("model") != model or artifact.get("endpoint_tag") != tag:
        fail(f"artifact describes {artifact.get('model')!r}@{artifact.get('endpoint_tag')!r}")

    candidate = gate_candidates(snapshot, model).get(f"{model}::{tag}")
    if candidate is None:
        fail(f"{tag!r} is not a candidate of {model!r} in the committed snapshot")
    prices = artifact.get("endpoint_prices") or {}
    in_price = float(prices.get("price_prompt_per_token", float("nan")))
    out_price = float(prices.get("price_completion_per_token", float("nan")))
    if not _close(in_price, candidate.price_prompt_per_token) or \
            not _close(out_price, candidate.price_completion_per_token):
        fail(f"artifact prices ({in_price}, {out_price}) differ from the committed snapshot "
             f"({candidate.price_prompt_per_token}, {candidate.price_completion_per_token})")
    if not _close(in_price, float(binding["price_prompt_per_token"])) or \
            not _close(out_price, float(binding["price_completion_per_token"])):
        fail("artifact prices differ from the bound prices")

    rows = artifact["rows"]
    if len(rows) != I.COORDINATES_PER_MODEL:
        fail(f"{len(rows)} priced rows, expected {I.COORDINATES_PER_MODEL}")
    hashes = [str(r["request_sha256"]) for r in rows]
    coords = [(str(r["cell_id"]), str(r["probe_id"]), int(r["order_idx"])) for r in rows]
    if len(set(hashes)) != len(hashes):
        fail("duplicate request hashes among the priced rows")
    if len(set(coords)) != len(coords):
        fail("duplicate coordinates among the priced rows")
    rendered = {r.request_sha256 for r in requests}
    if set(hashes) != rendered:
        fail(f"the priced request set does not equal the rendered grid "
             f"({len(set(hashes) - rendered)} priced-only, {len(rendered - set(hashes))} "
             f"rendered-only)")
    if set(hashes) != set(manifest.request_sha256s):
        fail("the priced request set does not equal the manifest's 528 request hashes")
    if binding.get("request_set_sha256") != request_set_sha256(hashes):
        fail("the priced request set does not match the bound request-set digest")

    draws = int(artifact.get("draws_per_request", 0))
    if draws != I.DRAWS_PER_COORDINATE:
        fail(f"artifact prices {draws} draws per coordinate, expected "
             f"{I.DRAWS_PER_COORDINATE}")
    allowance = int(artifact.get("completion_allowance", 0))
    if allowance < G.MIN_COMPLETION_ALLOWANCE:
        fail(f"completion allowance {allowance} is below the frozen "
             f"{G.MIN_COMPLETION_ALLOWANCE}")

    input_cost = 0.0
    tokens_total = 0
    for row in rows:
        raw_tokens = int(row["raw_input_tokens"])
        projected = int(row["projected_input_tokens"])
        if projected != G.projected_input_tokens(raw_tokens):
            fail(f"row {str(row['request_sha256'])[:12]} carries projected tokens {projected} "
                 f"!= ceil(1.10 x {raw_tokens}) under the frozen margin")
        if int(row["draws"]) != draws:
            fail(f"row {str(row['request_sha256'])[:12]} prices {row['draws']} draws")
        expected_row_cost = projected * draws * in_price
        if not _close(float(row["input_cost_for_draws"]), expected_row_cost):
            fail(f"row {str(row['request_sha256'])[:12]} input cost "
                 f"{row['input_cost_for_draws']} != {expected_row_cost}")
        tokens_total += projected
        input_cost += float(row["input_cost_for_draws"])

    if int(artifact.get("projected_input_tokens_total", -1)) != tokens_total:
        fail("projected_input_tokens_total does not equal the sum of the rows")
    if not _close(float(artifact["projected_input_cost"]), input_cost):
        fail("projected_input_cost does not equal the sum of the row costs")
    completion_cost = len(rows) * draws * allowance * out_price
    if not _close(float(artifact["projected_completion_cost"]), completion_cost):
        fail("projected_completion_cost does not equal 528 x 25 x allowance x output price")
    total = (float(artifact["projected_input_cost"])
             + float(artifact["projected_completion_cost"])
             + float(artifact["reconciled_prior_gate_spend"])
             + float(artifact["retry_reserve"]))
    if not _close(float(artifact["total"]), total):
        fail("total does not equal input + completion + prior gate spend + retry reserve")
    if not _close(float(artifact.get("stop", 0.0)), G.GLOBAL_STUDY_STOP):
        fail(f"artifact stop {artifact.get('stop')} is not the frozen "
             f"${G.GLOBAL_STUDY_STOP:.2f}")
    if float(artifact["total"]) > float(artifact["stop"]) or not artifact.get("fits"):
        fail(f"projected total ${float(artifact['total']):.4f} does not fit the "
             f"${float(artifact['stop']):.2f} stop")
    for key in ("total", "projected_input_cost", "projected_completion_cost",
                "reconciled_prior_gate_spend", "retry_reserve"):
        if not _close(float(artifact[key]), float(binding[key])):
            fail(f"artifact {key} differs from the bound value")
    if int(binding["projected_input_tokens_total"]) != tokens_total:
        fail("projected_input_tokens_total differs from the bound value")
    if int(binding["completion_allowance"]) != allowance:
        fail("completion allowance differs from the bound value")

    return artifact, digest


def worst_case_lookup(projection: G.CostProjection | Mapping[str, Any]
                      ) -> Callable[[str], float]:
    """Per-draw worst-case cost by request hash, straight from the projection.

    This is what the hard stop is checked against before every call: the projected input
    tokens (already carrying the frozen 10% margin) at the endpoint's input price, plus the
    completion allowance at its output price.
    """
    if isinstance(projection, G.CostProjection):
        rows = [r.as_dict() for r in projection.rows]
        in_price = projection.price_prompt_per_token
        out_price = projection.price_completion_per_token
        allowance = projection.completion_allowance
    else:
        rows = list(projection.get("rows") or ())
        prices = projection.get("endpoint_prices") or {}
        in_price = float(prices.get("price_prompt_per_token", 0.0))
        out_price = float(prices.get("price_completion_per_token", 0.0))
        allowance = int(projection.get("completion_allowance", G.MIN_COMPLETION_ALLOWANCE))
    per_draw = {
        str(row["request_sha256"]):
            float(row["projected_input_tokens"]) * in_price + allowance * out_price
        for row in rows
    }

    def lookup(request_sha256: str) -> float:
        try:
            return per_draw[request_sha256]
        except KeyError:
            raise StudyRunError(
                f"request {request_sha256[:12]} is not in the promoted projection — refusing "
                f"to pay for a call the full-grid gate never priced") from None

    return lookup


# =======================================================================================
# Manifest binding (R-V7-7 / R-E6) and ledger reconstruction (R-C2)
# =======================================================================================

@dataclass(frozen=True)
class DesignBinding:
    """The design-side hashes the manifest binds, alongside the runner revision."""
    design_sha256: str
    item_bank_sha256: str
    payload_sha256: str
    guard_sha256: str
    runner_revision: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def runner_revision() -> str:
    """A content revision of the runner itself: the source of this module plus the renderer."""
    digest = hashlib.sha256()
    for path in (Path(__file__), Path(__file__).with_name("study_render.py")):
        digest.update(path.read_bytes() if path.exists() else b"")
    return f"sha256:{digest.hexdigest()[:16]}"


def default_binding(primary: str = "ENG") -> DesignBinding:
    """Compute the frozen design/item-bank/payload/guard hashes from the repository."""
    from alignment.q1_channel import GUARD_TEXT, PAYLOADS, payload_placebo
    from alignment.q2_hosted import load_probe_items

    items = load_probe_items(primary)
    normalised = json.loads(json.dumps(items, sort_keys=True, default=str))
    texts: dict[str, Optional[str]] = {}
    for probe_id in sorted(items):
        item = items[probe_id]
        for key, builder in sorted(PAYLOADS.items()):
            texts[f"{key}|{probe_id}"] = builder(item)
        texts[f"placebo|{probe_id}"] = payload_placebo(item)
    return DesignBinding(
        design_sha256=hashlib.sha256(DESIGN_DOC.read_bytes()).hexdigest(),
        item_bank_sha256=I.canonical_sha256(normalised),
        payload_sha256=I.canonical_sha256(texts),
        guard_sha256=_sha256_text(GUARD_TEXT),
        runner_revision=runner_revision(),
    )


def build_study_manifest(*, model: str, endpoint_tag: str,
                         requests: Sequence[StudyRequestLike], probe_ids: Sequence[str],
                         snapshot_sha256: str, binding: DesignBinding) -> I.Manifest:
    """Bind all 13,200 draw identities, the 528 request hashes, the committed endpoint
    snapshot, the design/item-bank/payload/guard hashes, and the runner revision."""
    sha_by_coordinate = {(r.cell_id, r.probe_id, int(r.order_idx)): r.request_sha256
                         for r in requests}
    if len(sha_by_coordinate) != I.COORDINATES_PER_MODEL:
        raise I.CountMismatch(
            f"manifest needs {I.COORDINATES_PER_MODEL} unique coordinates, got "
            f"{len(sha_by_coordinate)}")
    return I.build_manifest(
        model=model,
        endpoint_slug=endpoint_tag,
        endpoint_snapshot_sha256=snapshot_sha256,
        design_sha256=binding.design_sha256,
        item_bank_sha256=binding.item_bank_sha256,
        payload_sha256=binding.payload_sha256,
        guard_sha256=binding.guard_sha256,
        runner_revision=binding.runner_revision,
        probe_ids=list(probe_ids),
        request_sha_by_coordinate=sha_by_coordinate,
    )


def manifest_path(run_dir: Path | str, model: str) -> Path:
    return Path(run_dir) / f"manifest_{_safe_model(model)}.json"


def write_study_manifest(run_dir: Path | str, model: str,
                         manifest: I.Manifest) -> I.ResumeDecision:
    """Write the manifest before execution, or resume on a BYTE-IDENTICAL one.

    Any mismatch raises `identity.ManifestMismatch`: a run resumes only on the manifest it
    started under, and the stored file is never rewritten or repaired.
    """
    return I.write_or_resume_manifest(manifest_path(run_dir, model), manifest)


def walk_store(run_dir: Path | str) -> L.EnvelopeStore:
    """Records of the synthetic capability probes (non-study, but paid)."""
    return L.EnvelopeStore(Path(run_dir) / "walk")


def study_store(run_dir: Path | str) -> L.EnvelopeStore:
    """Records of the study draws. Smoke and full share ONE store — that is what makes the
    240 smoke draws the first five of the 25 rather than a separate payment.

    This store holds exactly ONE terminal sampling outcome per manifest-bound draw. Every wire
    attempt behind that outcome lives in the append-only attempt store below (PS-4).
    """
    return L.EnvelopeStore(Path(run_dir) / "study")


def attempt_store(run_dir: Path | str) -> L.EnvelopeStore:
    """The append-only store of EVERY returned wire attempt (PS-4).

    A study draw's identity is `request hash + immutable draw index` and is bound by the
    manifest, so it cannot absorb extra indices for retries. The previous implementation
    therefore kept retry responses in memory and persisted only the terminal one: a paid
    non-terminal 429/5xx response, and the evidence needed to reconcile it, was lost on any
    process exit during the retry ladder. Attempts now get their own immutable identities in
    their own store, linked to the sampling draw by the shared request hash and by
    `attempt_draw_index`, and it is the attempt store — not the study store — that carries the
    money into the $8.50 stop.
    """
    return L.EnvelopeStore(Path(run_dir) / ATTEMPT_DIRNAME)


def attempt_store_for(store: L.EnvelopeStore) -> L.EnvelopeStore:
    """The attempt store that belongs beside a given study store."""
    return L.EnvelopeStore(Path(store.run_dir).parent / ATTEMPT_DIRNAME)


def attempt_draw_index(draw_index: int, attempt: int,
                       max_attempts: int = G.MAX_ATTEMPTS) -> int:
    """The immutable attempt identity index for attempt `attempt` of sampling draw `draw_index`.

    `BASE + draw_index * max_attempts + attempt` is injective over the frozen ranges and lies
    entirely above the 0-24 sampling indices, so no attempt identity can ever be mistaken for
    (or collide with) a manifest-bound sampling draw.
    """
    if not 0 <= int(attempt) < int(max_attempts):
        raise StudyRunError(
            f"attempt {attempt} is outside the frozen C3 policy of {max_attempts} attempts")
    if int(draw_index) < 0:
        raise StudyRunError("draw index must be non-negative")
    return ATTEMPT_DRAW_INDEX_BASE + int(draw_index) * int(max_attempts) + int(attempt)


def attempt_draw_ids(request_sha256: str, draw_index: int,
                     max_attempts: int = G.MAX_ATTEMPTS) -> tuple[str, ...]:
    """Every attempt identity one sampling draw is authorised to have paid for."""
    return tuple(I.draw_id(request_sha256, attempt_draw_index(draw_index, k, max_attempts))
                 for k in range(max_attempts))


def authorised_attempt_draw_ids(study_draw_ids: Sequence[str],
                                max_attempts: int = G.MAX_ATTEMPTS) -> set[str]:
    """The deterministic, pre-computable attempt identities of a set of sampling draws."""
    out: set[str] = set()
    for identity in study_draw_ids:
        sha, sep, index = str(identity).partition("#draw")
        if not sep:
            continue
        out |= set(attempt_draw_ids(sha, int(index), max_attempts))
    return out


def _prior_dirs() -> list[Path]:
    return [d for d in C.PRIOR_RECORD_DIRS if d.exists()]


def _reconcile_v7_canary(raw_dir: Path) -> tuple[float, int, tuple[str, ...]]:
    """Reconcile the signed v7 canary's persisted envelopes into prior spend.

    Read through `RawEnvelope`/`is_unbilled_rejection` rather than the generic record reader,
    so a router 4xx that provably incurred no charge reconciles at exactly 0.00 while anything
    else with a missing cost still fails closed.
    """
    if not raw_dir.exists():
        return 0.0, 0, ()
    total = 0.0
    count = 0
    sources: list[str] = []
    for path in sorted(raw_dir.glob("*.json")):
        envelope = L.RawEnvelope.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if envelope.cost_usd is not None:
            total += float(envelope.cost_usd)
        elif L.is_unbilled_rejection(envelope.response_body or {}, envelope.http_status,
                                     envelope.response_headers):
            total += 0.0
        else:
            raise L.ReconciliationError(
                f"v7 canary record {path} carries no returned cost and is not a provable "
                f"unbilled rejection (generation id {envelope.generation_id!r}); reconcile it "
                f"before any further paid call (R-C2)")
        count += 1
        sources.append(str(path))
    return total, count, tuple(sources)


def default_reconciliation() -> L.ReconciliationResult:
    """Reconstruct cumulative PRIOR spend from the actual persisted paid records.

    Every paid Q2 record — v5 gate runs, pre-v7 diagnostics (debited at their documented
    conservative UPPER bound and labelled non-reconciled), and the signed v7 canary — counts
    against the single $8.50 stop.
    """
    base = L.reconcile_prior_spend(_prior_dirs(),
                                   non_reconciled=list(C.PRIOR_DIAGNOSTIC_COMPONENTS))
    extra, count, sources = _reconcile_v7_canary(V7_CANARY_RAW)
    return L.ReconciliationResult(
        reconciled_usd=base.reconciled_usd + extra,
        record_count=base.record_count + count,
        components=base.components,
        sources=base.sources + sources,
    )


def open_ledger(run_dir: Path | str, *, model: str, endpoint: str = "",
                study_draw_ids: Sequence[str] = (),
                reconciliation: Optional[L.ReconciliationResult] = None,
                max_attempts: int = G.MAX_ATTEMPTS) -> L.V7Ledger:
    """R-C2: rebuild the ledger from EVERY persisted record BEFORE the first budget check.

    Both stores are reconstructed under one manifest binding, so walk probes and study draws
    share the single $8.50 stop and a restarted process resumes at the cumulative spend rather
    than at zero.
    """
    if reconciliation is None:
        reconciliation = L.ReconciliationResult(reconciled_usd=0.0, record_count=0)
    # The walk store is deliberately SHARED across the frozen panel so that every model's
    # spend counts against the one $8.50 stop. The manifest must therefore authorise the walk
    # draws of EVERY panel model, not just the current one: otherwise reconstructing the
    # ledger for the second model hits the first model's persisted walk envelope and raises
    # ManifestBindingError. The panel is frozen, so these ids are deterministic and
    # pre-computable — this widens the binding, it does not weaken it (a draw outside the
    # panel's authorised set is still refused). The same argument applies to the frozen C3
    # retry ladder: each sampling draw's `max_attempts` attempt identities are deterministic,
    # so they are authorised up front and every returned attempt has an identity to be booked
    # under (PS-4).
    authorised = set(study_draw_ids)
    authorised |= authorised_attempt_draw_ids(study_draw_ids, max_attempts)
    for panel_model in G.PANEL_ORDER:
        authorised |= set(walk_draw_ids(panel_model, max_attempts))
    manifest = L.RunManifest.from_draw_ids(authorised, model=model, endpoint=endpoint)
    # Money is reconstructed from the ATTEMPT store: it holds every returned wire response,
    # including the paid non-terminal retries the old runner discarded.
    ledger = L.reconstruct_ledger(attempt_store(run_dir), manifest=manifest,
                                  reconciliation=reconciliation)
    _verify_sampling_outcomes(study_store(run_dir), attempt_store(run_dir),
                              manifest=manifest, ledger=ledger, max_attempts=max_attempts)
    for envelope in walk_store(run_dir).envelopes():
        ledger.book_envelope(envelope)
    return ledger


def _verify_sampling_outcomes(store: L.EnvelopeStore, attempts: L.EnvelopeStore, *,
                              manifest: L.RunManifest, ledger: L.V7Ledger,
                              max_attempts: int) -> None:
    """Apply the R-E3 binding/uniqueness checks to the study store WITHOUT double-booking.

    A terminal sampling outcome is the same wire response as its terminal attempt, and that
    attempt has already been booked from the attempt store, so booking the study record again
    would count one paid response twice against the $8.50 stop. A study record with NO attempt
    record at all (written before the attempt store existed) is still booked here — otherwise
    a pre-PS-4 run would silently understate its spend.
    """
    booked = set(ledger.booked_draw_ids())
    seen: set[str] = set()
    for envelope in store.envelopes():
        if not manifest.contains(envelope.draw_id):
            raise L.ManifestBindingError(
                f"persisted record {envelope.draw_id} is not bound by manifest "
                f"{manifest.manifest_sha256[:12]} — refusing to reconstruct an unaudited run")
        if envelope.draw_id in seen:
            raise L.ManifestBindingError(
                f"draw {envelope.draw_id} appears more than once in {store.raw_dir}")
        seen.add(envelope.draw_id)
        linked = attempt_draw_ids(envelope.request_sha256, envelope.draw_index, max_attempts)
        if not any(identity in booked for identity in linked):
            ledger.book_envelope(envelope)


# =======================================================================================
# Staged authorization (PS-1) — the records the frozen design requires BEFORE the smoke
# =======================================================================================
#
# The frozen "Staged authorization" rule (requirement 4) is: *only after endpoints are promoted
# (or models excluded) AND the funding decision is recorded* may the 240-call smoke run.
#
# Record scheme, and why it is this one
# -------------------------------------
# `interlock` writes ONE `promotion_record.json` per run directory. This run renders a distinct
# manifest per model — different endpoint slug, different 528 request hashes, different 13,200
# draw identities — so a single write-once file physically cannot bind both models' promotion
# decisions: whichever model recorded second would either destroy the first record or bind to a
# manifest that is wrong for it. Therefore:
#
#   * PROMOTION records are MODEL-SPECIFIC (`interlock/promotion_record_<model>.json`). A
#     promotion decision is about one model at one endpoint under one manifest; the
#     `interlock.PromotionRecord` schema already carries exactly one `model` field, so only its
#     filename was ever panel-level.
#   * The FUNDING record is PANEL-LEVEL and there is exactly one per run
#     (`interlock/funding_record_panel.json`). The $8.50 stop is ONE stop shared by the whole
#     panel — "overriding all component caps", "not repurposed", "finish current model then
#     stop". A per-model funding record would assert per-model budgets, which the frozen design
#     explicitly refuses. It therefore binds EVERY panel model's manifest digest and projection
#     artifact digest, and names the models it authorizes.
#
# Both are derived from immutable evidence already on disk — the walk record and the bound
# projection artifact — never from a hand-typed endpoint tag or amount.
#
# These records are distinct artifacts from `interlock`'s own `promotion_record.json` /
# `funding_record.json`, which gate HEADLINE AGGREGATION (a later, separate step) and whose
# single-manifest schema cannot express the panel binding required here.

AUTHORIZATION_PROMOTION_SCHEMA = "q2_v7.study_run.model_promotion_authorization.v1"
AUTHORIZATION_FUNDING_SCHEMA = "q2_v7.study_run.panel_funding_authorization.v1"

FUNDING_AUTHORIZATION_FILENAME = "funding_record_panel.json"


def authorization_dir(run_dir: Path | str) -> Path:
    """The interlock directory — the two authorization families live side by side."""
    return K.interlock_dir(run_dir)


def promotion_authorization_path(run_dir: Path | str, model: str) -> Path:
    return authorization_dir(run_dir) / f"promotion_record_{_safe_model(model)}.json"


def funding_authorization_path(run_dir: Path | str) -> Path:
    return authorization_dir(run_dir) / FUNDING_AUTHORIZATION_FILENAME


def _walk_evidence(run_dir: Path | str, model: str) -> tuple[dict, str]:
    """The immutable walk record and its digest. The promoted tag is READ, never retyped."""
    path = walk_record_path(run_dir, model)
    if not path.exists():
        raise AuthorizationError(
            f"no walk record at {path} — the endpoint-promotion decision cannot be authorized "
            f"before the `walk` stage has produced its evidence")
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def build_promotion_authorization(run_dir: Path | str, *, model: str, snapshot: E.Snapshot,
                                  manifest: Optional[I.Manifest] = None,
                                  requests: Optional[Sequence[StudyRequestLike]] = None,
                                  probe_ids: Optional[Sequence[str]] = None,
                                  primary: str = "ENG",
                                  recorded_by: str = "") -> dict:
    """Derive one model's promotion authorization payload from the on-disk evidence (PS-1.2).

    Everything in the payload comes from `walk_<model>.json` and from the bound projection
    artifact: the endpoint tag, the projection total, the artifact digest. Nothing is supplied
    by the operator except who recorded the decision.
    """
    walk, walk_sha256 = _walk_evidence(run_dir, model)
    excluded = bool(walk.get("excluded")) or not walk.get("promoted_tag")
    payload: dict[str, Any] = {
        "schema": AUTHORIZATION_PROMOTION_SCHEMA,
        "model": model,
        "endpoint_snapshot_sha256": snapshot.sha256,
        "walk_record_sha256": walk_sha256,
        "excluded": excluded,
        "exclusion_reason": (walk.get("exclusion_reason") if excluded else None),
        "promoted_tag": (None if excluded else str(walk["promoted_tag"])),
        "promoted_endpoint_name": "",
        "promoted_upstream_model": "",
        "manifest_sha256": None,
        "projection_artifact_filename": None,
        "projection_artifact_sha256": None,
        "projection_total_usd": None,
        "projection_stop_usd": None,
        "recorded_utc": _utc_now(),
        "recorded_by": recorded_by,
    }
    if excluded:
        return payload

    tag = str(walk["promoted_tag"])
    candidate = gate_candidates(snapshot, model).get(f"{model}::{tag}")
    if candidate is None:
        raise AuthorizationError(
            f"the walk record promotes {tag!r}, which is not a candidate of {model!r} in the "
            f"committed endpoint snapshot")
    if manifest is None:
        probe_ids = list(probe_ids) if probe_ids is not None else probe_ids_for(primary)
        requests = requests if requests is not None else render_study_grid(model, tag, probe_ids)
        manifest = build_study_manifest(model=model, endpoint_tag=tag, requests=requests,
                                        probe_ids=probe_ids, snapshot_sha256=snapshot.sha256,
                                        binding=default_binding(primary))
    if requests is None:
        raise AuthorizationError("the rendered 528-request grid is required to authorize a "
                                 "promotion; it is what the projection is checked against")
    stored = manifest_path(run_dir, model)
    if stored.exists() and stored.read_bytes() != manifest.raw:
        raise AuthorizationError(
            f"the manifest on disk at {stored} is not the recomputed manifest for {model!r} — "
            f"refusing to authorize a promotion against a manifest this run cannot reproduce")
    artifact, artifact_sha256 = verify_projection(
        run_dir, model=model, tag=tag, snapshot=snapshot, manifest=manifest, requests=requests)
    binding = load_projection_binding(run_dir, model, tag)

    payload.update({
        "promoted_endpoint_name": candidate.endpoint_name,
        "promoted_upstream_model": (E.resolved_model_evidence(candidate.endpoint_name) or ""),
        "manifest_sha256": manifest.sha256,
        "projection_artifact_filename": binding["artifact_filename"],
        "projection_artifact_sha256": artifact_sha256,
        "projection_total_usd": float(artifact["total"]),
        "projection_stop_usd": float(artifact["stop"]),
    })
    return payload


def record_promotion_authorization(run_dir: Path | str, **kwargs) -> dict:
    """Write one model's promotion authorization. Write-once; makes NO paid call."""
    payload = build_promotion_authorization(run_dir, **kwargs)
    return _write_once_record(promotion_authorization_path(run_dir, payload["model"]),
                              payload, error=AuthorizationError)


def load_promotion_authorization(run_dir: Path | str, model: str) -> dict:
    return _read_once_record(promotion_authorization_path(run_dir, model),
                             AUTHORIZATION_PROMOTION_SCHEMA, error=AuthorizationError)


def build_funding_authorization(run_dir: Path | str, *, decision: str, authorized: bool,
                                reconciliation: L.ReconciliationResult,
                                hard_stop_usd: float = L.HARD_STOP_USD,
                                panel: Sequence[str] = G.PANEL_ORDER,
                                recorded_by: str = "") -> dict:
    """Derive the panel funding authorization payload from the recorded promotion decisions.

    Requires a promotion record for EVERY panel model — a promotion or an explicit exclusion —
    because the frozen rule is "only after endpoints are promoted (or models excluded) AND the
    funding decision is recorded". Binds each model's manifest digest and projection artifact
    digest (PS-1.3) alongside the $8.50 hard stop, the reconciled prior spend and the headroom
    that decision leaves.
    """
    models: list[dict] = []
    for model in panel:
        record = load_promotion_authorization(run_dir, model)
        models.append({
            "model": model,
            "excluded": bool(record["excluded"]),
            "endpoint_tag": record["promoted_tag"],
            "manifest_sha256": record["manifest_sha256"],
            "projection_artifact_sha256": record["projection_artifact_sha256"],
            "projection_total_usd": record["projection_total_usd"],
            "promotion_binding_sha256": record["binding_sha256"],
        })
    reconciled = float(reconciliation.total_usd)
    totals = [float(m["projection_total_usd"]) for m in models
              if m["projection_total_usd"] is not None]
    return {
        "schema": AUTHORIZATION_FUNDING_SCHEMA,
        "authorized": bool(authorized),
        "decision": decision,
        "hard_stop_usd": float(hard_stop_usd),
        "reconciled_prior_usd": reconciled,
        "reconciliation_is_exact": bool(reconciliation.is_exact),
        "available_headroom_usd": float(hard_stop_usd) - reconciled,
        "max_projected_total_usd": (max(totals) if totals else None),
        "models": models,
        "recorded_utc": _utc_now(),
        "recorded_by": recorded_by,
    }


def record_funding_authorization(run_dir: Path | str, **kwargs) -> dict:
    """Write the panel funding authorization. Write-once; makes NO paid call."""
    payload = build_funding_authorization(run_dir, **kwargs)
    return _write_once_record(funding_authorization_path(run_dir), payload,
                              error=AuthorizationError)


def load_funding_authorization(run_dir: Path | str) -> dict:
    return _read_once_record(funding_authorization_path(run_dir),
                             AUTHORIZATION_FUNDING_SCHEMA, error=AuthorizationError)


def require_paid_stage_authorization(run_dir: Path | str, *, model: str, tag: str,
                                     manifest: I.Manifest, snapshot: E.Snapshot,
                                     artifact_sha256: str,
                                     reconciliation: L.ReconciliationResult,
                                     stage: str = "smoke") -> tuple[dict, dict]:
    """RAISE unless BOTH frozen authorizations apply to exactly this paid stage (PS-1.4).

    Called before a transport is constructed, so every failure mode below — missing, refused,
    malformed, stale, cross-model, wrong-manifest, wrong-projection — produces zero wire calls.
    """
    run_dir = Path(run_dir)
    promotion = load_promotion_authorization(run_dir, model)      # raises when absent/edited

    def refuse(msg: str) -> None:
        raise AuthorizationError(
            f"{stage} refused for {model}@{tag}: {msg}. The frozen staged authorization "
            f"permits a paid study stage only after the endpoint-promotion decision and the "
            f"funding decision are recorded under {authorization_dir(run_dir)}.")

    if promotion.get("model") != model:
        refuse(f"the promotion record is for {promotion.get('model')!r}")
    if promotion.get("excluded"):
        refuse(f"the recorded decision is a capability/budget EXCLUSION "
               f"({promotion.get('exclusion_reason')}); there is no reduced-cell and no "
               f"reduced-S substitute")
    if promotion.get("promoted_tag") != tag:
        refuse(f"the promotion record promotes {promotion.get('promoted_tag')!r}, not {tag!r}")
    if promotion.get("manifest_sha256") != manifest.sha256:
        refuse(f"the promotion record binds manifest "
               f"{str(promotion.get('manifest_sha256'))[:12]}, not this run's "
               f"{manifest.sha256[:12]}")
    if promotion.get("endpoint_snapshot_sha256") != snapshot.sha256:
        refuse("the promotion record binds a different committed endpoint snapshot")
    if promotion.get("projection_artifact_sha256") != artifact_sha256:
        refuse(f"the promotion record binds projection artifact "
               f"{str(promotion.get('projection_artifact_sha256'))[:12]}, not the one this "
               f"stage would price from ({artifact_sha256[:12]})")
    _, walk_sha256 = _walk_evidence(run_dir, model)
    if promotion.get("walk_record_sha256") != walk_sha256:
        refuse("the walk record has changed since the promotion was authorized — the "
               "authorization is stale")

    funding = load_funding_authorization(run_dir)                 # raises when absent/edited
    if not funding.get("authorized"):
        refuse(f"the recorded funding decision REFUSES this run "
               f"({funding.get('decision')!r})")
    if not _close(float(funding.get("hard_stop_usd", 0.0)), L.HARD_STOP_USD):
        refuse(f"the funding record names a ${float(funding.get('hard_stop_usd', 0.0)):.2f} "
               f"stop, not the frozen ${L.HARD_STOP_USD:.2f}")
    if not _close(float(funding.get("reconciled_prior_usd", -1.0)),
                  float(reconciliation.total_usd)):
        refuse(f"prior reconciled spend has moved from "
               f"${float(funding.get('reconciled_prior_usd', -1.0)):.6f} to "
               f"${float(reconciliation.total_usd):.6f} since the funding decision")
    entries = [m for m in (funding.get("models") or []) if m.get("model") == model]
    if not entries:
        refuse("the funding record does not cover this model")
    entry = entries[0]
    if entry.get("endpoint_tag") != tag:
        refuse(f"the funding record funds {entry.get('endpoint_tag')!r} for this model")
    if entry.get("manifest_sha256") != manifest.sha256:
        refuse("the funding record binds a different manifest for this model")
    if entry.get("projection_artifact_sha256") != artifact_sha256:
        refuse("the funding record binds a different projection artifact for this model")
    if entry.get("promotion_binding_sha256") != promotion.get("binding_sha256"):
        refuse("the funding record was recorded against a different promotion record")
    if float(funding.get("available_headroom_usd", 0.0)) <= 0.0:
        refuse(f"the recorded funding decision leaves no headroom "
               f"(${float(funding.get('available_headroom_usd', 0.0)):.6f})")
    total = promotion.get("projection_total_usd")
    if total is None or float(total) > L.HARD_STOP_USD:
        refuse(f"the authorized projection total {total} does not fit the "
               f"${L.HARD_STOP_USD:.2f} stop")
    return promotion, funding


# =======================================================================================
# Draw execution — shared by the smoke and the full run
# =======================================================================================

@dataclass(frozen=True)
class DrawOutcome:
    """One attempted draw, whether freshly sent or replayed from its record."""
    cell_id: str
    probe_id: str
    order_idx: int
    draw_index: int
    draw_id: str
    request_sha256: str
    http_status: int
    parse_ok: bool
    parse_reason: str
    choice: Optional[int]                 # 0-based display position, or None (fail closed)
    cost_usd: Optional[float]
    reused: bool
    failures: tuple[str, ...]

    @property
    def coordinate(self) -> tuple[str, str, int]:
        return (self.cell_id, self.probe_id, self.order_idx)

    @property
    def valid(self) -> bool:
        return self.http_status == 200 and self.parse_ok and not self.failures

    def as_sampling_draw(self) -> G.SamplingDraw:
        """The completeness/bootstrap view of this draw.

        `valid`, not `parse_ok`, decides: a reply that parses but failed the frozen C1
        provider audit, the reasoning-off rule, or cost accounting is INADMISSIBLE evidence,
        and counting it as a good draw would let a mis-routed model clear a validity gate.
        Fail closed — an inadmissible draw is recorded as unparseable, never guessed.
        """
        return G.SamplingDraw(cell_id=self.cell_id, probe_id=self.probe_id,
                              order_idx=self.order_idx, draw_index=self.draw_index,
                              choice=self.choice if self.valid else None)


@dataclass(frozen=True)
class PlanRun:
    outcomes: tuple[DrawOutcome, ...]
    halted: bool
    halt_reason: str
    n_sent: int
    n_reused: int

    @property
    def n_attempted(self) -> int:
        return len(self.outcomes)

    @property
    def n_parsed(self) -> int:
        return sum(1 for o in self.outcomes if o.parse_ok)

    @property
    def parse_rate(self) -> float:
        return (self.n_parsed / len(self.outcomes)) if self.outcomes else 0.0


def plan_smoke_draws(smoke_requests: Sequence[StudyRequestLike]
                     ) -> list[tuple[StudyRequestLike, int]]:
    """48 smoke coordinates x draw indices 0-4 = exactly 240 draws."""
    if len(smoke_requests) != I.SMOKE_COORDINATES:
        raise I.CountMismatch(
            f"the smoke grid is frozen at {I.SMOKE_COORDINATES} coordinates, got "
            f"{len(smoke_requests)}")
    plan = [(r, index) for r in smoke_requests
            for index in range(I.SMOKE_DRAWS_PER_COORDINATE)]
    if len(plan) != I.SMOKE_DRAWS_TOTAL:
        raise I.CountMismatch(f"expected {I.SMOKE_DRAWS_TOTAL} smoke draws, got {len(plan)}")
    return plan


def plan_full_draws(requests: Sequence[StudyRequestLike]
                    ) -> list[tuple[StudyRequestLike, int]]:
    """528 coordinates x draw indices 0-24 = exactly 13,200 attempted draws.

    The smoke draws are NOT a separate stratum here: they are draw indices 0-4 of 48 of these
    coordinates and are replayed from their records, never repaid.
    """
    if len(requests) != I.COORDINATES_PER_MODEL:
        raise I.CountMismatch(
            f"the study grid is frozen at {I.COORDINATES_PER_MODEL} coordinates, got "
            f"{len(requests)}")
    plan = [(r, index) for r in requests for index in range(I.DRAWS_PER_COORDINATE)]
    if len(plan) != I.DRAWS_PER_MODEL:
        raise I.CountMismatch(f"expected {I.DRAWS_PER_MODEL} draws, got {len(plan)}")
    return plan


def audit_failures(response: Mapping[str, Any], *, model: str, tag: str,
                   snapshot: Optional[E.Snapshot]) -> tuple[str, ...]:
    """The FULL frozen C1 provider-audit proof plus the R-V7-1 reasoning-off rule, applied to
    a STUDY draw.

    The adversarial review found these were exercised only on the ~9 synthetic promotion-walk
    probes, so a study response could enter the eight estimands while carrying no
    `openrouter_metadata` at all, no reasoning-token evidence, a different provider display
    name, `strategy != "direct"`, `attempt != 1`, two available candidates, or an undated
    catalog slug — every one of which the frozen proof rejects. The proof is written for
    "a study response", so it must run on every draw, not only at the gate.
    """
    if snapshot is None:
        return ("audit:no_snapshot",)
    out: list[str] = []
    audit = E.verify_provider_audit(response, model, tag, snapshot)
    if not getattr(audit, "ok", False):
        out.extend(f"audit:{f}" for f in (getattr(audit, "failures", ()) or ()))
    reasoning = E.verify_reasoning_off(response)
    if not getattr(reasoning, "ok", False):
        out.extend(f"reasoning:{f}" for f in (getattr(reasoning, "failures", ()) or ()))
    return tuple(out)


def _replay(request: StudyRequestLike, draw_index: int, envelope: L.RawEnvelope,
            store: L.EnvelopeStore) -> DrawOutcome:
    """Replay a persisted draw FROM ITS RECORD (R-C1).

    The existence of a file is never evidence of success: the record's real HTTP status,
    content, cost and linked validation record decide the verdict, so a persisted failure
    stays a failure.
    """
    if envelope.request_sha256 != request.request_sha256:
        raise StudyRunError(
            f"persisted envelope {envelope.draw_id} carries request hash "
            f"{envelope.request_sha256} != recomputed {request.request_sha256}")
    if envelope.draw_index != draw_index:
        raise StudyRunError(
            f"persisted envelope {envelope.draw_id} carries draw index "
            f"{envelope.draw_index} != planned {draw_index}")

    failures: list[str] = []
    if envelope.http_status != 200:
        failures.append("http_error")
    if envelope.cost_usd is None and envelope.cost_status == "missing":
        failures.append("cost_unreconciled")
    parse = (I.parse_option(_message_content(envelope.response_body or {}))
             if envelope.http_status == 200
             else I.ParseResult(False, None, None, "http_error"))

    derived = store.get_derived(envelope.draw_id)
    if derived is not None:
        if derived.raw_sha256 != envelope.content_sha256():
            raise StudyRunError(
                f"derived record for {envelope.draw_id} is bound to raw hash "
                f"{derived.raw_sha256[:12]} but the envelope hashes to "
                f"{envelope.content_sha256()[:12]} — refusing to trust the audit trail")
        if not derived.valid:
            # A persisted invalid call stays invalid regardless of what a re-parse says.
            failures.extend(f for f in derived.failures if f not in failures)
            if parse.ok and not failures:
                failures.append("excluded_by_derived_record")
    else:
        _write_derived(store, envelope,
                       valid=(envelope.http_status == 200 and parse.ok and not failures),
                       failures=(*failures, *(() if parse.ok else (f"parse:{parse.reason}",))))

    return DrawOutcome(
        cell_id=request.cell_id, probe_id=request.probe_id, order_idx=int(request.order_idx),
        draw_index=draw_index, draw_id=envelope.draw_id,
        request_sha256=request.request_sha256, http_status=envelope.http_status,
        parse_ok=bool(parse.ok and not failures), parse_reason=parse.reason,
        choice=parse.index, cost_usd=envelope.cost_usd, reused=True,
        failures=tuple(failures))


def _persist_sampling_outcome(*, store: L.EnvelopeStore, draw: StudyDraw,
                              request_body: Mapping[str, Any],
                              request_headers: Mapping[str, str], wire: WireResult,
                              bucket: str, model: str, provider: str,
                              stage: str) -> Optional[L.RawEnvelope]:
    """Persist THE ONE terminal sampling outcome under the manifest-bound draw identity.

    Deliberately not booked here: this is the same wire response that was already persisted and
    booked under its own immutable attempt identity, and booking it twice would count one paid
    response twice against the $8.50 stop. `open_ledger` reconstructs money from the attempt
    store for exactly this reason, and still books any study record that has no attempt behind
    it (a pre-PS-4 record).
    """
    existing = store.get(draw.draw_id)
    if existing is not None:                       # crash between attempt and outcome: resume
        return existing
    envelope = L.build_envelope(
        draw=draw, request_body=request_body, request_headers=request_headers,
        response_body=wire.body, response_headers=wire.headers, http_status=wire.status,
        bucket=bucket, model=model, provider=provider, stage=stage)
    store.put(envelope)
    return envelope


def _send_draw(*, request: StudyRequestLike, draw_index: int, model: str, tag: str,
               headers: Mapping[str, str], store: L.EnvelopeStore, ledger: L.V7Ledger,
               transport: Transport, stage: str, bucket: str, sleep: G.Sleeper,
               clock: G.Clock, max_attempts: int,
               snapshot: Optional[E.Snapshot] = None,
               attempts: Optional[L.EnvelopeStore] = None,
               worst_case_call_usd: float = 0.0) -> DrawOutcome:
    """Send ONE study draw under the frozen C3 retry policy, persisting EVERY attempt (PS-4).

    Each wire attempt is persisted and booked under its own immutable attempt identity in the
    append-only attempt store BEFORE the retry policy is allowed to classify it, so a process
    exit anywhere in the retry ladder — including inside a backoff sleep — leaves complete,
    reconcilable evidence of every paid response. The terminal attempt is then persisted ONCE
    more, unbooked, in the study store under the manifest-bound sampling identity: that is the
    single outcome the completeness gate and the estimands see, so the 13,200 count is
    unchanged.

    An attempt whose returned cost cannot be reconciled still becomes durable evidence, and the
    run then FAILS CLOSED rather than continuing with an understated cumulative total (R-E2).

    Booking rule, stated exactly once: a returned response is booked EXACTLY ONCE, under its
    attempt identity. `open_ledger` authorises those identities, so that is what happens in
    every run this module drives. A caller whose ledger manifest binds only the 13,200 sampling
    identities (a pre-PS-4 ledger) cannot book an attempt identity; there the TERMINAL response
    is booked under its manifest-bound sampling identity instead — still exactly once, still
    against the same $8.50 stop — and a NON-terminal response that no identity can book halts
    the run, because that spend would otherwise escape the ledger entirely.
    """
    draw = StudyDraw(request_sha256=request.request_sha256, draw_index=draw_index)
    attempts = attempts if attempts is not None else attempt_store_for(store)
    wires: list[WireResult] = []
    attempt_ids: list[str] = []
    attempt_costs: list[Optional[float]] = []
    attempt_failures: list[tuple[str, ...]] = []

    def send() -> G.AttemptOutcome:
        # PS-7: the hard stop must be checked immediately before EVERY wire call, not once
        # per logical draw. `execute_plan` gates the draw, but the C3 ladder can then send up
        # to five times; each earlier attempt is booked (PS-4), so a retry can breach the stop
        # after its predecessor was legitimately allowed. Reserving all five up front is the
        # wrong fix -- it would halt otherwise valid draws whose retries are never used.
        decision = ledger.must_halt_before_next_call(worst_case_call_usd)
        if decision.halt:
            raise HardStopReached(decision.reason)
        wire = _post_once(transport, request.body, headers)
        index = len(wires)
        wires.append(wire)
        attempt = StudyDraw(
            request_sha256=request.request_sha256,
            draw_index=attempt_draw_index(draw_index, index, max_attempts))
        cost, failures, envelope = _record_and_book(
            store=attempts, ledger=ledger, draw=attempt, request_body=request.body,
            request_headers=headers, wire=wire, bucket=bucket, model=model, provider=tag,
            stage=f"{stage}_attempt")
        _write_derived(attempts, envelope,
                       valid=(wire.status == 200 and not failures),
                       failures=(*failures,
                                 *(("http_error",) if wire.status != 200 else ())))
        attempt_ids.append(attempt.draw_id)
        attempt_costs.append(cost)
        attempt_failures.append(tuple(failures))
        return G.AttemptOutcome(status=wire.status,
                                retry_after_s=_retry_after_seconds(wire.headers),
                                is_byok=_is_byok(wire.body), payload=wire.body)

    G.execute_with_retries(send, sleep=sleep, clock=clock, max_attempts=max_attempts)

    unreconciled = [identity for identity, failures in zip(attempt_ids, attempt_failures)
                    if any(f.startswith("cost_unreconciled") for f in failures)]
    if unreconciled:
        raise StudyRunError(
            f"attempt(s) {unreconciled} behind draw {draw.draw_id} returned no reconcilable "
            f"cost; every attempt is durable under {attempts.raw_dir}, but the run halts for "
            f"reconciliation rather than continuing with an understated cumulative total "
            f"(R-E2/R-C3)")
    unbindable = [identity for identity, failures in zip(attempt_ids[:-1], attempt_failures)
                  if any(f.startswith("ManifestBindingError") for f in failures)]
    if unbindable:
        raise StudyRunError(
            f"non-terminal attempt(s) {unbindable} behind draw {draw.draw_id} returned a paid "
            f"response that no authorised identity can book; the responses are durable under "
            f"{attempts.raw_dir}, but the run halts for reconciliation rather than "
            f"understating cumulative spend")

    terminal = wires[-1]
    failures = attempt_failures[-1]
    cost = attempt_costs[-1]
    if any(f.startswith("ManifestBindingError") for f in failures):
        # Pre-PS-4 ledger: the attempt identity is unauthorised, so the terminal response is
        # booked under the manifest-bound sampling identity. It is still booked exactly once.
        cost, failures, envelope = _record_and_book(
            store=store, ledger=ledger, draw=draw, request_body=request.body,
            request_headers=headers, wire=terminal, bucket=bucket, model=model, provider=tag,
            stage=stage)
    else:
        envelope = _persist_sampling_outcome(
            store=store, draw=draw, request_body=request.body, request_headers=headers,
            wire=terminal, bucket=bucket, model=model, provider=tag, stage=stage)

    parse = (I.parse_option(_message_content(terminal.body)) if terminal.status == 200
             else I.ParseResult(False, None, None, "http_error"))
    # The full C1 proof + reasoning-off rule on EVERY study draw, not just at the gate.
    audit = (audit_failures(terminal.body, model=model, tag=tag, snapshot=snapshot)
             if terminal.status == 200 else ())
    all_failures = tuple([
        *failures,
        *(("http_error",) if terminal.status != 200 else ()),
        *((f"parse:{parse.reason}",) if not parse.ok else ()),
        *audit,
    ])
    valid = terminal.status == 200 and parse.ok and not failures and not audit
    _write_derived(store, envelope, valid=valid, failures=all_failures)
    return DrawOutcome(
        cell_id=request.cell_id, probe_id=request.probe_id, order_idx=int(request.order_idx),
        draw_index=draw_index, draw_id=draw.draw_id,
        request_sha256=request.request_sha256, http_status=terminal.status,
        parse_ok=bool(parse.ok), parse_reason=parse.reason, choice=parse.index,
        cost_usd=cost, reused=False, failures=all_failures)


def execute_plan(*, plan: Sequence[tuple[StudyRequestLike, int]], model: str, tag: str,
                 key: str, store: L.EnvelopeStore, ledger: L.V7Ledger, transport: Transport,
                 worst_case_usd: Callable[[str], float], stage: str, bucket: str,
                 sleep: G.Sleeper = time.sleep, clock: G.Clock = time.monotonic,
                 max_attempts: int = G.MAX_ATTEMPTS,
                 snapshot: Optional[E.Snapshot] = None,
                 attempts: Optional[L.EnvelopeStore] = None) -> PlanRun:
    """Execute a planned set of draws with restart and the hard stop enforced.

    A draw already on disk is REPLAYED from its record and the transport is not called for it.
    Before every call that would actually be sent, the realised ledger decides whether the
    $8.50 stop permits it; if not the run halts BEFORE that call.
    """
    headers = E.request_headers(key)
    attempts = attempts if attempts is not None else attempt_store_for(store)
    outcomes: list[DrawOutcome] = []
    n_sent = n_reused = 0
    halted = False
    halt_reason = ""

    for request, draw_index in plan:
        identity = I.draw_id(request.request_sha256, draw_index)
        existing = store.get(identity)
        if existing is not None:
            outcomes.append(_replay(request, draw_index, existing, store))
            n_reused += 1
            continue

        worst_case = worst_case_usd(request.request_sha256)
        decision = ledger.must_halt_before_next_call(worst_case)
        if decision.halt:
            halted = True
            halt_reason = decision.reason
            break

        try:
            outcomes.append(_send_draw(
                request=request, draw_index=draw_index, model=model, tag=tag, headers=headers,
                store=store, ledger=ledger, transport=transport, stage=stage, bucket=bucket,
                sleep=sleep, clock=clock, max_attempts=max_attempts, snapshot=snapshot,
                attempts=attempts, worst_case_call_usd=worst_case))
        except HardStopReached as exc:
            # PS-7: a RETRY would have breached the stop. Everything already sent is durable
            # and booked; the ladder stopped without sending again. The run halts here and the
            # model is reported incomplete with no headline.
            halted = True
            halt_reason = str(exc)
            break
        n_sent += 1

    return PlanRun(outcomes=tuple(outcomes), halted=halted, halt_reason=halt_reason,
                   n_sent=n_sent, n_reused=n_reused)


# =======================================================================================
# Stages 3 and 4 — the 240-draw smoke and its promotion gate
# =======================================================================================

@dataclass(frozen=True)
class SmokeGateReport:
    """The frozen measurement-validity gate, decided BEFORE any contrast."""
    promoted: bool
    failures: tuple[str, ...]
    n_draws: int
    overall_parse_rate: float
    parseable_by_coordinate: Mapping[tuple[str, str, int], int]

    def as_record(self) -> dict:
        return {
            "promoted": self.promoted,
            "failures": list(self.failures),
            "n_draws": self.n_draws,
            "overall_parse_rate": self.overall_parse_rate,
            "min_parseable_per_coordinate": MIN_SMOKE_PARSEABLE_PER_COORDINATE,
            "min_overall_parse_rate": G.MIN_PARSEABLE_OVERALL,
            "parseable_by_coordinate": {f"{c}|{p}|{o}": n for (c, p, o), n
                                        in sorted(self.parseable_by_coordinate.items())},
        }


#: Frozen: >= 4/5 parseable in EVERY smoke coordinate.
MIN_SMOKE_PARSEABLE_PER_COORDINATE = 4


def smoke_promotion_gate(outcomes: Sequence[DrawOutcome]) -> SmokeGateReport:
    """Promote only if EVERY smoke coordinate yields at least one parseable reply, the
    per-coordinate parseable rate is >= 4/5, and the overall parse rate is >= 0.95.

    Unparseable replies are never guessed or clamped. A failure here is a MEASUREMENT-VALIDITY
    failure: the model emits no headline.
    """
    attempted: dict[tuple[str, str, int], int] = {}
    parseable: dict[tuple[str, str, int], int] = {}
    for outcome in outcomes:
        coord = outcome.coordinate
        attempted[coord] = attempted.get(coord, 0) + 1
        parseable.setdefault(coord, 0)
        # `valid`, not `parse_ok`: a reply that parses but failed the C1 provider audit, the
        # reasoning-off rule, or cost accounting is inadmissible and never counts as a good
        # reply for this measurement-validity gate.
        if outcome.valid:
            parseable[coord] += 1

    failures: list[str] = []
    if len(outcomes) != I.SMOKE_DRAWS_TOTAL:
        failures.append(f"{len(outcomes)} smoke draws attempted, expected "
                        f"{I.SMOKE_DRAWS_TOTAL}")
    if len(attempted) != I.SMOKE_COORDINATES:
        failures.append(f"{len(attempted)} smoke coordinates, expected "
                        f"{I.SMOKE_COORDINATES}")

    silent = sorted(c for c, n in parseable.items() if n < 1)
    if silent:
        failures.append(f"coordinates with no parseable reply at all: {silent[:5]} "
                        f"({len(silent)} total)")
    thin = sorted(c for c, n in parseable.items()
                  if n < MIN_SMOKE_PARSEABLE_PER_COORDINATE)
    if thin:
        failures.append(
            f"coordinates below {MIN_SMOKE_PARSEABLE_PER_COORDINATE}/"
            f"{I.SMOKE_DRAWS_PER_COORDINATE} parseable: "
            f"{[(c, parseable[c]) for c in thin[:5]]} ({len(thin)} total)")

    n_parsed = sum(parseable.values())
    rate = (n_parsed / len(outcomes)) if outcomes else 0.0
    if rate < G.MIN_PARSEABLE_OVERALL:
        failures.append(f"overall smoke parse rate {rate:.4f} < {G.MIN_PARSEABLE_OVERALL}")

    return SmokeGateReport(promoted=not failures, failures=tuple(failures),
                           n_draws=len(outcomes), overall_parse_rate=rate,
                           parseable_by_coordinate=parseable)


@dataclass(frozen=True)
class SmokeReport:
    model: str
    endpoint: str
    run: PlanRun
    gate: SmokeGateReport

    @property
    def promoted(self) -> bool:
        return self.gate.promoted and not self.run.halted

    @property
    def emit_headline(self) -> bool:
        return False        # the smoke NEVER emits a headline; it is a validity gate only

    def as_record(self) -> dict:
        return {
            "artifact": "Q2 Stage-2 v7.2 outcome-blinded smoke",
            "model": self.model,
            "endpoint": self.endpoint,
            "n_attempted": self.run.n_attempted,
            "n_sent": self.run.n_sent,
            "n_reused": self.run.n_reused,
            "halted": self.run.halted,
            "halt_reason": self.run.halt_reason,
            "gate": self.gate.as_record(),
            "promoted": self.promoted,
        }


def smoke_record_path(run_dir: Path | str, model: str) -> Path:
    return Path(run_dir) / f"smoke_{_safe_model(model)}.json"


def run_smoke(*, model: str, tag: str, key: str,
              smoke_requests: Sequence[StudyRequestLike], store: L.EnvelopeStore,
              ledger: L.V7Ledger, transport: Transport,
              worst_case_usd: Callable[[str], float],
              run_dir: Optional[Path] = None,
              sleep: G.Sleeper = time.sleep, clock: G.Clock = time.monotonic,
              max_attempts: int = G.MAX_ATTEMPTS,
              snapshot: Optional[E.Snapshot] = None,
              attempts: Optional[L.EnvelopeStore] = None) -> SmokeReport:
    """Execute the 240 outcome-blinded smoke draws and decide the frozen promotion gate."""
    run = execute_plan(plan=plan_smoke_draws(smoke_requests), model=model, tag=tag, key=key,
                       store=store, ledger=ledger, transport=transport,
                       worst_case_usd=worst_case_usd, stage=SMOKE_STAGE, bucket=SMOKE_BUCKET,
                       sleep=sleep, clock=clock, max_attempts=max_attempts,
                       snapshot=snapshot, attempts=attempts)
    report = SmokeReport(model=model, endpoint=tag, run=run,
                         gate=smoke_promotion_gate(run.outcomes))
    if run_dir is not None:
        path = smoke_record_path(run_dir, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.as_record(), sort_keys=True, indent=1))
    return report


def require_smoke_promotion(report: SmokeReport) -> None:
    """Fail closed: an unpromoted smoke is a measurement-validity failure, not a finding to
    work around. No headline is emitted and the full run never starts."""
    if not report.promoted:
        raise MeasurementValidityFailure(
            f"{report.model}@{report.endpoint} failed the 240-draw smoke promotion gate; no "
            f"headline is emitted: " + "; ".join(report.gate.failures or (report.run.halt_reason,)))


# =======================================================================================
# Stage 5 — the full run
# =======================================================================================

@dataclass(frozen=True)
class FullRunReport:
    model: str
    endpoint: str
    run: PlanRun
    completeness: Optional[G.CompletenessReport]

    @property
    def complete(self) -> bool:
        return (not self.run.halted and self.completeness is not None
                and self.completeness.complete)

    @property
    def model_incomplete(self) -> bool:
        return not self.complete

    @property
    def emit_headline(self) -> bool:
        """A headline requires a completed model. A halt at the hard stop NEVER emits one."""
        return self.complete

    def as_record(self) -> dict:
        return {
            "artifact": "Q2 Stage-2 v7.2 full run",
            "model": self.model,
            "endpoint": self.endpoint,
            "n_attempted": self.run.n_attempted,
            "n_sent": self.run.n_sent,
            "n_reused": self.run.n_reused,
            "expected_attempted": I.DRAWS_PER_MODEL,
            "halted": self.run.halted,
            "halt_reason": self.run.halt_reason,
            "model_incomplete": self.model_incomplete,
            "emit_headline": self.emit_headline,
            "completeness": (self.completeness.as_record() if self.completeness else None),
        }


def full_record_path(run_dir: Path | str, model: str) -> Path:
    return Path(run_dir) / f"full_{_safe_model(model)}.json"


def run_full(*, model: str, tag: str, key: str, requests: Sequence[StudyRequestLike],
             probe_ids: Sequence[str], store: L.EnvelopeStore, ledger: L.V7Ledger,
             transport: Transport, worst_case_usd: Callable[[str], float],
             run_dir: Optional[Path] = None,
             sleep: G.Sleeper = time.sleep, clock: G.Clock = time.monotonic,
             max_attempts: int = G.MAX_ATTEMPTS,
             snapshot: Optional[E.Snapshot] = None,
             attempts: Optional[L.EnvelopeStore] = None) -> FullRunReport:
    """Execute the full 13,200-draw design, reusing every persisted smoke draw.

    The 240 smoke draws are draw indices 0-4 of 48 of these 528 coordinates: they are replayed
    from their records and never repaid, leaving 12,960 additional draws. If realised cost
    drift would make the next call breach $8.50 the run halts BEFORE that call, the model is
    reported incomplete, and no headline is emitted — "finish current model" never overrides
    the stop.
    """
    run = execute_plan(plan=plan_full_draws(requests), model=model, tag=tag, key=key,
                       store=store, ledger=ledger, transport=transport,
                       worst_case_usd=worst_case_usd, stage=FULL_STAGE, bucket=FULL_BUCKET,
                       sleep=sleep, clock=clock, max_attempts=max_attempts,
                       snapshot=snapshot, attempts=attempts)
    completeness: Optional[G.CompletenessReport] = None
    if not run.halted:
        completeness = G.completeness_gate(
            [o.as_sampling_draw() for o in run.outcomes], expected_probe_ids=list(probe_ids))
    report = FullRunReport(model=model, endpoint=tag, run=run, completeness=completeness)
    if run_dir is not None:
        path = full_record_path(run_dir, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.as_record(), sort_keys=True, indent=1))
    return report


# =======================================================================================
# Pinned tokenizer (C2) — a local, hash-verified read; never a download
# =======================================================================================

def pinned_tokenizer(model: str, snapshot: E.Snapshot, tokenizer_dir: Path | str
                     ) -> G.Tokenizer:
    """Load the pinned official tokenizer from a LOCAL directory, verifying every file hash
    against the committed snapshot. There is no download and no fallback: an unverifiable
    tokenizer means no projection, which means no promotion."""
    spec = snapshot.tokenizers.get(model)
    if not isinstance(spec, Mapping):
        raise StudyRunError(f"the committed snapshot pins no tokenizer for {model!r}")
    directory = Path(tokenizer_dir)
    for name, expected in (spec.get("files") or {}).items():
        path = directory / name
        if not path.exists():
            raise StudyRunError(
                f"pinned tokenizer file {name} is absent from {directory} (repo "
                f"{spec.get('repo_id')} at revision {spec.get('revision')})")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise StudyRunError(
                f"pinned tokenizer file {name} hashes to {digest} != committed {expected}")
    # PS-2: return the gate's PinnedTokenizer, NOT a bare closure. `project_full_grid`
    # dispatches on the object's type: a PinnedTokenizer carrying a chat template takes the
    # exact frozen-C2 serialization path, while a plain `str -> int` callable silently falls
    # back to the fixed-overhead heuristic and labels the projection
    # `fixed_overhead_fallback`. Returning a closure here would mean the real study
    # instrument never used the frozen method. Do NOT wrap this in a lambda.
    return G.load_pinned_tokenizer(model, directory, spec=spec)


# =======================================================================================
# CLI — one stage per invocation; NOTHING auto-advances
# =======================================================================================

def _print_ledger(ledger: L.V7Ledger) -> None:
    print(f"prior reconciled spend: ${ledger.prior_usd:.6f} (exact={ledger.is_exact})")
    print(f"current-run spend already on disk: ${ledger.run_usd:.6f}")
    print(f"hard stop ${ledger.hard_stop_usd:.2f}; remaining ${ledger.remaining_usd:.4f}\n")


def _stage_walk(args, *, key: str, snapshot: E.Snapshot, run_dir: Path) -> int:
    probes = probe_ids_for(args.primary)
    tokenizer = pinned_tokenizer(args.model, snapshot, args.tokenizer_dir)
    ledger = open_ledger(run_dir, model=args.model, reconciliation=default_reconciliation())
    _print_ledger(ledger)
    result = run_walk(model=args.model, key=key, snapshot=snapshot,
                      store=walk_store(run_dir), ledger=ledger,
                      transport=SingleAttemptTransport(ca_file=args.ca_file),
                      requests_for=lambda tag: render_study_grid(args.model, tag, probes),
                      tokenizer=tokenizer, retry_reserve_usd=args.retry_reserve,
                      projection_dir=run_dir, run_dir=run_dir)
    for probe in result.probes:
        print(f"### {probe.tag}: HTTP {probe.http_status} ({probe.terminal_reason}, "
              f"{probe.attempts_made} attempts) cost=${probe.booked_cost_usd:.8f}")
        for failure in (*probe.envelope_audit_failures, *probe.reasoning_failures):
            print(f"    {failure}")
    if result.excluded:
        print(f"\n{args.model}: CAPABILITY/BUDGET EXCLUSION — {result.decision.exclusion_reason}")
        print("There is no reduced-cell and no reduced-S substitute. Nothing further runs.")
        return 1
    print(f"\npromoted {result.promoted_tag!r}; record at {result.record_path}")
    print(f"next stage (invoke separately): `{USAGE}` with stage `project`")
    return 0


def _stage_project(args, *, key: str, snapshot: E.Snapshot, run_dir: Path) -> int:
    tag = load_promotion(run_dir, args.model)
    probes = probe_ids_for(args.primary)
    requests = render_study_grid(args.model, tag, probes)
    tokenizer = pinned_tokenizer(args.model, snapshot, args.tokenizer_dir)
    ledger = open_ledger(run_dir, model=args.model, endpoint=tag,
                         study_draw_ids=[I.draw_id(r.request_sha256, i) for r in requests
                                         for i in range(I.DRAWS_PER_COORDINATE)],
                         reconciliation=default_reconciliation())
    _print_ledger(ledger)
    candidate = gate_candidates(snapshot, args.model)[f"{args.model}::{tag}"]
    projection = build_projection(model=args.model, candidate=candidate, requests=requests,
                                 tokenizer=tokenizer, ledger=ledger,
                                 retry_reserve_usd=args.retry_reserve)
    # PS-2: a study projection MUST use the frozen documented-tokenizer serialization. This
    # raises if the fixed-overhead fallback was taken (e.g. a model with no pinned chat
    # template), so a heuristic projection can never reach authorize/smoke.
    G.require_frozen_c2_serialization(projection)
    manifest = build_study_manifest(model=args.model, endpoint_tag=tag, requests=requests,
                                    probe_ids=probes, snapshot_sha256=snapshot.sha256,
                                    binding=default_binding(args.primary))
    decision = write_study_manifest(run_dir, args.model, manifest)
    path = write_projection(run_dir, projection)
    binding = write_projection_binding(run_dir, projection, snapshot=snapshot,
                                       manifest=manifest, artifact_path=path,
                                       recorded_by=args.recorded_by)
    print(f"projection artifact: {path}")
    print(f"artifact sha256 {binding['artifact_sha256'][:16]} bound by "
          f"{projection_binding_path(run_dir, args.model, tag).name}")
    print(f"total ${projection.total:.4f} of ${projection.stop:.2f}; fits={projection.fits}")
    print(f"manifest {decision.sha256[:12]} (created={decision.created}, "
          f"resumed={decision.resumed}) binds {manifest.n_draws} draws / "
          f"{manifest.n_coordinates} coordinates")
    print(f"next stage (invoke separately): `{USAGE}` with stage `authorize`")
    return 0 if projection.fits else 1


def _stage_authorize(args, *, key: str, snapshot: E.Snapshot, run_dir: Path) -> int:
    """Record the frozen staged authorization. This stage makes NO paid call of any kind.

    `--record-funding` records the ONE panel-level funding decision; without it the stage
    records this model's endpoint-promotion decision, derived entirely from the immutable walk
    record and the bound projection artifact.
    """
    print("authorize: no network call and no paid call is made by this stage.\n")
    if args.record_funding:
        if not args.funding_decision:
            print("--funding-decision TEXT is required: the funding decision is recorded "
                  "verbatim, not inferred", file=sys.stderr)
            return 2
        record = record_funding_authorization(
            run_dir, decision=args.funding_decision, authorized=not args.refuse_funding,
            reconciliation=default_reconciliation(), recorded_by=args.recorded_by)
        print(f"panel funding decision recorded at {funding_authorization_path(run_dir)}")
        print(f"authorized={record['authorized']} hard stop "
              f"${record['hard_stop_usd']:.2f}; reconciled prior "
              f"${record['reconciled_prior_usd']:.6f} (exact="
              f"{record['reconciliation_is_exact']}); headroom "
              f"${record['available_headroom_usd']:.4f}")
        for entry in record["models"]:
            print(f"    {entry['model']}: endpoint={entry['endpoint_tag']!r} "
                  f"excluded={entry['excluded']} "
                  f"manifest={str(entry['manifest_sha256'])[:12]} "
                  f"projection={str(entry['projection_artifact_sha256'])[:12]} "
                  f"total={entry['projection_total_usd']}")
        if not record["authorized"]:
            print("\nFUNDING REFUSED — no paid study stage may run.")
            return 1
        print(f"\nnext stage (invoke separately): `{USAGE}` with stage `smoke`")
        return 0

    record = record_promotion_authorization(
        run_dir, model=args.model, snapshot=snapshot, primary=args.primary,
        recorded_by=args.recorded_by)
    print(f"promotion decision recorded at "
          f"{promotion_authorization_path(run_dir, args.model)}")
    if record["excluded"]:
        print(f"{args.model}: recorded as a capability/budget EXCLUSION "
              f"({record['exclusion_reason']}); no paid study stage may run for it.")
        return 1
    print(f"promoted {record['promoted_tag']!r} (from walk record "
          f"{record['walk_record_sha256'][:12]}); manifest "
          f"{record['manifest_sha256'][:12]}; projection "
          f"{record['projection_artifact_sha256'][:12]} totalling "
          f"${record['projection_total_usd']:.4f} of "
          f"${record['projection_stop_usd']:.2f}")
    print(f"\nrecord the panel funding decision next: `{USAGE}` with stage `authorize` "
          f"--record-funding --funding-decision TEXT")
    return 0


def _prepared(args, *, snapshot: E.Snapshot, run_dir: Path, stage: str = "smoke"):
    """Shared smoke/full preparation: promoted tag, grid, manifest, projection, authorization,
    ledger, worst case — in that order, and ALL of it before any transport can be constructed.

    Both fail-closed gates the v7.2 pre-smoke re-audit demanded live here, so a missing,
    refused, malformed, stale, cross-model or wrong-manifest authorization (PS-1) and an
    absent, unbound, edited or arithmetically inconsistent projection (PS-3) each abort the
    invocation with exactly ZERO wire calls: the caller has not yet built a transport.
    """
    tag = load_promotion(run_dir, args.model)
    probes = probe_ids_for(args.primary)
    requests = render_study_grid(args.model, tag, probes)
    manifest = build_study_manifest(model=args.model, endpoint_tag=tag, requests=requests,
                                    probe_ids=probes, snapshot_sha256=snapshot.sha256,
                                    binding=default_binding(args.primary))
    write_study_manifest(run_dir, args.model, manifest)          # resumes only if identical
    reconciliation = default_reconciliation()
    artifact, artifact_sha256 = verify_projection(
        run_dir, model=args.model, tag=tag, snapshot=snapshot, manifest=manifest,
        requests=requests)
    require_paid_stage_authorization(
        run_dir, model=args.model, tag=tag, manifest=manifest, snapshot=snapshot,
        artifact_sha256=artifact_sha256, reconciliation=reconciliation, stage=stage)
    ledger = open_ledger(run_dir, model=args.model, endpoint=tag,
                         study_draw_ids=manifest.draw_identities,
                         reconciliation=reconciliation)
    return tag, probes, requests, ledger, worst_case_lookup(artifact)


def _stage_smoke(args, *, key: str, snapshot: E.Snapshot, run_dir: Path) -> int:
    # `_prepared` raises before this function ever names a transport class (PS-1/PS-3).
    tag, probes, requests, ledger, worst_case = _prepared(args, snapshot=snapshot,
                                                          run_dir=run_dir, stage="smoke")
    _print_ledger(ledger)
    smoke = render_smoke_grid(args.model, tag, probes)
    report = run_smoke(model=args.model, tag=tag, key=key, smoke_requests=smoke,
                       store=study_store(run_dir), ledger=ledger,
                       transport=SingleAttemptTransport(ca_file=args.ca_file),
                       worst_case_usd=worst_case, run_dir=run_dir,
                       snapshot=snapshot)
    print(f"smoke: {report.run.n_attempted} attempted "
          f"({report.run.n_sent} sent, {report.run.n_reused} replayed); "
          f"parse rate {report.gate.overall_parse_rate:.4f}")
    for failure in report.gate.failures:
        print(f"    {failure}")
    if not report.promoted:
        print("MEASUREMENT-VALIDITY FAILURE — no headline is emitted and the full run does "
              "not start.")
        return 1
    print(f"next stage (invoke separately): `{USAGE}` with stage `full`")
    return 0


def _stage_full(args, *, key: str, snapshot: E.Snapshot, run_dir: Path) -> int:
    tag, probes, requests, ledger, worst_case = _prepared(args, snapshot=snapshot,
                                                          run_dir=run_dir, stage="full")
    smoke_record = smoke_record_path(run_dir, args.model)
    if not smoke_record.exists() or not json.loads(smoke_record.read_text()).get("promoted"):
        print(f"the smoke stage has not been run and promoted for {args.model} "
              f"({smoke_record}) — refusing to start the full run", file=sys.stderr)
        return 2
    _print_ledger(ledger)
    report = run_full(model=args.model, tag=tag, key=key, requests=requests,
                      probe_ids=probes, store=study_store(run_dir), ledger=ledger,
                      transport=SingleAttemptTransport(ca_file=args.ca_file),
                      worst_case_usd=worst_case, run_dir=run_dir, snapshot=snapshot)
    print(f"full run: {report.run.n_attempted} attempted of {I.DRAWS_PER_MODEL} "
          f"({report.run.n_sent} sent, {report.run.n_reused} replayed)")
    if report.run.halted:
        print(f"HALTED before the next call: {report.run.halt_reason}")
    print(f"model_incomplete={report.model_incomplete} emit_headline={report.emit_headline}")
    print(f"cumulative ${ledger.total_spent_usd:.6f} of ${ledger.hard_stop_usd:.2f} "
          f"(exact={ledger.is_exact})")
    return 0 if report.emit_headline else 1


_DISPATCH: Mapping[str, Callable[..., int]] = {
    "walk": _stage_walk,
    "project": _stage_project,
    "authorize": _stage_authorize,
    "smoke": _stage_smoke,
    "full": _stage_full,
}

#: Stages that can send a paid request. `authorize` is deliberately NOT one of them.
PAID_STAGES: tuple[str, ...] = ("walk", "smoke", "full")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m alignment.q2_v7.study_run",
        description=("Q2 Stage-2 v7.2 study runner. Each stage is invoked SEPARATELY and "
                     "never starts its successor."),
        epilog=f"usage: {USAGE}")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--model", required=True,
                        help=f"one of the frozen panel, in order: {list(G.PANEL_ORDER)}")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    parser.add_argument("--i-have-authorized-paid-spend", action="store_true", dest="ack",
                        help="required acknowledgement that this makes PAID OpenRouter calls")
    parser.add_argument("--tokenizer-dir", default=None,
                        help="local directory holding the pinned tokenizer files (C2)")
    parser.add_argument("--retry-reserve", type=float, default=DEFAULT_RETRY_RESERVE_USD)
    parser.add_argument("--primary", default="ENG")
    parser.add_argument("--ca-file", default=None)
    parser.add_argument("--recorded-by", default="",
                        help="who recorded a decision (`authorize`/`project` stages)")
    parser.add_argument("--record-funding", action="store_true",
                        help="`authorize`: record the ONE panel-level funding decision")
    parser.add_argument("--funding-decision", default="",
                        help="`authorize --record-funding`: the decision, recorded verbatim")
    parser.add_argument("--refuse-funding", action="store_true",
                        help="`authorize --record-funding`: record a REFUSAL (authorized=false)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.ack:
        print("This makes PAID OpenRouter calls. Re-run with "
              "--i-have-authorized-paid-spend", file=sys.stderr)
        return 2
    # `authorize` records decisions from files already on disk; it never opens a socket, so it
    # neither needs nor is given a credential.
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key and args.stage != "authorize":
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2
    if args.model not in G.PANEL_ORDER:
        print(f"{args.model!r} is not in the frozen v7 panel {list(G.PANEL_ORDER)}; the "
              f"panel and its order are frozen and no model is substituted", file=sys.stderr)
        return 2
    if args.stage in ("walk", "project") and not args.tokenizer_dir:
        print("--tokenizer-dir is required: the C2 full-grid projection uses the PINNED "
              "official tokenizer, hash-verified against the committed snapshot",
              file=sys.stderr)
        return 2

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = E.load_snapshot(ROOT / E.SNAPSHOT_PATH)

    try:
        # Exactly ONE stage runs per invocation: no stage ever advances to the next.
        return _DISPATCH[args.stage](args, key=key, snapshot=snapshot, run_dir=run_dir)
    except (StudyRunError, L.LedgerError, G.GateError, I.IdentityError, E.EnvelopeError,
            K.InterlockError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
