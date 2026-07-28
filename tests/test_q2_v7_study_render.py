"""No-network tests for the Q2 Stage-2 v7.2 study-grid renderer (`alignment.q2_v7.study_render`).

Nothing here contacts a network, downloads a tokenizer, or reads an API key: the module under
test is pure and reads only the locally frozen item bank. The suite asserts the two properties
that make the frozen design payable —

* the grid is EXACTLY 528 unique coordinates with 528 distinct request hashes, and
* the 48 smoke requests are byte-identical (by hash) to their twins inside those 528, which is
  what lets the 240 smoke draws be reused as the first five of 25 rather than repaid —

plus the frozen envelope on every body and the inheritance of all prompt text from the frozen
local design (asserted against `q2_hosted.build_call_request`, never against a literal string).
"""
from __future__ import annotations

import pytest

from alignment.instrument import measure as M
from alignment.q1_channel import GUARD_TEXT, WILLIAMS_ORDERS_4
from alignment.q2_hosted import (SMOKE_PROBES, CallSpec, build_call_request, cid_for,
                                 load_probe_items)
from alignment.q2_v7 import study_render as SR
from alignment.q2_v7.envelope import REASONING_OFF
from alignment.q2_v7.gate import SpecViolation

MODEL = "qwen/qwen3.5-397b-a17b"
TAG = "alibaba"


@pytest.fixture(scope="module")
def probes() -> list[str]:
    return SR.probe_ids_for()


@pytest.fixture(scope="module")
def grid(probes) -> list[SR.StudyRequest]:
    return SR.render_study_grid(MODEL, TAG, probes)


@pytest.fixture(scope="module")
def smoke(probes) -> list[SR.StudyRequest]:
    return SR.render_smoke_grid(MODEL, TAG, probes)


@pytest.fixture(scope="module")
def items() -> dict:
    return load_probe_items()


def _user(req: SR.StudyRequest) -> str:
    return next(m["content"] for m in req.body["messages"] if m["role"] == "user")


def _system(req: SR.StudyRequest) -> str:
    return next(m["content"] for m in req.body["messages"] if m["role"] == "system")


def _pick(reqs, cell_id, probe_id="pol_ai_due_process", order_idx=0) -> SR.StudyRequest:
    return next(r for r in reqs
                if r.coordinate == (cell_id, probe_id, order_idx))


# =======================================================================================
# Counts and identity
# =======================================================================================

def test_probe_ids_for_returns_the_twelve_frozen_probes(probes):
    assert len(probes) == 12
    assert len(set(probes)) == 12
    assert set(SMOKE_PROBES) <= set(probes)
    assert {"pol_ai_due_process", "pol_surveillance"} <= set(probes)


def test_study_grid_is_exactly_528_unique_coordinates(grid):
    assert len(grid) == 528 == 11 * 12 * 4
    assert len({r.coordinate for r in grid}) == 528
    assert len({r.cell_id for r in grid}) == 11
    assert len({r.probe_id for r in grid}) == 12
    assert {r.order_idx for r in grid} == set(range(4)) == set(range(len(WILLIAMS_ORDERS_4)))


def test_study_grid_hashes_are_unique(grid):
    assert len({r.request_sha256 for r in grid}) == 528


def test_smoke_grid_is_exactly_48_unique_coordinates(smoke):
    assert len(smoke) == 48 == 6 * 2 * 4
    assert len({r.coordinate for r in smoke}) == 48
    assert len({r.request_sha256 for r in smoke}) == 48
    assert {r.probe_id for r in smoke} == set(SMOKE_PROBES)
    assert len({r.cell_id for r in smoke}) == 6


def test_smoke_hashes_are_a_subset_of_the_full_grid_hashes(grid, smoke):
    """R-V7-7 smoke reuse is only sound if the smoke request is the SAME request."""
    grid_hashes = {r.request_sha256 for r in grid}
    smoke_hashes = {r.request_sha256 for r in smoke}
    assert smoke_hashes <= grid_hashes
    assert len(smoke_hashes) == 48


