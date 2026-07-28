"""Q2 Stage-2 v7.2 promotion-and-funding blinding interlock.

Implements the frozen "Outcome-blinding interlock" of `paper/Q2_STAGE2_HOSTED_DESIGN.md`
as revised by R-V7-7 ("draw identity, manifest, honest blinding").

The frozen rule
---------------
No substantive outcome — score, contrast, crack count, direction, or effect size — becomes
visible until BOTH (a) the model's endpoint-promotion decision and (b) the funding decision
are recorded. Until then the operator sees only request integrity, resolved provider,
parse/coverage, errors, usage, and cumulative cost. **Headline aggregation refuses to run
until both records exist.**

What is and is NOT claimed (R-V7-7, verbatim intent)
----------------------------------------------------
Raw persisted responses necessarily contain substantive answers and are **not** claimed to
be literally invisible. NO sealing, access-control, or encryption mechanism is implemented
or claimed here. The interlock this module provides is **procedural**:

* the runner and gate reports never display or aggregate substantive replies — that is what
  `gate_view` mechanises, and `assert_outcome_blinded` checks;
* raw envelopes remain uninspected under the declared operator protocol until the promotion
  and funding records exist — that is what `require_headline_permitted` mechanises, by
  refusing to let any aggregation run first.

If literal invisibility is later desired, an access-control/encryption mechanism must be
specified and tested; this module deliberately does not pretend to be one.

Artifacts
---------
`PromotionRecord` and `FundingRecord` are immutable, persisted JSON artifacts under
`<run_dir>/interlock/`. Each carries a UTC timestamp, the decision content, the run
manifest digest, and a `binding_sha256` computed over its own canonical payload INCLUDING
that manifest digest — so a record cannot be silently moved onto a different run, and a
record edited after the fact fails to load.

Writing refuses to replace an existing record: an interlock decision is evidence, and the
`--force`-style overwrite that destroyed a prior audit record (R-V7-6) has no counterpart
here.

NETWORK: none. Pure functions plus local file reads/writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from alignment.q2_v7 import envelope
from alignment.q2_v7.identity import (
    N_OPTIONS,
    PARSE_EMPTY,
    PARSE_NOT_ANCHORED,
    PARSE_OK,
    PARSE_OUT_OF_RANGE,
    parse_option,
)

#: Sub-directory of the run directory holding the two interlock records.
INTERLOCK_DIRNAME = "interlock"
PROMOTION_RECORD_FILENAME = "promotion_record.json"
FUNDING_RECORD_FILENAME = "funding_record.json"

PROMOTION_SCHEMA = "q2_v7.promotion_record.v1"
FUNDING_SCHEMA = "q2_v7.funding_record.v1"
GATE_VIEW_SCHEMA = "q2_v7.gate_view.v1"

#: The two records the frozen interlock requires, in the order the staged authorization
#: (v7 "Staged authorization", requirement 1) records them.
REQUIRED_RECORDS: tuple[str, ...] = ("promotion", "funding")


# =======================================================================================
# Errors — every failure mode is fail-closed and loud.
# =======================================================================================

class InterlockError(RuntimeError):
    """Base class for every interlock failure."""


class RecordExistsError(InterlockError):
    """An interlock record is already persisted; it is evidence and is never replaced."""


class RecordBindingError(InterlockError):
    """A persisted record is malformed, unbound, or bound to a different run manifest."""


class HeadlineBlocked(InterlockError):
    """Headline aggregation was attempted before both interlock records existed."""


class BlindingViolation(InterlockError):
    """An operator view carried substantive outcome content."""


# =======================================================================================
# 1. The immutable, persisted records
# =======================================================================================

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _binding_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical record payload, which includes `manifest_sha256`.

    This is what binds the decision to one run: recomputing it over a payload whose manifest
    digest (or any decision field) differs yields a different value, and loading fails.
    """
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


