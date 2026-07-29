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

MONEY REPRESENTATION — the single canonical quantization rule (PS-6)
--------------------------------------------------------------------------------------
A money ledger that can report spend ABOVE its own ceiling is not trustworthy at a $8.50
boundary. Binary floats make that possible: ten returned costs of `0.0001` sum to
`0.0010000000000000002`, which is strictly greater than a `0.001` stop even though the
arithmetic is nominally exact. Money here is therefore represented EXACTLY, as
`decimal.Decimal`, and every accumulation and comparison happens in that domain.

THE RULE (applied at INGESTION — the moment any amount enters this module):

    unit           1e-12 USD (one pico-dollar); `MONEY_QUANTUM_USD`,
                   `MONEY_DECIMAL_PLACES == 12`
    rounding mode  ROUND_HALF_UP (nearest; ties away from zero); `MONEY_ROUNDING`
    exception      a STRICTLY POSITIVE amount never quantizes to zero — if it would, it is
                   raised to one whole quantum, so a paid call is never booked as free
    entry points   `to_money()` is the ONLY way an amount becomes ledger money, and every
                   ingestion path calls it: `returned_cost`, `RawEnvelope.from_dict`,
                   `DerivedRecord.from_dict`, `NonReconciledComponent`, `_persisted_cost`,
                   `reconcile_prior_spend`, `ModelProjection`, `V7Ledger.book_envelope`,
                   `check_before_call`, `may_start_call`, `may_start_model`,
                   `must_halt_before_next_call`, the hard stop itself, and every reported or
                   serialized figure.

Why a NEAREST mode and not ROUND_CEILING: the quantum's job is to erase binary
representation noise, and only a nearest mode does that. `float("0.0001")` is really
0.000100000000000000004792…; rounding that UP would book 0.000100000001 and ten such calls
would breach a $0.001 stop for the same reason floats do. ROUND_HALF_UP is chosen over
ROUND_HALF_EVEN because a tie then rounds away from zero, so a booked cost never
under-states; at 1e-12 against $8.50 the choice is immaterial to the estimand and matters
only as a documented, deterministic rule.

Why 1e-12: it is finer than any billable OpenRouter amount by several orders of magnitude
(the smallest cost this project has ever observed is $2.07e-05), and ~10^3 coarser than the
float representation error of any amount in this module's range (|x| < $10^3), so
`float -> Decimal -> quantize` is a lossless normalization of every real cost while being a
strict noise filter. Quantized 12-dp amounts below $10^3 carry at most 15 significant digits
and therefore also round-trip exactly through `float`, which is what keeps the
float-compatible public API and the exact internals in agreement.

Public API stays FLOAT-COMPATIBLE: callers pass floats and read floats (`total_spent_usd`,
`run_usd`, `prior_usd`, `remaining_usd`, `hard_stop_usd`, `book_envelope`, `audit_summary`,
`spend_by_bucket`, every `to_dict`) exactly as before; conversion happens at the boundary.
The exact values are exposed alongside them as `*_exact_usd` (`Decimal`) for anyone who
needs to prove an equality rather than approximate one. Every decision inside this module —
the pre-call check, the start decision, the halt decision, reconstruction, and the reported
totals — is computed from the SAME quantized Decimals, so they cannot disagree.

This module is pure + filesystem only. It makes NO network calls of any kind.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

# =======================================================================================
# Frozen constants
# =======================================================================================

#: v7.1 R-V7-6 unified hard stop. ALL paid Q2 spend counts against this single figure.
HARD_STOP_USD: float = 8.50

#: Retained for backward compatibility ONLY. Cap comparisons used to add this slack because
#: they were performed in binary floating point. They are now exact `Decimal` comparisons
#: (see the module docstring), so NO comparison in this module adds any slack: a total exactly
#: at the hard stop is permitted and one quantum over it is refused.
EPS: float = 1e-12

# ---- the canonical money representation (see the module docstring) ---------------------

#: Number of decimal places money is quantized to at ingestion.
MONEY_DECIMAL_PLACES: int = 12

#: The quantum: 1e-12 USD (one pico-dollar).
MONEY_QUANTUM_USD: Decimal = Decimal(1).scaleb(-MONEY_DECIMAL_PLACES)

#: The single rounding mode: nearest, ties away from zero.
MONEY_ROUNDING: str = ROUND_HALF_UP

#: Arithmetic context for money. The precision is far wider than any total this study can
#: reach (12 dp against a $8.50 stop is 13 significant digits), so addition of quantized
#: amounts is exact and never silently rounds.
MONEY_CONTEXT: Context = Context(prec=60, rounding=MONEY_ROUNDING)

