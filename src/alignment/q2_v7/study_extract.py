"""Q2 Stage-2 v7.2 study extraction — persisted raw envelopes to the eight frozen estimands.

FROZEN SPEC (implemented, never redesigned): `paper/Q2_STAGE2_HOSTED_DESIGN.md`,
"Estimands (per model, non-pooled; per R-H2)", the "v7 amendment", "v7.1 revision" (R-V7-3,
R-V7-7) and the "v7.2 closure" (C4). Everything structural — the 11 cells, 12 probes, four
Williams orders, 25 draws per coordinate, the completeness rule, the nested bootstrap, the
S-F4 anchored parser, the local crack (`item_cracks`/`guard_closes`, FLOOR_MIN) and
materiality (MATERIALITY) thresholds — is IMPORTED from the frozen modules. Nothing is
restated here as a literal.

This module is the read-only analysis path:

    raw envelopes (+ linked derived records)   [alignment.q2_v7.ledger]
        -> per-draw coordinates + S-F4 parse   [alignment.q2_v7.identity]
        -> R-V7-3 completeness gate            [alignment.q2_v7.gate]
        -> C4 nested bootstrap, eight frozen contrasts
        -> Q1-inherited crack/materiality diagnostics
        -> one deterministic JSON artifact

NETWORK: none. Filesystem reads and pure functions only. Nothing here can issue a request.

FAIL-LOUD. Every ambiguity resolves to a raised error or a `choice=None`, never to a guess:

  * an unparseable, empty, prose, or out-of-range reply becomes `choice=None` — the S-F4
    parser never guesses and never clamps, and an out-of-range display position is rejected
    outright rather than allowed to negative-index into a Williams order;
  * a draw whose linked `DerivedRecord` marks it excluded (failed provider audit, positive
    reasoning tokens, response-cache HIT, HTTP error) never contributes to an estimand;
  * a study envelope that the run manifest does not bind, a draw identity that disagrees with
    its envelope's own fields, a derived record whose `raw_sha256` does not match the
    envelope it claims to describe, a second serving provider, or a paid envelope with no
    recoverable returned cost all RAISE;
  * the completeness gate runs FIRST and an incomplete model emits NO estimand at all — not
    a contrast, not a protective mass, not a diagnostic.

RESOLVED SPEC AMBIGUITIES (documented, not silently chosen):

  1. **An excluded draw is an ATTEMPTED draw with no valid measurement.** R-V7-3 requires
     "25 attempted draws per order" AND ">= 20/25 parseable" per order. An excluded draw was
     attempted and paid for; it simply yielded no usable choice. It is therefore carried into
     the gate as an attempted draw with `choice=None`, which (a) keeps the attempted count
     honest, (b) makes exclusions bite through the >= 20/25 and >= 0.95 parseable rules
     rather than through a misleading "wrong attempt count" message, and (c) guarantees the
     draw can never enter a protective mass or a contrast. Its exclusion reasons stay in the
     audit trail. Dropping it entirely would fail the model on any single exclusion while
     mislabelling the cause as a missing attempt.
  2. **`extract_model` needs the item bank** (option labels and `floor_dir`) to reconstruct
     protective mass. `items` is an explicit keyword; when omitted it is loaded from the
     frozen local bank via `alignment.q2_hosted.load_probe_items` (a local file read).
  3. **Coordinates come from the run manifest**, whose `coordinates` rows bind
     `request_sha256 -> (cell_id, probe_id, order_idx)` (R-V7-7). A draw identity supplies
     only the request hash and the immutable draw index, so the manifest is the only
     non-guessing way to recover a coordinate. Both draw-identity spellings in the repo
     (`<sha>#draw<i>` from `identity`, `<sha>#<i>` from `ledger.DrawIdentity`) are accepted
     and are cross-checked against the envelope's own `request_sha256`/`draw_index` fields.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from alignment.q1_channel import FLOOR_MIN, guard_closes, item_cracks
from alignment.q2_hosted import MATERIALITY, aggregate_sampling_mass, cid_for
from alignment.q2_v7 import envelope as ENV
from alignment.q2_v7 import identity as ID
from alignment.q2_v7 import ledger as LG
from alignment.q2_v7.gate import (BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED, CELL_IDS,
                                  CONTRAST_NAMES, N_OPTIONS, N_ORDERS_REQUIRED,
                                  CompletenessReport, IncompleteModel, NestedBootstrapResult,
                                  SamplingDraw, completeness_gate, nested_bootstrap,
                                  require_complete)

ARTIFACT_SCHEMA = "q2_v7.study_extract.v1"

#: Filename of the run manifest inside an `EnvelopeStore` run directory, used when the caller
#: does not pass one explicitly.
MANIFEST_FILENAME = "manifest.json"

#: Envelope stages that MUST be bound by the run manifest. Anything else (a canary, an
#: endpoint-promotion gate probe, a standalone diagnostic) is not a study draw and is
#: recorded as ignored rather than forced into a coordinate.
STUDY_STAGES: frozenset[str] = frozenset({"study", "smoke"})


class ExtractionError(RuntimeError):
    """A fail-closed extraction failure. Never downgraded to a warning or a default."""


class HeadlineBlocked(ExtractionError):
    """The outcome-blinding interlock is not satisfied, so nothing substantive is aggregated.

    v7 "Outcome-blinding interlock (frozen)": no substantive outcome becomes visible until
    BOTH (a) the model's endpoint-promotion decision and (b) the funding decision are
    recorded — "headline aggregation refuses to run until both records exist".
    """


# =======================================================================================
# Coordinate index — request hash -> (cell_id, probe_id, order_idx), from the run manifest
# =======================================================================================

@dataclass(frozen=True)
class CoordinateIndex:
    """The manifest's binding of request hashes to coordinates (R-V7-7)."""
    by_request_sha256: Mapping[str, tuple[str, str, int]]
    manifest_sha256: Optional[str]
    model: Optional[str]
    endpoint_slug: Optional[str]

    def coordinate(self, request_sha256: str) -> Optional[tuple[str, str, int]]:
        return self.by_request_sha256.get(request_sha256)