@dataclass(frozen=True)
class PromotionRecord:
    """(a) The recorded endpoint-promotion decision for ONE model.

    Deterministic content only: which endpoint the frozen walk promoted (or that the model
    was excluded), the full-grid projection total that decided criterion (c), and the run
    manifest it belongs to. Nothing substantive.
    """
    model: str
    manifest_sha256: str
    promoted_tag: Optional[str] = None
    promoted_endpoint_name: str = ""
    promoted_upstream_model: str = ""
    projection_total_usd: Optional[float] = None
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    recorded_utc: str = ""
    recorded_by: str = ""

    def payload(self) -> dict[str, Any]:
        """The canonical, binding-covered body of this record."""
        return {
            "schema": PROMOTION_SCHEMA,
            "model": self.model,
            "manifest_sha256": self.manifest_sha256,
            "promoted_tag": self.promoted_tag,
            "promoted_endpoint_name": self.promoted_endpoint_name,
            "promoted_upstream_model": self.promoted_upstream_model,
            "projection_total_usd": (None if self.projection_total_usd is None
                                     else float(self.projection_total_usd)),
            "excluded": bool(self.excluded),
            "exclusion_reason": self.exclusion_reason,
            "recorded_utc": self.recorded_utc,
            "recorded_by": self.recorded_by,
        }

    @property
    def binding_sha256(self) -> str:
        return _binding_digest(self.payload())

    def to_dict(self) -> dict[str, Any]:
        out = self.payload()
        out["binding_sha256"] = self.binding_sha256
        return out

    @staticmethod
    def from_dict(obj: Mapping[str, Any]) -> "PromotionRecord":
        return _record_from_dict(PromotionRecord, PROMOTION_SCHEMA, obj)


@dataclass(frozen=True)
class FundingRecord:
    """(b) The recorded funding decision.

    `authorized` is the decision itself; the amounts are the headroom it authorizes against
    the single $8.50 hard stop (R-V7-6). Nothing substantive.
    """
    manifest_sha256: str
    authorized: bool = False
    decision: str = ""
    available_usd: Optional[float] = None
    hard_stop_usd: Optional[float] = None
    reconciled_prior_usd: Optional[float] = None
    recorded_utc: str = ""
    recorded_by: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "schema": FUNDING_SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "authorized": bool(self.authorized),
            "decision": self.decision,
            "available_usd": (None if self.available_usd is None
                              else float(self.available_usd)),
            "hard_stop_usd": (None if self.hard_stop_usd is None
                              else float(self.hard_stop_usd)),
            "reconciled_prior_usd": (None if self.reconciled_prior_usd is None
                                     else float(self.reconciled_prior_usd)),
            "recorded_utc": self.recorded_utc,
            "recorded_by": self.recorded_by,
        }

    @property
    def binding_sha256(self) -> str:
        return _binding_digest(self.payload())

    def to_dict(self) -> dict[str, Any]:
        out = self.payload()
        out["binding_sha256"] = self.binding_sha256
        return out

    @staticmethod
    def from_dict(obj: Mapping[str, Any]) -> "FundingRecord":
        return _record_from_dict(FundingRecord, FUNDING_SCHEMA, obj)


def _record_from_dict(cls, schema: str, obj: Mapping[str, Any]):
    if not isinstance(obj, Mapping):
        raise RecordBindingError(f"{schema}: record is not a mapping")
    if obj.get("schema") != schema:
        raise RecordBindingError(f"{schema}: wrong schema {obj.get('schema')!r}")
    fields = {f for f in cls.__dataclass_fields__}                      # noqa: SLF001
    try:
        rec = cls(**{k: v for k, v in obj.items() if k in fields})
    except TypeError as exc:
        raise RecordBindingError(f"{schema}: malformed record ({exc})") from None
    stored = obj.get("binding_sha256")
    if not isinstance(stored, str) or not stored:
        raise RecordBindingError(f"{schema}: record carries no binding_sha256")
    if stored != rec.binding_sha256:
        raise RecordBindingError(
            f"{schema}: binding_sha256 {stored!r} does not match the record payload — the "
            f"record was edited after it was written, or moved onto another run")
    return rec


def interlock_dir(run_dir: Path | str) -> Path:
    return Path(run_dir) / INTERLOCK_DIRNAME


def promotion_record_path(run_dir: Path | str) -> Path:
    return interlock_dir(run_dir) / PROMOTION_RECORD_FILENAME


def funding_record_path(run_dir: Path | str) -> Path:
    return interlock_dir(run_dir) / FUNDING_RECORD_FILENAME


