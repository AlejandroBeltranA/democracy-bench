"""Q2 Stage-2 v7.2 executable study sequence — the integrated live runner.

The v7.2 code review's "Implementation-scope gap" section names exactly what this module is:
the one executable path that renders the frozen grid, walks the endpoint sequence, projects
the full-grid cost, executes the outcome-blinded smoke, reuses those draws inside the full
13,200-draw design, and enforces restart and the hard stop throughout.

Six separately callable, separately testable stages (nothing ever auto-advances):

1. `run_walk`      — the deterministic endpoint promotion walk (ONE synthetic, non-study
                     capability probe per candidate, in frozen sequence order).
2. `run_projection`— the C2 documented-tokenizer full-grid projection artifact.
3. `run_smoke`     — the 240 outcome-blinded smoke draws (48 coordinates x draw indices 0-4).
4. `smoke_promotion_gate` — the frozen measurement-validity gate on those 240 draws.
5. `run_full`      — the remaining 12,960 draws (240 + 12,960 = 13,200 attempted per model),
                     reusing every persisted smoke draw and never repaying it.
6. `build_study_manifest` / `write_study_manifest` — the R-V7-7 manifest binding, plus
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
  that would breach it, the model is reported incomplete, and no headline is emitted.

NETWORK: the HTTP transport is an INJECTED seam (`SingleAttemptTransport` is the only live
implementation and is constructed solely by `main`). Every stage function takes the transport
as an argument, so the whole module is exercised with no network in
`tests/test_q2_v7_study_run.py`.

Usage (each stage is invoked separately; no stage ever starts its successor):

    python -m alignment.q2_v7.study_run {walk,project,smoke,full} \
        --model MODEL --run-dir DIR --i-have-authorized-paid-spend
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from alignment.q2_v7 import canary as C
from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import identity as I
from alignment.q2_v7 import ledger as L

ROOT = Path(__file__).resolve().parents[3]
API_URL = "https://openrouter.ai/api/v1/chat/completions"
DESIGN_DOC = ROOT / "paper" / "Q2_STAGE2_HOSTED_DESIGN.md"
DEFAULT_RUN_DIR = ROOT / "out" / "q2_stage2_v7_study"
V7_CANARY_RAW = ROOT / "out" / "q2_stage2_v7_canary" / "raw"

STAGES: tuple[str, ...] = ("walk", "project", "smoke", "full")

#: Reporting labels only — ALL buckets share the single $8.50 stop (R-V7-6).
WALK_STAGE, WALK_BUCKET = "gate", "gate"
SMOKE_STAGE, SMOKE_BUCKET = "smoke", "smoke"
FULL_STAGE, FULL_BUCKET = "study", "study"

#: Worst case debited against the stop before one synthetic capability probe. The probe is a
#: two-message, four-token call; a cent is orders of magnitude above its realised cost.
PROBE_WORST_CASE_USD = 0.01

#: Separately quantified retry reserve (C2 `total` term). Overridable per run; never zero by
#: default, because a projection with no reserve can authorise a run it cannot finish.
DEFAULT_RETRY_RESERVE_USD = 0.25

USAGE = ("python -m alignment.q2_v7.study_run {walk,project,smoke,full} "
         "--model MODEL --run-dir DIR --i-have-authorized-paid-spend")


# =======================================================================================
# Errors — every failure mode is fail-closed and loud.
# =======================================================================================

class StudyRunError(RuntimeError):
    """Fail-closed runner failure."""


class CapabilityExclusion(StudyRunError):
    """No endpoint in the model's frozen sequence passed (a)+(b)+(c).

    There is NO reduced-cell and NO reduced-S substitute: the model is reported as a
    capability/budget exclusion and nothing further is executed for it.
    """


class MeasurementValidityFailure(StudyRunError):
    """The 240-draw smoke did not clear the frozen promotion gate. No headline is emitted."""


class HardStopHalt(StudyRunError):
    """The $8.50 stop would be breached by the next call."""


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


def projection_path(projection_dir: Path | str, projection: G.CostProjection) -> Path:
    tag = projection.endpoint_tag.replace("/", "__")
    return Path(projection_dir) / f"projection_{_safe_model(projection.model)}__{tag}.json"


def write_projection(projection_dir: Path | str, projection: G.CostProjection) -> Path:
    """Persist the per-candidate cost artifact. An existing artifact is NEVER overwritten: a
    projection that decided a promotion is immutable evidence."""
    path = projection_path(projection_dir, projection)
    if path.exists():
        return path
    G.write_projection_artifact(path, projection)
    return path


def read_projection(path: Path | str) -> dict:
    return json.loads(Path(path).read_text())


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
    240 smoke draws the first five of the 25 rather than a separate payment."""
    return L.EnvelopeStore(Path(run_dir) / "study")


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
    # panel's authorised set is still refused).
    authorised = set(study_draw_ids)
    for panel_model in G.PANEL_ORDER:
        authorised |= set(walk_draw_ids(panel_model, max_attempts))
    manifest = L.RunManifest.from_draw_ids(authorised, model=model, endpoint=endpoint)
    ledger = L.reconstruct_ledger(study_store(run_dir), manifest=manifest,
                                  reconciliation=reconciliation)
    for envelope in walk_store(run_dir).envelopes():
        ledger.book_envelope(envelope)
    return ledger


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


