"""ADVERSARIAL conformance tests for the Q2 Stage-2 v7.2 STUDY RUNNER.

Authored independently from the frozen written specification, NOT from the builders' code:

  * `paper/Q2_STAGE2_HOSTED_DESIGN.md` — v7 amendment, v7.1 revision (R-V7-1..R-V7-7),
    v7.2 closure (C1..C4), "Estimands", "Outcome-blinding interlock".
  * `paper/Q2_STAGE2_V72_CODE_REVIEW.md` — R-C1..R-C6 and the implementation-scope gap.
  * `paper/Q2_STAGE2_RUNNER_REVIEW.md` — R-E1..R-E7.
  * `paper/Q2_STAGE2_FRONTIER_DECISION.md` — S-F1..S-F6.

Every test names the frozen requirement it enforces. Modules still under construction are
`pytest.skip`ped with a message naming the missing spec requirement rather than crashing
collection, so this file is safe to run against a partially built runner.

NETWORK: none. Nothing here issues a request, and the fake transports assert that too.
"""
from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path

import numpy as np
import pytest

from alignment.q1_channel import WILLIAMS_ORDERS_4
from alignment import drift

# --------------------------------------------------------------------------------------
# Reviewed, green baseline modules — their CONTRACTS are what the new code must honour.
# --------------------------------------------------------------------------------------
envelope = pytest.importorskip("alignment.q2_v7.envelope")
identity = pytest.importorskip("alignment.q2_v7.identity")
ledger = pytest.importorskip("alignment.q2_v7.ledger")
gate = pytest.importorskip("alignment.q2_v7.gate")

ROOT = Path(__file__).resolve().parents[1]
V7_DIR = ROOT / "src" / "alignment" / "q2_v7"


# ======================================================================================
# Defensive import helpers — a missing symbol yields a SKIP naming the spec requirement
# ======================================================================================

def _module(name: str, requirement: str):
    """Import `alignment.q2_v7.<name>` or skip, naming the unmet frozen requirement."""
    try:
        return importlib.import_module(f"alignment.q2_v7.{name}")
    except Exception as exc:  # noqa: BLE001 - a broken module is a skip, not a crash here
        pytest.skip(f"alignment.q2_v7.{name} unavailable ({type(exc).__name__}: {exc}); "
                    f"NOT-YET-IMPLEMENTED: {requirement}")


def _attr(mod, names, requirement):
    """First present attribute among `names`, else skip naming the frozen requirement."""
    if isinstance(names, str):
        names = (names,)
    for n in names:
        if hasattr(mod, n):
            return getattr(mod, n)
    pytest.skip(f"{mod.__name__} exposes none of {list(names)}; "
                f"NOT-YET-IMPLEMENTED: {requirement}")


def _study_render():
    return _module("study_render", "render the 528 exact frozen request bodies (v7 'Call "
                                   "structure'; R-V7-2 renders and hashes all 528)")


def _study_run():
    return _module("study_run", "the integrated promotion-walk / projection / smoke / full-run "
                                "executor (V72_CODE_REVIEW 'Implementation-scope gap')")


def _study_extract():
    return _module("study_extract", "completeness gate -> nested bootstrap -> the eight "
                                    "estimands (R-V7-3, C4, design 'Estimands')")


def _interlock():
    return _module("interlock", "the promotion/funding outcome-blinding interlock "
                                "(design 'Outcome-blinding interlock', R-V7-7 honest blinding)")


# ======================================================================================
# Shared synthetic fixtures (no network, no item bank needed)
# ======================================================================================

CELL_IDS = tuple(gate.CELL_IDS)
PROBES = tuple(f"probe_{i:02d}" for i in range(12))
N_ORDERS = 4
ATTEMPTED = 25

#: Per-coordinate display-choice splits expressible in BOTH 25ths and 20ths, so a dataset
#: can be rebuilt at a different valid-draw count with IDENTICAL observed proportions.
_SPLITS_25 = ((15, 10), (10, 15), (20, 5), (5, 20))
_SPLITS_20 = ((12, 8), (8, 12), (16, 4), (4, 16))


def _items(n_options: int = 4, floor_dir: int = 1):
    return {p: {"scale": {"labels": [f"o{i}" for i in range(n_options)]},
                "floor_dir": floor_dir}
            for p in PROBES}


def _split_for(cell_idx: int, probe_idx: int, order_idx: int, valid: int):
    if valid == 25:
        table = _SPLITS_25
    elif valid == 20:
        table = _SPLITS_20
    else:                                   # generic split for the gate-failure fixtures
        n0 = (valid * 3) // 5
        return (n0, valid - n0)
    return table[(cell_idx + probe_idx + order_idx) % len(table)]


def _draws(valid_at=lambda c, p, o: 25, cells=CELL_IDS, probes=PROBES,
           choices_for=None):
    """A complete 528-coordinate x 25-attempted draw set.

    `valid_at(cell_id, probe_id, order_idx) -> int` fixes the number of PARSEABLE draws at a
    coordinate; the remainder are `choice=None` (fail-closed unparseable replies).
    """
    out = []
    for ci, cell in enumerate(cells):
        for pi, probe in enumerate(probes):
            for oi in range(N_ORDERS):
                valid = int(valid_at(cell, probe, oi))
                if choices_for is None:
                    n0, n1 = _split_for(ci, pi, oi, valid)
                    seq = [0] * n0 + [1] * n1
                else:
                    seq = list(choices_for(cell, probe, oi, valid))
                assert len(seq) == valid
                seq = seq + [None] * (ATTEMPTED - valid)
                for di, ch in enumerate(seq):
                    out.append(gate.SamplingDraw(cell, probe, oi, di, ch))
    return out


def _report(draws):
    return gate.completeness_gate(draws, expected_probe_ids=PROBES)


def _canon_counts(k: int, n: int = 25):
    """`k` of `n` draws on the PROTECTIVE (upper) canonical half, split evenly within halves."""
    lo = n - k
    return [lo - lo // 2, lo // 2, k - k // 2, k // 2]


def _canonical_choices(cell, probe, order_idx, valid):
    """Display positions realising a fixed CANONICAL preference for this probe.

    Necessary because the four Williams orders form a balanced Latin square: a display
    distribution that is identical across all four orders order-balances to a UNIFORM
    canonical distribution and therefore to protective mass exactly 0.5, whatever the display
    split. Only a canonical target produces genuine per-probe variation.
    """
    k = 2 + 2 * PROBES.index(probe)                        # 2, 4, ... 24 of 25
    counts = _canon_counts(k, valid)
    order_map = WILLIAMS_ORDERS_4[order_idx]
    seq = []
    for display in range(4):
        seq += [display] * counts[order_map[display]]
    return seq


# ======================================================================================
# AREA 1 — counts and reuse
# ======================================================================================

class TestCountsAndReuse:
    """Frozen: 528 coordinates, 13,200 draws/model, 240 smoke, 12,960 additional; the 240
    are INSIDE the 13,200 and are never added on top (R-V7-2, R-V7-7)."""

    def test_frozen_counts_are_exactly_the_design_arithmetic(self):
        s = identity.call_structure()
        assert s["coordinates_per_model"] == 528
        assert s["draws_per_coordinate"] == 25
        assert s["draws_per_model"] == 13_200
        assert s["smoke_coordinates"] == 48
        assert s["smoke_draws_total"] == 240
        assert s["additional_draws_after_smoke"] == 12_960

    def test_smoke_is_never_added_on_top_of_the_full_run(self):
        """R-V7-2: 'The 240 smoke draws are counted ONCE ... never added on top.'"""
        assert (identity.SMOKE_DRAWS_TOTAL
                + identity.ADDITIONAL_DRAWS_AFTER_SMOKE) == identity.DRAWS_PER_MODEL == 13_200
        assert identity.DRAWS_PER_MODEL != 13_200 + 240, "240 added on top of 13,200"
        assert gate.DRAWS_PER_MODEL == 13_200
        assert gate.ADDITIONAL_DRAWS_AFTER_SMOKE == 12_960

    def test_render_produces_exactly_528_unique_coordinates_and_hashes(self):
        sr = _study_render()
        probes = sr.probe_ids_for()
        grid = sr.render_study_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes)
        assert len(grid) == 528
        assert len({r.coordinate for r in grid}) == 528
        assert len({r.request_sha256 for r in grid}) == 528, \
            "two coordinates render to the same body — 528 distinct requests is frozen"

    def test_the_48_smoke_hashes_are_a_subset_of_the_528(self):
        """THE reuse claim. If the smoke renders even one byte differently, its 240 draws are
        silently REPAID and 'never repaid, never statistically deduplicated' is false."""
        sr = _study_render()
        probes = sr.probe_ids_for()
        full = sr.render_study_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes)
        smoke = sr.render_smoke_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes)
        assert len(smoke) == 48

        full_by_coord = {r.coordinate: r.request_sha256 for r in full}
        for r in smoke:
            assert r.coordinate in full_by_coord, \
                f"smoke coordinate {r.coordinate} is not one of the 528"
            assert r.request_sha256 == full_by_coord[r.coordinate], (
                f"smoke request for {r.coordinate} hashes differently from its full-grid twin "
                f"— the 240 smoke draws would be REPAID")
        assert {r.request_sha256 for r in smoke} <= {r.request_sha256 for r in full}

    def test_smoke_bodies_are_byte_identical_to_their_full_grid_twins(self):
        sr = _study_render()
        probes = sr.probe_ids_for()
        full = {r.coordinate: r.body
                for r in sr.render_study_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes)}
        for r in sr.render_smoke_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes):
            assert json.dumps(r.body, sort_keys=True) == json.dumps(full[r.coordinate],
                                                                    sort_keys=True)

    def test_smoke_draw_ids_are_the_first_five_of_the_twenty_five(self):
        """R-V7-7: smoke draws 0-4 ARE the first five of the coordinate's 25."""
        sha = "a" * 64
        full = identity.coordinate_draw_ids(sha)
        smoke = identity.smoke_draw_ids(sha)
        assert len(full) == 25 and len(smoke) == 5
        assert list(smoke) == list(full[:5])

    def test_smoke_and_full_grids_share_one_provider_tag_binding(self):
        """A smoke rendered against a different endpoint tag must NOT collide with the full
        grid — reuse across endpoints would silently mix providers (R-H7 consistency)."""
        sr = _study_render()
        probes = sr.probe_ids_for()
        a = sr.render_smoke_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes)
        b = sr.render_smoke_grid("qwen/qwen3.5-397b-a17b", "digitalocean", probes)
        assert {r.request_sha256 for r in a}.isdisjoint({r.request_sha256 for r in b})


