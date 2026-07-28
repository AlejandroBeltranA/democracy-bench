"""Stage-2 v7 audit ledger — immutable raw envelopes, fail-closed cost, restart
reconstruction, prior-spend reconciliation, and the single $8.50 hard stop.

FROZEN SPEC (implemented, not redesigned):
  * paper/Q2_STAGE2_RUNNER_REVIEW.md  R-E1, R-E2, R-E3, R-E5
  * paper/Q2_STAGE2_HOSTED_DESIGN.md  "v7.1 revision" R-V7-6, "v7.2 closure"

Frozen rules this module enforces:

  R-E1/R-E5  One immutable raw envelope per attempted request that received a response,
             containing the COMPLETE request body (credential redacted), redacted request
             headers, COMPLETE response body, response headers, HTTP status, generation id,
             timestamp, draw identity, returned usage, returned cost, and
             `openrouter_metadata`. Written temp-file-then-atomic-rename. Persistence happens
             BEFORE any validation or scoring, so a paid-but-invalid response is never
             discarded. Overwriting an existing record is REFUSED — the `--force` overwrite of
             the round-2 `llama@digitalocean` canary envelope is exactly the audit failure
             R-E5/S-F6 prohibit, and it is the reason `PriorSpend` can never be called exact.

  R-E2       Cost fails closed. A successful, non-cached response without a finite,
             non-negative returned cost (`usage.cost` or `usage.total_cost`) RAISES; it is
             never booked as 0.0. The returned cost is booked regardless of whether routing,
             parsing, coverage, or scoring later fail. Validation status lives in a SEPARATE
             derived record linked to the raw envelope; invalid calls are excluded from
             estimands but never erased from the audit trail or the ledger.

  R-E3       Restart reconstructs the full ledger from every persisted raw record in the run
             directory BEFORE the first budget check. Every record must belong to the frozen
             manifest and appear exactly once. A restarted process does NOT reset cumulative
             spend.

  R-V7-6     Prior spend is reconciled from actual persisted records PLUS declared
             `non_reconciled` components debited at a conservative documented UPPER amount;
             a total carrying any such component is reported NOT exact (`is_exact` False).
             UNIFIED HARD STOP: for v7 ALL paid Q2 spend — study calls, non-study canaries,
             diagnostics — counts against the single $8.50 stop (this supersedes v5's
             separate-canary treatment). "Finish current model" NEVER overrides the hard stop:
             a model may be started only if its conservative complete-run projection plus
             reserve fits, and realized-cost drift halts execution before the next call, with
             the model reported incomplete and NO headline emitted.

This module is pure + filesystem only. It makes NO network calls of any kind.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

# =======================================================================================
# Frozen constants
# =======================================================================================

#: v7.1 R-V7-6 unified hard stop. ALL paid Q2 spend counts against this single figure.
HARD_STOP_USD: float = 8.50

#: Floating-point slack for cap comparisons (sub-nano-dollar; far below any real call cost).
EPS: float = 1e-12

#: Header names whose values are secrets and must be redacted before persistence.
SECRET_HEADERS: frozenset[str] = frozenset({
    "authorization", "x-api-key", "api-key", "apikey", "openai-api-key",
    "openrouter-api-key", "proxy-authorization", "cookie", "set-cookie",
})

#: Request-body keys that must never be persisted verbatim.
SECRET_BODY_KEYS: frozenset[str] = frozenset({"api_key", "apikey", "authorization", "key"})

REDACTED: str = "REDACTED"


# =======================================================================================
# Errors — every one of these is fail-closed
# =======================================================================================

class LedgerError(RuntimeError):
    """Base for every fail-closed audit/accounting failure in this module."""


class EnvelopeExistsError(LedgerError):
    """Refusing to overwrite an already-persisted immutable raw envelope (R-E5/S-F6).

    This is the failure mode that already bit this project once: `--force` overwrote the
    round-2 `llama@digitalocean` envelope and destroyed an audit record that can no longer be
    reconstructed. There is no force flag here, by design.
    """


class CostAccountingError(LedgerError):
    """A successful, non-cached response carried no finite, non-negative returned cost (R-E2).

    Never degrade this to 0.0. Reconcile via the persisted generation id, or declare the
    amount as a `NonReconciledComponent` upper bound.
    """


class ManifestBindingError(LedgerError):
    """A persisted record does not belong to the frozen manifest, or appears more than once."""


class ReconciliationError(LedgerError):
    """A prior-spend record could not be reconciled to a returned cost."""


class HardStopExceeded(LedgerError):
    """Raised BEFORE a call whose worst-case cost could breach the $8.50 hard stop."""


class DoubleBookingError(LedgerError):
    """The same draw identity was booked into the ledger twice."""


# =======================================================================================
# Draw identity (R-V7-7: canonical request SHA-256 + immutable draw index)
# =======================================================================================

@dataclass(frozen=True)
class DrawIdentity:
    """Draw identity = canonical request SHA-256 + immutable draw index.

    The smoke/full-stage label is deliberately EXCLUDED from identity so smoke draws 0-4 are
    reused as the first five of the 25 draws at a coordinate (R-V7-7).
    """
    request_sha256: str
    draw_index: int

    def __post_init__(self) -> None:
        if not self.request_sha256 or len(self.request_sha256) != 64:
            raise ValueError(f"request_sha256 must be a 64-hex digest, got {self.request_sha256!r}")
        if int(self.draw_index) < 0:
            raise ValueError("draw_index must be non-negative")

    @property
    def draw_id(self) -> str:
        return f"{self.request_sha256}#{self.draw_index}"

    @staticmethod
    def parse(draw_id: str) -> "DrawIdentity":
        if "#" not in draw_id:
            raise ValueError(f"malformed draw id {draw_id!r}")
        sha, _, idx = draw_id.partition("#")
        return DrawIdentity(request_sha256=sha, draw_index=int(idx))


def canonical_json(obj: Any) -> str:
    """Canonical serialization used for every hash and every persisted file."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# =======================================================================================