def _write_record(path: Path, record) -> str:
    """Persist one interlock record atomically. Refuses to replace an existing record."""
    if path.exists():
        raise RecordExistsError(
            f"{path} already exists — an interlock decision is immutable evidence and is "
            f"never rewritten")
    body = _canonical(record.to_dict())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o444)
    except OSError:                                    # pragma: no cover - platform-dependent
        pass
    return hashlib.sha256(body.encode()).hexdigest()


def _read_record(path: Path, cls):
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RecordBindingError(f"{path}: unreadable interlock record ({exc})") from None
    return cls.from_dict(obj)


def record_promotion(run_dir: Path | str,
                     *,
                     model: str,
                     manifest_sha256: str,
                     promoted_tag: Optional[str] = None,
                     promoted_endpoint_name: str = "",
                     projection_total_usd: Optional[float] = None,
                     excluded: bool = False,
                     exclusion_reason: Optional[str] = None,
                     recorded_by: str = "",
                     recorded_utc: Optional[str] = None) -> PromotionRecord:
    """Record decision (a): the deterministic endpoint-promotion outcome. Write-once."""
    if not isinstance(manifest_sha256, str) or not manifest_sha256:
        raise RecordBindingError("a promotion record must be bound to a run manifest digest")
    rec = PromotionRecord(
        model=model,
        manifest_sha256=manifest_sha256,
        promoted_tag=promoted_tag,
        promoted_endpoint_name=promoted_endpoint_name,
        promoted_upstream_model=(
            envelope.resolved_model_evidence(promoted_endpoint_name) or ""),
        projection_total_usd=projection_total_usd,
        excluded=bool(excluded),
        exclusion_reason=exclusion_reason,
        recorded_utc=recorded_utc or _utc_now(),
        recorded_by=recorded_by,
    )
    _write_record(promotion_record_path(run_dir), rec)
    return rec


def record_funding(run_dir: Path | str,
                   *,
                   manifest_sha256: str,
                   authorized: bool,
                   decision: str = "",
                   available_usd: Optional[float] = None,
                   hard_stop_usd: Optional[float] = None,
                   reconciled_prior_usd: Optional[float] = None,
                   recorded_by: str = "",
                   recorded_utc: Optional[str] = None) -> FundingRecord:
    """Record decision (b): the funding decision. Write-once."""
    if not isinstance(manifest_sha256, str) or not manifest_sha256:
        raise RecordBindingError("a funding record must be bound to a run manifest digest")
    rec = FundingRecord(
        manifest_sha256=manifest_sha256,
        authorized=bool(authorized),
        decision=decision,
        available_usd=available_usd,
        hard_stop_usd=hard_stop_usd,
        reconciled_prior_usd=reconciled_prior_usd,
        recorded_utc=recorded_utc or _utc_now(),
        recorded_by=recorded_by,
    )
    _write_record(funding_record_path(run_dir), rec)
    return rec


def load_promotion_record(run_dir: Path | str) -> Optional[PromotionRecord]:
    return _read_record(promotion_record_path(run_dir), PromotionRecord)


def load_funding_record(run_dir: Path | str) -> Optional[FundingRecord]:
    return _read_record(funding_record_path(run_dir), FundingRecord)


# =======================================================================================
# 2. Interlock state and the refusal that guards every aggregation
# =======================================================================================

@dataclass(frozen=True)
class InterlockState:
    """Which interlock records exist for one run directory, and therefore what is permitted."""
    run_dir: str
    promotion: Optional[PromotionRecord] = None
    funding: Optional[FundingRecord] = None
    expected_manifest_sha256: Optional[str] = None
    binding_failures: tuple[str, ...] = ()

    @property
    def promotion_recorded(self) -> bool:
        return self.promotion is not None

    @property
    def funding_recorded(self) -> bool:
        return self.funding is not None

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name, present in
                     (("promotion", self.promotion_recorded),
                      ("funding", self.funding_recorded)) if not present)

    @property
    def headline_permitted(self) -> bool:
        """True only when BOTH records exist and both bind to the expected manifest."""
        return not self.missing and not self.binding_failures

    #: `ok` is the vocabulary the surrounding v7 gates use for a pass/fail verdict.
    @property
    def ok(self) -> bool:
        return self.headline_permitted

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "promotion_recorded": self.promotion_recorded,
            "funding_recorded": self.funding_recorded,
            "missing": list(self.missing),
            "binding_failures": list(self.binding_failures),
            "headline_permitted": self.headline_permitted,
        }