def _manifest_body(manifest: Any, store: Optional["LG.EnvelopeStore"]) -> tuple[Mapping, Optional[str]]:
    """Normalise the accepted manifest spellings to `(body, sha256)`; raise on anything else."""
    if manifest is None:
        if store is None:
            raise ExtractionError("no manifest supplied and no store to locate one in")
        path = Path(store.run_dir) / MANIFEST_FILENAME
        if not path.exists():
            raise ExtractionError(
                f"no run manifest at {path}: coordinates are recovered from the manifest "
                f"(R-V7-7) and are never guessed from a request body")
        manifest = path
    if isinstance(manifest, ID.Manifest):
        return manifest.body, manifest.sha256
    if isinstance(manifest, (str, os.PathLike)):
        path = Path(manifest)
        if not path.exists():
            raise ExtractionError(f"run manifest {path} does not exist")
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"run manifest {path} is not valid JSON: {exc}") from exc
        if not isinstance(body, Mapping):
            raise ExtractionError(f"run manifest {path} is not a JSON object")
        return body, ID.canonical_sha256(body)
    if isinstance(manifest, Mapping) and "coordinates" in manifest:
        return manifest, ID.canonical_sha256(manifest)
    raise ExtractionError(
        f"unusable manifest of type {type(manifest).__name__}: pass an identity.Manifest, a "
        f"path to the persisted manifest, or its parsed body")


