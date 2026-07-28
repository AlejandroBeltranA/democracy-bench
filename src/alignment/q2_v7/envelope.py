"""Q2 Stage-2 v7.2 frozen request envelope, endpoint snapshot, and response audits.

Implements exactly the frozen spec in `paper/Q2_STAGE2_HOSTED_DESIGN.md` — the "v7
amendment", the "v7.1 revision" (R-V7-1..R-V7-7), and the "v7.2 closure" (C1..C4). Nothing
here is a redesign; every constant and rule is quoted from that document.

Everything in this module is a PURE function over dicts. There is no transport, no I/O other
than reading the committed snapshot file, and no network call of any kind. The caller owns the
transport seam (see `alignment.q2_hosted.Transport`).

What is frozen here
-------------------
* `build_sampling_request` — the exact v7 sampling body: `temperature 1.0`, `top_p 1.0`
  (R-V7-1 froze BOTH on all nine candidates; an endpoint that rejects either FAILS and the
  walk advances — parameters are never dropped), `max_tokens 4`, the DOCUMENTED reasoning-off
  control `reasoning:{"effort":"none"}` (R-V7-1 replaced the draft's undocumented
  `{"enabled":false}`), NO `seed` key at all (independent draws), no stop sequences,
  `provider.only=[tag]` with `allow_fallbacks:false` and `require_parameters:true`, and
  `usage.include:true` so the RETURNED cost drives the ledger.
* `request_headers` — `X-OpenRouter-Metadata: enabled` (routing metadata is what the C1 audit
  proof is read from) and `X-OpenRouter-Cache: false` on EVERY draw (R-V7-7). The key is put
  in the Authorization header and never stored, logged, or echoed by this module.
* `load_snapshot` — parses and SHA-256-binds the committed endpoint snapshot (C1). A snapshot
  whose recomputed digest differs from the expected value is a hard failure.
* `verify_provider_audit` — the FROZEN C1 provider-audit proof. Critically, C1 states: "Do not
  require a response field to equal the variant tag if the API does not return such a field."
  The API returns a provider DISPLAY NAME (`"Parasail"`), never the variant tag
  (`"parasail/fp8"`), so the proof runs through the snapshot's tag -> display-name mapping.
  Missing routing metadata FAILS. (This deliberately reverses the older
  `q2_hosted.provider_matches(declared, None) -> True` behaviour flagged in
  `paper/Q2_STAGE2_RUNNER_REVIEW.md`: absence of evidence is never proof of routing.)
* `verify_reasoning_off` — the R-V7-1 exact rule: the reported reasoning-token count must equal
  EXACTLY 0 (superseding v7's "approximately 0" wording), the response must carry no reasoning
  payload, and the required usage fields must be present.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------------------
# Frozen constants (v7 "Frozen sampling envelope" as revised by R-V7-1 / R-V7-7)
# ---------------------------------------------------------------------------------------

TEMPERATURE: float = 1.0
TOP_P: float = 1.0
MAX_TOKENS: int = 4
#: R-V7-1: OpenRouter's DOCUMENTED reasoning-off control. Not `{"enabled": false}`.
REASONING_OFF: dict = {"effort": "none"}
#: v7.2 C1: the bound snapshot artifact and its digest.
SNAPSHOT_PATH = "out/q2_stage2_endpoint_snapshot/manifest.json"
SNAPSHOT_SHA256 = "4b4b11a466cdf3af377a1a96b8478aac72fc2a22290315eac15aff9c780b295f"
#: C1 proof: OpenRouter must have routed directly, first attempt, one candidate, no BYOK.
REQUIRED_STRATEGY = "direct"
REQUIRED_ATTEMPT = 1
REQUIRED_AVAILABLE_CANDIDATES = 1
#: R-V7-1: usage fields that must be present for a draw to be auditable.
REQUIRED_USAGE_FIELDS: tuple[str, ...] = ("prompt_tokens", "completion_tokens", "total_tokens")
#: Response keys that would carry a reasoning payload; any non-empty one FAILS.
REASONING_PAYLOAD_KEYS: tuple[str, ...] = ("reasoning", "reasoning_content", "reasoning_details")
#: Metadata keys that would evidence a fallback hop; any truthy one FAILS.
FALLBACK_EVIDENCE_KEYS: tuple[str, ...] = (
    "fallback", "fallback_used", "fell_back", "fallbacks_used", "did_fallback",
)
ALLOWED_ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})

_SUMMARY_AVAILABLE = re.compile(r"available=(\d+)")
_SUMMARY_SELECTED = re.compile(r"selected=([^,]+)")


# ---------------------------------------------------------------------------------------
# Errors (fail-closed, consistent with q2_hosted's ProviderMismatch/ElicitationError style)
# ---------------------------------------------------------------------------------------

class EnvelopeError(RuntimeError):
    """Base for every fail-closed error raised by the v7 envelope module."""


class SnapshotError(EnvelopeError):
    """The committed endpoint snapshot is missing, malformed, or fails its SHA-256 binding."""


class ProviderAuditError(EnvelopeError):
    """A response failed the frozen C1 provider-audit proof. Its draw is not usable."""


class ReasoningError(EnvelopeError):
    """A response failed the R-V7-1 reasoning-off proof. Its endpoint/draw is not usable."""


# ---------------------------------------------------------------------------------------
# 1. Frozen sampling request
# ---------------------------------------------------------------------------------------

def _provider_block(provider_tag: str) -> dict:
    """The frozen routing block: exactly one candidate, no fallbacks, declared params only."""
    return {"only": [provider_tag], "allow_fallbacks": False, "require_parameters": True}


def _normalise_messages(messages: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Copy the chat messages into plain, canonically serialisable dicts. Fails closed on any
    shape the frozen envelope does not define, so a malformed prompt can never be paid for."""
    if isinstance(messages, (str, bytes, Mapping)) or not isinstance(messages, Iterable):
        raise EnvelopeError("messages must be a sequence of {role, content} mappings")
    out: list[dict] = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, Mapping):
            raise EnvelopeError(f"message {i} is not a mapping")
        role = msg.get("role")
        content = msg.get("content")
        if role not in ALLOWED_ROLES:
            raise EnvelopeError(f"message {i} has unsupported role {role!r}")
        if not isinstance(content, str):
            raise EnvelopeError(f"message {i} content must be a string")
        extra = set(msg) - {"role", "content"}
        if extra:
            raise EnvelopeError(f"message {i} carries undeclared keys {sorted(extra)}")
        out.append({"role": role, "content": content})
    if not out:
        raise EnvelopeError("messages must not be empty")
    return out