def _send_draw(*, request: StudyRequestLike, draw_index: int, model: str, tag: str,
               headers: Mapping[str, str], store: L.EnvelopeStore, ledger: L.V7Ledger,
               transport: Transport, stage: str, bucket: str, sleep: G.Sleeper,
               clock: G.Clock, max_attempts: int,
               snapshot: Optional[E.Snapshot] = None) -> DrawOutcome:
    """Send ONE study draw under the frozen C3 retry policy, persisting the terminal response.

    Only the terminal response is persisted, because a study draw's identity (request hash +
    immutable draw index) is bound by the manifest and cannot absorb extra indices. A
    non-terminal transient attempt that nevertheless returned a finite cost therefore cannot be
    booked under any authorised identity, and the run FAILS CLOSED for reconciliation rather
    than continuing with an understated total.
    """
    draw = StudyDraw(request_sha256=request.request_sha256, draw_index=draw_index)
    wires: list[WireResult] = []

    def send() -> G.AttemptOutcome:
        wire = _post_once(transport, request.body, headers)
        wires.append(wire)
        return G.AttemptOutcome(status=wire.status,
                                retry_after_s=_retry_after_seconds(wire.headers),
                                is_byok=_is_byok(wire.body), payload=wire.body)

    G.execute_with_retries(send, sleep=sleep, clock=clock, max_attempts=max_attempts)
    for wire in wires[:-1]:
        try:
            unbooked = L.returned_cost(wire.body)
        except L.CostAccountingError:
            continue                       # transient failures return no cost — the normal case
        if unbooked > 0:
            raise StudyRunError(
                f"a non-terminal attempt on draw {draw.draw_id} returned a cost of "
                f"${unbooked:.8f} that no authorised draw identity can book; halting for "
                f"reconciliation rather than understating cumulative spend")

    terminal = wires[-1]
    cost, failures, envelope = _record_and_book(
        store=store, ledger=ledger, draw=draw, request_body=request.body,
        request_headers=headers, wire=terminal, bucket=bucket, model=model, provider=tag,
        stage=stage)

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
                 snapshot: Optional[E.Snapshot] = None) -> PlanRun:
    """Execute a planned set of draws with restart and the hard stop enforced.

    A draw already on disk is REPLAYED from its record and the transport is not called for it.
    Before every call that would actually be sent, the realised ledger decides whether the
    $8.50 stop permits it; if not the run halts BEFORE that call.
    """
    headers = E.request_headers(key)
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

        decision = ledger.must_halt_before_next_call(worst_case_usd(request.request_sha256))
        if decision.halt:
            halted = True
            halt_reason = decision.reason
            break

        outcomes.append(_send_draw(
            request=request, draw_index=draw_index, model=model, tag=tag, headers=headers,
            store=store, ledger=ledger, transport=transport, stage=stage, bucket=bucket,
            sleep=sleep, clock=clock, max_attempts=max_attempts, snapshot=snapshot))
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
              snapshot: Optional[E.Snapshot] = None) -> SmokeReport:
    """Execute the 240 outcome-blinded smoke draws and decide the frozen promotion gate."""
    run = execute_plan(plan=plan_smoke_draws(smoke_requests), model=model, tag=tag, key=key,
                       store=store, ledger=ledger, transport=transport,
                       worst_case_usd=worst_case_usd, stage=SMOKE_STAGE, bucket=SMOKE_BUCKET,
                       sleep=sleep, clock=clock, max_attempts=max_attempts,
                       snapshot=snapshot)
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
             snapshot: Optional[E.Snapshot] = None) -> FullRunReport:
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
                       snapshot=snapshot)
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
    try:
        from tokenizers import Tokenizer as HFTokenizer       # type: ignore
    except ImportError as exc:                                 # pragma: no cover
        raise StudyRunError(f"the `tokenizers` package is required: {exc}") from None
    tok = HFTokenizer.from_file(str(directory / "tokenizer.json"))

    def count(text: str) -> int:
        return len(tok.encode(text).ids)

    return count


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
    path = write_projection(run_dir, projection)
    manifest = build_study_manifest(model=args.model, endpoint_tag=tag, requests=requests,
                                    probe_ids=probes, snapshot_sha256=snapshot.sha256,
                                    binding=default_binding(args.primary))
    decision = write_study_manifest(run_dir, args.model, manifest)
    print(f"projection artifact: {path}")
    print(f"total ${projection.total:.4f} of ${projection.stop:.2f}; fits={projection.fits}")
    print(f"manifest {decision.sha256[:12]} (created={decision.created}, "
          f"resumed={decision.resumed}) binds {manifest.n_draws} draws / "
          f"{manifest.n_coordinates} coordinates")
    print(f"next stage (invoke separately): `{USAGE}` with stage `smoke`")
    return 0 if projection.fits else 1