def coordinate_index(manifest: Any = None, *, store: Optional["LG.EnvelopeStore"] = None,
                     probe_ids: Optional[Sequence[str]] = None,
                     model: Optional[str] = None) -> CoordinateIndex:
    """Build the request-hash -> coordinate index from the run manifest, fail-closed.

    Rejects a manifest that binds an unexpected cell, probe, or order, a duplicate request
    hash, or a different model than the one being extracted: an analysis that silently
    tolerates a manifest mismatch is not an audit.
    """
    body, sha = _manifest_body(manifest, store)
    bound_model = body.get("model")
    if model is not None and bound_model is not None and bound_model != model:
        raise ExtractionError(
            f"manifest binds model {bound_model!r}, extraction asked for {model!r}")
    rows = body.get("coordinates")
    if not isinstance(rows, list) or not rows:
        raise ExtractionError("manifest binds no coordinates")

    expected_cells = set(CELL_IDS)
    expected_probes = set(probe_ids) if probe_ids is not None else None
    index: dict[str, tuple[str, str, int]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ExtractionError(f"malformed manifest coordinate row: {row!r}")
        try:
            cell_id = str(row["cell_id"])
            probe_id = str(row["probe_id"])
            order_idx = int(row["order_idx"])
            request_sha = str(row["request_sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtractionError(f"malformed manifest coordinate row {row!r}: {exc}") from exc
        if cell_id not in expected_cells:
            raise ExtractionError(f"manifest binds unexpected cell {cell_id!r}")
        if expected_probes is not None and probe_id not in expected_probes:
            raise ExtractionError(f"manifest binds unexpected probe {probe_id!r}")
        if not (0 <= order_idx < N_ORDERS_REQUIRED):
            raise ExtractionError(f"manifest binds unexpected order index {order_idx}")
        if request_sha in index and index[request_sha] != (cell_id, probe_id, order_idx):
            raise ExtractionError(
                f"manifest binds request {request_sha} to two coordinates: "
                f"{index[request_sha]} and {(cell_id, probe_id, order_idx)}")
        index[request_sha] = (cell_id, probe_id, order_idx)

    return CoordinateIndex(by_request_sha256=index, manifest_sha256=sha,
                           model=(str(bound_model) if bound_model is not None else None),
                           endpoint_slug=(str(body["endpoint_slug"])
                                          if body.get("endpoint_slug") is not None else None))


# =======================================================================================
# Per-draw extraction
# =======================================================================================

@dataclass(frozen=True)
class DrawRecord:
    """The audit row for ONE persisted study draw — kept whether or not it is admitted."""
    draw_id: str
    request_sha256: str
    draw_index: int
    cell_id: str
    probe_id: str
    order_idx: int
    choice: Optional[int]
    parse_reason: str
    excluded: bool
    exclusion_reasons: tuple[str, ...]
    http_status: int
    cost_usd: Optional[float]
    cost_status: str
    provider: str
    stage: str

    @property
    def coordinate(self) -> tuple[str, str, int]:
        return (self.cell_id, self.probe_id, self.order_idx)

    @property
    def sort_key(self) -> tuple[str, str, int, int]:
        return (self.cell_id, self.probe_id, self.order_idx, self.draw_index)

    def as_dict(self) -> dict:
        return {
            "draw_id": self.draw_id,
            "request_sha256": self.request_sha256,
            "draw_index": self.draw_index,
            "cell_id": self.cell_id,
            "probe_id": self.probe_id,
            "order_idx": self.order_idx,
            "choice": self.choice,
            "parse_reason": self.parse_reason,
            "excluded": self.excluded,
            "exclusion_reasons": list(self.exclusion_reasons),
            "http_status": self.http_status,
            "cost_usd": self.cost_usd,
            "cost_status": self.cost_status,
            "provider": self.provider,
            "stage": self.stage,
        }


@dataclass(frozen=True)
class DrawExtraction:
    """Every study draw found on disk: the admitted `SamplingDraw`s plus the full audit trail."""
    model: str
    manifest_sha256: Optional[str]
    endpoint_slug: Optional[str]
    provider: Optional[str]
    records: tuple[DrawRecord, ...]
    draws: tuple[SamplingDraw, ...]
    ignored_draw_ids: tuple[str, ...]

    @property
    def excluded(self) -> tuple[DrawRecord, ...]:
        return tuple(r for r in self.records if r.excluded)

    @property
    def admitted(self) -> tuple[DrawRecord, ...]:
        return tuple(r for r in self.records if not r.excluded)

    def exclusion_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.excluded:
            for reason in record.exclusion_reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))

    def parse_summary(self) -> dict:
        """Parse/exclusion rates. `parse_rate` is over ALL attempted draws (the figure the
        R-V7-3 gate applies); `parse_rate_admitted` is over the non-excluded draws only."""
        n = len(self.records)
        admitted = self.admitted
        n_parsed = sum(1 for r in self.records if r.choice is not None)
        n_parsed_admitted = sum(1 for r in admitted if r.choice is not None)
        reasons: dict[str, int] = {}
        for record in self.records:
            reasons[record.parse_reason] = reasons.get(record.parse_reason, 0) + 1
        per_cell: dict[str, dict] = {}
        for cell in CELL_IDS:
            rows = [r for r in self.records if r.cell_id == cell]
            parsed = sum(1 for r in rows if r.choice is not None)
            per_cell[cell] = {
                "n_attempted": len(rows),
                "n_parsed": parsed,
                "n_excluded": sum(1 for r in rows if r.excluded),
                "parse_rate": (parsed / len(rows)) if rows else 0.0,
            }
        return {
            "n_attempted": n,
            "n_parsed": n_parsed,
            "n_excluded": len(self.excluded),
            "parse_rate": (n_parsed / n) if n else 0.0,
            "parse_rate_admitted": (n_parsed_admitted / len(admitted)) if admitted else 0.0,
            "parse_reasons": dict(sorted(reasons.items())),
            "exclusion_reasons": self.exclusion_counts(),
            "per_cell": per_cell,
            "n_ignored_non_study_envelopes": len(self.ignored_draw_ids),
        }

    def as_audit(self) -> dict:
        return {
            "model": self.model,
            "manifest_sha256": self.manifest_sha256,
            "endpoint_slug": self.endpoint_slug,
            "provider": self.provider,
            "parse": self.parse_summary(),
            "excluded_draws": [r.as_dict() for r in self.excluded],
            "ignored_draw_ids": list(self.ignored_draw_ids),
        }


def _parse_identity(env: "LG.RawEnvelope") -> tuple[str, int]:
    """Recover `(request_sha256, draw_index)` from the draw identity and CROSS-CHECK it
    against the envelope's own fields. Both repo spellings are accepted; a disagreement is an
    audit-integrity failure, not something to paper over."""
    try:
        sha, idx = ID.parse_draw_id(env.draw_id)
    except ID.IdentityError:
        try:
            parsed = LG.DrawIdentity.parse(env.draw_id)
        except (ValueError, TypeError) as exc:
            raise ExtractionError(
                f"malformed draw identity {env.draw_id!r}: {exc}") from exc
        sha, idx = parsed.request_sha256, parsed.draw_index
    if sha != env.request_sha256 or idx != env.draw_index:
        raise ExtractionError(
            f"draw identity {env.draw_id!r} disagrees with the envelope fields "
            f"(request_sha256={env.request_sha256!r}, draw_index={env.draw_index})")
    return sha, idx


def _reply_text(env: "LG.RawEnvelope") -> tuple[Optional[str], Optional[str]]:
    """`(text, hard_reason)` — the assistant reply, or a reason it cannot be read as text.

    A non-string content payload is NOT coerced: it is unparseable by construction.
    """
    choices = (env.response_body or {}).get("choices")
    if not isinstance(choices, list) or not choices:
        return None, "no_choices"
    first = choices[0]
    if not isinstance(first, Mapping):
        return None, "malformed_choice"
    message = first.get("message")
    if not isinstance(message, Mapping):
        return None, "no_message"
    content = message.get("content")
    if content is None:
        return None, None                       # empty reply -> the parser's `empty` reason
    if not isinstance(content, str):
        return None, "non_string_content"
    return content, None


def _reasoning_tokens(env: "LG.RawEnvelope") -> Optional[int]:
    """Reported reasoning-token count, or None when the endpoint reported none.

    Only a POSITIVE count is an exclusion here (the frozen reasoning-off PROOF, which also
    rejects an absent count, is the endpoint-promotion gate's job, not the extractor's).
    """
    usage = env.usage or {}
    details = usage.get("completion_tokens_details")
    if isinstance(details, Mapping) and isinstance(details.get("reasoning_tokens"), int) \
            and not isinstance(details.get("reasoning_tokens"), bool):
        return int(details["reasoning_tokens"])
    value = usage.get("reasoning_tokens")
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    return None


def _exclusion_reasons(env: "LG.RawEnvelope",
                       derived: Optional["LG.DerivedRecord"]) -> tuple[str, ...]:
    """Every reason this paid draw may not enter an estimand. Order is deterministic."""
    reasons: list[str] = []
    if derived is None:
        # ledger.estimand_eligible_draw_ids: validation is REQUIRED, never assumed.
        reasons.append("no_derived_record")
    else:
        if not derived.valid:
            reasons.append("derived_invalid")
        if derived.excluded_from_estimands:
            reasons.append("derived_excluded")
        for failure in derived.failures:
            reasons.append(f"derived_failure:{failure}")
    if int(env.http_status) != 200:
        reasons.append(f"http_status:{int(env.http_status)}")
    if LG.is_cache_hit(env.response_body or {}, env.response_headers):
        reasons.append("cache_hit")
    reasoning = _reasoning_tokens(env)
    if reasoning is not None and reasoning > 0:
        reasons.append(f"reasoning_tokens:{reasoning}")
    metadata = env.openrouter_metadata
    if isinstance(metadata, Mapping) and metadata.get("is_byok") is True:
        reasons.append("is_byok")

    # The FULL frozen C1 provider-audit proof and the R-V7-1 reasoning-off rule, re-verified
    # here from the RAW envelope rather than trusted from the derived record.
    #
    # The adversarial review found the study path applied only the subset above, so a draw
    # could enter the eight estimands while carrying no routing metadata at all, no
    # reasoning-token evidence (an unreported count is NOT a zero count), a different provider
    # display name, `strategy != "direct"`, `attempt != 1`, two available candidates, or an
    # undated catalog slug. C1 is written for "a study response", so it binds every draw.
    #
    # Re-deriving rather than trusting `derived` is deliberate defence in depth: a record
    # written by an older or weaker writer must not be able to admit a non-conforming draw.
    if int(env.http_status) == 200:
        reasons.extend(_frozen_proof_failures(env))
    return tuple(dict.fromkeys(reasons))        # de-duplicated, order preserved


def _frozen_proof_failures(env: "LG.RawEnvelope") -> list[str]:
    """C1 + R-V7-1 applied to one persisted envelope; fail-closed if it cannot be checked."""
    try:
        from alignment.q2_v7 import envelope as EV
        root = Path(__file__).resolve().parents[3]
        snapshot = EV.load_snapshot(root / EV.SNAPSHOT_PATH)
    except Exception as exc:                     # a missing/altered snapshot is not a pass
        return [f"audit_unverifiable:{type(exc).__name__}"]

    out: list[str] = []
    body = env.response_body or {}
    try:
        audit = EV.verify_provider_audit(body, env.model, env.provider, snapshot)
        if not getattr(audit, "ok", False):
            out.extend(f"audit:{f}" for f in (getattr(audit, "failures", ()) or ()))
    except Exception as exc:
        out.append(f"audit_error:{type(exc).__name__}")
    try:
        reasoning = EV.verify_reasoning_off(body)
        if not getattr(reasoning, "ok", False):
            out.extend(f"reasoning:{f}" for f in (getattr(reasoning, "failures", ()) or ()))
    except Exception as exc:
        out.append(f"reasoning_error:{type(exc).__name__}")
    return out


def extract_draws(store: "LG.EnvelopeStore", *, probe_ids: Sequence[str], model: str,
                  manifest: Any = None) -> DrawExtraction:
    """Rebuild every study draw from the persisted immutable envelopes, with its audit row.

    Fail-loud on any audit-integrity failure; `choice=None` (never a guess) on any reply that
    the frozen S-F4 anchored parser does not accept.
    """
    index = coordinate_index(manifest, store=store, probe_ids=probe_ids, model=model)

    records: list[DrawRecord] = []
    ignored: list[str] = []
    seen: set[str] = set()
    providers: set[str] = set()

    for env in store.envelopes():
        if env.draw_id in seen:
            raise ExtractionError(f"draw {env.draw_id} appears more than once in {store.raw_dir}")
        seen.add(env.draw_id)

        sha, draw_index = _parse_identity(env)
        coord = index.coordinate(sha)
        if coord is None:
            if env.stage in STUDY_STAGES:
                raise ExtractionError(
                    f"study draw {env.draw_id} carries request {sha} which the run manifest "
                    f"does not bind — refusing to attribute it to a coordinate")
            ignored.append(env.draw_id)
            continue
        if env.model and env.model != model:
            raise ExtractionError(
                f"manifest-bound draw {env.draw_id} carries model {env.model!r}, not {model!r}")

        derived = store.get_derived(env.draw_id)
        if derived is not None and derived.raw_sha256 != env.content_sha256():
            raise ExtractionError(
                f"derived record for {env.draw_id} links raw hash {derived.raw_sha256[:12]} "
                f"but the persisted envelope hashes to {env.content_sha256()[:12]}")

        text, hard_reason = _reply_text(env)
        if hard_reason is not None:
            choice, parse_reason = None, hard_reason
        else:
            parsed = ID.parse_option(text, N_OPTIONS)
            choice, parse_reason = parsed.index, parsed.reason
        if choice is not None and not (0 <= int(choice) < N_OPTIONS):
            # Unreachable through `parse_option`; asserted so a future parser change can never
            # let an out-of-range display position negative-index into a Williams order.
            raise ExtractionError(
                f"parser returned display position {choice} outside [0,{N_OPTIONS}) for "
                f"{env.draw_id} — an out-of-range reply must be recorded as None")

        reasons = _exclusion_reasons(env, derived)
        cell_id, probe_id, order_idx = coord
        records.append(DrawRecord(
            draw_id=env.draw_id, request_sha256=sha, draw_index=draw_index,
            cell_id=cell_id, probe_id=probe_id, order_idx=order_idx,
            choice=(None if reasons else choice), parse_reason=parse_reason,
            excluded=bool(reasons), exclusion_reasons=reasons,
            http_status=int(env.http_status), cost_usd=env.cost_usd,
            cost_status=env.cost_status, provider=env.provider, stage=env.stage))
        if env.provider:
            providers.add(env.provider)

    if len(providers) > 1:
        raise ExtractionError(
            f"study draws were served by more than one provider {sorted(providers)} — a "
            f"model's headline may never mix endpoints")
    provider = next(iter(providers)) if providers else None
    if index.endpoint_slug is not None and provider is not None \
            and index.endpoint_slug != provider:
        raise ExtractionError(
            f"manifest binds endpoint {index.endpoint_slug!r} but the envelopes were served "
            f"by {provider!r}")

    records.sort(key=lambda r: r.sort_key)
    draws = tuple(SamplingDraw(cell_id=r.cell_id, probe_id=r.probe_id, order_idx=r.order_idx,
                               draw_index=r.draw_index, choice=r.choice)
                  for r in records)
    return DrawExtraction(model=model, manifest_sha256=index.manifest_sha256,
                          endpoint_slug=index.endpoint_slug, provider=provider,
                          records=tuple(records), draws=draws,
                          ignored_draw_ids=tuple(sorted(ignored)))


def _extract_or_empty(store: "LG.EnvelopeStore", *, probe_ids: Sequence[str], model: str,
                      manifest: Any = None) -> DrawExtraction:
    """`extract_draws`, except that a store holding NO envelopes and no manifest yields an
    empty extraction rather than a missing-manifest error.

    A run with nothing in it is unambiguously an incomplete model — there is no coordinate to
    guess and nothing to emit. A store that DOES hold envelopes but has no manifest still
    fails loud: that is a misconfigured analysis, not an empty run.
    """
    if manifest is None and not store.envelopes() \
            and not (Path(store.run_dir) / MANIFEST_FILENAME).exists():
        return DrawExtraction(model=model, manifest_sha256=None, endpoint_slug=None,
                              provider=None, records=(), draws=(), ignored_draw_ids=())
    return extract_draws(store, probe_ids=probe_ids, model=model, manifest=manifest)


def load_draws(store: "LG.EnvelopeStore", *, probe_ids: Sequence[str], model: str,
               manifest: Any = None) -> list[SamplingDraw]:
    """The `gate.SamplingDraw` rows reconstructed from the persisted immutable envelopes.

    An excluded draw is retained as an ATTEMPTED draw whose `choice` is None, so it can never
    reach an estimand while the attempted count stays honest (see the module docstring).
    `extract_draws` returns the same rows plus the full audit trail.
    """
    return list(extract_draws(store, probe_ids=probe_ids, model=model, manifest=manifest).draws)


# =======================================================================================
# Spend reconciliation over the persisted envelopes
# =======================================================================================

def reconcile_spend(extraction: DrawExtraction, store: "LG.EnvelopeStore", *,
                    reconciliation: Optional["LG.ReconciliationResult"] = None) -> dict:
    """Book the RETURNED cost of every persisted envelope in this run, plus any reconciled
    prior spend. Fails closed exactly as R-E2 requires: an envelope with no recoverable
    returned cost is never written off as free.

    Summation is `math.fsum` over costs sorted by draw id, so the total is deterministic and
    independent of directory-iteration order.
    """
    by_draw: dict[str, float] = {}
    by_bucket: dict[str, float] = {}
    for env in store.envelopes():
        cost = env.cost_usd
        if cost is None:
            if LG.is_unbilled_rejection(env.response_body or {}, env.http_status,
                                        env.response_headers):
                cost = 0.0
            else:
                raise ExtractionError(
                    f"envelope {env.draw_id} was persisted without a returned cost "
                    f"(cost_status={env.cost_status!r}); refusing to book it as free (R-E2)")
        by_draw[env.draw_id] = float(cost)
        by_bucket[env.bucket] = by_bucket.get(env.bucket, 0.0) + float(cost)

    run_usd = math.fsum(by_draw[k] for k in sorted(by_draw))
    prior_usd = reconciliation.total_usd if reconciliation is not None else 0.0
    return {
        "run_usd": run_usd,
        "prior_usd": prior_usd,
        "total_usd": run_usd + prior_usd,
        "hard_stop_usd": LG.HARD_STOP_USD,
        "is_exact": bool(reconciliation.is_exact) if reconciliation is not None else True,
        "n_booked_envelopes": len(by_draw),
        "n_study_draws": len(extraction.records),
        "by_bucket": {k: by_bucket[k] for k in sorted(by_bucket)},
        "reconciliation": (reconciliation.to_dict() if reconciliation is not None else None),
    }


# =======================================================================================
# Q1-inherited crack and materiality diagnostics
# =======================================================================================

def _mean(values: Iterable[float]) -> float:
    vals = sorted(float(v) for v in values)
    return math.fsum(vals) / len(vals) if vals else 0.0


def _ci_excludes_zero(ci: Sequence[float]) -> bool:
    low, high = float(ci[0]), float(ci[1])
    return low > 0.0 or high < 0.0


def crack_diagnostics(mass: Mapping[str, Mapping[str, float]],
                      contrasts: Mapping[str, Mapping[str, Any]]) -> dict:
    """The Q1-inherited crack and materiality diagnostics, so the hosted result is directly
    comparable to the local one.

    Thresholds are IMPORTED, never restated: `item_cracks` / `guard_closes` / `FLOOR_MIN`
    from the frozen local channel design, `MATERIALITY` from the frozen hosted design. The
    values are echoed into the artifact only so every reported number is regenerable.
    """
    base_cell = cid_for("baseline", "no_guard")
    if base_cell not in mass:
        raise ExtractionError("no baseline/no_guard protective mass — cannot judge cracks")
    baseline = mass[base_cell]
    probes = sorted(baseline)

    per_cell: dict[str, dict] = {}
    for cell in CELL_IDS:
        cell_mass = mass.get(cell)
        if cell_mass is None or sorted(cell_mass) != probes:
            raise ExtractionError(
                f"cell {cell!r} has protective mass for {sorted(cell_mass or {})}, expected "
                f"{probes}")
        cracked = [p for p in probes if item_cracks(baseline[p], cell_mass[p])]
        below = [p for p in probes if cell_mass[p] < FLOOR_MIN]
        per_cell[cell] = {
            "mean_protective_mass": _mean(cell_mass[p] for p in probes),
            "n_cracked": len(cracked),
            "cracked_probes": cracked,
            "n_below_floor": len(below),
            "below_floor_probes": below,
            "margins_to_floor": {p: cell_mass[p] - FLOOR_MIN for p in probes},
        }

    closure: dict[str, dict] = {}
    for payload_key in ("data_only", "combined"):
        unguarded = cid_for(payload_key, "no_guard")
        guarded = cid_for(payload_key, "system_guard")
        cracked = [p for p in probes if item_cracks(baseline[p], mass[unguarded][p])]
        closed = [p for p in cracked if guard_closes(mass[guarded][p])]
        closure[guarded] = {
            "unguarded_cell": unguarded,
            "n_cracked_unguarded": len(cracked),
            "cracked_probes": cracked,
            "n_closed": len(closed),
            "closed_probes": closed,
        }

    materiality: dict[str, dict] = {}
    for name in CONTRAST_NAMES:
        row = contrasts[name]
        mean = float(row["mean"])
        ci = [float(row["ci"][0]), float(row["ci"][1])]
        excludes_zero = _ci_excludes_zero(ci)
        materiality[name] = {
            "mean": mean,
            "ci": ci,
            "abs_mean_at_least_threshold": abs(mean) >= MATERIALITY,
            "ci_excludes_zero": excludes_zero,
            "material": bool(abs(mean) >= MATERIALITY and excludes_zero),
            "harmful": bool(ci[1] < 0.0),
        }

    return {
        "thresholds": {"floor_min": FLOOR_MIN, "materiality": MATERIALITY,
                       "source": "inherited from the frozen local design "
                                 "(alignment.q1_channel / alignment.q2_hosted)"},
        "per_cell": per_cell,
        "system_guard_closure": closure,
        "contrast_materiality": materiality,
    }


# =======================================================================================
# The model-level result
# =======================================================================================

@dataclass(frozen=True)
class ModelResult:
    """One model's extraction outcome. `complete=False` means NO estimand exists — not a
    contrast, not a protective mass, not a diagnostic."""
    model: str
    complete: bool
    completeness: CompletenessReport
    extraction: DrawExtraction
    spend: Mapping[str, Any]
    promoted_endpoint: Optional[str]
    endpoint_snapshot_sha256: Optional[str]
    manifest_sha256: Optional[str]
    estimands: Optional[NestedBootstrapResult] = None
    protective_mass: Optional[Mapping[str, Mapping[str, float]]] = None
    diagnostics: Optional[Mapping[str, Any]] = None

    @property
    def failures(self) -> tuple[str, ...]:
        return self.completeness.failures

    def require_complete(self) -> "ModelResult":
        """Fail closed for a caller that wants an exception rather than a report."""
        require_complete(self.completeness)
        return self

    def as_artifact(self) -> dict:
        """The deterministic artifact body. Regenerating it from the same raw envelopes
        yields byte-identical JSON (see `write_artifact`)."""
        body: dict = {
            "schema": ARTIFACT_SCHEMA,
            "design_doc": "paper/Q2_STAGE2_HOSTED_DESIGN.md",
            "model": self.model,
            "complete": self.complete,
            "headline_emitted": self.estimands is not None,
            "completeness": self.completeness.as_record(),
            "endpoint": {
                "promoted_endpoint": self.promoted_endpoint,
                "endpoint_snapshot_sha256": self.endpoint_snapshot_sha256,
            },
            "manifest_sha256": self.manifest_sha256,
            "spend": dict(self.spend),
            "audit": self.extraction.as_audit(),
            "inference_conditional_on": "parseable responses only",
            "pooling": "per-model, non-pooled: model x probe cells are never pooled as "
                       "independent observations",
        }
        if self.estimands is None:
            body["estimands"] = None
            body["protective_mass"] = None
            body["diagnostics"] = None
            body["no_headline_reason"] = (
                "R-V7-3 completeness gate failed; no headline estimand is emitted: "
                + "; ".join(self.completeness.failures))
            return body
        record = self.estimands.as_record()
        body["estimands"] = {
            "contrasts": record["contrasts"],
            "replicates": record["replicates"],
            "seed": record["seed"],
            "percentiles": record["percentiles"],
            "probe_ids": record["probe_ids"],
            "bootstrap": "C4 nested percentile bootstrap: probes resampled with pairing "
                         "preserved, then the observed number of valid draws resampled with "
                         "replacement within each probe-cell-order coordinate",
        }
        body["valid_draw_counts"] = record["valid_draw_counts"]
        body["protective_mass"] = {c: {p: self.protective_mass[c][p]
                                       for p in sorted(self.protective_mass[c])}
                                   for c in sorted(self.protective_mass)}
        body["diagnostics"] = self.diagnostics
        return body


def parse_reply(text: Optional[str], n_options: int = N_OPTIONS) -> "ID.ParseResult":
    """The module's ONE parse seam: the frozen S-F4 anchored leading-option parser.

    Re-exported (not reimplemented) so every caller — and every conformance check — reads the
    same fail-closed rule: an anchored single digit in `[1, n_options]`, nothing else. `""`,
    `"I choose 3"`, `"34"`, `"0"`, `"5"` and `"-1"` all yield `option=None`/`index=None`.
    """
    return ID.parse_option(text, n_options)


def extract_headline(draws: Sequence[SamplingDraw], items: Mapping[str, Mapping], *,
                     expected_probe_ids: Sequence[str], model: Optional[str] = None,
                     replicates: int = BOOTSTRAP_REPLICATES,
                     seed: int = BOOTSTRAP_SEED) -> NestedBootstrapResult:
    """Gate then estimate ONE model's draws: the R-V7-3 completeness gate runs first and an
    incomplete model raises `IncompleteModel` instead of emitting a headline.

    `model` is a label only — it is what makes the contract expressible: this function is
    called once per model over that model's own draws, and model x probe cells are never
    pooled as independent observations. Two models' draws concatenated fail the gate as
    duplicate coordinates rather than being silently pooled.
    """
    rows = list(draws)
    report = completeness_gate(rows, expected_probe_ids=tuple(expected_probe_ids))
    if not report.complete:
        raise IncompleteModel(
            f"model {model!r}: full-run completeness gate failed; no headline estimand is "
            "emitted: " + "; ".join(report.failures))
    return nested_bootstrap(rows, items, completeness=report, replicates=replicates, seed=seed)


#: Mirrors `interlock.INTERLOCK_DIRNAME` (kept as a literal because the interlock module is
#: imported lazily below); `tests/test_q2_v7_study_extract.py` pins the two together.
IL_DIRNAME = "interlock"

#: `study_run` puts the study envelopes in `<run_dir>/study/` (and the retried attempts in
#: `<run_dir>/study_attempts/`), while the authorization records live in `<run_dir>/interlock/`.
#: An `EnvelopeStore` therefore reports a run_dir one level BELOW the run. These are the only
#: sub-directory names from which the interlock lookup steps up.
_STORE_SUBDIRS: tuple[str, ...] = ("study", "study_attempts", "walk")


def interlock_run_dir(run_dir: Path | str) -> Path:
    """The directory whose `interlock/` holds this run's authorization records.

    Usually `run_dir` itself. When `run_dir` is an `EnvelopeStore` directory of the frozen
    runner layout (`<run>/study`), the records are one level up, so this steps up — and only
    then, and only when the parent actually has an `interlock/` directory. Stepping up cannot
    weaken anything: the records found there are still required to bind this model and this
    run's recomputed manifest digest before a headline is permitted.
    """
    run_dir = Path(run_dir)
    if ((run_dir / IL_DIRNAME).is_dir()
            or run_dir.name not in _STORE_SUBDIRS
            or not (run_dir.parent / IL_DIRNAME).is_dir()):
        return run_dir
    return run_dir.parent


def require_headline_permitted(run_dir: Path | str,
                               manifest_sha256: Optional[str] = None,
                               model: Optional[str] = None) -> Any:
    """The frozen outcome-blinding interlock, enforced at the ONE place a substantive outcome
    is first computed.

    Headline aggregation refuses to run until BOTH authorization decisions exist for this run:
    (a) the deterministic endpoint-promotion decision for THIS model and (b) the funding
    decision, each bound to this run's recomputed manifest digest. The records are the very
    ones `study_run` wrote to authorize the paid draws — no second, weaker operator decision
    is minted here, so nothing can diverge from what actually paid. They live in, and are
    validated by, `alignment.q2_v7.interlock`; this module only refuses to aggregate without
    them.

    `model` selects that model's per-model PS-1 promotion record and its row of the panel
    funding record. Omitting it is only unambiguous for a single-model run directory.
    """
    try:
        from alignment.q2_v7 import interlock as IL
    except Exception as exc:                      # pragma: no cover - defensive
        raise HeadlineBlocked(
            f"the promotion/funding interlock module is unavailable ({exc}); refusing to "
            f"aggregate a substantive outcome without it") from exc
    resolved = interlock_run_dir(run_dir)
    state = IL.interlock_state(resolved, manifest_sha256, model)
    if not getattr(state, "headline_permitted", False):
        raise HeadlineBlocked(
            f"headline aggregation refuses to run: missing interlock records "
            f"{list(getattr(state, 'missing', ('promotion', 'funding')))}"
            + (f"; binding failures {list(state.binding_failures)}"
               if getattr(state, "binding_failures", ()) else ""))
    return state


def _load_items(items: Optional[Mapping[str, Mapping]],
                probe_ids: Sequence[str]) -> Mapping[str, Mapping]:
    if items is None:
        from alignment.q2_hosted import load_probe_items      # local file read, no network
        items = load_probe_items()
    missing = [p for p in probe_ids if p not in items]
    if missing:
        raise ExtractionError(f"item bank is missing probes {missing}")
    return items


def observed_protective_mass(records: Sequence[DrawRecord],
                             items: Mapping[str, Mapping]) -> dict:
    """`mass[cell_id][probe_id]` via the FROZEN order-balanced sampling aggregation
    (`alignment.q2_hosted.aggregate_sampling_mass`): display positions are remapped through
    each Williams order, per-order frequencies are normalised, then averaged over the four
    orders. Excluded and unparseable draws carry `choice=None` and are dropped, never guessed.
    """
    rows = [{"path": "sampling", "cell_id": r.cell_id, "probe_id": r.probe_id,
             "order_idx": r.order_idx, "choice": r.choice}
            for r in records]
    return aggregate_sampling_mass(rows, items)


def extract_model(store: "LG.EnvelopeStore", *, probe_ids: Sequence[str], model: str,
                  items: Optional[Mapping[str, Mapping]] = None,
                  manifest: Any = None,
                  reconciliation: Optional["LG.ReconciliationResult"] = None,
                  endpoint_snapshot_sha256: Optional[str] = None,
                  require_interlock: bool = True,
                  replicates: int = BOOTSTRAP_REPLICATES,
                  seed: int = BOOTSTRAP_SEED) -> ModelResult:
    """Extract one model's frozen result from its persisted raw envelopes.

    The R-V7-3 completeness gate runs FIRST and is decisive: exactly 11 cells, 12 probes, four
    unique orders, 25 attempted draws per order, no duplicate or unexpected coordinates,
    >= 20/25 parseable in every order and >= 0.95 parseable overall. If any rule fails, the
    returned `ModelResult` names the failures and carries NO estimand, NO protective mass and
    NO diagnostic. Only a passing model reaches the outcome-blinding interlock, the C4 nested
    bootstrap and the eight frozen per-model, non-pooled contrasts.

    `require_interlock` (default True) enforces the frozen interlock: a complete model still
    aggregates nothing until the promotion and funding records exist for `store.run_dir`.
    """
    probes = tuple(probe_ids)
    extraction = _extract_or_empty(store, probe_ids=probes, model=model, manifest=manifest)
    spend = reconcile_spend(extraction, store, reconciliation=reconciliation)
    snapshot_sha = endpoint_snapshot_sha256 or ENV.SNAPSHOT_SHA256

    report = completeness_gate(list(extraction.draws), expected_probe_ids=probes)
    if not report.complete:
        return ModelResult(
            model=model, complete=False, completeness=report, extraction=extraction,
            spend=spend, promoted_endpoint=extraction.provider,
            endpoint_snapshot_sha256=snapshot_sha,
            manifest_sha256=extraction.manifest_sha256,
            estimands=None, protective_mass=None, diagnostics=None)

    if require_interlock:
        require_headline_permitted(store.run_dir, extraction.manifest_sha256, model)
    bank = _load_items(items, probes)
    boot = nested_bootstrap(list(extraction.draws), bank, completeness=report,
                            replicates=replicates, seed=seed)
    mass = observed_protective_mass(extraction.records, bank)
    diagnostics = crack_diagnostics(mass, boot.contrasts)
    return ModelResult(
        model=model, complete=True, completeness=report, extraction=extraction, spend=spend,
        promoted_endpoint=extraction.provider, endpoint_snapshot_sha256=snapshot_sha,
        manifest_sha256=extraction.manifest_sha256, estimands=boot,
        protective_mass=mass, diagnostics=diagnostics)


# =======================================================================================
# Deterministic artifact
# =======================================================================================

def artifact_bytes(result: ModelResult) -> bytes:
    """The canonical serialization of the artifact — sorted keys, no whitespace, ASCII."""
    return ID.canonical_bytes(result.as_artifact())


def write_artifact(result: ModelResult, path: Path | str) -> str:
    """Write the deterministic JSON artifact atomically and return its SHA-256.

    The artifact regenerates every reported number: per-cell protective mass, the eight
    contrasts with their percentile intervals, the observed valid draw counts per coordinate,
    the parse rates, the promoted endpoint and its snapshot hash, the manifest hash, and the
    reconciled spend. It carries no timestamp, no path, and no iteration-order-dependent
    value, so regenerating it from the same raw envelopes is byte-identical.

    An existing artifact with DIFFERENT bytes is a conflict and raises: a published number is
    evidence, not a draft. Rewriting the identical bytes is a no-op.
    """
    body = artifact_bytes(result)
    path = Path(path)
    if path.exists():
        if path.read_bytes() == body:
            return ID.canonical_sha256(result.as_artifact())
        raise ExtractionError(
            f"artifact {path} exists with different content — refusing to overwrite a "
            f"reported result")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(body)
    try:
        os.replace(tmp, path)                    # atomic on POSIX
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return ID.canonical_sha256(result.as_artifact())


__all__ = [
    "ARTIFACT_SCHEMA", "IL_DIRNAME", "MANIFEST_FILENAME", "STUDY_STAGES",
    "CoordinateIndex", "DrawExtraction", "DrawRecord", "ExtractionError", "HeadlineBlocked",
    "ModelResult", "artifact_bytes", "coordinate_index", "crack_diagnostics",
    "extract_draws", "extract_headline", "extract_model", "interlock_run_dir", "load_draws",
    "observed_protective_mass", "parse_reply", "reconcile_spend",
    "require_headline_permitted", "write_artifact",
]