#: Exact zero, already quantized.
MONEY_ZERO: Decimal = Decimal(0).quantize(MONEY_QUANTUM_USD)

#: The canonical rule, in a form that travels with every serialized report.
MONEY_RULE: dict = {
    "representation": "decimal.Decimal",
    "unit_usd": str(MONEY_QUANTUM_USD),
    "decimal_places": MONEY_DECIMAL_PLACES,
    "rounding": MONEY_ROUNDING,
    "applied": "at ingestion, once, by to_money()",
    "positive_never_rounds_to_zero": True,
}


def to_money(value: Any) -> Decimal:
    """Quantize any amount into ledger money — the ONE canonical ingestion rule.

    Rule: nearest 1e-12 USD, ties away from zero (`ROUND_HALF_UP`); a strictly positive
    amount never quantizes to zero (it is raised to one quantum), so a paid call can never be
    booked as free.

    Floats are converted through their EXACT binary value (`Decimal(float)`), so the quantum
    filters representation noise rather than compounding it. Raises `ValueError` on anything
    that is not a finite number.
    """
    if isinstance(value, Decimal):
        exact = value
    elif isinstance(value, bool):                       # bool is an int; never money
        raise ValueError(f"{value!r} is not a monetary amount")
    elif isinstance(value, int):
        exact = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"monetary amount must be finite, got {value!r}")
        exact = Decimal(value)                          # exact binary value, then quantize
    elif isinstance(value, str):
        try:
            exact = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{value!r} is not a monetary amount") from exc
    else:
        raise ValueError(f"{value!r} is not a monetary amount")

    if not exact.is_finite():
        raise ValueError(f"monetary amount must be finite, got {value!r}")

    with localcontext(MONEY_CONTEXT):
        quantized = exact.quantize(MONEY_QUANTUM_USD, rounding=MONEY_ROUNDING)
        if quantized == 0 and exact > 0:
            # Never round a genuinely paid amount down to free (R-E2 in miniature).
            quantized = MONEY_QUANTUM_USD
        elif quantized == 0 and exact < 0:
            quantized = -MONEY_QUANTUM_USD
        return quantized


def from_money(amount: Decimal) -> float:
    """The float view of an exact amount, for the float-compatible public API.

    Quantized amounts in this module's range carry at most 15 significant digits, so this is a
    lossless round trip: `to_money(from_money(x)) == x`.
    """
    return float(amount)


def money_sum(values: Iterable[Any]) -> Decimal:
    """Exact sum of quantized amounts. Every input is ingested through `to_money` first."""
    with localcontext(MONEY_CONTEXT):
        total = MONEY_ZERO
        for value in values:
            total += to_money(value)
        return total


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


def is_unbilled_rejection(response: Mapping[str, Any], http_status: int,
                          response_headers: Optional[Mapping[str, Any]] = None) -> bool:
    """True when a 4xx response provably never reached a provider, so nothing was billed.

    This is deliberately NARROW. A missing cost is normally an accounting failure that must
    fail closed (R-E2), and provider-level failures CAN incur prompt cost — OpenRouter says
    so explicitly. But a ROUTER-level rejection (`provider.only` matched no endpoint, a data
    policy filtered every candidate, unsupported parameters filtered the endpoint) is decided
    before any generation exists: there is no generation id, no usage, and no completion to
    bill. Booking 0.0 for that case is a statement of fact, not a silent write-off, and the
    envelope records `cost_status='unbilled_rejection'` so the reason stays auditable.

    Requires ALL of: a 4xx status; an OpenRouter-shaped error body; no generation id
    anywhere; and no usage block. Anything else (any 2xx, any 5xx, or a 4xx that carries a
    generation id or usage) still fails closed.
    """
    if not (400 <= int(http_status) < 500):
        return False
    if not isinstance(response, Mapping) or not isinstance(response.get("error"), Mapping):
        return False
    if _extract_generation_id(response, response_headers) is not None:
        return False
    if response.get("usage"):
        return False
    return True


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


def _money_or_none(value: Any) -> Optional[Decimal]:
    """Quantized non-negative money, or None when the value is unusable as an amount."""
    try:
        amount = to_money(value)
    except (ValueError, TypeError, ArithmeticError):
        return None
    return None if amount < 0 else amount


def _finite_non_negative(value: Any) -> Optional[float]:
    """Float view of `_money_or_none` — same rule, float-compatible return."""
    amount = _money_or_none(value)
    return None if amount is None else from_money(amount)