# ======================================================================================
# AREA 2 — never repay a persisted draw; a persisted FAILURE stays failed (R-C1)
# ======================================================================================

class _CountingTransport:
    """A transport that must never be called for a persisted draw. It refuses to do IO."""

    def __init__(self, responder=None):
        self.calls = []
        self._responder = responder

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._responder is None:
            raise AssertionError("transport called for a draw that is already persisted — "
                                 "a paid draw was about to be REPAID")
        return self._responder(*args, **kwargs)

    # alias shapes a runner might use
    post = send = __call__


MODEL = "qwen/qwen3.5-397b-a17b"
TAG = "alibaba"


class _FakeRequest:
    """The `StudyRequestLike` shape study_run consumes: coordinate + body + request hash."""

    def __init__(self, cell_id="baseline::no_guard", probe_id="pol_ai_due_process",
                 order_idx=0, seed="x"):
        self.cell_id = cell_id
        self.probe_id = probe_id
        self.order_idx = order_idx
        self.body = envelope.build_sampling_request(
            MODEL, TAG, [{"role": "system", "content": f"s{seed}"},
                         {"role": "user", "content": f"u{seed}"}])
        self.request_sha256 = envelope.canonical_request_sha256(self.body)


def _req(**kw):
    return _FakeRequest(**kw)


def _wire_body(cost=0.0001, content="2"):
    body = {
        "id": "gen-1",
        "model": MODEL,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 53, "completion_tokens": 1, "total_tokens": 54,
                  "completion_tokens_details": {"reasoning_tokens": 0}},
        "openrouter_metadata": {"requested": MODEL, "strategy": "direct", "attempt": 1,
                                "is_byok": False,
                                "endpoints": {"available": [{"provider": "Alibaba",
                                                             "model": MODEL + "-20260216",
                                                             "selected": True}]}},
    }
    if cost is not None:
        body["usage"]["cost"] = cost
    return body


class _FakeTransport:
    def __init__(self, status=200, cost=0.0001, content="2"):
        self.calls = []
        self._status, self._cost, self._content = status, cost, content

    def post(self, body, headers, timeout=60.0):
        self.calls.append(dict(body))
        payload = _wire_body(cost=self._cost, content=self._content)
        if self._status != 200:
            payload["error"] = {"code": self._status, "message": "denied"}
            payload.pop("usage", None)
        return self._status, {}, json.dumps(payload)


class _NoCallTransport:
    """Any call here means a persisted draw was about to be REPAID."""

    calls: list = []

    def post(self, body, headers, timeout=60.0):
        raise AssertionError("transport called for an already-persisted draw — it would be "
                             "PAID FOR TWICE")


def _clock():
    t = [0.0]

    def tick():
        t[0] += 0.001
        return t[0]

    return tick


def _run_ledger(requests, prior=0.0, stop=8.50):
    """A ledger bound to exactly the identities the frozen manifest would authorise."""
    ids = [identity.draw_id(r.request_sha256, i) for r in requests for i in range(25)]
    manifest = ledger.RunManifest.from_draw_ids(ids, model=MODEL, endpoint=TAG)
    rec = ledger.ReconciliationResult(reconciled_usd=prior, record_count=0)
    return ledger.V7Ledger(reconciliation=rec, hard_stop_usd=stop, manifest=manifest)


def _persist(store, sha, idx, *, status, cost, stage="study"):
    draw = ledger.DrawIdentity(request_sha256=sha, draw_index=idx)
    body = {"id": f"gen-{idx}", "usage": {"cost": cost} if cost is not None else {},
            "choices": [{"message": {"content": "2"}}]}
    if status != 200:
        body["error"] = {"code": status, "message": "denied"}
    env = ledger.build_envelope(draw=draw, request_body={"model": "m"}, request_headers={},
                               response_body=body, response_headers={}, http_status=status,
                               bucket="study", model="m", provider="p", stage=stage)
    store.put(env)
    return env