def build_sampling_request(model_slug: str,
                           provider_tag: str,
                           messages: Sequence[Mapping[str, Any]]) -> dict:
    """The EXACT JSON body sent to OpenRouter for one v7 sampling draw. Pure and frozen — the
    snapshot tests assert this key-for-key.

    Frozen per the v7 envelope as revised by R-V7-1 and R-V7-7:

    * `temperature 1.0` / `top_p 1.0` on every candidate (never conditionally omitted);
    * `max_tokens 4`;
    * `reasoning:{"effort":"none"}` — the DOCUMENTED reasoning-off control;
    * NO `seed` key at all: draws must be independent, so the key is absent, not null;
    * no stop sequences;
    * `provider.only=[provider_tag]`, `allow_fallbacks:false`, `require_parameters:true`;
    * `usage:{"include":true}` so the returned cost (not a catalog estimate) drives the ledger.

    `provider_tag` is the exact snapshot tag (e.g. `parasail/fp8`) and is sent verbatim; the
    RESPONSE is audited against the tag's display name, not against the tag (C1).
    """
    if not isinstance(model_slug, str) or not model_slug.strip():
        raise EnvelopeError("model_slug must be a non-empty string")
    if not isinstance(provider_tag, str) or not provider_tag.strip():
        raise EnvelopeError("provider_tag must be a non-empty string")
    return {
        "model": model_slug,
        "messages": _normalise_messages(messages),
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": MAX_TOKENS,
        "reasoning": dict(REASONING_OFF),
        "provider": _provider_block(provider_tag),
        "usage": {"include": True},
    }
    # NOTE: no "seed", no "stop", no "logprobs" — the sampling path is the only v7 path.


def request_headers(key: str) -> dict:
    """The frozen v7 request headers.

    `X-OpenRouter-Metadata: enabled` opts in to the routing metadata that the C1 audit proof
    reads. `X-OpenRouter-Cache: false` is required on EVERY draw (R-V7-7) so 13,200 independent
    draws can never collapse onto a cached completion.

    The API key is placed in the Authorization header and is never stored, logged, hashed, or
    returned anywhere else by this module.
    """
    if not isinstance(key, str) or not key.strip():
        raise EnvelopeError("API key must be a non-empty string")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Metadata": "enabled",
        "X-OpenRouter-Cache": "false",
    }


