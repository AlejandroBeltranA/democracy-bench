"""Q2 Stage-2 v7.2 frozen hosted-run components (`paper/Q2_STAGE2_HOSTED_DESIGN.md`).

Pure functions only: no network call is made anywhere in this package. Transport is the
caller's responsibility (see `alignment.q2_hosted.Transport`).
"""

from alignment.q2_v7.envelope import (  # noqa: F401
    MAX_TOKENS,
    REASONING_OFF,
    REQUIRED_ATTEMPT,
    REQUIRED_AVAILABLE_CANDIDATES,
    REQUIRED_STRATEGY,
    SNAPSHOT_PATH,
    SNAPSHOT_SHA256,
    TEMPERATURE,
    TOP_P,
    AuditResult,
    EnvelopeError,
    ProviderAuditError,
    ReasoningError,
    ReasoningResult,
    Snapshot,
    SnapshotCandidate,
    SnapshotError,
    build_sampling_request,
    canonical_request_sha256,
    load_snapshot,
    request_headers,
    verify_provider_audit,
    verify_reasoning_off,
)

from alignment.q2_v7.interlock import (  # noqa: F401
    FundingRecord,
    HeadlineBlocked,
    InterlockError,
    InterlockState,
    PromotionRecord,
    assert_outcome_blinded,
    blinding_interlock,
    gate_view,
    interlock_state,
    record_funding,
    record_promotion,
    require_headline_permitted,
)

__all__ = [
    "MAX_TOKENS", "REASONING_OFF", "REQUIRED_ATTEMPT", "REQUIRED_AVAILABLE_CANDIDATES",
    "REQUIRED_STRATEGY", "SNAPSHOT_PATH", "SNAPSHOT_SHA256", "TEMPERATURE", "TOP_P",
    "AuditResult", "EnvelopeError", "ProviderAuditError", "ReasoningError", "ReasoningResult",
    "Snapshot", "SnapshotCandidate", "SnapshotError",
    "build_sampling_request", "canonical_request_sha256", "load_snapshot",
    "request_headers", "verify_provider_audit", "verify_reasoning_off",
    # Outcome-blinding interlock (v7 "Outcome-blinding interlock", R-V7-7).
    "FundingRecord", "HeadlineBlocked", "InterlockError", "InterlockState",
    "PromotionRecord", "assert_outcome_blinded", "blinding_interlock", "gate_view",
    "interlock_state", "record_funding", "record_promotion", "require_headline_permitted",
]