class TestNeverRepayAndFailuresStayFailed:

    def test_restart_reconstructs_spend_rather_than_resetting_it(self, tmp_path):
        """R-C2/R-E3: current-run spend must not disappear on restart."""
        store = ledger.EnvelopeStore(tmp_path / "run")
        sha = "c" * 64
        for i in range(3):
            _persist(store, sha, i, status=200, cost=0.5)
        manifest = ledger.RunManifest.from_draw_ids(
            [ledger.DrawIdentity(sha, i).draw_id for i in range(25)])
        rebuilt = ledger.reconstruct_ledger(store, manifest=manifest)
        assert rebuilt.run_usd == pytest.approx(1.5), \
            "restart reset cumulative spend to zero (R-C2)"

    def test_a_persisted_failure_stays_failed(self, tmp_path):
        """R-C1: existence of a file must never be converted into an HTTP-200 success."""
        store = ledger.EnvelopeStore(tmp_path / "run")
        sha = "d" * 64
        _persist(store, sha, 0, status=404, cost=None)
        env = store.get(ledger.DrawIdentity(sha, 0).draw_id)
        assert env is not None
        assert env.http_status == 404, "the persisted status was not preserved"
        assert env.cost_usd in (None, 0.0)
        # The reuse decision must consult the loaded envelope, never `store.has(...)` alone.
        assert store.has(env.draw_id) and env.http_status != 200, (
            "store.has() is True for a FAILED draw; any reuse path keyed on existence alone "
            "reports a 404 as a passing 200 (R-C1)")

    def test_persisted_failure_without_cost_fails_closed_in_the_ledger(self, tmp_path):
        """R-C2.4/R-E2: a record with a missing cost stops for reconciliation; it is never
        skipped and never booked as free."""
        store = ledger.EnvelopeStore(tmp_path / "run")
        sha = "e" * 64
        draw = ledger.DrawIdentity(sha, 0)
        body = {"id": "gen-x", "choices": [{"message": {"content": "2"}}]}  # 200, no usage/cost
        env = ledger.build_envelope(draw=draw, request_body={}, request_headers={},
                                    response_body=body, response_headers={}, http_status=200,
                                    bucket="study", model="m", provider="p", stage="study")
        store.put(env)
        manifest = ledger.RunManifest.from_draw_ids([draw.draw_id])
        with pytest.raises(ledger.CostAccountingError):
            ledger.reconstruct_ledger(store, manifest=manifest)

    # -- end-to-end through the real study_run executor --------------------------------

    def test_execute_plan_does_not_repay_a_persisted_draw(self, tmp_path):
        """THE money test. `execute_plan` must look a draw up under the SAME identity
        `_send_draw` persisted it with. Restart, and the 240-draw smoke reuse, both depend on
        it (R-V7-7, R-E3, spec gate 4)."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        lg = _run_ledger([req])
        plan = [(req, i) for i in range(3)]

        t1 = _FakeTransport()
        run1 = sr.execute_plan(plan=plan, model=MODEL, tag=TAG, key="sk-test", store=store,
                               ledger=lg, transport=t1, worst_case_usd=lambda sha: 0.0001,
                               stage="study", bucket="study",
                               sleep=lambda s: None, clock=_clock())
        assert run1.n_sent == 3 and len(t1.calls) == 3

        t2 = _NoCallTransport()
        run2 = sr.execute_plan(plan=plan, model=MODEL, tag=TAG, key="sk-test", store=store,
                               ledger=_run_ledger([req]), transport=t2,
                               worst_case_usd=lambda sha: 0.0001, stage="study",
                               bucket="study", sleep=lambda s: None, clock=_clock())
        assert t2.calls == [], "a persisted draw was RE-SENT and therefore REPAID"
        assert run2.n_reused == 3 and run2.n_sent == 0

    def test_the_smoke_draws_are_replayed_by_the_full_run(self, tmp_path):
        """R-V7-7: the 240 smoke draws are the first five of the 25 and are 'never repaid'."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        lg = _run_ledger([req])
        smoke_plan = [(req, i) for i in range(5)]
        full_plan = [(req, i) for i in range(25)]

        sr.execute_plan(plan=smoke_plan, model=MODEL, tag=TAG, key="k", store=store,
                        ledger=lg, transport=_FakeTransport(),
                        worst_case_usd=lambda sha: 0.0001, stage="smoke", bucket="smoke",
                        sleep=lambda s: None, clock=_clock())
        t = _FakeTransport()
        run = sr.execute_plan(plan=full_plan, model=MODEL, tag=TAG, key="k", store=store,
                              ledger=_run_ledger([req]), transport=t,
                              worst_case_usd=lambda sha: 0.0001, stage="study",
                              bucket="study", sleep=lambda s: None, clock=_clock())
        assert run.n_reused == 5, (
            f"only {run.n_reused} of the 5 smoke draws were replayed — the rest were REPAID")
        assert run.n_sent == 20 and len(t.calls) == 20

    def test_the_manifest_binds_the_identity_the_runner_persists(self, tmp_path):
        """Root cause of any reuse/accounting break: the manifest and the envelope store must
        agree on ONE draw-identity spelling, or nothing is bound, booked, or reused."""
        sr = _study_run()
        req = _req()
        manifest_ids = set(sr.plan_full_draws([_req(seed=f"g{i}", probe_id=f"p{i}")
                                               for i in range(528)]) and
                           [identity.draw_id(req.request_sha256, i) for i in range(25)])
        store = ledger.EnvelopeStore(tmp_path / "study")
        sr.execute_plan(plan=[(req, 3)], model=MODEL, tag=TAG, key="k", store=store,
                        ledger=_run_ledger([req]), transport=_FakeTransport(),
                        worst_case_usd=lambda sha: 0.0001, stage="study", bucket="study",
                        sleep=lambda s: None, clock=_clock())
        for env in store.envelopes():
            assert env.draw_id in manifest_ids, (
                f"the runner persisted {env.draw_id!r}, which the frozen manifest does not "
                f"bind — the draw is unbound, unbooked and never reused")

    def test_a_sent_draw_is_actually_booked_against_the_hard_stop(self, tmp_path):
        """R-E1/R-E2/R-C3: the returned cost of every sent draw enters the $8.50 ledger."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        lg = _run_ledger([req])
        sr.execute_plan(plan=[(req, 0), (req, 1)], model=MODEL, tag=TAG, key="k", store=store,
                        ledger=lg, transport=_FakeTransport(cost=0.001),
                        worst_case_usd=lambda sha: 0.0001, stage="study", bucket="study",
                        sleep=lambda s: None, clock=_clock())
        assert lg.run_usd == pytest.approx(0.002), (
            f"two paid draws booked ${lg.run_usd:.8f}; spend is escaping the hard-stop ledger")

    def test_restart_reconstruction_accepts_the_runners_own_records(self, tmp_path):
        """R-C2: `open_ledger`-style reconstruction must not reject the records the runner
        itself wrote."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        sr.execute_plan(plan=[(req, 0)], model=MODEL, tag=TAG, key="k", store=store,
                        ledger=_run_ledger([req]), transport=_FakeTransport(cost=0.003),
                        worst_case_usd=lambda sha: 0.0001, stage="study", bucket="study",
                        sleep=lambda s: None, clock=_clock())
        manifest = ledger.RunManifest.from_draw_ids(
            [identity.draw_id(req.request_sha256, i) for i in range(25)])
        rebuilt = ledger.reconstruct_ledger(store, manifest=manifest)
        assert rebuilt.run_usd == pytest.approx(0.003)

    def test_a_persisted_404_is_replayed_as_a_failure_not_a_success(self, tmp_path):
        """R-C1 end to end."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        sr.execute_plan(plan=[(req, 0)], model=MODEL, tag=TAG, key="k", store=store,
                        ledger=_run_ledger([req]),
                        transport=_FakeTransport(status=404, cost=None),
                        worst_case_usd=lambda sha: 0.0001, stage="study", bucket="study",
                        sleep=lambda s: None, clock=_clock())
        run = sr.execute_plan(plan=[(req, 0)], model=MODEL, tag=TAG, key="k", store=store,
                              ledger=_run_ledger([req]), transport=_NoCallTransport(),
                              worst_case_usd=lambda sha: 0.0001, stage="study",
                              bucket="study", sleep=lambda s: None, clock=_clock())
        out = run.outcomes[0]
        assert out.reused is True
        assert out.http_status == 404, "a persisted 404 was replayed as HTTP 200 (R-C1)"
        assert out.valid is False and not out.parse_ok


# ======================================================================================
# AREA 3 — draw identity = request SHA-256 + draw index, stage label EXCLUDED (R-V7-7)
# ======================================================================================

class TestDrawIdentity:

    def test_identity_excludes_the_stage_label(self):
        sig = inspect.signature(identity.draw_id)
        assert list(sig.parameters) == ["request_sha", "draw_index"], (
            "draw_id takes more than (request_sha, draw_index) — a stage label in identity "
            "breaks smoke reuse (R-V7-7)")
        assert identity.draw_id("a" * 64, 3) == identity.draw_id("a" * 64, 3)

    def test_identity_changes_with_one_byte_of_the_request(self):
        a = identity.request_sha256({"model": "m", "messages": [{"role": "user", "content": "x"}]})
        b = identity.request_sha256({"model": "m", "messages": [{"role": "user", "content": "y"}]})
        assert a != b

    def test_the_runner_persists_the_identity_its_manifest_binds(self, tmp_path):
        """Two draw-identity spellings coexist in the package: `identity.draw_id` renders
        `<sha>#draw<i>` (what the R-V7-7 manifest binds) and `ledger.DrawIdentity` renders
        `<sha>#<i>`. If the runner ever persists under the ledger spelling, its own manifest
        cannot bind the record: nothing is booked, nothing is reused, everything is repaid."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        sr.execute_plan(plan=[(req, 0)], model=MODEL, tag=TAG, key="k", store=store,
                        ledger=_run_ledger([req]), transport=_FakeTransport(),
                        worst_case_usd=lambda sha: 0.0001, stage="study", bucket="study",
                        sleep=lambda s: None, clock=_clock())
        persisted = [e.draw_id for e in store.envelopes()]
        assert persisted == [identity.draw_id(req.request_sha256, 0)], (
            f"the runner persisted {persisted} but its manifest binds "
            f"{identity.draw_id(req.request_sha256, 0)!r}")

    def test_the_runner_never_keys_a_study_draw_with_the_bare_ledger_spelling(self):
        """Regression guard on the reconciliation above: a bare `L.DrawIdentity(...)` in the
        study path would silently reintroduce the unbindable spelling."""
        sr = _study_run()
        src = inspect.getsource(sr)
        bare = re.findall(r"L\.DrawIdentity\(", src)
        assert not bare, (
            f"{len(bare)} bare `L.DrawIdentity(` construction(s) in study_run: a study draw "
            f"must be keyed by the manifest spelling (`identity.draw_id`)")

    def test_the_ledger_parser_never_silently_mis_reads_a_manifest_draw_id(self):
        """`ledger.DrawIdentity.parse` cannot read `<sha>#draw<i>`. That is tolerable only
        because it fails LOUDLY; a silent mis-parse would mis-attribute a draw."""
        with pytest.raises((ValueError, TypeError)):
            ledger.DrawIdentity.parse(identity.draw_id("a" * 64, 7))

    def test_study_run_keys_smoke_and_full_draws_identically(self, tmp_path):
        """A smoke draw and a full-run draw at the same coordinate/index must land on ONE
        record. `execute_plan` takes the stage as a plain label, so this is testable by
        persisting under one stage and replaying under the other."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        sr.execute_plan(plan=[(req, 0)], model=MODEL, tag=TAG, key="k", store=store,
                        ledger=_run_ledger([req]), transport=_FakeTransport(),
                        worst_case_usd=lambda sha: 0.0001, stage="smoke", bucket="smoke",
                        sleep=lambda s: None, clock=_clock())
        run = sr.execute_plan(plan=[(req, 0)], model=MODEL, tag=TAG, key="k", store=store,
                              ledger=_run_ledger([req]), transport=_NoCallTransport(),
                              worst_case_usd=lambda sha: 0.0001, stage="study",
                              bucket="study", sleep=lambda s: None, clock=_clock())
        assert run.n_reused == 1 and run.n_sent == 0, \
            "smoke and full-run draws are keyed differently — reuse breaks (R-V7-7)"

    def test_the_plans_are_exactly_240_and_13200(self):
        sr = _study_run()
        smoke = [_req(seed=str(i), probe_id=f"p{i}") for i in range(48)]
        full = [_req(seed=f"f{i}", probe_id=f"p{i}") for i in range(528)]
        assert len(sr.plan_smoke_draws(smoke)) == 240
        assert len(sr.plan_full_draws(full)) == 13_200
        with pytest.raises(identity.CountMismatch):
            sr.plan_smoke_draws(smoke[:47])
        with pytest.raises(identity.CountMismatch):
            sr.plan_full_draws(full[:527])

    def test_the_full_plan_contains_the_smoke_plan(self):
        """12,960 additional = 13,200 - 240, not 13,200 + 240."""
        sr = _study_run()
        req = _req()
        smoke = {(r.request_sha256, i) for r, i in sr.plan_smoke_draws([req] * 48)
                 if r is req}
        full = {(r.request_sha256, i) for r, i in sr.plan_full_draws([req] * 528) if r is req}
        assert smoke <= full
        assert len(full - smoke) == 20


# ======================================================================================
# AREA 4 — full-grid cost projection (R-V7-2 / S-F5 / C2 / R-C4)
# ======================================================================================

def _candidate(tag="alibaba", model="qwen/qwen3.5-397b-a17b", pin=0.39e-6, pout=2.34e-6):
    return gate.EndpointCandidate(model=model, tag=tag, provider_name="Alibaba",
                                  endpoint_name=f"Alibaba | {model}", quantization="unknown",
                                  price_prompt_per_token=pin, price_completion_per_token=pout)


def _synthetic_grid(n=528, overhead=None):
    reqs = []
    for i in range(n):
        body = {"model": "m", "messages": [{"role": "system", "content": "s" * (i + 1)},
                                           {"role": "user", "content": f"u{i}"}]}
        reqs.append(gate.render_request(CELL_IDS[i % 11], f"p{i}", i % 4, body,
                                        template_overhead=overhead))
    return reqs


def _tok(text: str) -> int:
    return max(1, len(text.split()) + len(text) // 4)


class TestCostProjection:

    def test_projection_has_no_additive_smoke_term(self):
        """R-V7-2: the 240 smoke draws are counted ONCE, already inside 528 x 25."""
        proj = gate.project_full_grid(
            model="qwen/qwen3.5-397b-a17b", candidate=_candidate(),
            requests=_synthetic_grid(), tokenizer=_tok, completion_allowance_tokens=5,
            reconciled_prior_gate_spend=0.03, retry_reserve=0.10)
        assert proj.total_draws == 13_200
        assert proj.smoke_counted_once is True
        recomputed = (proj.projected_input_cost + proj.projected_completion_cost
                      + proj.reconciled_prior_gate_spend + proj.retry_reserve)
        assert proj.total == pytest.approx(recomputed), \
            "the projection total carries a term beyond the frozen C2 formula"
        # 240 smoke draws priced again would show up as ~240/13200 of the grid cost.
        assert proj.total < recomputed * 1.001

    def test_projection_refuses_a_partial_grid(self):
        with pytest.raises(gate.SpecViolation):
            gate.project_full_grid(model="qwen/qwen3.5-397b-a17b", candidate=_candidate(),
                                   requests=_synthetic_grid(527), tokenizer=_tok,
                                   completion_allowance_tokens=5,
                                   reconciled_prior_gate_spend=0.0, retry_reserve=0.0)

    def test_projection_is_not_a_single_probe_cost_times_13200(self):
        """R-V7-2: 'A synthetic canary does not represent the 528 differently sized requests.'"""
        reqs = _synthetic_grid()
        proj = gate.project_full_grid(model="qwen/qwen3.5-397b-a17b", candidate=_candidate(),
                                      requests=reqs, tokenizer=_tok,
                                      completion_allowance_tokens=5,
                                      reconciled_prior_gate_spend=0.0, retry_reserve=0.0)
        assert len({r.raw_input_tokens for r in proj.rows}) > 1, \
            "every one of the 528 rows has the same token count — this is not a full-grid gate"
        single = proj.rows[0].projected_input_tokens * 13_200 * _candidate().price_prompt_per_token
        assert proj.projected_input_cost != pytest.approx(single), \
            "the projection equals one probe's cost x 13,200 (the R-V7-2 defect)"

    def test_projection_includes_chat_template_overhead(self):
        """R-C4: a bare content concatenation omits roles, delimiters, special tokens and the
        generation prompt, and therefore UNDERSTATES what the provider bills."""
        with_overhead = _synthetic_grid()
        without = _synthetic_grid(overhead=0)
        kw = dict(model="qwen/qwen3.5-397b-a17b", candidate=_candidate(), tokenizer=_tok,
                  completion_allowance_tokens=5, reconciled_prior_gate_spend=0.0,
                  retry_reserve=0.0)
        a = gate.project_full_grid(requests=with_overhead, **kw)
        b = gate.project_full_grid(requests=without, **kw)
        assert b.total < a.total, (
            "a projection ignoring chat-template overhead is NOT provably smaller than the "
            "corrected one — R-C4 is not enforced")
        assert gate.chat_template_overhead(2) > 0

    def test_rendered_study_requests_carry_nonzero_template_overhead(self):
        """R-C4: `render_request` must not hand the projection a zero-overhead payload unless
        the tokenizer itself applies the pinned chat template."""
        sr = _study_render()
        probes = sr.probe_ids_for()
        grid = sr.render_study_grid("qwen/qwen3.5-397b-a17b", "alibaba", probes)
        assert all(r.rendered.template_overhead_tokens > 0 for r in grid), (
            "rendered requests carry template_overhead_tokens == 0; the C2 projection would "
            "tokenize a bare content concatenation (R-C4)")

    def test_ten_percent_margin_is_exact_integer_arithmetic(self):
        assert gate.projected_input_tokens(100) == 110
        assert gate.projected_input_tokens(1) == 2
        assert gate.INPUT_TOKEN_SAFETY_MARGIN == 1.10

    def test_completion_allowance_never_below_the_four_token_cap(self):
        assert gate.completion_allowance([]) == 4
        assert gate.completion_allowance([5]) == 5
        with pytest.raises(gate.SpecViolation):
            gate.project_full_grid(model="qwen/qwen3.5-397b-a17b", candidate=_candidate(),
                                   requests=_synthetic_grid(), tokenizer=_tok,
                                   completion_allowance_tokens=3,
                                   reconciled_prior_gate_spend=0.0, retry_reserve=0.0)

    def test_projection_promotion_requires_fit_under_850(self):
        expensive = _candidate(pin=1.0e-3, pout=1.0e-3)
        proj = gate.project_full_grid(model="qwen/qwen3.5-397b-a17b", candidate=expensive,
                                      requests=_synthetic_grid(), tokenizer=_tok,
                                      completion_allowance_tokens=5,
                                      reconciled_prior_gate_spend=0.0, retry_reserve=0.0)
        assert proj.stop == 8.50 and proj.fits is False


# ======================================================================================
# AREA 5 — deterministic promotion walk, retry policy, BYOK, no reduced-design substitute
# ======================================================================================

def _probe_ok(tag, candidate):
    return gate.EndpointProbeResult(
        tag=tag, http_status=200, requested_provider_only=(tag,), n_candidates_available=1,
        selected_provider_name=candidate.provider_name, requested_model=candidate.model,
        returned_model_evidence=candidate.model, strategy="direct", attempt=1,
        fallback_occurred=False, is_byok=False, reasoning_tokens=0,
        has_reasoning_payload=False, usage_fields_present=True, parsed_leading_digit=2,
        billed_completion_tokens=4)


class TestPromotionWalk:

    def _candidates(self, model, tags, prices=None):
        out = {}
        for i, t in enumerate(tags):
            p = (prices or {}).get(t, 0.39e-6)
            out[f"{model}::{t}"] = gate.EndpointCandidate(
                model=model, tag=t, provider_name=f"Name{i}", endpoint_name=f"Name{i} | {model}",
                quantization="unknown", price_prompt_per_token=p,
                price_completion_per_token=p * 6)
        return out

    def test_frozen_sequences_match_the_design_table(self):
        assert gate.PANEL_ORDER == ("qwen/qwen3.5-397b-a17b", "deepseek/deepseek-v4-pro")
        assert gate.frozen_sequence("qwen/qwen3.5-397b-a17b") == (
            "alibaba", "digitalocean", "streamlake", "parasail/fp8")
        assert gate.frozen_sequence("deepseek/deepseek-v4-pro") == (
            "deepseek", "fireworks", "novita/fp8", "parasail/fp8", "streamlake/fp8")

    def test_walk_is_strictly_ordered_and_short_circuits(self):
        model = "qwen/qwen3.5-397b-a17b"
        seq = gate.frozen_sequence(model)
        cands = self._candidates(model, seq)
        probed = []

        def probe(tag):
            probed.append(tag)
            cand = cands[f"{model}::{tag}"]
            if tag == seq[0]:
                return gate.EndpointProbeResult(tag=tag, http_status=400)
            return _probe_ok(tag, cand)

        def project(cand):
            return gate.project_full_grid(model=model, candidate=cand,
                                          requests=_synthetic_grid(), tokenizer=_tok,
                                          completion_allowance_tokens=4,
                                          reconciled_prior_gate_spend=0.0, retry_reserve=0.0)

        d = gate.promotion_walk(model=model, probe=probe, project=project, candidates=cands)
        assert probed == [seq[0], seq[1]], "the walk is not strictly in frozen order"
        assert d.promoted_tag == seq[1]
        assert seq[2] not in probed and seq[3] not in probed, \
            "a later endpoint was probed after an earlier one already passed"

    def test_a_cheaper_later_endpoint_never_reorders_the_walk(self):
        """v7.2 C1: 'prices are recorded, not used to reorder.'"""
        model = "qwen/qwen3.5-397b-a17b"
        seq = gate.frozen_sequence(model)
        cheap = {seq[3]: 1e-9}          # the LAST endpoint is by far the cheapest
        cands = self._candidates(model, seq, prices={**{t: 1e-6 for t in seq}, **cheap})
        probed = []

        def probe(tag):
            probed.append(tag)
            return _probe_ok(tag, cands[f"{model}::{tag}"])

        def project(cand):
            return gate.project_full_grid(model=model, candidate=cand,
                                          requests=_synthetic_grid(), tokenizer=_tok,
                                          completion_allowance_tokens=4,
                                          reconciled_prior_gate_spend=0.0, retry_reserve=0.0)

        d = gate.promotion_walk(model=model, probe=probe, project=project, candidates=cands)
        assert d.promoted_tag == seq[0], "a cheaper later endpoint reordered the frozen walk"
        assert probed == [seq[0]]

    def test_supplying_a_different_sequence_is_refused(self):
        model = "qwen/qwen3.5-397b-a17b"
        cands = self._candidates(model, gate.frozen_sequence(model))
        with pytest.raises(gate.SpecViolation):
            gate.promotion_walk(model=model, probe=lambda t: _probe_ok(t, list(cands.values())[0]),
                                project=lambda c: None, candidates=cands,
                                sequence=("parasail/fp8", "alibaba"))

    def test_exclusion_offers_no_reduced_cell_or_reduced_s_substitute(self):
        model = "deepseek/deepseek-v4-pro"
        seq = gate.frozen_sequence(model)
        cands = self._candidates(model, seq)
        d = gate.promotion_walk(model=model,
                                probe=lambda t: gate.EndpointProbeResult(tag=t, http_status=404),
                                project=lambda c: None, candidates=cands)
        assert d.excluded and d.promoted_tag is None and d.substitute is None
        assert "exclusion" in (d.exclusion_reason or "")

    # -- retry policy (C3 / R-V7-5) ----------------------------------------------------

    def test_hard_4xx_skips_immediately_with_no_retries(self):
        clock = iter([0.0] * 50)
        r = gate.execute_with_retries(lambda: gate.AttemptOutcome(status=400),
                                      sleep=lambda s: None, clock=lambda: next(clock))
        assert r.terminal_reason == "hard_4xx"
        assert r.attempts_made == 1 and r.sleeps == ()

    def test_429_is_one_initial_attempt_plus_four_retries(self):
        """C3: 'five attempts = one initial attempt + four retries.'"""
        t = [0.0]

        def clock():
            return t[0]

        def sleep(s):
            t[0] += s

        r = gate.execute_with_retries(lambda: gate.AttemptOutcome(status=429),
                                      sleep=sleep, clock=clock)
        assert r.terminal_reason == "attempts_exhausted"
        assert r.attempts_made == 5 and r.retries_made == 4
        assert r.sleeps == (2.0, 4.0, 8.0, 16.0), "frozen backoff ladder 2/4/8/16 s"

    def test_retry_after_is_honoured_only_inside_the_ten_minute_window(self):
        t = [0.0]
        r = gate.execute_with_retries(
            lambda: gate.AttemptOutcome(status=429, retry_after_s=900.0),
            sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
        assert r.terminal_reason == "window_exhausted"
        assert r.sleeps == (), "the runner slept past the 10-minute window (C3)"
        assert t[0] == 0.0

    def test_retry_after_shorter_than_the_window_is_honoured(self):
        t = [0.0]
        r = gate.execute_with_retries(
            lambda: gate.AttemptOutcome(status=429, retry_after_s=30.0),
            sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
        assert r.terminal_reason == "attempts_exhausted"
        assert r.sleeps == (30.0, 30.0, 30.0, 30.0)

    def test_a_429_alone_never_advances_the_walk(self):
        """R-V7-5: 'A single 429 is a transient response, not a capability result.'"""
        assert gate.classify_status(429) == "transient"
        assert gate.classify_status(408) == "transient"
        assert gate.classify_status(503) == "transient"
        assert gate.classify_status(404) == "hard"
        assert gate.classify_status(400) == "hard"

    def test_is_byok_true_is_an_availability_failure(self):
        t = [0.0]
        r = gate.execute_with_retries(
            lambda: gate.AttemptOutcome(status=200, is_byok=True),
            sleep=lambda s: None, clock=lambda: t[0])
        assert r.terminal_reason == "byok" and r.attempts_made == 1
        cand = _candidate()
        res = _probe_ok(cand.tag, cand)
        byok = gate.EndpointProbeResult(**{**res.__dict__, "is_byok": True})
        assert any("byok" in f.lower() for f in gate.audit_envelope(byok, cand))

    def test_no_reduced_design_substitute_exists_anywhere(self):
        """v7 requirement 4: the eight-cell (9,600) branch, the 11-vs-8 rule, S1 and S2 are
        RETIRED. Assert absence by symbol search across the whole v7 package."""
        offenders = []
        for path in sorted(V7_DIR.glob("*.py")):
            src = path.read_text(encoding="utf-8")
            code = "\n".join(l for l in src.splitlines()
                             if not l.lstrip().startswith("#"))
            for lit in (r"\b9600\b", r"\b9_600\b"):
                if re.search(lit, code):
                    offenders.append(f"{path.name}: numeric literal {lit}")
            for m in re.finditer(r"^\s*def\s+(\w*(?:eight_cell|reduced_s|reduced_cell)\w*)",
                                 code, re.M | re.I):
                offenders.append(f"{path.name}: def {m.group(1)}")
        # `gate.reduced_design_substitute` is the sanctioned refusal, not a substitute.
        offenders = [o for o in offenders if "reduced_design_substitute" not in o]
        assert not offenders, f"a reduced-design substitute survives: {offenders}"
        with pytest.raises(gate.SpecViolation):
            gate.reduced_design_substitute()
        assert gate.REDUCED_DESIGNS_RETIRED is True


# ======================================================================================
# AREA 6 — the $8.50 hard stop counts ALL Q2 spend and is never overridden
# ======================================================================================

def _ledger(prior=0.0, **kw):
    rec = ledger.ReconciliationResult(reconciled_usd=prior, record_count=0)
    return ledger.V7Ledger(reconciliation=rec, **kw)


class TestHardStop:

    def test_the_stop_is_850_and_unified_across_all_q2_spend(self):
        """R-V7-6: 'ALL paid Q2 spend — study calls, non-study canaries, and diagnostics —
        counts against the single $8.50 hard stop.'"""
        assert ledger.HARD_STOP_USD == 8.50
        assert gate.GLOBAL_STUDY_STOP == 8.50
        lg = _ledger(prior=1.0)
        assert lg.total_spent_usd == pytest.approx(1.0)
        with pytest.raises(ledger.HardStopExceeded):
            lg.check_before_call(7.51)

    def test_finish_current_model_never_authorizes_a_breach(self):
        """R-V7-6: 'The cut rule may prevent starting DeepSeek; it can never authorize
        overspending to finish Qwen.'"""
        lg = _ledger(prior=8.49)
        lg.current_model = "qwen/qwen3.5-397b-a17b"
        lg.current_model_complete = False
        halt = lg.must_halt_before_next_call(0.02)
        assert halt.halt is True
        assert halt.model_incomplete is True
        assert halt.emit_headline is False, \
            "a mid-model halt still authorizes a headline (R-V7-6)"

    def test_a_model_is_never_started_when_its_complete_run_does_not_fit(self):
        lg = _ledger(prior=8.00)
        proj = ledger.ModelProjection(model="deepseek/deepseek-v4-pro", endpoint="deepseek",
                                      projected_input_cost_usd=1.0,
                                      projected_completion_cost_usd=0.2,
                                      retry_reserve_usd=0.1)
        d = lg.may_start_model(proj)
        assert d.allowed is False and d.budget_excluded is True
        assert "reduced" in d.reason and "no reduced" in d.reason
        with pytest.raises(ledger.HardStopExceeded):
            lg.start_model(proj)

    def test_a_partially_run_model_emits_no_headline(self):
        lg = _ledger(prior=0.0)
        lg.current_model = "qwen/qwen3.5-397b-a17b"
        lg.current_model_complete = False
        ok = lg.must_halt_before_next_call(0.0)
        assert ok.halt is False and ok.emit_headline is False
        lg.mark_model_complete()
        assert lg.must_halt_before_next_call(0.0).emit_headline is True

    def test_execute_plan_halts_before_the_breaching_call(self, tmp_path):
        """R-V7-6: 'if realized cost drift would make the next call breach $8.50, halt BEFORE
        that call'. The halt must precede the send, not follow it."""
        sr = _study_run()
        req = _req()
        store = ledger.EnvelopeStore(tmp_path / "study")
        lg = _run_ledger([req], prior=8.49)
        t = _FakeTransport(cost=0.01)
        run = sr.execute_plan(plan=[(req, i) for i in range(5)], model=MODEL, tag=TAG,
                              key="k", store=store, ledger=lg, transport=t,
                              worst_case_usd=lambda sha: 0.05, stage="study", bucket="study",
                              sleep=lambda s: None, clock=_clock())
        assert run.halted is True
        assert t.calls == [], "a call was SENT after the hard stop should have halted the run"
        assert lg.total_spent_usd <= 8.50 + 1e-9

    def test_a_halted_full_run_emits_no_headline(self, tmp_path):
        """'finish current model' never overrides the stop: halting mid-model reports the
        model incomplete and emits NO headline."""
        sr = _study_run()
        reqs = [_req(seed=f"h{i}", probe_id=f"p{i % 12}", cell_id=CELL_IDS[i % 11],
                     order_idx=i % 4) for i in range(528)]
        store = ledger.EnvelopeStore(tmp_path / "study")
        lg = _run_ledger([reqs[0]], prior=8.50)
        report = sr.run_full(model=MODEL, tag=TAG, key="k", requests=reqs,
                             probe_ids=[f"p{i}" for i in range(12)], store=store, ledger=lg,
                             transport=_NoCallTransport(),
                             worst_case_usd=lambda sha: 0.01, sleep=lambda s: None,
                             clock=_clock())
        assert report.run.halted is True
        assert report.model_incomplete is True
        assert report.emit_headline is False, "a halted model still authorized a headline"
        assert report.completeness is None

    def test_double_booking_a_draw_is_refused(self, tmp_path):
        store = ledger.EnvelopeStore(tmp_path / "run")
        sha = "1" * 64
        env = _persist(store, sha, 0, status=200, cost=0.25)
        lg = _ledger()
        lg.book_envelope(env)
        with pytest.raises(ledger.DoubleBookingError):
            lg.book_envelope(env)
        assert lg.run_usd == pytest.approx(0.25)