def _prepared(args, *, snapshot: E.Snapshot, run_dir: Path):
    """Shared smoke/full preparation: promoted tag, grid, manifest, ledger, worst case."""
    tag = load_promotion(run_dir, args.model)
    probes = probe_ids_for(args.primary)
    requests = render_study_grid(args.model, tag, probes)
    manifest = build_study_manifest(model=args.model, endpoint_tag=tag, requests=requests,
                                    probe_ids=probes, snapshot_sha256=snapshot.sha256,
                                    binding=default_binding(args.primary))
    write_study_manifest(run_dir, args.model, manifest)          # resumes only if identical
    ledger = open_ledger(run_dir, model=args.model, endpoint=tag,
                         study_draw_ids=manifest.draw_identities,
                         reconciliation=default_reconciliation())
    artifact = read_projection(
        run_dir / f"projection_{_safe_model(args.model)}__{tag.replace('/', '__')}.json")
    return tag, probes, requests, ledger, worst_case_lookup(artifact)


def _stage_smoke(args, *, key: str, snapshot: E.Snapshot, run_dir: Path) -> int:
    tag, probes, requests, ledger, worst_case = _prepared(args, snapshot=snapshot,
                                                          run_dir=run_dir)
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
                                                          run_dir=run_dir)
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
    "smoke": _stage_smoke,
    "full": _stage_full,
}


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
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.ack:
        print("This makes PAID OpenRouter calls. Re-run with "
              "--i-have-authorized-paid-spend", file=sys.stderr)
        return 2
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
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
    except (StudyRunError, L.LedgerError, G.GateError, I.IdentityError, E.EnvelopeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
