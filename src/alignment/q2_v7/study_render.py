"""Q2 Stage-2 v7.2 study-grid renderer — frozen by `paper/Q2_STAGE2_HOSTED_DESIGN.md`.

Renders the 528 unique cell-probe-order request bodies of one model's complete v7.2 design,
and the 48-coordinate outcome-blinded smoke subset, as EXACT frozen-envelope sampling bodies.

Two invariants make this module worth existing separately from the enumerators in
`alignment.q2_hosted`:

1. **Nothing here writes a prompt.** Payload texts, the single guard text, its three
   placements (`user_before` / `user_after` / `system_guard`), the probe item bank, the four
   Williams display orders and the display-to-canonical remap are inherited VERBATIM from the
   frozen local design through `q2_hosted.build_call_request` -> `q1_channel.cell_spec` /
   `instrument.measure.forced_choice_prompt`. This module takes the messages that machinery
   produces and re-wraps them in the v7 envelope; it never restates or rewords a prompt. The
   hosted runner differs from the local design ONLY in the provider's chat-role mechanics and
   the routing/inference envelope.

2. **The 48 smoke requests are byte-identical to their twins inside the 528.** Smoke reuse
   (R-V7-7: the 240 smoke draws ARE the first five of the 25 draws for 48 of the 528
   coordinates, never repaid and never statistically deduplicated) is only sound if the smoke
   request hashes to exactly the same value as its full-grid twin. Because both grids route
   through the same `_render_one`, and neither the smoke/full-stage label nor the draw index
   enters the request body, that identity holds by construction — and
   `tests/test_q2_v7_study_render.py` asserts it by hash.

Every body is produced by `envelope.build_sampling_request`, so each carries the frozen v7
envelope exactly: temperature 1.0, top_p 1.0, max_tokens 4, `reasoning:{"effort":"none"}`,
NO `seed` key, `provider.only=[tag]` with `allow_fallbacks:false` / `require_parameters:true`,
and `usage:{"include":true}`. Every request is also wrapped as a `gate.RenderedRequest` so the
R-C4 chat-template overhead is carried into the C2 full-grid cost projection.

NETWORK: none. This module is pure: it reads the local frozen item bank and returns data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from alignment.q2_hosted import (HOSTED_CELLS, SMOKE_CELLS, SMOKE_PROBES, CallSpec,
                                 build_call_request, cid_for, load_probe_items)
from alignment.q2_v7.envelope import build_sampling_request, canonical_request_sha256
from alignment.q2_v7.gate import (CELL_IDS, N_CELLS_REQUIRED, N_COORDINATES,
                                  N_ORDERS_REQUIRED, N_PROBES_REQUIRED, RenderedRequest,
                                  SpecViolation, render_request)

#: The frozen smoke cell ids, derived from the frozen `(payload_key, guard_arm)` pairs. A
#: subset of `CELL_IDS` by construction; asserted below so a future edit to either tuple that
#: broke the subset relation would fail at import rather than at spend time.
SMOKE_CELL_IDS: tuple[str, ...] = tuple(cid_for(pk, ga) for pk, ga in SMOKE_CELLS)

#: 6 frozen smoke cells x 2 frozen smoke probes x 4 Williams orders = 48 coordinates.
N_SMOKE_COORDINATES = len(SMOKE_CELL_IDS) * len(SMOKE_PROBES) * N_ORDERS_REQUIRED

#: The sampling path is the only v7 path (the logprob path is retired by the v6/v7 amendments).
PATH = "sampling"

if set(SMOKE_CELL_IDS) - set(CELL_IDS):        # pragma: no cover - structural guard
    raise SpecViolation("the frozen smoke cells are not a subset of the frozen 11 cells")


# =======================================================================================
# The rendered unit
# =======================================================================================

@dataclass(frozen=True)
class StudyRequest:
    """One of the 528 unique cell-probe-order coordinates of a model's complete design.

    `body` is the exact frozen v7 sampling request body as sent (no draw index: 25 independent
    draws share one body and are distinguished only by the immutable draw index of R-V7-7's
    draw identity). `rendered` is the `gate.RenderedRequest` view the C2 cost projection
    consumes, carrying the R-C4 chat-template overhead.
    """
    cell_id: str
    probe_id: str
    order_idx: int
    body: dict
    request_sha256: str
    rendered: RenderedRequest

    @property
    def coordinate(self) -> tuple[str, str, int]:
        return (self.cell_id, self.probe_id, self.order_idx)


# =======================================================================================
# Validation helpers — every one fails closed
# =======================================================================================

def _require_slug(value: str, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecViolation(f"{what} must be a non-empty string")
    return value


def _validated_probe_ids(probe_ids: Sequence[str]) -> tuple[str, ...]:
    """The frozen probe requirement: exactly 12, unique, and including both smoke probes.

    The complete design is 11 cells x 12 probes x 4 orders; R-V7-3 refuses a headline from any
    run that is not exactly that. Enforcing the shape at render time means an under-specified
    probe list can never become a paid grid.
    """
    if isinstance(probe_ids, (str, bytes)):
        raise SpecViolation("probe_ids must be a sequence of probe ids, not a string")
    ids = tuple(probe_ids)
    for p in ids:
        _require_slug(p, "probe id")
    if len(ids) != N_PROBES_REQUIRED:
        raise SpecViolation(
            f"the frozen design requires exactly {N_PROBES_REQUIRED} probes, got {len(ids)}")
    if len(set(ids)) != len(ids):
        raise SpecViolation("duplicate probe id in the requested grid")
    missing = [p for p in SMOKE_PROBES if p not in ids]
    if missing:
        raise SpecViolation(f"probe set is missing the frozen smoke probes {missing}")
    return ids


def _items_for(probe_ids: Sequence[str], primary: str = "ENG") -> dict:
    """The frozen item bank restricted to the requested probes, failing closed on any id the
    bank does not contain (a typo'd probe must never be silently dropped from the grid)."""
    bank = load_probe_items(primary)
    unknown = [p for p in probe_ids if p not in bank]
    if unknown:
        raise SpecViolation(f"probe ids absent from the frozen item bank: {unknown}")
    return {p: bank[p] for p in probe_ids}


def _check_grid(requests: Sequence[StudyRequest], expected: int, what: str) -> None:
    """Count / coordinate-uniqueness / hash-uniqueness gate on a finished grid."""
    if len(requests) != expected:
        raise SpecViolation(f"{what} must contain exactly {expected} requests, got {len(requests)}")
    coords = {r.coordinate for r in requests}
    if len(coords) != expected:
        raise SpecViolation(f"{what} contains duplicate cell-probe-order coordinates")
    hashes = {r.request_sha256 for r in requests}
    if len(hashes) != expected:
        raise SpecViolation(f"{what} contains duplicate request hashes: "
                            f"{expected - len(hashes)} collision(s)")


# =======================================================================================
# Rendering
# =======================================================================================

def _render_one(model: str, tag: str, cell_id: str, probe_id: str, order_idx: int,
                item: Mapping) -> StudyRequest:
    """Render ONE coordinate.

    The prompt is not built here. `q2_hosted.build_call_request` maps the cell id to
    (system, user) through the frozen `q1_channel.cell_spec` conditioning — which is what puts
    the guard text before the payload (`user_before`), after it (`user_after`), or in the
    system message (`system_guard`) — and lays the four options out in the requested Williams
    display order. Only those messages are lifted out; the v7 envelope is applied on top.
    """
    spec = CallSpec(model=model, provider=tag, path=PATH, cell_id=cell_id,
                    probe_id=probe_id, order_idx=order_idx)
    frozen_messages = build_call_request(spec, item)["messages"]
    body = build_sampling_request(model, tag, frozen_messages)
    return StudyRequest(
        cell_id=cell_id,
        probe_id=probe_id,
        order_idx=order_idx,
        body=body,
        request_sha256=canonical_request_sha256(body),
        rendered=render_request(cell_id, probe_id, order_idx, body),
    )


def _render(model: str, tag: str, cell_ids: Sequence[str], probe_ids: Sequence[str],
            items: Mapping[str, Mapping]) -> list[StudyRequest]:
    return [_render_one(model, tag, cid, pid, oi, items[pid])
            for cid in cell_ids
            for pid in probe_ids
            for oi in range(N_ORDERS_REQUIRED)]


def render_study_grid(model: str, tag: str, probe_ids: Sequence[str]) -> list[StudyRequest]:
    """The complete frozen grid for one model: 11 cells x 12 probes x 4 orders = 528 unique
    requests, each of which is drawn 25 times in the full run (528 x 25 = 13,200).

    Deterministic order: cells in the frozen `HOSTED_CELLS` order, probes in the caller's
    order, then the four Williams orders. Fails closed on any count, coordinate, or hash
    deviation from the frozen design.
    """
    _require_slug(model, "model slug")
    _require_slug(tag, "provider tag")
    probes = _validated_probe_ids(probe_ids)
    if len(CELL_IDS) != N_CELLS_REQUIRED:      # pragma: no cover - structural guard
        raise SpecViolation(f"the frozen design requires exactly {N_CELLS_REQUIRED} cells")
    grid = _render(model, tag, CELL_IDS, probes, _items_for(probes))
    _check_grid(grid, N_COORDINATES, "the full study grid")
    return grid


def render_smoke_grid(model: str, tag: str, probe_ids: Sequence[str]) -> list[StudyRequest]:
    """The outcome-blinded smoke subset: 6 frozen smoke cells x the 2 frozen smoke probes x 4
    orders = 48 coordinates (240 draws at 5 per coordinate).

    Each returned request is byte-identical to its twin in `render_study_grid`, so the 240
    smoke draws are reusable as the first five of the coordinate's 25 draws — never repaid.
    `probe_ids` is validated against the same frozen 12-probe requirement so a smoke grid can
    never be rendered from a probe set whose full grid would be rejected; the smoke PROBES
    themselves are frozen (`SMOKE_PROBES`) and are not taken from the argument.
    """
    _require_slug(model, "model slug")
    _require_slug(tag, "provider tag")
    _validated_probe_ids(probe_ids)
    grid = _render(model, tag, SMOKE_CELL_IDS, SMOKE_PROBES, _items_for(SMOKE_PROBES))
    _check_grid(grid, N_SMOKE_COORDINATES, "the smoke grid")
    return grid


def probe_ids_for(primary: str = "ENG") -> list[str]:
    """The 12 frozen floor-probe ids, read from the frozen item bank and validated: exactly 12,
    unique, and containing both frozen smoke probes."""
    ids = list(load_probe_items(primary))
    return list(_validated_probe_ids(ids))