# ======================================================================================
# AREA 7 — the completeness gate PRECEDES every estimand (R-V7-3)
# ======================================================================================

class TestCompletenessGate:

    def test_a_complete_run_passes(self):
        rep = _report(_draws())
        assert rep.complete, rep.failures
        assert rep.n_draws == 13_200 and rep.n_coordinates == 528

    def test_nineteen_of_twenty_five_in_one_order_emits_nothing(self):
        """R-V7-3: '>= 20/25 parseable in EVERY order.' 19 in ONE order is a failure."""
        bad = (CELL_IDS[0], PROBES[0], 0)

        def valid_at(c, p, o):
            return 19 if (c, p, o) == bad else 25

        draws = _draws(valid_at=valid_at)
        rep = _report(draws)
        assert not rep.complete
        with pytest.raises(gate.IncompleteModel):
            gate.require_complete(rep)
        with pytest.raises(gate.IncompleteModel):
            gate.headline_estimands(draws, _items(), expected_probe_ids=PROBES)

    def test_overall_094_emits_nothing(self):
        """R-V7-3: '>= 0.95 parseable overall.' 0.94 must emit NOTHING."""
        # 25 valid everywhere except a set of coordinates at 20/25 chosen so the overall
        # rate lands at 0.94 while EVERY order still satisfies >= 20/25.
        target_unparseable = int(round(13_200 * 0.06))          # 792
        n_thin = target_unparseable // 5                        # 158 coordinates at 20/25
        coords = [(c, p, o) for c in CELL_IDS for p in PROBES for o in range(N_ORDERS)]
        thin = set(coords[:n_thin])

        draws = _draws(valid_at=lambda c, p, o: 20 if (c, p, o) in thin else 25)
        rep = _report(draws)
        assert rep.overall_parse_rate == pytest.approx(0.94, abs=1e-3)
        assert not rep.complete, "a 0.94 overall parse rate passed the gate"
        assert any("overall parse rate" in f for f in rep.failures)
        with pytest.raises(gate.IncompleteModel):
            gate.headline_estimands(draws, _items(), expected_probe_ids=PROBES)

    def test_a_missing_cell_probe_or_order_emits_nothing(self):
        draws = [d for d in _draws() if d.cell_id != CELL_IDS[10]]
        assert not _report(draws).complete
        draws = [d for d in _draws() if d.probe_id != PROBES[11]]
        assert not _report(draws).complete
        draws = [d for d in _draws() if d.order_idx != 3]
        assert not _report(draws).complete

    def test_duplicate_and_unexpected_coordinates_are_rejected(self):
        draws = _draws()
        draws.append(gate.SamplingDraw(CELL_IDS[0], PROBES[0], 0, 0, 1))       # duplicate index
        rep = _report(draws)
        assert not rep.complete and any("duplicate" in f for f in rep.failures)

        draws = _draws()
        draws.append(gate.SamplingDraw("not_a_cell::no_guard", PROBES[0], 0, 0, 1))
        rep = _report(draws)
        assert not rep.complete and any("unexpected" in f for f in rep.failures)

    def test_the_gate_runs_before_the_bootstrap_not_after(self):
        src = inspect.getsource(gate.headline_estimands)
        assert src.index("completeness_gate") < src.index("nested_bootstrap")
        assert src.index("require_complete") < src.index("nested_bootstrap")

    def test_study_extract_gates_before_the_bootstrap(self):
        se = _study_extract()
        for fn in (se.extract_model, se.extract_headline):
            src = inspect.getsource(fn)
            gate_at = src.index("completeness_gate")
            parts = src.split('"""')
            body = parts[2] if len(parts) >= 3 else src
            est_at = min(i for i in (body.find("nested_bootstrap("),
                                     body.find("extract_headline("),
                                     body.find("crack_diagnostics(")) if i >= 0)
            gate_at = body.index("completeness_gate")
            assert gate_at < est_at, (
                f"{fn.__name__} reaches an estimand before the R-V7-3 completeness gate")

    def test_study_extract_headline_refuses_an_incomplete_model(self):
        se = _study_extract()
        bad = [d for d in _draws() if d.order_idx != 3]
        with pytest.raises(gate.IncompleteModel):
            se.extract_headline(bad, _items(), expected_probe_ids=PROBES, model=MODEL)

        bad2 = _draws(valid_at=lambda c, p, o: 19 if (c, p, o) == (CELL_IDS[0], PROBES[0], 0)
                      else 25)
        with pytest.raises(gate.IncompleteModel):
            se.extract_headline(bad2, _items(), expected_probe_ids=PROBES, model=MODEL)

    def test_study_extract_model_emits_nothing_when_incomplete(self, tmp_path):
        se = _study_extract()
        store = ledger.EnvelopeStore(tmp_path / "study")
        manifest = {"model": MODEL, "coordinates": [], "draw_identities": []}
        try:
            res = se.extract_model(store, probe_ids=list(PROBES), model=MODEL,
                                   manifest=manifest, items=_items())
        except Exception as exc:                    # noqa: BLE001 — shape may differ
            assert not isinstance(exc, (ValueError, AttributeError)), exc
            return                                  # failing closed is also acceptable
        assert res.complete is False
        assert res.estimands is None, "an incomplete model emitted estimands"
        assert res.protective_mass is None and res.diagnostics is None