def interlock_state(run_dir: Path | str,
                    expected_manifest_sha256: Optional[str] = None) -> InterlockState:
    """Report which interlock records exist for `run_dir`.

    A record that is present but unreadable, unbound, or bound to a manifest other than
    `expected_manifest_sha256` is NOT counted as recorded: absence of a valid record and
    presence of an invalid one both leave the headline blocked.
    """
    run_dir = Path(run_dir)
    failures: list[str] = []
    promotion: Optional[PromotionRecord] = None
    funding: Optional[FundingRecord] = None

    try:
        promotion = load_promotion_record(run_dir)
    except InterlockError as exc:
        failures.append(f"promotion: {exc}")
    try:
        funding = load_funding_record(run_dir)
    except InterlockError as exc:
        failures.append(f"funding: {exc}")

    if expected_manifest_sha256 is not None:
        for name, rec in (("promotion", promotion), ("funding", funding)):
            if rec is not None and rec.manifest_sha256 != expected_manifest_sha256:
                failures.append(
                    f"{name}: bound to manifest {rec.manifest_sha256!r}, not "
                    f"{expected_manifest_sha256!r}")
    return InterlockState(
        run_dir=str(run_dir),
        promotion=promotion,
        funding=funding,
        expected_manifest_sha256=expected_manifest_sha256,
        binding_failures=tuple(failures),
    )


def blinding_interlock(promotion_record: Any = None, funding_record: Any = None) -> bool:
    """The pure predicate: may a substantive outcome be aggregated or displayed?

    True only when BOTH decisions are recorded — (a) the endpoint-promotion decision and
    (b) the funding decision. Accepts the dataclasses above or any mapping standing in for
    them; a funding record that records a REFUSAL (`authorized` false) does not unblock the
    headline, and neither does an empty or unbound record.
    """
    return _promotion_ok(promotion_record) and _funding_ok(funding_record)


def _field(rec: Any, name: str, default: Any = None) -> Any:
    if rec is None:
        return default
    if isinstance(rec, Mapping):
        return rec.get(name, default)
    return getattr(rec, name, default)


def _promotion_ok(rec: Any) -> bool:
    if rec is None or (isinstance(rec, Mapping) and not rec):
        return False
    if isinstance(rec, InterlockState):
        return rec.promotion_recorded
    # A promotion decision is recorded either as a promoted endpoint or as an explicit
    # exclusion; both are decisions. An empty record is neither.
    if _field(rec, "excluded") is True:
        return True
    tag = _field(rec, "promoted_tag", _field(rec, "tag"))
    return isinstance(tag, str) and bool(tag)


def _funding_ok(rec: Any) -> bool:
    if rec is None or (isinstance(rec, Mapping) and not rec):
        return False
    if isinstance(rec, InterlockState):
        return rec.funding_recorded
    authorized = _field(rec, "authorized")
    if isinstance(authorized, bool):
        return authorized
    decision = _field(rec, "decision")
    return isinstance(decision, str) and bool(decision)


def require_headline_permitted(run_dir: Path | str,
                               expected_manifest_sha256: Optional[str] = None
                               ) -> InterlockState:
    """RAISE unless both interlock records exist. Call this BEFORE emitting anything.

    This is the refusal the frozen design names: "Headline aggregation refuses to run until
    both records exist." Every aggregation path — headline extraction, contrast
    reconstruction, effect sizes, crack counts — must pass through here first.
    """
    state = interlock_state(run_dir, expected_manifest_sha256)
    if not state.headline_permitted:
        detail = []
        if state.missing:
            detail.append("missing records: " + ", ".join(state.missing))
        if state.binding_failures:
            detail.append("; ".join(state.binding_failures))
        raise HeadlineBlocked(
            "headline aggregation refuses to run: the v7 outcome-blinding interlock requires "
            "BOTH the endpoint-promotion decision and the funding decision to be recorded "
            f"under {interlock_dir(run_dir)} first ({'; '.join(detail)})")
    return state