def test_smoke_requests_are_byte_identical_to_their_grid_twins(grid, smoke):
    by_coord = {r.coordinate: r for r in grid}
    for s in smoke:
        twin = by_coord[s.coordinate]
        assert s.body == twin.body
        assert s.request_sha256 == twin.request_sha256
        assert s.rendered.payload_text == twin.rendered.payload_text


def test_rendered_carries_coordinate_hash_and_template_overhead(grid):
    for r in grid[:24]:
        assert r.rendered.coordinate == r.coordinate
        assert r.rendered.request_sha256 == r.request_sha256
        assert r.rendered.template_overhead_tokens > 0      # R-C4 overhead is carried
        assert r.rendered.payload_text


# =======================================================================================
# Frozen envelope on every body
# =======================================================================================

def test_every_body_carries_the_frozen_envelope(grid):
    for r in grid:
        b = r.body
        assert b["model"] == MODEL
        assert b["temperature"] == 1.0
        assert b["top_p"] == 1.0
        assert b["max_tokens"] == 4
        assert b["reasoning"] == {"effort": "none"} == REASONING_OFF
        assert "seed" not in b                      # independent draws: absent, not null
        assert "logprobs" not in b and "top_logprobs" not in b
        assert "stop" not in b
        assert b["provider"] == {"only": [TAG], "allow_fallbacks": False,
                                 "require_parameters": True}
        assert b["usage"] == {"include": True}
        assert [m["role"] for m in b["messages"]] == ["system", "user"]


def test_smoke_bodies_carry_the_same_frozen_envelope(smoke):
    for r in smoke:
        assert "seed" not in r.body
        assert r.body["max_tokens"] == 4
        assert r.body["reasoning"] == {"effort": "none"}
        assert r.body["provider"]["only"] == [TAG]


# =======================================================================================
# Prompt text is INHERITED, never restated
# =======================================================================================

def test_prompt_text_is_inherited_from_the_frozen_builder(grid, items):
    """Compare against `q2_hosted.build_call_request`, not against a hardcoded string."""
    checked = 0
    for r in grid:
        if r.probe_id != "pol_surveillance" or r.order_idx != 2:
            continue
        spec = CallSpec(model=MODEL, provider=TAG, path="sampling", cell_id=r.cell_id,
                        probe_id=r.probe_id, order_idx=r.order_idx)
        frozen = build_call_request(spec, items[r.probe_id])
        assert r.body["messages"] == frozen["messages"]
        checked += 1
    assert checked == 11


def test_system_text_is_the_frozen_survey_system(grid):
    unguarded = _pick(grid, cid_for("data_only", "no_guard"))
    assert _system(unguarded) == M.SURVEY_SYSTEM


# =======================================================================================
# Guard placement
# =======================================================================================

def test_system_guard_cell_puts_the_guard_in_the_system_role(grid):
    r = _pick(grid, cid_for("data_only", "system_guard"))
    assert GUARD_TEXT in _system(r)
    assert GUARD_TEXT not in _user(r)
    assert _system(r).startswith(M.SURVEY_SYSTEM)


def test_user_before_and_user_after_differ_from_each_other_and_from_no_guard(grid):
    before = _pick(grid, cid_for("data_only", "user_before"))
    after = _pick(grid, cid_for("data_only", "user_after"))
    none = _pick(grid, cid_for("data_only", "no_guard"))

    assert GUARD_TEXT in _user(before) and GUARD_TEXT in _user(after)
    assert GUARD_TEXT not in _user(none)
    # the guard leads in user_before and trails in user_after
    assert _user(before).startswith(GUARD_TEXT)
    assert not _user(after).startswith(GUARD_TEXT)

    texts = {_user(before), _user(after), _user(none)}
    assert len(texts) == 3
    hashes = {before.request_sha256, after.request_sha256, none.request_sha256}
    assert len(hashes) == 3
    # the guard lives in the user turn for all three, never in the system turn
    for r in (before, after, none):
        assert _system(r) == M.SURVEY_SYSTEM