# ======================================================================================
# AREA 8 — the nested bootstrap (C4)
# ======================================================================================

class TestNestedBootstrap:

    def test_frozen_replicates_and_seed(self):
        assert gate.BOOTSTRAP_REPLICATES == 2000 and gate.BOOTSTRAP_SEED == 0
        assert (gate.PERCENTILE_LOW, gate.PERCENTILE_HIGH) == (2.5, 97.5)
        sig = inspect.signature(gate.nested_bootstrap)
        assert sig.parameters["replicates"].default == 2000
        assert sig.parameters["seed"].default == 0

    def test_reproducible_at_a_fixed_seed(self):
        draws = _draws()
        rep = _report(draws)
        a = gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=200)
        b = gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=200)
        for name in gate.CONTRAST_NAMES:
            assert a.contrasts[name]["ci"] == b.contrasts[name]["ci"]

    def test_a_different_seed_moves_the_interval(self):
        draws = _draws()
        rep = _report(draws)
        a = gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=200, seed=0)
        b = gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=200, seed=1)
        assert a.contrasts["data_effect"]["ci"] != b.contrasts["data_effect"]["ci"]

    def test_probe_resampling_preserves_pairing(self):
        """C4: 'resample the 12 probes with pairing preserved.'

        Two cells given IDENTICAL per-probe canonical distributions, where the per-probe
        protective-mass LEVEL sweeps 0.08 -> 0.96. With one shared probe index vector the
        paired difference is pure finite-draw noise; resampling probes independently per cell
        would let the level variance leak into the contrast and inflate the interval ~4.5x.
        """
        draws = _draws(choices_for=_canonical_choices)
        rep = _report(draws)
        assert rep.complete, rep.failures

        # Guard against a vacuous fixture: the per-probe LEVELS must really vary.
        levels = []
        for probe in PROBES:
            acc = np.zeros(4)
            for o in range(N_ORDERS):
                c = gate._canonical_counts(
                    _canonical_choices(CELL_IDS[2], probe, o, 25), o, 4)
                acc += c / c.sum()
            levels.append(float(drift.protective_mass(acc / acc.sum(), 1)))
        spread = max(levels) - min(levels)
        assert spread > 0.5, f"fixture is vacuous: per-probe mass spread only {spread:.3f}"
        unpaired_width = 2 * 1.96 * float(np.std(levels)) / np.sqrt(12) * np.sqrt(2)
        assert unpaired_width > 0.4

        res = gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=1500)
        lo, hi = res.contrasts["data_effect"]["ci"]
        assert res.contrasts["data_effect"]["mean"] == pytest.approx(0.0, abs=1e-9)
        assert (hi - lo) < 0.20, (
            f"data_effect CI width {hi - lo:.4f} on two identically distributed cells, against "
            f"an unpaired expectation of ~{unpaired_width:.2f}: the probe resample is NOT "
            f"paired across cells (C4)")

    def test_finite_draw_resampling_actually_happens(self):
        """C4 inner level: 'within each selected probe-cell-order coordinate, resample with
        replacement EXACTLY the observed number of valid draws.'

        Two datasets with IDENTICAL observed proportions at every coordinate, differing ONLY
        in the observed valid COUNT (25 vs 20) on the two cells that form `data_effect`.

        The point estimate must be identical (same proportions) and the interval must NOT be:
        an estimator that resampled a constant 25 would consume the same rng stream from the
        same proportions and return a byte-identical interval. The direction is checked as a
        seed-averaged width, because the finite-draw signal in this frozen design (~5% of the
        interval width) is smaller than single-seed percentile Monte-Carlo error.
        """
        thin_cells = {gate.cid_for("data_only", "no_guard"),
                      gate.cid_for("baseline", "no_guard")}
        full = _draws()
        thin = _draws(valid_at=lambda c, p, o: 20 if c in thin_cells else 25)
        rep_full, rep_thin = _report(full), _report(thin)
        assert rep_full.complete and rep_thin.complete, (rep_full.failures, rep_thin.failures)
        assert rep_thin.overall_parse_rate >= gate.MIN_PARSEABLE_OVERALL

        items = _items()
        widths_full, widths_thin = [], []
        a = b = None
        for seed in range(5):
            a = gate.nested_bootstrap(full, items, completeness=rep_full,
                                      replicates=3000, seed=seed)
            b = gate.nested_bootstrap(thin, items, completeness=rep_thin,
                                      replicates=3000, seed=seed)
            ca, cb = a.contrasts["data_effect"]["ci"], b.contrasts["data_effect"]["ci"]
            assert ca != cb, (
                f"seed {seed}: identical proportions with 25 vs 20 observed valid draws gave "
                f"the SAME interval {ca} — the inner resample ignores the observed valid "
                f"count, i.e. finite-draw resampling is not happening (C4)")
            widths_full.append(ca[1] - ca[0])
            widths_thin.append(cb[1] - cb[0])
            # identical proportions => identical point estimate
            assert a.contrasts["data_effect"]["mean"] == pytest.approx(
                b.contrasts["data_effect"]["mean"], abs=1e-12)

        mean_full = sum(widths_full) / len(widths_full)
        mean_thin = sum(widths_thin) / len(widths_thin)
        assert mean_thin > mean_full, (
            f"fewer observed valid draws (20 vs 25) on both cells of data_effect did not "
            f"widen the interval on average ({mean_thin:.6f} vs {mean_full:.6f})")
        assert sum(t > f for f, t in zip(widths_full, widths_thin)) >= 4, \
            "the widening is not reproducible across seeds"

        # C4: 'Report observed valid draw counts per coordinate.'
        assert min(b.valid_counts.values()) == 20
        assert max(b.valid_counts.values()) == 25
        assert set(a.valid_counts.values()) == {25}
        assert len(b.valid_counts) == 528

    def test_a_coordinate_with_no_valid_draws_never_reaches_the_bootstrap(self):
        draws = _draws()
        rep = _report(draws)
        stripped = [d for d in draws
                    if not (d.coordinate == (CELL_IDS[0], PROBES[0], 0))]
        stripped += [gate.SamplingDraw(CELL_IDS[0], PROBES[0], 0, i, None) for i in range(25)]
        with pytest.raises(gate.SpecViolation):
            gate.nested_bootstrap(stripped, _items(), completeness=rep, replicates=10)

    def test_bootstrap_refuses_an_incomplete_report(self):
        draws = [d for d in _draws() if d.order_idx != 3]
        rep = _report(draws)
        with pytest.raises(gate.IncompleteModel):
            gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=10)