# =======================================================================================
# 3. The outcome-blinded operator (gate) view
# =======================================================================================

#: The ONLY sections the frozen interlock permits before both records exist.
GATE_VIEW_SECTIONS: tuple[str, ...] = (
    "request_integrity", "resolved_provider", "parse_coverage", "errors", "usage", "cost",
)

#: Keys whose presence would mean a substantive outcome leaked into the blinded view.
_SUBSTANTIVE_KEY = re.compile(
    r"(?i)(choice|contrast|direction|effect|estimand|headline|protective|mass|"
    r"frequenc|histogram|distribution|score|answer|reply|body|text|delta|floor|steer|"
    r"option_?\d|selected_?option|digit)")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _reply_text(env: Any) -> Optional[str]:
    """The assistant reply, read ONLY to compute a parse/coverage boolean. Never emitted."""
    body = _get(env, "response_body") or {}
    if not isinstance(body, Mapping):
        return None
    choices = body.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    message = first.get("message")
    if isinstance(message, Mapping) and isinstance(message.get("content"), str):
        return message["content"]
    return first.get("text") if isinstance(first.get("text"), str) else None


def _selected_endpoint(env: Any) -> tuple[Optional[str], Optional[str]]:
    """(display name, dated upstream model) from the routing metadata, or (None, None)."""
    meta = _get(env, "openrouter_metadata")
    if not isinstance(meta, Mapping):
        return (None, None)
    endpoints = meta.get("endpoints")
    available = endpoints.get("available") if isinstance(endpoints, Mapping) else None
    if not isinstance(available, list):
        return (None, None)
    entries = [e for e in available if isinstance(e, Mapping)]
    chosen = [e for e in entries if e.get("selected") is True]
    target = chosen[0] if chosen else (entries[0] if len(entries) == 1 else None)
    if target is None:
        return (None, None)
    provider = target.get("provider")
    upstream = envelope.resolved_model_evidence(target.get("model"))
    return (provider if isinstance(provider, str) else None, upstream)


def gate_view(envelopes: Iterable[Any],
              *,
              prior_usd: float = 0.0,
              expected_draws: Optional[int] = None,
              n_options: int = N_OPTIONS) -> dict[str, Any]:
    """Build the outcome-blinded operator view of a set of raw envelopes.

    Contains ONLY what the frozen interlock permits before both records exist: request
    integrity, resolved provider, parse/coverage rates, errors, usage, and cumulative cost.

    It contains NO choice frequencies, contrasts, directions, or effect sizes. Replies are
    read exactly once, to classify each as parseable or not under the frozen S-F4 anchored
    parser; the parsed OPTION is discarded immediately and never counted by value, so two
    runs whose answers differ entirely but whose parse outcomes agree produce byte-identical
    views. That property is the mechanised meaning of "the runner and gate reports never
    display or aggregate substantive answers" (R-V7-7).
    """
    draw_ids: list[str] = []
    request_hashes: list[str] = []
    providers: dict[tuple[str, str, str], int] = {}
    status_counts: dict[str, int] = {}
    reasons = {PARSE_EMPTY: 0, PARSE_NOT_ANCHORED: 0, PARSE_OUT_OF_RANGE: 0}
    n_env = n_responses = n_parseable = 0
    n_http_ok = n_http_error = n_cache_hit = n_missing_cost = n_costed = 0
    prompt_tokens = completion_tokens = total_tokens = 0
    returned_usd = 0.0

    for env in envelopes:
        n_env += 1
        did = _get(env, "draw_id")
        if isinstance(did, str):
            draw_ids.append(did)
        rsha = _get(env, "request_sha256")
        if isinstance(rsha, str):
            request_hashes.append(rsha)

        status = _get(env, "http_status")
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1
        if isinstance(status, int) and 200 <= status < 300:
            n_http_ok += 1
        else:
            n_http_error += 1

        display, upstream = _selected_endpoint(env)
        key = (str(_get(env, "model") or ""),
               display or str(_get(env, "provider") or ""),
               upstream or "")
        providers[key] = providers.get(key, 0) + 1

        cost_status = _get(env, "cost_status")
        if cost_status == "cache_hit_zero":
            n_cache_hit += 1
        cost = _get(env, "cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            returned_usd += float(cost)
            n_costed += 1
        else:
            n_missing_cost += 1

        usage = _get(env, "usage") or {}
        if isinstance(usage, Mapping):
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)

        text = _reply_text(env)
        if text is not None:
            n_responses += 1
            res = parse_option(text, n_options)
            # The parsed option is DISCARDED here; only ok/not-ok and the fail reason live on.
            if res.reason == PARSE_OK:
                n_parseable += 1
            else:
                reasons[res.reason] = reasons.get(res.reason, 0) + 1

    n_unique_draws = len(set(draw_ids))
    view = {
        "schema": GATE_VIEW_SCHEMA,
        "blinded": True,
        "blinding": "procedural",
        "blinding_rule": "R-V7-7",
        "request_integrity": {
            "n_envelopes": n_env,
            "n_unique_draw_ids": n_unique_draws,
            "n_duplicate_draw_ids": len(draw_ids) - n_unique_draws,
            "n_unique_request_sha256": len(set(request_hashes)),
            "n_unbound": n_env - len(draw_ids),
            "expected_draws": expected_draws,
        },
        "resolved_provider": [
            {"model": m, "provider": p, "upstream_model": u, "n": n}
            for (m, p, u), n in sorted(providers.items())
        ],
        "parse_coverage": {
            "n_responses": n_responses,
            "n_parseable": n_parseable,
            "parse_rate": (n_parseable / n_responses) if n_responses else None,
            "coverage_rate": ((n_env / expected_draws)
                              if expected_draws else None),
            "unparseable": dict(sorted(reasons.items())),
        },
        "errors": {
            "n_http_ok": n_http_ok,
            "n_http_error": n_http_error,
            "status_counts": dict(sorted(status_counts.items())),
            "n_cache_hit": n_cache_hit,
            "n_missing_cost": n_missing_cost,
        },
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "cost": {
            "returned_usd": returned_usd,
            "prior_usd": float(prior_usd),
            "cumulative_usd": float(prior_usd) + returned_usd,
            "n_costed": n_costed,
        },
    }
    assert_outcome_blinded(view)
    return view