# Redaction (R-E5: redact only secrets; discard nothing else)
# =======================================================================================

def redact_headers(headers: Mapping[str, Any]) -> dict:
    """Redact credential-bearing headers. Every other header is kept verbatim."""
    out: dict = {}
    for name, value in (headers or {}).items():
        out[name] = REDACTED if str(name).lower() in SECRET_HEADERS else value
    return out


def redact_request_body(body: Mapping[str, Any]) -> dict:
    """Deep-copy the request body with credential-shaped top-level keys redacted.

    Message roles/content, provider block, decode parameters, and every other field are kept
    verbatim — the envelope must be sufficient to reproduce the exact request.
    """
    out: dict = {}
    for key, value in (body or {}).items():
        if str(key).lower() in SECRET_BODY_KEYS:
            out[key] = REDACTED
        else:
            out[key] = json.loads(json.dumps(value)) if isinstance(value, (dict, list)) else value
    return out


# =======================================================================================
# Returned cost (R-E2: fails closed)
# =======================================================================================

#: The documented OpenRouter response-cache status header (S-F2).
CACHE_STATUS_HEADER = "X-OpenRouter-Cache-Status"


def cache_status(response_headers: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The returned `X-OpenRouter-Cache-Status`, case-insensitively, or None."""
    for k, v in (response_headers or {}).items():
        if str(k).lower() == CACHE_STATUS_HEADER.lower():
            return str(v)
    return None


def is_cache_hit(response: Mapping[str, Any],
                 response_headers: Optional[Mapping[str, Any]] = None) -> bool:
    """Identify a response served from OpenRouter's response cache.

    The frozen v7 envelope sends `X-OpenRouter-Cache:false`, so this must never be true on a
    study draw. S-F2 requires the runner to persist `X-OpenRouter-Cache-Status` when present
    and REJECT any `HIT`: a replayed identical output destroys sampling independence, and its
    zeroed usage is otherwise indistinguishable from the R-E2 accounting failure.
    """
    status = cache_status(response_headers)
    if status is not None and status.strip().upper().startswith("HIT"):
        return True
    if response.get("cached") is True:
        return True
    usage = response.get("usage") or {}
    return bool(usage.get("cache_hit") is True or usage.get("is_cache_hit") is True)


class CacheHitRejected(LedgerError):
    """A response-cache HIT was returned despite `X-OpenRouter-Cache: false` (S-F2).

    The draw is not an independent sample and must never enter a headline estimate.
    """


def reject_cache_hit(response: Mapping[str, Any],
                     response_headers: Optional[Mapping[str, Any]] = None) -> None:
    """Fail closed on a response-cache HIT (S-F2)."""
    if is_cache_hit(response, response_headers):
        raise CacheHitRejected(
            f"response-cache {cache_status(response_headers) or 'HIT'} returned despite "
            "X-OpenRouter-Cache: false; the draw is a replay, not an independent sample")


def _finite_non_negative(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num < 0.0:
        return None
    return num


def returned_cost(response: Mapping[str, Any]) -> float:
    """The RETURNED cost of a call, or RAISE (R-E2). Never falls back to 0.0.

    A cache hit may legitimately return no cost or 0.0 and is booked at 0.0; anything else
    without a finite, non-negative `usage.cost` / `usage.total_cost` is an accounting failure.
    """
    usage = response.get("usage") or {}
    raw = usage.get("cost")
    if raw is None:
        raw = usage.get("total_cost")

    if raw is None:
        if is_cache_hit(response):
            return 0.0
        raise CostAccountingError(
            "successful non-cached response carried no usage.cost / usage.total_cost; "
            "refusing to book 0.0 — reconcile via the persisted generation id or declare a "
            "NonReconciledComponent upper bound (R-E2)")

    cost = _finite_non_negative(raw)
    if cost is None:
        raise CostAccountingError(
            f"returned cost {raw!r} is not finite and non-negative; refusing to book (R-E2)")
    return cost


# =======================================================================================
# Immutable raw envelope (R-E1 / R-E5)
# =======================================================================================

@dataclass(frozen=True)
class RawEnvelope:
    """One immutable envelope per attempted request that received a response.

    Everything needed to reproduce and audit the call is here; only credentials are redacted.
    """
    draw_id: str
    request_sha256: str
    draw_index: int
    request_body: dict
    request_headers: dict          # already redacted
    response_body: dict
    response_headers: dict
    http_status: int
    generation_id: Optional[str]
    timestamp: str                 # ISO-8601 UTC
    usage: dict                    # returned usage, verbatim
    cost_usd: Optional[float]      # returned cost; None ONLY when accounting failed
    cost_status: str               # 'returned' | 'cache_hit_zero' | 'missing'
    openrouter_metadata: Optional[dict]
    bucket: str                    # reporting label only — ALL buckets share the $8.50 stop
    model: str
    provider: str
    stage: str                     # 'canary' | 'gate' | 'smoke' | 'study' | 'diagnostic'

    def to_dict(self) -> dict:
        return {
            "schema": "q2_v7.raw_envelope.v1",
            "draw_id": self.draw_id,
            "request_sha256": self.request_sha256,
            "draw_index": self.draw_index,
            "request_body": self.request_body,
            "request_headers": self.request_headers,
            "response_body": self.response_body,
            "response_headers": self.response_headers,
            "http_status": self.http_status,
            "generation_id": self.generation_id,
            "timestamp": self.timestamp,
            "usage": self.usage,
            "cost_usd": self.cost_usd,
            "cost_status": self.cost_status,
            "openrouter_metadata": self.openrouter_metadata,
            "bucket": self.bucket,
            "model": self.model,
            "provider": self.provider,
            "stage": self.stage,
        }

    @staticmethod
    def from_dict(obj: Mapping[str, Any]) -> "RawEnvelope":
        return RawEnvelope(
            draw_id=obj["draw_id"],
            request_sha256=obj["request_sha256"],
            draw_index=int(obj["draw_index"]),
            request_body=dict(obj.get("request_body") or {}),
            request_headers=dict(obj.get("request_headers") or {}),
            response_body=dict(obj.get("response_body") or {}),
            response_headers=dict(obj.get("response_headers") or {}),
            http_status=int(obj["http_status"]),
            generation_id=obj.get("generation_id"),
            timestamp=obj["timestamp"],
            usage=dict(obj.get("usage") or {}),
            cost_usd=(None if obj.get("cost_usd") is None else float(obj["cost_usd"])),
            cost_status=obj.get("cost_status", "missing"),
            openrouter_metadata=obj.get("openrouter_metadata"),
            bucket=obj.get("bucket", "unknown"),
            model=obj.get("model", ""),
            provider=obj.get("provider", ""),
            stage=obj.get("stage", "unknown"),
        )

    def content_sha256(self) -> str:
        return canonical_sha256(self.to_dict())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_generation_id(response: Mapping[str, Any],
                           response_headers: Mapping[str, Any]) -> Optional[str]:
    """Generation id from the response body or `X-Generation-Id` (R-E2 reconciliation hook)."""
    for key in ("id", "generation_id"):
        value = response.get(key)
        if value:
            return str(value)
    for name, value in (response_headers or {}).items():
        if str(name).lower() in ("x-generation-id", "x-request-id") and value:
            return str(value)
    return None


def build_envelope(*, draw: DrawIdentity, request_body: Mapping[str, Any],
                   request_headers: Mapping[str, Any], response_body: Mapping[str, Any],
                   response_headers: Mapping[str, Any], http_status: int,
                   bucket: str, model: str, provider: str, stage: str,
                   timestamp: Optional[str] = None) -> RawEnvelope:
    """Build the immutable envelope. Never raises on a missing cost — persistence must not be
    blocked by an accounting failure (R-E1: persist BEFORE validation)."""
    try:
        cost: Optional[float] = returned_cost(response_body)
        status = "cache_hit_zero" if (cost == 0.0 and is_cache_hit(response_body)) else "returned"
    except CostAccountingError:
        cost, status = None, "missing"

    return RawEnvelope(
        draw_id=draw.draw_id,
        request_sha256=draw.request_sha256,
        draw_index=draw.draw_index,
        request_body=redact_request_body(request_body),
        request_headers=redact_headers(request_headers),
        response_body=json.loads(json.dumps(response_body)),
        response_headers=dict(response_headers or {}),
        http_status=int(http_status),
        generation_id=_extract_generation_id(response_body, response_headers),
        timestamp=timestamp or _utc_now(),
        usage=dict(response_body.get("usage") or {}),
        cost_usd=cost,
        cost_status=status,
        openrouter_metadata=response_body.get("openrouter_metadata"),
        bucket=bucket,
        model=model,
        provider=provider,
        stage=stage,
    )


# =======================================================================================
# Derived validation record — separate from, and linked to, the raw envelope (R-E1.3)
# =======================================================================================

@dataclass(frozen=True)
class DerivedRecord:
    """Validation/scoring status for one raw envelope.

    Kept in a SEPARATE artifact linked by draw id + the raw envelope's content hash, so an
    invalid call is excluded from estimands while its audit and cost history stay intact.
    """
    draw_id: str
    raw_sha256: str
    valid: bool
    failures: tuple[str, ...]
    excluded_from_estimands: bool
    booked_cost_usd: float
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "schema": "q2_v7.derived_record.v1",
            "draw_id": self.draw_id,
            "raw_sha256": self.raw_sha256,
            "valid": self.valid,
            "failures": list(self.failures),
            "excluded_from_estimands": self.excluded_from_estimands,
            "booked_cost_usd": self.booked_cost_usd,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(obj: Mapping[str, Any]) -> "DerivedRecord":
        return DerivedRecord(
            draw_id=obj["draw_id"],
            raw_sha256=obj["raw_sha256"],
            valid=bool(obj["valid"]),
            failures=tuple(obj.get("failures") or ()),
            excluded_from_estimands=bool(obj.get("excluded_from_estimands", not obj["valid"])),
            booked_cost_usd=float(obj.get("booked_cost_usd", 0.0)),
            timestamp=obj["timestamp"],
        )


# =======================================================================================
# Store — temp file + atomic rename, refuse-overwrite
# =======================================================================================

def _safe_name(draw_id: str) -> str:
    # draw ids are hex + '#' + int; keep the same filename convention as q2_hosted.RawStore.
    return draw_id.replace("#", "__") + ".json"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)              # atomic on POSIX
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class EnvelopeStore:
    """Immutable envelope store: one file per draw, atomic write, NEVER overwritten.

    `run_dir/raw/<draw>.json`      immutable raw envelopes
    `run_dir/derived/<draw>.json`  linked validation records
    """

    def __init__(self, run_dir: Path | str):
        self.run_dir = Path(run_dir)
        self.raw_dir = self.run_dir / "raw"
        self.derived_dir = self.run_dir / "derived"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)

    # ---- raw -------------------------------------------------------------------------
    def raw_path(self, draw_id: str) -> Path:
        return self.raw_dir / _safe_name(draw_id)

    def has(self, draw_id: str) -> bool:
        return self.raw_path(draw_id).exists()

    def put(self, envelope: RawEnvelope) -> Path:
        """Persist one immutable envelope. REFUSES to overwrite an existing record."""
        path = self.raw_path(envelope.draw_id)
        if path.exists():
            raise EnvelopeExistsError(
                f"raw envelope {envelope.draw_id} already exists at {path} — refusing to "
                f"overwrite an immutable audit record (R-E5/S-F6). There is no --force.")
        _atomic_write(path, canonical_json(envelope.to_dict()))
        return path

    def get(self, draw_id: str) -> Optional[RawEnvelope]:
        path = self.raw_path(draw_id)
        if not path.exists():
            return None
        return RawEnvelope.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def raw_paths(self) -> list[Path]:
        return sorted(self.raw_dir.glob("*.json"))

    def envelopes(self) -> list[RawEnvelope]:
        out: list[RawEnvelope] = []
        for path in self.raw_paths():
            obj = json.loads(path.read_text(encoding="utf-8"))
            env = RawEnvelope.from_dict(obj)
            if _safe_name(env.draw_id) != path.name:
                raise ManifestBindingError(
                    f"record {path.name} carries draw id {env.draw_id!r} — filename/content "
                    f"mismatch, refusing to trust the audit trail")
            out.append(env)
        return out

    # ---- derived ---------------------------------------------------------------------
    def put_derived(self, record: DerivedRecord) -> Path:
        path = self.derived_dir / _safe_name(record.draw_id)
        if path.exists():
            raise EnvelopeExistsError(
                f"derived record {record.draw_id} already exists — refusing to overwrite")
        _atomic_write(path, canonical_json(record.to_dict()))
        return path

    def get_derived(self, draw_id: str) -> Optional[DerivedRecord]:
        path = self.derived_dir / _safe_name(draw_id)
        if not path.exists():
            return None
        return DerivedRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def derived_records(self) -> list[DerivedRecord]:
        return [DerivedRecord.from_dict(json.loads(p.read_text(encoding="utf-8")))
                for p in sorted(self.derived_dir.glob("*.json"))]


# =======================================================================================
# Manifest binding (R-E3: every record belongs to the manifest and appears exactly once)
# =======================================================================================

@dataclass(frozen=True)
class RunManifest:
    """The frozen set of draw identities this run is allowed to have paid for."""
    manifest_sha256: str
    draw_ids: frozenset[str]
    model: str = ""
    endpoint: str = ""

    @staticmethod
    def from_draw_ids(draw_ids: Iterable[str], *, model: str = "",
                      endpoint: str = "") -> "RunManifest":
        ids = frozenset(draw_ids)
        digest = canonical_sha256({"model": model, "endpoint": endpoint,
                                   "draw_ids": sorted(ids)})
        return RunManifest(manifest_sha256=digest, draw_ids=ids, model=model, endpoint=endpoint)

    def contains(self, draw_id: str) -> bool:
        return draw_id in self.draw_ids


# =======================================================================================
# Prior-spend reconciliation (R-V7-6)
# =======================================================================================

@dataclass(frozen=True)
class NonReconciledComponent:
    """Spend that cannot be reconstructed from a persisted record.

    Debited at a documented conservative UPPER amount and labelled non-reconciled; any total
    carrying one of these is NOT exact.
    """
    label: str
    upper_bound_usd: float
    reason: str

    def __post_init__(self) -> None:
        if _finite_non_negative(self.upper_bound_usd) is None:
            raise ValueError("non-reconciled upper bound must be finite and non-negative")

    def to_dict(self) -> dict:
        return {"label": self.label, "upper_bound_usd": self.upper_bound_usd,
                "reason": self.reason}


#: The one known non-reconciled component (v7.1 R-V7-6). `--force` overwrote the round-2
#: `llama@digitalocean` open-weight-canary envelope; the console-logged round value is
#: debited as a documented conservative upper bound and the total is never called exact.
FORCE_OVERWRITTEN_CANARY = NonReconciledComponent(
    label="openweight_logprob_canary_round2_llama_digitalocean",
    upper_bound_usd=0.0000207,
    reason=("--force overwrote the immutable envelope (the R-E1/R-E5/S-F6 failure); the "
            "transaction cannot be reconstructed from persisted artifacts, so the "
            "console-logged round value is debited as a conservative documented upper bound"),
)


@dataclass(frozen=True)
class ReconciliationResult:
    """Reconciled prior spend. `is_exact` is False whenever any component is non-reconciled."""
    reconciled_usd: float
    record_count: int
    components: tuple[NonReconciledComponent, ...] = ()
    sources: tuple[str, ...] = ()

    @property
    def non_reconciled_usd(self) -> float:
        return sum(c.upper_bound_usd for c in self.components)

    @property
    def total_usd(self) -> float:
        return self.reconciled_usd + self.non_reconciled_usd

    @property
    def is_exact(self) -> bool:
        """A total carrying any non-reconciled component may NEVER be reported as exact."""
        return not self.components

    def to_dict(self) -> dict:
        return {
            "reconciled_usd": self.reconciled_usd,
            "non_reconciled_usd": self.non_reconciled_usd,
            "total_usd": self.total_usd,
            "is_exact": self.is_exact,
            "record_count": self.record_count,
            "non_reconciled_components": [c.to_dict() for c in self.components],
            "sources": list(self.sources),
        }


def _persisted_cost(obj: Mapping[str, Any]) -> Optional[float]:
    """Returned cost of a persisted record, tolerating the v5 and v7 record shapes."""
    for key in ("cost_usd", "cost", "actual_cost"):
        if obj.get(key) is not None:
            return _finite_non_negative(obj[key])
    for holder in (obj.get("usage"), (obj.get("response_body") or {}).get("usage")):
        if isinstance(holder, Mapping):
            for key in ("cost", "total_cost"):
                if holder.get(key) is not None:
                    return _finite_non_negative(holder[key])
    return None


def reconcile_prior_spend(record_dirs: Sequence[Path | str], *,
                          non_reconciled: Sequence[NonReconciledComponent] = ()
                          ) -> ReconciliationResult:
    """Reconstruct prior spend from ACTUAL persisted records, plus declared non-reconciled
    components debited at their documented upper bound (R-V7-6).

    Fails closed: a persisted record with no recoverable returned cost raises rather than
    being silently treated as free. Such a record must be reconciled through its generation
    id or declared as a `NonReconciledComponent`.
    """
    total = 0.0
    count = 0
    sources: list[str] = []
    for directory in record_dirs:
        base = Path(directory)
        if not base.exists():
            raise ReconciliationError(f"prior-spend directory {base} does not exist")
        for path in sorted(base.rglob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ReconciliationError(f"unreadable prior record {path}: {exc}") from exc
            if not isinstance(obj, Mapping):
                continue
            cost = _persisted_cost(obj)
            if cost is None:
                raise ReconciliationError(
                    f"prior record {path} carries no finite returned cost; refusing to treat "
                    f"it as free — reconcile it or declare a NonReconciledComponent (R-V7-6)")
            total += cost
            count += 1
            sources.append(str(path))

    return ReconciliationResult(reconciled_usd=total, record_count=count,
                                components=tuple(non_reconciled), sources=tuple(sources))


# =======================================================================================
# Model projection and the start / halt decisions (R-V7-6)
# =======================================================================================

@dataclass(frozen=True)
class ModelProjection:
    """Conservative complete-run projection for one model at one candidate endpoint.

    Per v7.2 C2: projected input cost over all 528 requests x 25 draws with the frozen 10%
    tokenizer margin, plus the projected completion cost at the canary-derived allowance, plus
    a separately quantified retry reserve. The 240 smoke draws are counted ONCE — they are the
    first five draws of 48 of the 528 coordinates, already inside the 13,200.
    """
    model: str
    endpoint: str
    projected_input_cost_usd: float
    projected_completion_cost_usd: float
    retry_reserve_usd: float

    @property
    def complete_run_usd(self) -> float:
        return (self.projected_input_cost_usd
                + self.projected_completion_cost_usd
                + self.retry_reserve_usd)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "endpoint": self.endpoint,
            "projected_input_cost_usd": self.projected_input_cost_usd,
            "projected_completion_cost_usd": self.projected_completion_cost_usd,
            "retry_reserve_usd": self.retry_reserve_usd,
            "complete_run_usd": self.complete_run_usd,
        }


@dataclass(frozen=True)
class StartDecision:
    """Whether a model may be STARTED at all. A refused model is a budget exclusion — there is
    no reduced-cell, reduced-S, or partial-run substitute (v7 requirement 4)."""
    allowed: bool
    model: str
    endpoint: str
    already_spent_usd: float
    projected_total_usd: float
    hard_stop_usd: float
    reason: str

    @property
    def budget_excluded(self) -> bool:
        return not self.allowed

    @property
    def headroom_usd(self) -> float:
        return self.hard_stop_usd - self.projected_total_usd


@dataclass(frozen=True)
class HaltDecision:
    """Whether execution must stop BEFORE the next call.

    When `halt` is True the in-flight model is reported incomplete and NO headline is emitted.
    "Finish current model" never overrides the hard stop.
    """
    halt: bool
    reason: str
    model: Optional[str]
    model_incomplete: bool
    emit_headline: bool
    spent_usd: float
    hard_stop_usd: float


# =======================================================================================
# The ledger
# =======================================================================================

@dataclass
class V7Ledger:
    """Single-stop v7 ledger. ALL paid Q2 spend — study calls, non-study canaries, and
    diagnostics — counts against one $8.50 hard stop (R-V7-6, superseding v5's separate-canary
    treatment).

    Realized cost is booked from the RETURNED cost of each persisted envelope, whether or not
    routing/parsing/scoring subsequently passed.
    """
    reconciliation: ReconciliationResult
    hard_stop_usd: float = HARD_STOP_USD
    manifest: Optional[RunManifest] = None
    _booked: dict = field(default_factory=dict)      # draw_id -> cost
    _bucket_spend: dict = field(default_factory=dict)
    current_model: Optional[str] = None
    current_model_complete: bool = False

    # ---- totals ----------------------------------------------------------------------
    @property
    def prior_usd(self) -> float:
        return self.reconciliation.total_usd

    @property
    def run_usd(self) -> float:
        return sum(self._booked.values())

    @property
    def total_spent_usd(self) -> float:
        return self.prior_usd + self.run_usd

    @property
    def remaining_usd(self) -> float:
        return self.hard_stop_usd - self.total_spent_usd

    @property
    def is_exact(self) -> bool:
        """False whenever any component of the total is a non-reconciled upper bound."""
        return self.reconciliation.is_exact

    def booked_draw_ids(self) -> list[str]:
        return sorted(self._booked)

    def spend_by_bucket(self) -> dict:
        return dict(self._bucket_spend)

    # ---- booking ---------------------------------------------------------------------
    def book_envelope(self, envelope: RawEnvelope) -> float:
        """Book one envelope's RETURNED cost. Raises if the cost is missing (R-E2) or the draw
        was already booked. Called for valid AND invalid-but-paid responses alike (R-E1.2)."""
        if envelope.draw_id in self._booked:
            raise DoubleBookingError(
                f"draw {envelope.draw_id} already booked at "
                f"{self._booked[envelope.draw_id]:.8f} — refusing to double-count")
        if self.manifest is not None and not self.manifest.contains(envelope.draw_id):
            raise ManifestBindingError(
                f"draw {envelope.draw_id} is not bound by manifest "
                f"{self.manifest.manifest_sha256[:12]} — refusing to book")
        if envelope.cost_usd is None:
            raise CostAccountingError(
                f"draw {envelope.draw_id} was persisted without a returned cost "
                f"(generation id {envelope.generation_id!r}); refusing to book 0.0 (R-E2)")
        cost = float(envelope.cost_usd)
        self._booked[envelope.draw_id] = cost
        self._bucket_spend[envelope.bucket] = self._bucket_spend.get(envelope.bucket, 0.0) + cost
        return cost

    # ---- pre-call gate ---------------------------------------------------------------
    def check_before_call(self, worst_case_cost_usd: float, *, label: str = "call") -> None:
        """Refuse (raise) a request whose worst-case cost could breach the $8.50 hard stop."""
        cost = _finite_non_negative(worst_case_cost_usd)
        if cost is None:
            raise ValueError("worst-case cost must be finite and non-negative")
        if self.total_spent_usd + cost > self.hard_stop_usd + EPS:
            raise HardStopExceeded(
                f"{label} refused: ${self.total_spent_usd:.6f} spent + ${cost:.6f} worst case "
                f"would breach the ${self.hard_stop_usd:.2f} hard stop")

    def may_start_call(self, worst_case_cost_usd: float) -> bool:
        try:
            self.check_before_call(worst_case_cost_usd)
        except HardStopExceeded:
            return False
        return True

    # ---- model start / halt ----------------------------------------------------------
    def may_start_model(self, projection: ModelProjection) -> StartDecision:
        """A model may be STARTED only if its conservative complete-run projection plus reserve
        fits under the hard stop given everything already spent. Refusal is a budget exclusion;
        there is no partial run (v7 requirement 4, R-V7-6)."""
        projected_total = self.total_spent_usd + projection.complete_run_usd
        allowed = projected_total <= self.hard_stop_usd + EPS
        if allowed:
            reason = (f"complete-run projection ${projection.complete_run_usd:.6f} + "
                      f"${self.total_spent_usd:.6f} already spent fits the "
                      f"${self.hard_stop_usd:.2f} hard stop")
        else:
            reason = (f"budget exclusion: complete-run projection "
                      f"${projection.complete_run_usd:.6f} + ${self.total_spent_usd:.6f} "
                      f"already spent = ${projected_total:.6f} exceeds the "
                      f"${self.hard_stop_usd:.2f} hard stop; no reduced-cell or reduced-S "
                      f"substitute is permitted")
        return StartDecision(allowed=allowed, model=projection.model,
                             endpoint=projection.endpoint,
                             already_spent_usd=self.total_spent_usd,
                             projected_total_usd=projected_total,
                             hard_stop_usd=self.hard_stop_usd, reason=reason)

    def start_model(self, projection: ModelProjection) -> StartDecision:
        """Mark a model in flight after `may_start_model` allows it; raises otherwise."""
        decision = self.may_start_model(projection)
        if not decision.allowed:
            raise HardStopExceeded(decision.reason)
        self.current_model = projection.model
        self.current_model_complete = False
        return decision

    def mark_model_complete(self) -> None:
        self.current_model_complete = True

    def must_halt_before_next_call(self, next_call_worst_case_usd: float = 0.0) -> HaltDecision:
        """Post-call assertion: halt BEFORE the next request if realized cost has drifted such
        that the next call would breach $8.50 (or the stop is already breached).

        "Finish current model" NEVER overrides the hard stop: on halt the model is reported
        incomplete and no headline is emitted.
        """
        cost = _finite_non_negative(next_call_worst_case_usd)
        if cost is None:
            raise ValueError("next-call worst case must be finite and non-negative")

        spent = self.total_spent_usd
        if spent > self.hard_stop_usd + EPS:
            reason = (f"realized spend ${spent:.6f} already exceeds the "
                      f"${self.hard_stop_usd:.2f} hard stop")
            halt = True
        elif spent + cost > self.hard_stop_usd + EPS:
            reason = (f"next call worst case ${cost:.6f} on top of realized ${spent:.6f} "
                      f"would breach the ${self.hard_stop_usd:.2f} hard stop")
            halt = True
        else:
            reason = ""
            halt = False

        if not halt:
            return HaltDecision(halt=False, reason="within the hard stop",
                                model=self.current_model,
                                model_incomplete=not self.current_model_complete,
                                emit_headline=self.current_model_complete,
                                spent_usd=spent, hard_stop_usd=self.hard_stop_usd)
        return HaltDecision(halt=True, reason=reason, model=self.current_model,
                            model_incomplete=True, emit_headline=False,
                            spent_usd=spent, hard_stop_usd=self.hard_stop_usd)

    # ---- reporting -------------------------------------------------------------------
    def audit_summary(self) -> dict:
        return {
            "hard_stop_usd": self.hard_stop_usd,
            "prior_usd": self.prior_usd,
            "run_usd": self.run_usd,
            "total_spent_usd": self.total_spent_usd,
            "remaining_usd": self.remaining_usd,
            "is_exact": self.is_exact,
            "booked_draws": len(self._booked),
            "spend_by_bucket": self.spend_by_bucket(),
            "reconciliation": self.reconciliation.to_dict(),
        }


# =======================================================================================
# Restart reconstruction (R-E3) — runs BEFORE the first budget check
# =======================================================================================

def reconstruct_ledger(store: EnvelopeStore, *, manifest: RunManifest,
                       reconciliation: Optional[ReconciliationResult] = None,
                       hard_stop_usd: float = HARD_STOP_USD) -> V7Ledger:
    """Rebuild the full ledger from EVERY persisted raw record in the run directory.

    Verifies that each record belongs to the frozen manifest and appears exactly once, then
    books its returned cost — including invalid-but-paid calls. A restarted process therefore
    resumes at the cumulative spend, never at zero.
    """
    if reconciliation is None:
        reconciliation = ReconciliationResult(reconciled_usd=0.0, record_count=0)

    ledger = V7Ledger(reconciliation=reconciliation, hard_stop_usd=hard_stop_usd,
                      manifest=manifest)

    seen: set[str] = set()
    for envelope in store.envelopes():
        if not manifest.contains(envelope.draw_id):
            raise ManifestBindingError(
                f"persisted record {envelope.draw_id} is not bound by manifest "
                f"{manifest.manifest_sha256[:12]} — refusing to reconstruct an unaudited run")
        if envelope.draw_id in seen:
            raise ManifestBindingError(
                f"draw {envelope.draw_id} appears more than once in {store.raw_dir}")
        seen.add(envelope.draw_id)
        ledger.book_envelope(envelope)

    return ledger


# =======================================================================================
# The paid-call recording path (R-E1: persist BEFORE validation/scoring)
# =======================================================================================

@dataclass(frozen=True)
class RecordedCall:
    envelope: RawEnvelope
    path: Path
    booked_cost_usd: float


def record_response(*, store: EnvelopeStore, ledger: V7Ledger, draw: DrawIdentity,
                    request_body: Mapping[str, Any], request_headers: Mapping[str, Any],
                    response_body: Mapping[str, Any], response_headers: Mapping[str, Any],
                    http_status: int, bucket: str, model: str, provider: str, stage: str,
                    timestamp: Optional[str] = None) -> RecordedCall:
    """Persist the immutable envelope FIRST, then book the returned cost.

    Ordering is the point (R-E1): the envelope is on disk before any validation, scoring, or
    accounting can fail, so a paid response can never be discarded. If the returned cost is
    missing this raises `CostAccountingError` AFTER the envelope is durable — the call is
    already recorded and must be reconciled through its generation id, never booked as free.
    """
    envelope = build_envelope(draw=draw, request_body=request_body,
                              request_headers=request_headers, response_body=response_body,
                              response_headers=response_headers, http_status=http_status,
                              bucket=bucket, model=model, provider=provider, stage=stage,
                              timestamp=timestamp)
    path = store.put(envelope)                       # immutable, atomic, refuse-overwrite
    cost = ledger.book_envelope(envelope)            # raises on missing cost (R-E2)
    return RecordedCall(envelope=envelope, path=path, booked_cost_usd=cost)


def record_validation(store: EnvelopeStore, envelope: RawEnvelope, *, valid: bool,
                      failures: Sequence[str] = (),
                      timestamp: Optional[str] = None) -> DerivedRecord:
    """Write the SEPARATE derived validation record linked to a persisted raw envelope.

    An invalid call is excluded from estimands but keeps its audit record and its booked cost
    (R-E1.3/R-E1.4).
    """
    record = DerivedRecord(
        draw_id=envelope.draw_id,
        raw_sha256=envelope.content_sha256(),
        valid=valid,
        failures=tuple(failures),
        excluded_from_estimands=not valid,
        booked_cost_usd=float(envelope.cost_usd or 0.0),
        timestamp=timestamp or _utc_now(),
    )
    store.put_derived(record)
    return record


def estimand_eligible_draw_ids(store: EnvelopeStore) -> list[str]:
    """Draws admissible to the estimands: persisted, validated, and not excluded.

    A raw envelope with no derived record is NOT eligible — validation is required, never
    assumed.
    """
    eligible: list[str] = []
    for record in store.derived_records():
        if record.valid and not record.excluded_from_estimands:
            eligible.append(record.draw_id)
    return sorted(eligible)