# ======================================================================================
# AREA 9 — the parser fails closed EVERYWHERE (S-F4)
# ======================================================================================

class TestParserFailsClosed:

    @pytest.mark.parametrize("text", [
        "", "   ", "\n", None,
        "I choose 3", "The answer is 3", "Option 3 seems best",
        "34", "3 4", "3 or 4", "12",
        "0", "5", "9", "-1", "-3",
        "three", "II", "[3", "n/a",
    ])
    def test_unparseable_and_out_of_range_replies_become_none(self, text):
        assert identity.parse_choice_anchored(text) is None, \
            f"S-F4: {text!r} must fail closed, never be guessed or clamped"

    @pytest.mark.parametrize("text,expected", [("3", 3), ("3.", 3), (" 3 ", 3), ("1", 1),
                                               ("4", 4), ("2)", 2)])
    def test_anchored_leading_digits_parse(self, text, expected):
        res = identity.parse_option(text)
        assert res.ok and res.option == expected
        # the scorer-facing helper returns the 0-BASED display position
        assert identity.parse_choice_anchored(text) == expected - 1

    def test_a_negative_choice_can_never_index_the_williams_order(self):
        """The v7.1-round data-corruption class: `order[-1]` is a VALID Python lookup that
        silently mis-attributes a draw to the wrong canonical option."""
        with pytest.raises(gate.SpecViolation):
            gate.SamplingDraw(CELL_IDS[0], PROBES[0], 0, 0, -1)
        with pytest.raises(gate.SpecViolation):
            gate.SamplingDraw(CELL_IDS[0], PROBES[0], 0, 0, 4)
        with pytest.raises(gate.SpecViolation):
            gate.SamplingDraw(CELL_IDS[0], PROBES[0], 0, 0, True)

    def test_a_rehydrated_negative_choice_is_a_completeness_failure(self):
        """A draw rebuilt from JSON bypasses `__post_init__`; the gate must still catch it."""
        d = gate.SamplingDraw(CELL_IDS[0], PROBES[0], 0, 0, 1)
        object.__setattr__(d, "choice", -1)
        draws = [x for x in _draws() if not (x.coordinate == d.coordinate and x.draw_index == 0)]
        draws.append(d)
        rep = _report(draws)
        assert not rep.complete
        assert any("outside" in f for f in rep.failures), rep.failures

    def test_canonical_counts_refuse_a_negative_display_position(self):
        with pytest.raises(gate.SpecViolation):
            gate._canonical_counts([-1], 0, 4)
        with pytest.raises(gate.SpecViolation):
            gate._canonical_counts([4], 0, 4)

    def test_parse_result_reports_the_reason_not_a_guess(self):
        assert identity.parse_option("").reason == identity.PARSE_EMPTY
        assert identity.parse_option("I choose 3").reason == identity.PARSE_NOT_ANCHORED
        assert identity.parse_option("34").reason == identity.PARSE_NOT_ANCHORED
        assert identity.parse_option("5").reason == identity.PARSE_OUT_OF_RANGE
        assert identity.parse_option("0").reason == identity.PARSE_OUT_OF_RANGE
        for t in ("", "I choose 3", "34", "5", "0", "-1"):
            r = identity.parse_option(t)
            assert r.option is None and r.index is None and not r.ok

    def test_study_extract_parse_seam_fails_closed(self):
        se = _study_extract()
        for text in ("", "   ", None, "I choose 3", "The answer is 3", "34", "3 4",
                     "0", "5", "9", "-1", "three"):
            r = se.parse_reply(text)
            assert r.option is None and r.index is None and not r.ok, \
                f"S-F4: study_extract guessed {r!r} from {text!r}"
        ok = se.parse_reply("3")
        assert ok.ok and ok.option == 3 and ok.index == 2

    def test_study_extract_guards_the_display_position_against_negative_indexing(self):
        se = _study_extract()
        src = inspect.getsource(se.extract_draws)
        assert re.search(r"0\s*<=\s*int\(choice\)\s*<\s*N_OPTIONS", src), (
            "study_extract does not guard the recovered display position against the "
            "negative-index mis-attribution class (S-F4 / SamplingDraw contract)")


# ======================================================================================
# AREA 10 — outcome-blinding interlock
# ======================================================================================

_SUBSTANTIVE = ("choice", "choices", "frequency", "frequencies", "contrast", "contrasts",
                "effect", "effect_size", "direction", "protective_mass", "crack", "estimand",
                "mean", "ci", "distribution")


def _flatten_keys(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k).lower())
            out.extend(_flatten_keys(v, prefix))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_flatten_keys(v, prefix))
    return out