def assert_outcome_blinded(view: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fail closed unless `view` is a permitted outcome-blinded operator view.

    Structural check, applied to every view this module emits: no section beyond the frozen
    whitelist, and no key anywhere that names a substantive outcome.
    """
    if not isinstance(view, Mapping):
        raise BlindingViolation("an operator view must be a mapping")
    allowed_top = set(GATE_VIEW_SECTIONS) | {
        "schema", "blinded", "blinding", "blinding_rule"}
    extra = sorted(set(view) - allowed_top)
    if extra:
        raise BlindingViolation(
            f"outcome-blinded view carries non-permitted section(s) {extra}; only "
            f"{list(GATE_VIEW_SECTIONS)} are visible before the promotion and funding "
            f"records exist")
    offenders = sorted(_substantive_keys(view))
    if offenders:
        raise BlindingViolation(
            f"outcome-blinded view carries substantive outcome key(s) {offenders}")
    return view


def _substantive_keys(node: Any, path: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(node, Mapping):
        for k, v in node.items():
            here = f"{path}.{k}" if path else str(k)
            if isinstance(k, str) and _SUBSTANTIVE_KEY.search(k):
                found.add(here)
            found |= _substantive_keys(v, here)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            found |= _substantive_keys(v, f"{path}[{i}]")
    return found


__all__ = [
    "BlindingViolation", "FUNDING_RECORD_FILENAME", "FUNDING_SCHEMA", "FundingRecord",
    "GATE_VIEW_SCHEMA", "GATE_VIEW_SECTIONS", "HeadlineBlocked", "INTERLOCK_DIRNAME",
    "InterlockError", "InterlockState", "PROMOTION_RECORD_FILENAME", "PROMOTION_SCHEMA",
    "PromotionRecord", "REQUIRED_RECORDS", "RecordBindingError", "RecordExistsError",
    "assert_outcome_blinded", "blinding_interlock", "funding_record_path", "gate_view",
    "interlock_dir", "interlock_state", "load_funding_record", "load_promotion_record",
    "promotion_record_path", "record_funding", "record_promotion",
    "require_headline_permitted",
]