def canonical_request_sha256(body: Mapping[str, Any]) -> str:
    """Canonical SHA-256 of a request body — the identity half of R-V7-7's draw identity
    (`request SHA-256 + immutable draw index`). Same convention as `q2_hosted.request_key`."""
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# ---------------------------------------------------------------------------------------
# 2. Committed endpoint snapshot (C1)
# ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotCandidate:
    """One bound candidate endpoint from the committed snapshot."""
    model: str
    tag: str
    provider_name: str            # display name as OpenRouter returns it, e.g. "Parasail"
    endpoint_name: str            # "Parasail | deepseek/deepseek-v4-pro-20260423"
    upstream_model: str           # the datable upstream id parsed out of endpoint_name
    quantization: str             # catalog label; "unknown" is NOT full precision (R-V7-4)
    params_all_declared: bool
    supported_parameters: Mapping[str, bool]
    price_prompt_per_token: Decimal
    price_completion_per_token: Decimal

    @property
    def key(self) -> tuple[str, str]:
        return (self.model, self.tag)

    @property
    def price_prompt_per_million(self) -> Decimal:
        return self.price_prompt_per_token * Decimal(1_000_000)

    @property
    def price_completion_per_million(self) -> Decimal:
        return self.price_completion_per_token * Decimal(1_000_000)


@dataclass(frozen=True)
class Snapshot:
    """The committed, SHA-256-bound endpoint snapshot (v7.2 C1).

    Candidates are keyed by `(model, tag)` because tags are NOT globally unique: both
    `qwen/qwen3.5-397b-a17b @ parasail/fp8` and `deepseek/deepseek-v4-pro @ parasail/fp8`
    exist in the frozen table, and `streamlake` / `streamlake/fp8` share a display name.
    """
    path: str
    sha256: str
    artifact: str
    fetched_utc: str
    sources: tuple[str, ...]
    raw_file_sha256: Mapping[str, str]
    tokenizers: Mapping[str, Mapping[str, Any]]
    candidates: Mapping[tuple[str, str], SnapshotCandidate] = field(repr=False)

    def candidate(self, model: str, tag: str) -> SnapshotCandidate:
        """The bound candidate for `(model, tag)`. Fails closed on anything unbound."""
        try:
            return self.candidates[(model, tag)]
        except KeyError:
            raise SnapshotError(
                f"no snapshot candidate for model={model!r} tag={tag!r}"
            ) from None

    def display_name(self, model: str, tag: str) -> str:
        """The frozen tag -> provider display-name mapping the C1 audit proof compares against."""
        return self.candidate(model, tag).provider_name

    def quantization(self, model: str, tag: str) -> str:
        return self.candidate(model, tag).quantization

    def prices(self, model: str, tag: str) -> tuple[Decimal, Decimal]:
        """(prompt, completion) price per token, exactly as returned in the snapshot."""
        c = self.candidate(model, tag)
        return (c.price_prompt_per_token, c.price_completion_per_token)

    def tags_for(self, model: str) -> tuple[str, ...]:
        return tuple(tag for (m, tag) in self.candidates if m == model)


def _require_str(obj: Mapping[str, Any], key: str, where: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str) or not val:
        raise SnapshotError(f"{where}: missing or non-string {key!r}")
    return val


def _parse_candidate(raw: Mapping[str, Any], idx: int) -> SnapshotCandidate:
    where = f"candidate[{idx}]"
    if not isinstance(raw, Mapping):
        raise SnapshotError(f"{where}: not a mapping")
    model = _require_str(raw, "model", where)
    tag = _require_str(raw, "tag", where)
    provider_name = _require_str(raw, "provider_name", where)
    endpoint_name = _require_str(raw, "endpoint_name", where)
    # "DigitalOcean | qwen/qwen3.5-397b-a17b-20260216" -> display name + datable upstream id.
    if " | " not in endpoint_name:
        raise SnapshotError(f"{where}: endpoint_name {endpoint_name!r} is not '<provider> | <model>'")
    named, upstream_model = endpoint_name.split(" | ", 1)
    if named != provider_name:
        raise SnapshotError(
            f"{where}: endpoint_name provider {named!r} != provider_name {provider_name!r}")
    if not upstream_model:
        raise SnapshotError(f"{where}: endpoint_name carries no upstream model id")
    quantization = _require_str(raw, "quantization", where)
    declared = raw.get("params_all_declared")
    if not isinstance(declared, bool):
        raise SnapshotError(f"{where}: params_all_declared must be a bool")
    supported = raw.get("supported_parameters_subset")
    if not isinstance(supported, Mapping):
        raise SnapshotError(f"{where}: supported_parameters_subset must be a mapping")
    try:
        prompt_price = Decimal(_require_str(raw, "price_prompt_per_token", where))
        completion_price = Decimal(_require_str(raw, "price_completion_per_token", where))
    except SnapshotError:
        raise
    except Exception as exc:  # non-decimal price string
        raise SnapshotError(f"{where}: unparseable price ({exc})") from None
    return SnapshotCandidate(
        model=model,
        tag=tag,
        provider_name=provider_name,
        endpoint_name=endpoint_name,
        upstream_model=upstream_model,
        quantization=quantization,
        params_all_declared=declared,
        supported_parameters={str(k): bool(v) for k, v in supported.items()},
        price_prompt_per_token=prompt_price,
        price_completion_per_token=completion_price,
    )