class TestBlindingInterlock:

    def test_aggregation_refuses_unless_both_records_exist(self):
        """Design 'Outcome-blinding interlock': 'Headline aggregation refuses to run until
        both records exist' — the promotion decision AND the funding decision."""
        il = _interlock()
        promo = {"promoted_tag": "alibaba", "excluded": False}
        fund = {"authorized": True, "decision": "funded"}
        assert il.blinding_interlock(promo, fund) is True
        assert il.blinding_interlock(None, fund) is False, "no promotion record, yet unblinded"
        assert il.blinding_interlock(promo, None) is False, "no funding record, yet unblinded"
        assert il.blinding_interlock(None, None) is False
        assert il.blinding_interlock({}, fund) is False
        assert il.blinding_interlock(promo, {}) is False
        assert il.blinding_interlock(promo, {"authorized": False}) is False, \
            "a REFUSED funding decision unblocked the headline"

    def test_an_exclusion_is_a_recorded_promotion_decision(self):
        il = _interlock()
        assert il.blinding_interlock({"excluded": True, "promoted_tag": None},
                                     {"authorized": True}) is True

    def test_require_headline_permitted_raises_on_a_bare_run_dir(self, tmp_path):
        il = _interlock()
        with pytest.raises(il.HeadlineBlocked):
            il.require_headline_permitted(tmp_path)

    def test_require_headline_permitted_raises_with_only_one_record(self, tmp_path):
        il = _interlock()
        try:
            il.record_promotion(tmp_path, model=MODEL, promoted_tag=TAG,
                                manifest_sha256="a" * 64)
        except TypeError:
            pytest.skip("interlock.record_promotion signature differs; the pure predicate is "
                        "covered above")
        with pytest.raises(il.HeadlineBlocked):
            il.require_headline_permitted(tmp_path)

    def test_the_gate_view_carries_no_substantive_outcome(self, tmp_path):
        """Design: during the gate the operator sees only request integrity, resolved
        provider, parse/coverage, errors, usage and cumulative cost."""
        il = _interlock()
        store = ledger.EnvelopeStore(tmp_path / "study")
        req = _req()
        envs = []
        for i, content in enumerate(["1", "2", "3", "4", "prose"]):
            draw = ledger.DrawIdentity(req.request_sha256, i)
            env = ledger.build_envelope(
                draw=draw, request_body=req.body, request_headers={},
                response_body=_wire_body(content=content), response_headers={},
                http_status=200, bucket="study", model=MODEL, provider=TAG, stage="study")
            store.put(env)
            envs.append(env)
        view = il.gate_view(envs)
        il.assert_outcome_blinded(view)
        leaked = sorted(set(_flatten_keys(view)) & set(_SUBSTANTIVE))
        assert not leaked, f"the gate view leaks substantive outcome fields: {leaked}"
        text = json.dumps(view, default=str, sort_keys=True)
        for answer in ("\"1\"", "\"2\"", "\"3\"", "\"4\""):
            assert answer not in text, "the gate view echoes a substantive answer"

    def test_the_gate_view_is_invariant_to_the_answers_themselves(self):
        """The mechanised meaning of 'never display or aggregate substantive answers': two
        runs whose ANSWERS differ entirely but whose parse outcomes agree must produce the
        SAME view."""
        il = _interlock()
        req = _req()

        def envs(contents):
            out = []
            for i, c in enumerate(contents):
                out.append(ledger.build_envelope(
                    draw=ledger.DrawIdentity(req.request_sha256, i), request_body=req.body,
                    request_headers={}, response_body=_wire_body(content=c),
                    response_headers={}, http_status=200, bucket="study", model=MODEL,
                    provider=TAG, stage="study", timestamp="2026-07-28T00:00:00Z"))
            return out

        a = il.gate_view(envs(["1", "1", "1", "1"]))
        b = il.gate_view(envs(["4", "4", "4", "4"]))
        assert a == b, "the gate view changes with the model's answers — it is not blinded"

    def test_assert_outcome_blinded_rejects_a_leaky_view(self):
        il = _interlock()
        with pytest.raises(il.BlindingViolation):
            il.assert_outcome_blinded({"schema": "x", "contrasts": {"data_effect": 0.1}})
        with pytest.raises(il.BlindingViolation):
            il.assert_outcome_blinded({"usage": {"choice_frequencies": [1, 2, 3, 4]}})

    def test_headline_extraction_is_guarded_by_the_interlock(self):
        """Every aggregation path must pass through the interlock before emitting."""
        se = _study_extract()
        src = inspect.getsource(se)
        assert re.search(r"interlock|require_headline_permitted", src, re.I), (
            "study_extract never consults the outcome-blinding interlock: `extract_model` "
            "computes the nested bootstrap and the eight contrasts with no promotion/funding "
            "record required (design 'Outcome-blinding interlock')")


# ======================================================================================
# AREA 11 — exactly the eight frozen estimands, per model, non-pooled
# ======================================================================================

class TestEstimands:

    def test_exactly_the_eight_frozen_contrasts(self):
        expected = {
            "data_effect", "instruction_effect", "channel_contrast", "placebo_effect",
            "data_placement", "combined_placement",
            "data_system_recovery", "combined_system_recovery",
        }
        assert set(gate.CONTRAST_NAMES) == expected
        assert len(gate.CONTRAST_NAMES) == 8

    def test_the_contrast_definitions_match_the_frozen_prose(self):
        by_name = {n: (a, b) for n, a, b in gate.CONTRASTS}
        assert by_name["data_effect"] == (("data_only", "no_guard"), ("baseline", "no_guard"))
        assert by_name["instruction_effect"] == (("instruction_only", "no_guard"),
                                                 ("baseline", "no_guard"))
        assert by_name["placebo_effect"] == (("placebo", "no_guard"), ("baseline", "no_guard"))
        assert by_name["data_placement"] == (("data_only", "user_after"),
                                             ("data_only", "user_before"))
        assert by_name["combined_placement"] == (("combined", "user_after"),
                                                 ("combined", "user_before"))
        assert by_name["data_system_recovery"] == (("data_only", "system_guard"),
                                                   ("data_only", "no_guard"))
        assert by_name["combined_system_recovery"] == (("combined", "system_guard"),
                                                       ("combined", "no_guard"))

    def test_channel_contrast_is_data_minus_instruction(self):
        draws = _draws()
        rep = _report(draws)
        res = gate.nested_bootstrap(draws, _items(), completeness=rep, replicates=200)
        c = res.contrasts
        assert c["channel_contrast"]["mean"] == pytest.approx(
            c["data_effect"]["mean"] - c["instruction_effect"]["mean"], abs=1e-12)

    def test_a_result_carries_all_eight_and_only_eight(self):
        draws = _draws()
        res = gate.headline_estimands(draws, _items(), expected_probe_ids=PROBES,
                                      replicates=100)
        assert set(res.contrasts) == set(gate.CONTRAST_NAMES)
        assert len(res.contrasts) == 8
        assert res.probe_ids == tuple(sorted(PROBES))
        for v in res.contrasts.values():
            assert v["n_probes"] == 12, "cells were pooled across probes"

    def test_two_models_cannot_be_pooled_into_one_estimand(self):
        """Design: 'Model x probe cells are never pooled as independent observations.'
        Concatenating a second model's draws must be rejected as duplicate coordinates."""
        merged = _draws() + _draws()
        rep = _report(merged)
        assert not rep.complete and any("duplicate" in f for f in rep.failures), \
            "two models' draws pooled into one 26,400-draw set passed the gate"
        with pytest.raises(gate.IncompleteModel):
            gate.headline_estimands(merged, _items(), expected_probe_ids=PROBES)

    def test_study_extract_emits_per_model_records(self):
        se = _study_extract()
        fn = _attr(se, ("extract_headline", "headline", "extract", "estimands_for_model"),
                   "per-model, non-pooled estimands (design 'Estimands')")
        params = list(inspect.signature(fn).parameters)
        assert any("model" in p for p in params), (
            f"{fn.__name__}{tuple(params)} takes no model argument — per-model, non-pooled "
            f"extraction is not expressible")


# ======================================================================================
# AREA 12 — provider audit on EVERY study draw; reasoning tokens EXACTLY 0
# ======================================================================================

SNAPSHOT = ROOT / "out" / "q2_stage2_endpoint_snapshot" / "manifest.json"


def _snapshot():
    if not SNAPSHOT.exists():
        pytest.skip("committed endpoint snapshot absent; NOT-YET-IMPLEMENTED: C1 binding")
    return envelope.load_snapshot(SNAPSHOT)


QWEN = "qwen/qwen3.5-397b-a17b"