def returned_cost_exact(response: Mapping[str, Any]) -> Decimal:
    """The RETURNED cost of a call as EXACT quantized money, or RAISE (R-E2).

    This is the ingestion point for every cost that ever reaches the ledger: the canonical
    rule (nearest 1e-12 USD, ties away from zero) is applied here and nowhere else re-derived.
    """
    usage = response.get("usage") or {}
    raw = usage.get("cost")
    if raw is None:
        raw = usage.get("total_cost")

    if raw is None:
        if is_cache_hit(response):
            return MONEY_ZERO
        raise CostAccountingError(
            "successful non-cached response carried no usage.cost / usage.total_cost; "
            "refusing to book 0.0 — reconcile via the persisted generation id or declare a "
            "NonReconciledComponent upper bound (R-E2)")

    cost = _money_or_none(raw)
    if cost is None:
        raise CostAccountingError(
            f"returned cost {raw!r} is not finite and non-negative; refusing to book (R-E2)")
    return cost


def returned_cost(response: Mapping[str, Any]) -> float:
    """The RETURNED cost of a call, or RAISE (R-E2). Never falls back to 0.0.

    Float view of `returned_cost_exact` — the value is already quantized, so the persisted
    figure and the booked figure are the same number.

    A cache hit may legitimately return no cost or 0.0 and is booked at 0.0; anything else
    without a finite, non-negative `usage.cost` / `usage.total_cost` is an accounting failure.
    """
    return from_money(returned_cost_exact(response))


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
            # Re-quantized on read: a record written by any producer enters the ledger under
            # the one canonical rule, so what was persisted and what is booked cannot differ.
            cost_usd=(None if obj.get("cost_usd") is None
                      else from_money(to_money(obj["cost_usd"]))),
            cost_status=obj.get("cost_status", "missing"),
            openrouter_metadata=obj.get("openrouter_metadata"),
            bucket=obj.get("bucket", "unknown"),
            model=obj.get("model", ""),
            provider=obj.get("provider", ""),
            stage=obj.get("stage", "unknown"),
        )

    @property
    def cost_exact_usd(self) -> Optional[Decimal]:
        """The booked cost as exact quantized money, or None when accounting failed."""
        return None if self.cost_usd is None else to_money(self.cost_usd)

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
        if is_unbilled_rejection(response_body, http_status, response_headers):
            cost, status = 0.0, "unbilled_rejection"
        else:
            cost, status = None, "missing"

    return RawEnvelope(
        draw_id=draw.draw_id,
        request_sha256=draw.request_sha256,
        draw_index=draw.draw_index,
        request_body=redact_request_body(request_body),
        request_headers=redact_headers(request_headers),
        response_body=json.loads(json.dumps(response_body)),
        # RESPONSE headers go through the same redactor as request headers. SECRET_HEADERS
        # already lists `set-cookie`, but only the request side was ever redacted, so every
        # persisted envelope retained the provider's `set-cookie` value. It is a short-lived
        # Cloudflare bot-management cookie rather than a credential, but the repository's own
        # policy classifies the header as sensitive and the evidence is intended to be
        # publishable.
        response_headers=redact_headers(response_headers or {}),
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
            booked_cost_usd=from_money(to_money(obj.get("booked_cost_usd", 0.0))),
            timestamp=obj["timestamp"],
        )

    @property
    def booked_cost_exact_usd(self) -> Decimal:
        return to_money(self.booked_cost_usd)


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
        if _money_or_none(self.upper_bound_usd) is None:
            raise ValueError("non-reconciled upper bound must be finite and non-negative")

    @property
    def upper_bound_exact_usd(self) -> Decimal:
        """The declared upper bound under the canonical quantization rule."""
        return to_money(self.upper_bound_usd)

    def to_dict(self) -> dict:
        return {"label": self.label,
                "upper_bound_usd": from_money(self.upper_bound_exact_usd),
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
    def reconciled_exact_usd(self) -> Decimal:
        return to_money(self.reconciled_usd)

    @property
    def non_reconciled_exact_usd(self) -> Decimal:
        """Exact sum of the declared upper bounds — never a float accumulation."""
        return money_sum(c.upper_bound_usd for c in self.components)

    @property
    def total_exact_usd(self) -> Decimal:
        with localcontext(MONEY_CONTEXT):
            return self.reconciled_exact_usd + self.non_reconciled_exact_usd

    @property
    def non_reconciled_usd(self) -> float:
        return from_money(self.non_reconciled_exact_usd)

    @property
    def total_usd(self) -> float:
        return from_money(self.total_exact_usd)

    @property
    def is_exact(self) -> bool:
        """A total carrying any non-reconciled component may NEVER be reported as exact."""
        return not self.components

    def to_dict(self) -> dict:
        return {
            "reconciled_usd": from_money(self.reconciled_exact_usd),
            "non_reconciled_usd": self.non_reconciled_usd,
            "total_usd": self.total_usd,
            "is_exact": self.is_exact,
            "record_count": self.record_count,
            "non_reconciled_components": [c.to_dict() for c in self.components],
            "sources": list(self.sources),
        }


def _persisted_cost(obj: Mapping[str, Any]) -> Optional[Decimal]:
    """Returned cost of a persisted record as exact quantized money.

    Tolerates the v5 and v7 record shapes; None when no usable cost is present.
    """
    for key in ("cost_usd", "cost", "actual_cost"):
        if obj.get(key) is not None:
            return _money_or_none(obj[key])
    for holder in (obj.get("usage"), (obj.get("response_body") or {}).get("usage")):
        if isinstance(holder, Mapping):
            for key in ("cost", "total_cost"):
                if holder.get(key) is not None:
                    return _money_or_none(holder[key])
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
    total = MONEY_ZERO
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
            with localcontext(MONEY_CONTEXT):
                total += cost                     # exact: both operands are quantized money
            count += 1
            sources.append(str(path))

    return ReconciliationResult(reconciled_usd=from_money(total), record_count=count,
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
    def complete_run_exact_usd(self) -> Decimal:
        """Projection + reserve as EXACT money — the figure `may_start_model` compares."""
        return money_sum((self.projected_input_cost_usd,
                          self.projected_completion_cost_usd,
                          self.retry_reserve_usd))

    @property
    def complete_run_usd(self) -> float:
        return from_money(self.complete_run_exact_usd)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "endpoint": self.endpoint,
            # every reported figure is quantized by the one rule, so the parts and the total
            # in this record are guaranteed to add up
            "projected_input_cost_usd": from_money(to_money(self.projected_input_cost_usd)),
            "projected_completion_cost_usd": from_money(
                to_money(self.projected_completion_cost_usd)),
            "retry_reserve_usd": from_money(to_money(self.retry_reserve_usd)),
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
    def headroom_exact_usd(self) -> Decimal:
        with localcontext(MONEY_CONTEXT):
            return to_money(self.hard_stop_usd) - to_money(self.projected_total_usd)

    @property
    def headroom_usd(self) -> float:
        return from_money(self.headroom_exact_usd)


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
    _booked: dict = field(default_factory=dict)      # draw_id -> quantized Decimal cost
    _bucket_spend: dict = field(default_factory=dict)   # bucket -> quantized Decimal spend
    current_model: Optional[str] = None
    current_model_complete: bool = False

    # ---- totals (exact) ---------------------------------------------------------------
    # Every decision and every reported figure below is derived from THESE four Decimals, so
    # the pre-call check, the start/halt decisions, the reconstructed totals, and the audit
    # summary cannot disagree with one another.
    @property
    def hard_stop_exact_usd(self) -> Decimal:
        return to_money(self.hard_stop_usd)

    @property
    def prior_exact_usd(self) -> Decimal:
        return self.reconciliation.total_exact_usd

    @property
    def run_exact_usd(self) -> Decimal:
        """Exact sum of every booking. Order-independent and free of float error."""
        with localcontext(MONEY_CONTEXT):
            total = MONEY_ZERO
            for draw_id in sorted(self._booked):
                total += self._booked[draw_id]
            return total

    @property
    def total_spent_exact_usd(self) -> Decimal:
        with localcontext(MONEY_CONTEXT):
            return self.prior_exact_usd + self.run_exact_usd

    @property
    def remaining_exact_usd(self) -> Decimal:
        with localcontext(MONEY_CONTEXT):
            return self.hard_stop_exact_usd - self.total_spent_exact_usd

    # ---- totals (float view of the same exact figures) --------------------------------
    @property
    def prior_usd(self) -> float:
        return from_money(self.prior_exact_usd)

    @property
    def run_usd(self) -> float:
        return from_money(self.run_exact_usd)

    @property
    def total_spent_usd(self) -> float:
        return from_money(self.total_spent_exact_usd)

    @property
    def remaining_usd(self) -> float:
        return from_money(self.remaining_exact_usd)

    @property
    def is_exact(self) -> bool:
        """False whenever any component of the total is a non-reconciled upper bound."""
        return self.reconciliation.is_exact

    def booked_draw_ids(self) -> list[str]:
        return sorted(self._booked)

    def booked_cost_exact_usd(self, draw_id: str) -> Optional[Decimal]:
        """The exact amount booked for one draw, or None if it was never booked."""
        return self._booked.get(draw_id)

    def spend_by_bucket_exact(self) -> dict:
        return dict(self._bucket_spend)

    def spend_by_bucket(self) -> dict:
        return {bucket: from_money(amount) for bucket, amount in self._bucket_spend.items()}

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
            # Re-derive from the PERSISTED evidence: a record written before
            # `unbilled_rejection` existed may still provably qualify (4xx, no generation id,
            # no usage). This is deterministic re-reading, not a write-off — anything that
            # does not qualify still fails closed.
            if is_unbilled_rejection(envelope.response_body or {}, envelope.http_status,
                                     envelope.response_headers):
                self._booked[envelope.draw_id] = MONEY_ZERO
                self._bucket_spend[envelope.bucket] = self._bucket_spend.get(
                    envelope.bucket, MONEY_ZERO)
                return from_money(MONEY_ZERO)
            raise CostAccountingError(
                f"draw {envelope.draw_id} was persisted without a returned cost "
                f"(generation id {envelope.generation_id!r}); refusing to book 0.0 (R-E2)")
        cost = to_money(envelope.cost_usd)          # canonical rule, applied at ingestion
        self._booked[envelope.draw_id] = cost
        with localcontext(MONEY_CONTEXT):
            self._bucket_spend[envelope.bucket] = (
                self._bucket_spend.get(envelope.bucket, MONEY_ZERO) + cost)
        return from_money(cost)

    # ---- pre-call gate ---------------------------------------------------------------
    def check_before_call(self, worst_case_cost_usd: float, *, label: str = "call") -> None:
        """Refuse (raise) a request whose worst-case cost could breach the $8.50 hard stop.

        Exact: a projected total exactly AT the stop is permitted; one quantum over it is
        refused. No floating-point slack is added (see `EPS`).
        """
        cost = _money_or_none(worst_case_cost_usd)
        if cost is None:
            raise ValueError("worst-case cost must be finite and non-negative")
        spent = self.total_spent_exact_usd
        with localcontext(MONEY_CONTEXT):
            projected = spent + cost
        if projected > self.hard_stop_exact_usd:
            raise HardStopExceeded(
                f"{label} refused: ${spent:.6f} spent + ${cost:.6f} worst case "
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
        spent = self.total_spent_exact_usd
        complete_run = projection.complete_run_exact_usd
        with localcontext(MONEY_CONTEXT):
            projected_total = spent + complete_run
        allowed = projected_total <= self.hard_stop_exact_usd
        if allowed:
            reason = (f"complete-run projection ${complete_run:.6f} + "
                      f"${spent:.6f} already spent fits the "
                      f"${self.hard_stop_usd:.2f} hard stop")
        else:
            reason = (f"budget exclusion: complete-run projection "
                      f"${complete_run:.6f} + ${spent:.6f} "
                      f"already spent = ${projected_total:.6f} exceeds the "
                      f"${self.hard_stop_usd:.2f} hard stop; no reduced-cell or reduced-S "
                      f"substitute is permitted")
        return StartDecision(allowed=allowed, model=projection.model,
                             endpoint=projection.endpoint,
                             already_spent_usd=from_money(spent),
                             projected_total_usd=from_money(projected_total),
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
        cost = _money_or_none(next_call_worst_case_usd)
        if cost is None:
            raise ValueError("next-call worst case must be finite and non-negative")

        spent = self.total_spent_exact_usd
        stop = self.hard_stop_exact_usd
        with localcontext(MONEY_CONTEXT):
            projected = spent + cost
        if spent > stop:
            reason = (f"realized spend ${spent:.6f} already exceeds the "
                      f"${self.hard_stop_usd:.2f} hard stop")
            halt = True
        elif projected > stop:
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
                                spent_usd=from_money(spent),
                                hard_stop_usd=self.hard_stop_usd)
        return HaltDecision(halt=True, reason=reason, model=self.current_model,
                            model_incomplete=True, emit_headline=False,
                            spent_usd=from_money(spent), hard_stop_usd=self.hard_stop_usd)

    # ---- reporting -------------------------------------------------------------------
    def audit_summary(self) -> dict:
        """JSON-serializable report. Every figure is the float view of the SAME exact money
        the pre-call check and the halt decision used — never a separately re-derived sum."""
        return {
            "money_rule": MONEY_RULE,
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
        booked_cost_usd=from_money(to_money(envelope.cost_usd or 0.0)),
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