def load_snapshot(path: str | Path,
                  expected_sha256: str = SNAPSHOT_SHA256) -> Snapshot:
    """Load and SHA-256-BIND the committed endpoint snapshot (`manifest.json`).

    Fails closed if the file is missing, is not JSON, is structurally wrong, contains duplicate
    `(model, tag)` candidates, or — the C1 binding — if its recomputed SHA-256 does not equal
    `expected_sha256`. `expected_sha256` defaults to the digest frozen in the v7.2 closure;
    passing `None` is refused rather than silently skipping verification.
    """
    if not isinstance(expected_sha256, str) or not expected_sha256.strip():
        raise SnapshotError("expected_sha256 is required; the snapshot binding is not optional")
    p = Path(path)
    try:
        raw_bytes = p.read_bytes()
    except OSError as exc:
        raise SnapshotError(f"cannot read snapshot {p}: {exc}") from None
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if digest.lower() != expected_sha256.strip().lower():
        raise SnapshotError(
            f"snapshot SHA-256 mismatch for {p}: expected {expected_sha256}, got {digest}")
    try:
        doc = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise SnapshotError(f"snapshot {p} is not valid JSON: {exc}") from None
    if not isinstance(doc, Mapping):
        raise SnapshotError(f"snapshot {p} is not a JSON object")

    raw_candidates = doc.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise SnapshotError("snapshot carries no candidates")
    candidates: dict[tuple[str, str], SnapshotCandidate] = {}
    for i, rc in enumerate(raw_candidates):
        cand = _parse_candidate(rc, i)
        if cand.key in candidates:
            raise SnapshotError(f"duplicate snapshot candidate {cand.key}")
        candidates[cand.key] = cand

    sources = doc.get("sources") or []
    if not isinstance(sources, list):
        raise SnapshotError("snapshot 'sources' must be a list")
    raw_files = doc.get("raw_files") or {}
    if not isinstance(raw_files, Mapping):
        raise SnapshotError("snapshot 'raw_files' must be a mapping")
    file_hashes = {}
    for name, entry in raw_files.items():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("sha256"), str):
            raise SnapshotError(f"snapshot raw_files[{name!r}] carries no sha256")
        file_hashes[str(name)] = entry["sha256"]
    tokenizers = doc.get("tokenizers") or {}
    if not isinstance(tokenizers, Mapping):
        raise SnapshotError("snapshot 'tokenizers' must be a mapping")

    return Snapshot(
        path=str(p),
        sha256=digest,
        artifact=str(doc.get("artifact", "")),
        fetched_utc=str(doc.get("fetched_utc", "")),
        sources=tuple(str(s) for s in sources),
        raw_file_sha256=file_hashes,
        tokenizers={str(k): v for k, v in tokenizers.items()},
        candidates=candidates,
    )


# ---------------------------------------------------------------------------------------
# 3. Frozen C1 provider-audit proof
# ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditResult:
    """Outcome of the frozen C1 provider-audit proof for one response."""
    ok: bool
    failures: tuple[str, ...]
    expected_model: str
    expected_tag: str
    expected_display_name: str
    requested_model: Optional[str] = None
    response_model: Optional[str] = None
    selected_provider: Optional[str] = None
    returned_upstream_model: Optional[str] = None
    strategy: Optional[str] = None
    attempt: Optional[Any] = None
    is_byok: Optional[Any] = None
    available_count: Optional[int] = None

    def __bool__(self) -> bool:
        return self.ok

    def raise_for_status(self) -> "AuditResult":
        """Fail closed: raise `ProviderAuditError` unless the proof passed."""
        if not self.ok:
            raise ProviderAuditError(
                f"provider audit failed for {self.expected_model}@{self.expected_tag}: "
                + ", ".join(self.failures))
        return self