def _good_response(snap, model=QWEN, tag="alibaba"):
    """A response that satisfies the frozen C1 proof, built FROM the committed snapshot."""
    cand = snap.candidate(model, tag)
    return {
        "model": model,
        "choices": [{"message": {"content": "2"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 53, "completion_tokens": 1, "total_tokens": 54,
                  "cost": 0.000023, "completion_tokens_details": {"reasoning_tokens": 0}},
        "openrouter_metadata": {
            "requested": model, "strategy": "direct", "attempt": 1, "is_byok": False,
            "endpoints": {"available": [{"provider": cand.provider_name,
                                         "model": cand.upstream_model,
                                         "selected": True}]},
        },
    }


class TestProviderAuditAndReasoning:

    def test_the_c1_proof_accepts_a_conforming_response(self):
        snap = _snapshot()
        res = envelope.verify_provider_audit(_good_response(snap), QWEN, "alibaba", snap)
        assert res.ok, res.failures

    @pytest.mark.parametrize("label,mutate", [
        ("missing routing metadata", lambda m: m.pop("openrouter_metadata")),
        ("strategy", lambda m: m["openrouter_metadata"].__setitem__("strategy", "fallback")),
        ("attempt", lambda m: m["openrouter_metadata"].__setitem__("attempt", 2)),
        ("is_byok", lambda m: m["openrouter_metadata"].__setitem__("is_byok", True)),
        ("requested model", lambda m: m["openrouter_metadata"].__setitem__("requested", "x/y")),
        ("response model", lambda m: m.__setitem__("model", "other/model")),
        ("two candidates", lambda m: m["openrouter_metadata"]["endpoints"]["available"].append(
            {"provider": "Someone", "model": "x", "selected": False})),
        ("display name", lambda m: m["openrouter_metadata"]["endpoints"]["available"][0]
            .__setitem__("provider", "SomeoneElse")),
        ("undated model evidence", lambda m: m["openrouter_metadata"]["endpoints"]["available"]
            [0].__setitem__("model", QWEN)),
        ("fallback evidence", lambda m: m["openrouter_metadata"].__setitem__("fallback", True)),
    ], ids=lambda x: x if isinstance(x, str) else "")
    def test_the_c1_proof_fails_closed_on_every_missing_element(self, label, mutate):
        snap = _snapshot()
        resp = _good_response(snap)
        mutate(resp)
        res = envelope.verify_provider_audit(resp, QWEN, "alibaba", snap)
        assert not res.ok, f"the C1 audit passed despite: {label}"
        with pytest.raises(envelope.ProviderAuditError):
            res.raise_for_status()

    def test_reasoning_tokens_must_equal_exactly_zero(self):
        """R-V7-1: 'reported reasoning tokens must equal zero' — not 'approximately zero'."""
        snap = _snapshot()
        ok = _good_response(snap)
        assert envelope.verify_reasoning_off(ok).ok
        for bad_value in (1, 2, 17):
            r = json.loads(json.dumps(ok))
            r["usage"]["completion_tokens_details"]["reasoning_tokens"] = bad_value
            res = envelope.verify_reasoning_off(r)
            assert not res.ok, f"reasoning_tokens={bad_value} passed the exact-zero rule"
            with pytest.raises(envelope.ReasoningError):
                res.raise_for_status()

    def test_an_unreported_reasoning_count_is_not_a_zero_count(self):
        snap = _snapshot()
        r = _good_response(snap)
        r["usage"].pop("completion_tokens_details")
        assert not envelope.verify_reasoning_off(r).ok
        r2 = _good_response(snap)
        r2.pop("usage")
        assert not envelope.verify_reasoning_off(r2).ok

    def test_a_reasoning_payload_anywhere_fails(self):
        snap = _snapshot()
        for key in ("reasoning", "reasoning_content", "reasoning_details"):
            r = _good_response(snap)
            r["choices"][0]["message"][key] = "let me think"
            assert not envelope.verify_reasoning_off(r).ok, f"payload key {key} passed"

    def test_the_frozen_envelope_is_exactly_the_v72_body(self):
        body = envelope.build_sampling_request(
            QWEN, "parasail/fp8",
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
        assert body["temperature"] == 1.0 and body["top_p"] == 1.0
        assert body["max_tokens"] == 4
        assert body["reasoning"] == {"effort": "none"}, "R-V7-1: documented reasoning-off form"
        assert "seed" not in body, "R-V7-1/v7: seed is UNSET for independent draws"
        assert "stop" not in body and "logprobs" not in body and "top_logprobs" not in body
        assert body["provider"] == {"only": ["parasail/fp8"], "allow_fallbacks": False,
                                    "require_parameters": True}
        h = envelope.request_headers("sk-test")
        assert h["X-OpenRouter-Cache"] == "false", "R-V7-7/S-F2: cache disabled on every draw"
        assert h["X-OpenRouter-Metadata"] == "enabled"

    def test_every_study_request_carries_the_frozen_envelope(self):
        sr = _study_render()
        probes = sr.probe_ids_for()
        grid = sr.render_study_grid(QWEN, "alibaba", probes)
        for r in grid:
            b = r.body
            assert b["model"] == QWEN
            assert b["temperature"] == 1.0 and b["top_p"] == 1.0 and b["max_tokens"] == 4
            assert b["reasoning"] == {"effort": "none"}
            assert "seed" not in b and "stop" not in b and "logprobs" not in b
            assert b["provider"]["only"] == ["alibaba"]
            assert b["provider"]["allow_fallbacks"] is False
            assert b["provider"]["require_parameters"] is True
            assert {m["role"] for m in b["messages"]} <= {"system", "user"}

    # -- the audit must reach EVERY study draw, not only the gate probes ----------------

    def _store_with(self, tmp_path, responses):
        """A study store holding one envelope per response, each with a VALID derived record
        (exactly what `_send_draw` writes: http + parse + cost only)."""
        store = ledger.EnvelopeStore(tmp_path / "study")
        reqs = []
        for i, resp in enumerate(responses):
            req = _req(seed=f"s{i}", probe_id=PROBES[0], cell_id=CELL_IDS[0], order_idx=0)
            env = ledger.build_envelope(
                draw=ledger.DrawIdentity(req.request_sha256, 0), request_body=req.body,
                request_headers={}, response_body=resp, response_headers={},
                http_status=200, bucket="study", model=MODEL, provider=TAG, stage="study")
            store.put(env)
            ledger.record_validation(store, env, valid=True, failures=())
            reqs.append(req)
        manifest = {"model": MODEL, "endpoint_slug": TAG,
                    "coordinates": [{"cell_id": r.cell_id, "probe_id": r.probe_id,
                                     "order_idx": r.order_idx,
                                     "request_sha256": r.request_sha256} for r in reqs]}
        return store, manifest

    def _excluded(self, tmp_path, response):
        se = _study_extract()
        store, manifest = self._store_with(tmp_path, [response])
        ext = se.extract_draws(store, probe_ids=[PROBES[0]], model=MODEL, manifest=manifest)
        rec = ext.records[0]
        return rec.excluded, rec.exclusion_reasons

    def test_a_conforming_study_draw_is_admitted(self, tmp_path):
        snap = _snapshot()
        excluded, reasons = self._excluded(tmp_path, _good_response(snap))
        assert not excluded, reasons

    @pytest.mark.parametrize("label,mutate", [
        ("reasoning tokens 7",
         lambda r: r["usage"]["completion_tokens_details"].__setitem__("reasoning_tokens", 7)),
        ("is_byok true", lambda r: r["openrouter_metadata"].__setitem__("is_byok", True)),
    ], ids=lambda x: x if isinstance(x, str) else "")
    def test_an_audit_failing_study_draw_is_excluded(self, tmp_path, label, mutate):
        snap = _snapshot()
        resp = _good_response(snap)
        mutate(resp)
        excluded, reasons = self._excluded(tmp_path, resp)
        assert excluded, f"a study draw with {label} entered the estimands ({reasons})"

    @pytest.mark.parametrize("label,mutate", [
        ("no reasoning-token evidence at all",
         lambda r: r["usage"].pop("completion_tokens_details")),
        ("no routing metadata at all", lambda r: r.pop("openrouter_metadata")),
        ("wrong selected provider display name",
         lambda r: r["openrouter_metadata"]["endpoints"]["available"][0].__setitem__(
             "provider", "SomeoneElse")),
        ("strategy != direct",
         lambda r: r["openrouter_metadata"].__setitem__("strategy", "fallback")),
        ("attempt != 1", lambda r: r["openrouter_metadata"].__setitem__("attempt", 3)),
        ("two available candidates",
         lambda r: r["openrouter_metadata"]["endpoints"]["available"].append(
             {"provider": "Other", "model": "x", "selected": False})),
        ("undated model evidence",
         lambda r: r["openrouter_metadata"]["endpoints"]["available"][0].__setitem__(
             "model", MODEL)),
    ], ids=lambda x: x if isinstance(x, str) else "")
    def test_the_full_c1_proof_reaches_every_study_draw(self, tmp_path, label, mutate):
        """C1: 'A study response is accepted only if ...' — the proof is written for STUDY
        responses, not only for the promotion-gate probes. R-V7-1 likewise requires the usage
        fields to be PRESENT: an unreported reasoning count is not a zero count."""
        snap = _snapshot()
        resp = _good_response(snap)
        mutate(resp)
        # the frozen proof itself rejects this response ...
        assert not envelope.verify_provider_audit(resp, QWEN, "alibaba", snap).ok \
            or not envelope.verify_reasoning_off(resp).ok
        # ... so the study path must reject it too.
        excluded, reasons = self._excluded(tmp_path, resp)
        assert excluded, (
            f"a study draw that FAILS the frozen C1/R-V7-1 proof ({label}) was admitted to "
            f"the estimands; the per-draw audit is weaker than the gate audit ({reasons})")

    def test_the_superseded_v5_paid_cli_is_disabled(self):
        """R-C5: the v5 four-model logprob runner must refuse all paid stages."""
        hosted = pytest.importorskip("alignment.q2_hosted")
        for stage in ("canary", "smoke"):
            with pytest.raises(SystemExit):
                hosted.main(["--out-dir", "out/scratch", "--stage", stage,
                             "--i-have-authorized-paid-spend"])

    def test_the_pinned_tokenizer_is_verified_locally_and_never_downloaded(self, tmp_path):
        """C2/R-C4: an unverifiable tokenizer means no projection, which means no promotion."""
        sr = _study_run()
        snap = _snapshot()
        src = inspect.getsource(sr.pinned_tokenizer)
        assert "urlopen" not in src and "http" not in src.lower().replace("https://", ""), \
            "the tokenizer loader reaches the network"
        (tmp_path / "tokenizer.json").write_text("{}")
        with pytest.raises(Exception):
            sr.pinned_tokenizer(QWEN, snap, tmp_path)


# ======================================================================================
# Cross-cutting: nothing in the new modules may touch the network
# ======================================================================================

class TestNoNetwork:

    #: `study_run` legitimately owns the single live transport seam; nothing else may.
    PURE = ("study_render", "study_extract", "interlock", "identity", "gate")

    @pytest.mark.parametrize("name", PURE)
    def test_the_pure_modules_contain_no_transport_at_all(self, name):
        path = V7_DIR / f"{name}.py"
        if not path.exists():
            pytest.skip(f"{name}.py not yet written")
        code = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith("#"))
        for banned in ("import urllib", "urlopen(", "requests.post(", "requests.get(",
                       "httpx.", "socket.socket(", "http.client."):
            assert banned not in code, f"{name}.py references {banned}"

    def test_study_run_confines_the_network_to_one_injected_seam(self):
        sr = _study_run()
        src = inspect.getsource(sr)
        opens = [m.start() for m in re.finditer(r"\.open\(|urlopen\(", src)]
        cls = src.index("class SingleAttemptTransport")
        nxt = src.index("\n@dataclass", cls)
        assert opens, "no transport found at all"
        assert all(cls < i < nxt for i in opens), (
            "study_run opens a connection outside `SingleAttemptTransport` — the network is "
            "not a single injectable seam")

    def test_no_module_fires_a_request_on_import(self):
        for name in ("study_render", "study_run", "study_extract", "interlock"):
            path = V7_DIR / f"{name}.py"
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if line and not line[0].isspace():
                    assert "urlopen(" not in line and "requests." not in line, \
                        f"{name}.py issues a module-level request: {line!r}"

    def test_study_run_refuses_paid_execution_without_explicit_authorization(self):
        sr = _study_run()
        src = inspect.getsource(sr)
        assert re.search(r"i[-_]have[-_]authorized[-_]paid[-_]spend", src, re.I), (
            "study_run exposes no explicit paid-spend acknowledgement flag (design "
            "'Staged authorization')")
        parser = sr.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])