def test_combined_guard_arms_are_also_three_distinct_cells(grid):
    arms = [cid_for("combined", a) for a in ("no_guard", "user_before", "user_after",
                                             "system_guard")]
    reqs = [_pick(grid, cid) for cid in arms]
    assert len({r.request_sha256 for r in reqs}) == 4


# =======================================================================================
# Williams order
# =======================================================================================

def test_order_index_changes_the_displayed_option_order_and_the_hash(grid, items):
    cell = cid_for("baseline", "no_guard")
    probe = "pol_ai_due_process"
    labels = items[probe]["scale"]["labels"]

    seen_hashes = set()
    for oi in range(4):
        r = _pick(grid, cell, probe, oi)
        seen_hashes.add(r.request_sha256)
        user = _user(r)
        expected = [labels[c] for c in WILLIAMS_ORDERS_4[oi]]
        positions = [user.index(f"  {i + 1}. {lab}") for i, lab in enumerate(expected)]
        assert positions == sorted(positions)          # displayed in the frozen order
    assert len(seen_hashes) == 4


def test_all_four_frozen_orders_are_present_for_every_cell_probe(grid):
    by_cell_probe: dict = {}
    for r in grid:
        by_cell_probe.setdefault((r.cell_id, r.probe_id), set()).add(r.order_idx)
    assert len(by_cell_probe) == 11 * 12
    assert all(v == {0, 1, 2, 3} for v in by_cell_probe.values())


# =======================================================================================
# Fail-closed behaviour
# =======================================================================================

def test_probe_list_of_the_wrong_size_is_refused(probes):
    with pytest.raises(SpecViolation):
        SR.render_study_grid(MODEL, TAG, probes[:11])
    with pytest.raises(SpecViolation):
        SR.render_smoke_grid(MODEL, TAG, probes[:11])


def test_duplicate_probe_is_refused(probes):
    dup = list(probes[:11]) + [probes[0]]
    with pytest.raises(SpecViolation):
        SR.render_study_grid(MODEL, TAG, dup)


def test_probe_set_missing_a_smoke_probe_is_refused(probes):
    swapped = [p for p in probes if p != "pol_surveillance"] + ["pol_not_a_real_probe"]
    with pytest.raises(SpecViolation):
        SR.render_study_grid(MODEL, TAG, swapped)


def test_unknown_probe_id_is_refused(probes):
    swapped = [p for p in probes[:11]] + ["pol_not_a_real_probe"]
    with pytest.raises(SpecViolation):
        SR.render_study_grid(MODEL, TAG, swapped)


def test_empty_model_or_tag_is_refused(probes):
    with pytest.raises(SpecViolation):
        SR.render_study_grid("", TAG, probes)
    with pytest.raises(SpecViolation):
        SR.render_study_grid(MODEL, "  ", probes)
    with pytest.raises(SpecViolation):
        SR.render_smoke_grid(MODEL, "", probes)


def test_a_bare_string_is_not_a_probe_sequence():
    with pytest.raises(SpecViolation):
        SR.render_study_grid(MODEL, TAG, "pol_ai_due_process")


def test_grid_check_rejects_a_short_or_colliding_grid(grid):
    with pytest.raises(SpecViolation):
        SR._check_grid(grid[:-1], 528, "the full study grid")
    with pytest.raises(SpecViolation):
        SR._check_grid(list(grid[:-1]) + [grid[0]], 528, "the full study grid")


# =======================================================================================
# Cross-model / cross-tag identity
# =======================================================================================

def test_the_tag_and_model_are_part_of_the_request_identity(probes, grid):
    other = SR.render_study_grid(MODEL, "digitalocean", probes)
    assert not ({r.request_sha256 for r in other} & {r.request_sha256 for r in grid})
    # ...but the prompts themselves are identical across endpoints
    assert [_user(a) for a in other[:12]] == [_user(b) for b in grid[:12]]


def test_grid_is_deterministic(probes, grid):
    again = SR.render_study_grid(MODEL, TAG, probes)
    assert [r.request_sha256 for r in again] == [r.request_sha256 for r in grid]
    assert [r.coordinate for r in again] == [r.coordinate for r in grid]