def _metadata(response_json: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    meta = response_json.get("openrouter_metadata")
    return meta if isinstance(meta, Mapping) else None


def verify_provider_audit(response_json: Mapping[str, Any],
                          expected_model: str,
                          expected_tag: str,
                          snapshot: Snapshot) -> AuditResult:
    """The FROZEN v7.2 C1 provider-audit proof.

    A study response is accepted only if ALL of the following hold:

    1. routing metadata (`openrouter_metadata`) is present — MISSING METADATA FAILS, always;
    2. exactly one candidate was available;
    3. the selected provider DISPLAY NAME equals the snapshot's `(model, tag)` -> display-name
       mapping;
    4. requested and returned model evidence are consistent with the snapshot;
    5. `strategy == "direct"`;
    6. `attempt == 1` on success;
    7. no fallback occurred;
    8. `is_byok == false` (R-V7-5 — BYOK spend escapes the returned-cost ledger and would make
       the $8.50 stop incomplete).

    Per C1, NO response field is required to equal the variant tag (e.g. `parasail/fp8`): the
    API returns a display name and no tag field, so requiring one would fail every good
    response. The tag is carried on the REQUEST (`provider.only`) and is proved through the
    snapshot mapping here.
    """
    if not isinstance(response_json, Mapping):
        raise ProviderAuditError("response_json must be a mapping")
    candidate = snapshot.candidate(expected_model, expected_tag)
    expected_display = candidate.provider_name
    failures: list[str] = []

    meta = _metadata(response_json)
    if meta is None:
        # Absence of routing evidence is NOT evidence of correct routing. Fail closed.
        return AuditResult(ok=False, failures=("missing_openrouter_metadata",),
                           expected_model=expected_model, expected_tag=expected_tag,
                           expected_display_name=expected_display)

    if "error" in response_json:
        failures.append("error_in_response")

    requested = meta.get("requested")
    if requested != expected_model:
        failures.append(f"requested_model_mismatch:{requested!r}")

    response_model = response_json.get("model")
    if response_model is not None and response_model != expected_model:
        failures.append(f"response_model_mismatch:{response_model!r}")

    strategy = meta.get("strategy")
    if strategy != REQUIRED_STRATEGY:
        failures.append(f"strategy_not_direct:{strategy!r}")

    attempt = meta.get("attempt")
    if not (isinstance(attempt, int) and not isinstance(attempt, bool)
            and attempt == REQUIRED_ATTEMPT):
        failures.append(f"attempt_not_one:{attempt!r}")

    is_byok = meta.get("is_byok")
    if is_byok is not False:
        failures.append(f"is_byok_not_false:{is_byok!r}")

    for key in FALLBACK_EVIDENCE_KEYS:
        if meta.get(key):
            failures.append(f"fallback_occurred:{key}")

    endpoints = meta.get("endpoints")
    available = endpoints.get("available") if isinstance(endpoints, Mapping) else None
    selected_provider: Optional[str] = None
    returned_upstream: Optional[str] = None
    available_count: Optional[int] = None
    if not isinstance(available, list):
        failures.append("missing_available_candidates")
    else:
        available_count = len(available)
        if available_count != REQUIRED_AVAILABLE_CANDIDATES:
            failures.append(f"available_candidates_not_one:{available_count}")
        entries = [e for e in available if isinstance(e, Mapping)]
        chosen = [e for e in entries if e.get("selected") is True]
        if len(entries) == 1 and not chosen:
            # A single available endpoint under allow_fallbacks:false is the served one only if
            # it is actually flagged selected; an unselected sole candidate means no completion
            # was served from it (this is exactly the 429 shape seen in the canary records).
            failures.append("sole_candidate_not_selected")
        elif len(chosen) != 1 and entries:
            failures.append(f"selected_candidate_count:{len(chosen)}")
        target = chosen[0] if chosen else (entries[0] if entries else None)
        if target is not None:
            selected_provider = target.get("provider")
            returned_upstream = target.get("model")
            if selected_provider != expected_display:
                failures.append(f"display_name_mismatch:{selected_provider!r}")
            if returned_upstream != candidate.upstream_model:
                failures.append(f"returned_model_mismatch:{returned_upstream!r}")

    # Top-level display name, when the API supplies one, must agree with the same mapping.
    top_provider = response_json.get("provider")
    if isinstance(top_provider, str) and top_provider != expected_display:
        failures.append(f"response_provider_mismatch:{top_provider!r}")

    # `summary` is a human string ("available=1, selected=DigitalOcean"); when it is parseable
    # it must not contradict the structured evidence above.
    summary = meta.get("summary")
    if isinstance(summary, str):
        m = _SUMMARY_AVAILABLE.search(summary)
        if m and int(m.group(1)) != REQUIRED_AVAILABLE_CANDIDATES:
            failures.append(f"summary_available_not_one:{m.group(1)}")
        s = _SUMMARY_SELECTED.search(summary)
        if s and s.group(1).strip() != expected_display:
            failures.append(f"summary_selected_mismatch:{s.group(1).strip()!r}")

    return AuditResult(
        ok=not failures,
        failures=tuple(failures),
        expected_model=expected_model,
        expected_tag=expected_tag,
        expected_display_name=expected_display,
        requested_model=requested if isinstance(requested, str) else None,
        response_model=response_model if isinstance(response_model, str) else None,
        selected_provider=selected_provider if isinstance(selected_provider, str) else None,
        returned_upstream_model=returned_upstream if isinstance(returned_upstream, str) else None,
        strategy=strategy if isinstance(strategy, str) else None,
        attempt=attempt,
        is_byok=is_byok,
        available_count=available_count,
    )


# ---------------------------------------------------------------------------------------
# 4. Frozen R-V7-1 reasoning-off proof
# ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ReasoningResult:
    """Outcome of the R-V7-1 reasoning-off proof for one response."""
    ok: bool
    failures: tuple[str, ...]
    reasoning_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    def __bool__(self) -> bool:
        return self.ok

    def raise_for_status(self) -> "ReasoningResult":
        """Fail closed: raise `ReasoningError` unless the proof passed."""
        if not self.ok:
            raise ReasoningError("reasoning-off proof failed: " + ", ".join(self.failures))
        return self


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def verify_reasoning_off(response_json: Mapping[str, Any]) -> ReasoningResult:
    """The FROZEN R-V7-1 reasoning-off rule.

    "Reported reasoning-token count must equal 0, the response must carry no reasoning payload,
    and the required usage fields must be present; an endpoint that rejects `effort:"none"` or
    returns any positive reasoning-token count FAILS." This supersedes v7's "reasoning tokens
    approximately 0" wording — the threshold is EXACTLY zero.

    A missing `usage` block, a missing `completion_tokens_details.reasoning_tokens`, or any
    non-integer count is a FAILURE, never a pass: an unreported count is not a zero count.
    """
    if not isinstance(response_json, Mapping):
        raise ReasoningError("response_json must be a mapping")
    failures: list[str] = []

    usage = response_json.get("usage")
    reasoning_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    if not isinstance(usage, Mapping):
        failures.append("missing_usage")
    else:
        for fname in REQUIRED_USAGE_FIELDS:
            if not _is_int(usage.get(fname)):
                failures.append(f"missing_usage_field:{fname}")
        if _is_int(usage.get("completion_tokens")):
            completion_tokens = usage["completion_tokens"]
        details = usage.get("completion_tokens_details")
        if not isinstance(details, Mapping):
            failures.append("missing_completion_tokens_details")
        elif not _is_int(details.get("reasoning_tokens")):
            failures.append(f"missing_reasoning_tokens:{details.get('reasoning_tokens')!r}")
        else:
            reasoning_tokens = details["reasoning_tokens"]
            if reasoning_tokens != 0:
                failures.append(f"reasoning_tokens_not_zero:{reasoning_tokens}")

    # No reasoning payload anywhere in the returned choices.
    choices = response_json.get("choices")
    if isinstance(choices, list):
        for i, choice in enumerate(choices):
            if not isinstance(choice, Mapping):
                continue
            carriers = [choice]
            msg = choice.get("message")
            if isinstance(msg, Mapping):
                carriers.append(msg)
            delta = choice.get("delta")
            if isinstance(delta, Mapping):
                carriers.append(delta)
            for carrier in carriers:
                for key in REASONING_PAYLOAD_KEYS:
                    if carrier.get(key):
                        failures.append(f"reasoning_payload:choices[{i}].{key}")

    return ReasoningResult(
        ok=not failures,
        failures=tuple(failures),
        reasoning_tokens=reasoning_tokens,
        completion_tokens=completion_tokens,
    )
