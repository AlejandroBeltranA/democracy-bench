"""No-network readiness suite for `alignment.q2_v7.identity` (Stage-2 v7.2).

Covers the four frozen requirements this module implements:

  1. canonical request hashing — one changed character/role/provider/label/parameter changes
     the hash;
  2. draw identity (R-V7-7) — 25 draws share a request hash but have distinct identities;
     smoke draws 0-4 ARE the first five full-run draws at the same coordinate (reuse), and
     the smoke/full-stage label cannot enter identity;
  3. call-structure enumeration — exactly 528 / 13,200 / 240 / 12,960 (frozen arithmetic);
  4. manifest (R-E6, R-V7-7) — binds every draw identity and request hash plus the endpoint
     snapshot, design/item-bank/payload/guard hashes and runner revision; a byte-identical
     manifest resumes, any mismatch is rejected;
  5. S-F4 anchored parser — table-driven accept/reject, fail closed, never clamps.

Nothing here touches the network; every input is constructed in-process.
"""
from __future__ import annotations

import hashlib
import inspect
import json

import pytest

from alignment.q2_v7 import identity as I


# --------------------------------------------------------------------------- helpers

PROBE_IDS = (
    "pol_ai_due_process", "pol_ai_nhs_triage", "pol_ai_predictive_policing",
    "pol_ai_visa_no_reasons", "pol_ai_welfare_sanction", "pol_deport_no_appeal",
    "pol_dna_database", "pol_free_speech", "pol_id_cards", "pol_protest_ban",
    "pol_stop_search", "pol_surveillance",
)


def _body(*, system="You are a survey respondent.", prompt="Pick one option.",
          model="qwen/qwen3.5-397b-a17b", provider="alibaba", role="user",
          temperature=1.0, max_tokens=4):
    """A structurally realistic frozen-envelope request body (synthetic content only)."""
    return {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": role, "content": prompt}],
        "temperature": temperature,
        "top_p": 1.0,
        "max_tokens": max_tokens,
        "reasoning": {"effort": "none"},
        "provider": {"only": [provider], "allow_fallbacks": False,
                     "require_parameters": True},
        "usage": {"include": True},
    }


def _sha_map(probe_ids=PROBE_IDS):
    """A distinct, deterministic request hash for each of the 528 coordinates."""
    return {c: I.request_sha256(_body(prompt=f"probe={c.probe_id} cell={c.cell_id} "
                                             f"order={c.order_idx}"))
            for c in I.enumerate_coordinates(probe_ids)}


def _smoke_sha_map(full_map):
    """The same hashes, restricted to the 48 smoke coordinates — identical bodies, so the
    smoke run cannot accidentally produce a different request than its full-run twin."""
    return {c: full_map[c] for c in I.enumerate_smoke_coordinates()}


_MANIFEST_HASHES = {
    "endpoint_snapshot_sha256":
        "4b4b11a466cdf3af377a1a96b8478aac72fc2a22290315eac15aff9c780b295f",
    "design_sha256": hashlib.sha256(b"design").hexdigest(),
    "item_bank_sha256": hashlib.sha256(b"item-bank").hexdigest(),
    "payload_sha256": hashlib.sha256(b"payloads").hexdigest(),
    "guard_sha256": hashlib.sha256(b"guards").hexdigest(),
}


def _manifest(sha_map, **overrides):
    kwargs = dict(model="qwen/qwen3.5-397b-a17b", endpoint_slug="alibaba",
                  runner_revision="deadbeef", probe_ids=PROBE_IDS,
                  request_sha_by_coordinate=sha_map, **_MANIFEST_HASHES)
    kwargs.update(overrides)
    return I.build_manifest(**kwargs)


@pytest.fixture(scope="module")
def sha_map():
    return _sha_map()


@pytest.fixture(scope="module")
def manifest(sha_map):
    return _manifest(sha_map)


# ===========================================================================
# 1. Canonical request hashing
# ===========================================================================

def test_canonical_json_is_sorted_compact_and_ascii():
    assert I.canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == '{"a":{"c":3,"d":2},"b":1}'
    # unicode is escaped deterministically, so there is no text-encoding degree of freedom
    assert I.canonical_json({"k": "café"}) == '{"k":"caf\\u00e9"}'
    assert I.canonical_json({"k": "café"}).isascii()


def test_canonical_json_is_insensitive_to_key_insertion_order():
    a = {"model": "m", "messages": [{"role": "user", "content": "x"}], "top_p": 1.0}
    b = {"top_p": 1.0, "messages": [{"content": "x", "role": "user"}], "model": "m"}
    assert I.canonical_sha256(a) == I.canonical_sha256(b)


def test_canonical_json_fails_closed_on_unhashable_values():
    with pytest.raises(ValueError):
        I.canonical_json({"x": float("nan")})
    with pytest.raises(ValueError):
        I.canonical_json({"x": float("inf")})
    with pytest.raises(TypeError):
        I.canonical_json({"x": {1, 2}})


def test_request_sha256_is_lowercase_64_hex():
    sha = I.request_sha256(_body())
    assert I._HEX64.match(sha)


def test_request_sha256_rejects_non_mapping():
    with pytest.raises(I.IdentityError):
        I.request_sha256([("model", "m")])            # type: ignore[arg-type]


def test_identical_bodies_hash_identically():
    assert I.request_sha256(_body()) == I.request_sha256(_body())


PERTURBATIONS = {
    "one prompt character": dict(prompt="Pick one option!"),
    "one prompt character of whitespace": dict(prompt="Pick one option. "),
    "one system character": dict(system="You are a survey respondent!"),
    "message role": dict(role="assistant"),
    "provider tag": dict(provider="digitalocean"),
    "model id": dict(model="deepseek/deepseek-v4-pro"),
    "a parameter value": dict(temperature=0.9999999),
    "max_tokens": dict(max_tokens=5),
}


@pytest.mark.parametrize("label,mutation", sorted(PERTURBATIONS.items()))
def test_single_field_perturbation_changes_the_request_hash(label, mutation):
    assert I.request_sha256(_body()) != I.request_sha256(_body(**mutation)), label


def test_item_label_change_changes_the_request_hash():
    """An item/probe label lives inside the rendered prompt; changing it must move the hash."""
    a = I.request_sha256(_body(prompt="ITEM pol_surveillance: pick one."))
    b = I.request_sha256(_body(prompt="ITEM pol_id_cards: pick one."))
    assert a != b


def test_numeric_type_change_changes_the_request_hash():
    """4 and 4.0 are different wire values and must not collapse to one identity."""
    assert I.canonical_sha256({"max_tokens": 4}) != I.canonical_sha256({"max_tokens": 4.0})


def test_nested_provider_block_perturbation_changes_the_hash():
    a = _body()
    b = _body()
    b["provider"]["allow_fallbacks"] = True
    assert I.request_sha256(a) != I.request_sha256(b)


def test_every_coordinate_gets_a_distinct_request_hash(sha_map):
    assert len(set(sha_map.values())) == I.COORDINATES_PER_MODEL


# ===========================================================================
# 2. Draw identity (R-V7-7)
# ===========================================================================

def test_draw_id_shape_and_roundtrip():
    sha = I.request_sha256(_body())
    ident = I.draw_id(sha, 7)
    assert ident == f"{sha}#draw7"
    assert I.parse_draw_id(ident) == (sha, 7)


@pytest.mark.parametrize("bad_sha", ["", "abc", "Z" * 64, "A" * 64, "a" * 63, None, 12])
def test_draw_id_rejects_a_bad_request_hash(bad_sha):
    with pytest.raises(I.IdentityError):
        I.draw_id(bad_sha, 0)                          # type: ignore[arg-type]


@pytest.mark.parametrize("bad_index", [-1, "0", 1.0, True, None])
def test_draw_id_rejects_a_bad_draw_index(bad_index):
    with pytest.raises(I.IdentityError):
        I.draw_id(I.request_sha256(_body()), bad_index)   # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "not-an-id", "a" * 64, f"{'a' * 64}#draw", 7,
                                 f"{'a' * 64}#draw-1", f"{'a' * 64}#draw01"])
def test_parse_draw_id_fails_closed(bad):
    with pytest.raises(I.IdentityError):
        I.parse_draw_id(bad)                           # type: ignore[arg-type]


def test_25_draws_share_one_request_hash_but_have_distinct_identities():
    sha = I.request_sha256(_body())
    ids = I.coordinate_draw_ids(sha)
    assert len(ids) == I.DRAWS_PER_COORDINATE == 25
    assert len(set(ids)) == 25                       # the body alone could never be the key
    assert {I.parse_draw_id(i)[0] for i in ids} == {sha}
    assert [I.parse_draw_id(i)[1] for i in ids] == list(range(25))


def test_coordinate_draw_ids_refuses_more_than_the_frozen_25():
    sha = I.request_sha256(_body())
    with pytest.raises(I.IdentityError):
        I.coordinate_draw_ids(sha, 26)
    for bad in (0, -1, 2.0, True):
        with pytest.raises(I.IdentityError):
            I.coordinate_draw_ids(sha, bad)           # type: ignore[arg-type]


def test_smoke_draws_are_exactly_the_first_five_full_run_draws():
    """The reuse guarantee: smoke draws 0-4 ARE full-run draws 0-4, never repaid."""
    sha = I.request_sha256(_body())
    assert I.smoke_draw_ids(sha) == I.coordinate_draw_ids(sha)[:5]


def test_stage_label_cannot_enter_draw_identity():
    """R-V7-7: identity is request hash + draw index and NOTHING else."""
    params = set(inspect.signature(I.draw_id).parameters)
    assert params == {"request_sha", "draw_index"}
    # ... and no DrawSpec field records the stage either
    fields = set(I.DrawSpec.__dataclass_fields__)
    assert fields == {"coordinate", "request_sha256", "draw_index"}
    assert not any(w in f for f in fields for w in ("stage", "smoke", "label"))


def test_smoke_and_full_specs_at_one_coordinate_produce_identical_identities(sha_map):
    smoke = I.enumerate_smoke_draws(_smoke_sha_map(sha_map))
    full = I.enumerate_model_draws(PROBE_IDS, sha_map)
    full_by_coord = {}
    for spec in full:
        full_by_coord.setdefault(spec.coordinate, []).append(spec)
    checked = 0
    for spec in smoke:
        twin = full_by_coord[spec.coordinate][spec.draw_index]
        assert spec.identity == twin.identity
        assert spec.request_sha256 == twin.request_sha256
        checked += 1
    assert checked == I.SMOKE_DRAWS_TOTAL


def test_reuse_check_never_repays_a_completed_smoke_draw():
    sha = I.request_sha256(_body())
    check = I.reuse_check(sha, set(I.smoke_draw_ids(sha)))
    assert check.n_reused == 5
    assert check.n_remaining == 20
    assert check.reused == I.coordinate_draw_ids(sha)[:5]
    assert check.remaining == I.coordinate_draw_ids(sha)[5:]
    assert set(check.reused) & set(check.remaining) == set()
    assert len(check.reused) + len(check.remaining) == I.DRAWS_PER_COORDINATE


def test_reuse_check_on_a_fresh_coordinate_pays_for_all_25():
    sha = I.request_sha256(_body())
    check = I.reuse_check(sha, set())
    assert check.n_reused == 0 and check.n_remaining == 25


def test_reuse_check_ignores_other_coordinates_identities():
    mine = I.request_sha256(_body())
    other = I.request_sha256(_body(prompt="a different coordinate"))
    check = I.reuse_check(mine, set(I.coordinate_draw_ids(other)))
    assert check.n_reused == 0 and check.n_remaining == 25


def test_reuse_check_fails_closed_on_an_out_of_range_completed_draw():
    sha = I.request_sha256(_body())
    with pytest.raises(I.IdentityError):
        I.reuse_check(sha, {I.draw_id(sha, 25)})
    with pytest.raises(I.IdentityError):
        I.reuse_check(sha, set(I.coordinate_draw_ids(sha)), n_draws=5)


def test_reuse_check_rejects_a_bare_string():
    sha = I.request_sha256(_body())
    with pytest.raises(I.IdentityError):
        I.reuse_check(sha, I.draw_id(sha, 0))          # type: ignore[arg-type]


def test_assert_unique_draw_ids_detects_a_duplicate():
    sha = I.request_sha256(_body())
    ids = list(I.coordinate_draw_ids(sha))
    I.assert_unique_draw_ids(ids)
    with pytest.raises(I.IdentityError):
        I.assert_unique_draw_ids(ids + [ids[0]])


# ===========================================================================
# 3. Call-structure enumeration (frozen arithmetic)
# ===========================================================================

def test_frozen_counts_are_exactly_528_13200_240_12960():
    c = I.call_structure()
    assert c["coordinates_per_model"] == 528
    assert c["draws_per_model"] == 13_200
    assert c["smoke_coordinates"] == 48
    assert c["smoke_draws_total"] == 240
    assert c["additional_draws_after_smoke"] == 12_960
    assert c["smoke_draws_total"] + c["additional_draws_after_smoke"] == 13_200
    assert (c["cells"], c["probes"], c["orders"], c["draws_per_coordinate"]) == (11, 12, 4, 25)


def test_enumerate_coordinates_is_exactly_528_unique():
    coords = I.enumerate_coordinates(PROBE_IDS)
    assert len(coords) == 528 == len(set(coords))
    assert len({c.cell_id for c in coords}) == 11
    assert len({c.probe_id for c in coords}) == 12
    assert {c.order_idx for c in coords} == {0, 1, 2, 3}


def test_enumerate_smoke_coordinates_is_48_and_a_subset_of_the_528():
    smoke = I.enumerate_smoke_coordinates()
    assert len(smoke) == 48 == len(set(smoke))
    assert set(smoke) <= set(I.enumerate_coordinates(PROBE_IDS))
    assert {c.probe_id for c in smoke} == set(I.SMOKE_PROBES)
    assert len({c.cell_id for c in smoke}) == 6


def test_model_draws_are_exactly_13200_unique_identities(sha_map):
    specs = I.enumerate_model_draws(PROBE_IDS, sha_map)
    assert len(specs) == 13_200
    assert len({s.identity for s in specs}) == 13_200
    assert len({s.request_sha256 for s in specs}) == 528
    assert {s.draw_index for s in specs} == set(range(25))


def test_smoke_draws_are_exactly_240_and_leave_12960_additional(sha_map):
    smoke = I.enumerate_smoke_draws(_smoke_sha_map(sha_map))
    full = I.enumerate_model_draws(PROBE_IDS, sha_map)
    smoke_ids = {s.identity for s in smoke}
    full_ids = {s.identity for s in full}
    assert len(smoke_ids) == 240
    assert smoke_ids <= full_ids                      # every smoke draw is a full-run draw
    assert len(full_ids - smoke_ids) == 12_960        # additional post-promotion draws
    assert len(smoke_ids) + len(full_ids - smoke_ids) == 13_200


def test_enumeration_rejects_a_wrong_probe_set():
    with pytest.raises(I.CountMismatch):
        I.enumerate_coordinates(PROBE_IDS[:11])
    with pytest.raises(I.CountMismatch):
        I.enumerate_coordinates(PROBE_IDS + ("pol_extra",))
    with pytest.raises(I.IdentityError):
        I.enumerate_coordinates(PROBE_IDS[:11] + (PROBE_IDS[0],))     # duplicate
    swapped = tuple(p for p in PROBE_IDS if p != "pol_surveillance") + ("pol_other",)
    with pytest.raises(I.IdentityError):
        I.enumerate_coordinates(swapped)                              # smoke probe missing


def test_enumerate_draws_fails_closed_on_an_unbound_coordinate(sha_map):
    partial = dict(sha_map)
    partial.pop(next(iter(partial)))
    with pytest.raises(I.IdentityError):
        I.enumerate_model_draws(PROBE_IDS, partial)


def test_coordinate_keys_are_accepted_as_well_as_coordinate_objects(sha_map):
    by_key = {c.key: s for c, s in sha_map.items()}
    specs = I.enumerate_model_draws(PROBE_IDS, by_key)
    assert len(specs) == 13_200


def test_frozen_constants_match_the_existing_stage2_runner():
    """The v7 module restates the frozen cells/probes; this proves it never diverges."""
    from alignment import q2_hosted as Q
    assert I.HOSTED_CELLS == Q.HOSTED_CELLS
    assert I.SMOKE_CELLS == Q.SMOKE_CELLS
    assert I.SMOKE_PROBES == Q.SMOKE_PROBES
    assert I.N_ORDERS == Q.N_ORDERS == len(Q.WILLIAMS_ORDERS_4)
    assert I.N_PROBES == Q.N_PROBES
    assert I.DRAWS_PER_COORDINATE == Q.SAMPLES_PER_ORDER
    assert I.SMOKE_DRAWS_PER_COORDINATE == Q.SAMPLING_SMOKE_DRAWS
    assert I.COORDINATES_PER_MODEL == Q.MATRIX_CALLS_PER_MODEL
    assert sorted(PROBE_IDS) == sorted(Q.load_probe_items("ENG"))
    # the v7 cell_id spelling matches the frozen local cell ids
    assert I.Coordinate("data_only", "system_guard", "p", 0).cell_id == \
        Q.cid_for("data_only", "system_guard")


# ===========================================================================
# 4. Manifest (R-E6, R-V7-7)
# ===========================================================================

def test_manifest_binds_every_draw_identity_and_request_hash(manifest, sha_map):
    assert manifest.n_draws == 13_200
    assert manifest.n_coordinates == 528
    specs = I.enumerate_model_draws(PROBE_IDS, sha_map)
    assert manifest.draw_identities == tuple(s.identity for s in specs)
    assert set(manifest.request_sha256s) == set(sha_map.values())
    assert len(set(manifest.request_sha256s)) == 528


def test_manifest_binds_the_snapshot_design_and_runner_revision(manifest):
    body = manifest.body
    assert body["endpoint_snapshot_sha256"] == _MANIFEST_HASHES["endpoint_snapshot_sha256"]
    for key in ("design_sha256", "item_bank_sha256", "payload_sha256", "guard_sha256"):
        assert body[key] == _MANIFEST_HASHES[key]
    assert body["runner_revision"] == "deadbeef"
    assert body["counts"] == I.call_structure()


def test_manifest_hash_is_deterministic(sha_map):
    assert _manifest(sha_map).sha256 == _manifest(sha_map).sha256
    assert _manifest(sha_map).raw == _manifest(sha_map).raw


MANIFEST_PERTURBATIONS = {
    "model": dict(model="deepseek/deepseek-v4-pro"),
    "endpoint slug": dict(endpoint_slug="digitalocean"),
    "endpoint snapshot": dict(endpoint_snapshot_sha256=hashlib.sha256(b"other").hexdigest()),
    "design hash": dict(design_sha256=hashlib.sha256(b"design v8").hexdigest()),
    "item bank hash": dict(item_bank_sha256=hashlib.sha256(b"other bank").hexdigest()),
    "payload hash": dict(payload_sha256=hashlib.sha256(b"other payloads").hexdigest()),
    "guard hash": dict(guard_sha256=hashlib.sha256(b"other guards").hexdigest()),
    "runner revision": dict(runner_revision="cafebabe"),
}


@pytest.mark.parametrize("label,override", sorted(MANIFEST_PERTURBATIONS.items()))
def test_changing_one_bound_input_changes_the_manifest_hash(manifest, sha_map,
                                                            label, override):
    assert _manifest(sha_map, **override).sha256 != manifest.sha256, label


def test_changing_one_prompt_character_changes_the_manifest_hash(manifest, sha_map):
    perturbed = dict(sha_map)
    victim = I.enumerate_coordinates(PROBE_IDS)[0]
    perturbed[victim] = I.request_sha256(_body(prompt="Pick one option. "))
    assert _manifest(perturbed).sha256 != manifest.sha256


def test_manifest_rejects_a_malformed_bound_hash(sha_map):
    with pytest.raises(I.IdentityError):
        _manifest(sha_map, design_sha256="not-a-hash")
    with pytest.raises(I.IdentityError):
        _manifest(sha_map, runner_revision="")


def test_manifest_is_written_atomically_and_is_canonical(tmp_path, manifest):
    path = tmp_path / "run" / "manifest.json"
    decision = I.write_or_resume_manifest(path, manifest)
    assert decision.created and not decision.resumed and decision.may_run
    assert decision.sha256 == manifest.sha256
    assert path.read_bytes() == manifest.raw
    assert not list(path.parent.glob("*.tmp"))
    reloaded = json.loads(path.read_text())
    assert len(reloaded["draw_identities"]) == 13_200
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest.sha256


def test_identical_manifest_resumes_after_a_crash(tmp_path, sha_map):
    """R-E6 fix: the v5 runner refused ANY existing manifest, so a crash after manifest
    creation could not resume. An identical recomputation now resumes."""
    path = tmp_path / "manifest.json"
    first = I.write_or_resume_manifest(path, _manifest(sha_map))
    assert first.created
    before = path.read_bytes()
    second = I.write_or_resume_manifest(path, _manifest(sha_map))   # "restart"
    assert second.resumed and not second.created and second.may_run
    assert second.sha256 == first.sha256
    assert path.read_bytes() == before                              # never rewritten


@pytest.mark.parametrize("label,override", sorted(MANIFEST_PERTURBATIONS.items()))
def test_mismatched_manifest_is_rejected_on_restart(tmp_path, sha_map, label, override):
    path = tmp_path / "manifest.json"
    I.write_or_resume_manifest(path, _manifest(sha_map))
    stored = path.read_bytes()
    with pytest.raises(I.ManifestMismatch):
        I.write_or_resume_manifest(path, _manifest(sha_map, **override))
    assert path.read_bytes() == stored                              # never repaired


def test_mismatched_request_body_is_rejected_on_restart(tmp_path, sha_map):
    path = tmp_path / "manifest.json"
    I.write_or_resume_manifest(path, _manifest(sha_map))
    perturbed = dict(sha_map)
    victim = I.enumerate_coordinates(PROBE_IDS)[3]
    perturbed[victim] = I.request_sha256(_body(prompt="reworded probe"))
    with pytest.raises(I.ManifestMismatch) as err:
        I.write_or_resume_manifest(path, _manifest(perturbed))
    assert "coordinates" in str(err.value)


def test_corrupt_manifest_file_is_rejected_not_repaired(tmp_path, manifest):
    path = tmp_path / "manifest.json"
    path.write_text("{ this is not json")
    with pytest.raises(I.ManifestMismatch):
        I.write_or_resume_manifest(path, manifest)
    assert path.read_text() == "{ this is not json"


def test_noncanonical_but_equal_manifest_is_rejected(tmp_path, manifest):
    """Byte-identity is the rule: a re-indented file with identical fields does not resume."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest.body, indent=2, sort_keys=True))
    with pytest.raises(I.ManifestMismatch):
        I.write_or_resume_manifest(path, manifest)


def test_manifest_difference_report_names_the_changed_field(manifest, sha_map):
    other = _manifest(sha_map, runner_revision="cafebabe")
    diffs = I.manifest_differences(manifest.raw, other)
    assert any("runner_revision" in d for d in diffs)
    assert I.manifest_is_identical(manifest.raw, manifest)
    assert not I.manifest_is_identical(manifest.raw, other)


# ===========================================================================
# 5. S-F4 anchored leading-option parser
# ===========================================================================

ACCEPTED = {
    "bare digit": ("3", 3),
    "surrounding spaces": ("  3  ", 3),
    "trailing period": ("3.", 3),
    "parenthesized": ("(3)", 3),
    "bracketed": ("[2]", 2),
    "list punctuation": ("3)", 3),
    "trailing comma": ("4,", 4),
    "trailing colon": ("1:", 1),
    "leading newline": ("\n2\n", 2),
    "tab padded": ("\t1\t", 1),
    "first option": ("1", 1),
    "last option": ("4", 4),
    "spaced parens": ("( 3 )", 3),
    "paren then period": ("(3).", 3),
}

REJECTED = {
    "prose before the digit": "I choose 3",
    "prose before the digit, capitalized": "The answer is 3",
    "option word prefix": "Option 3",
    "two candidate digits concatenated": "34",
    "two candidate digits with prose": "3 or 4",
    "two candidate digits spaced": "3 4",
    "two candidate digits on separate lines": "3\n4",
    "leading zero padding": "03",
    "below range": "0",
    "above range": "5",
    "far above range": "9",
    "empty string": "",
    "whitespace only": "   ",
    "newline only": "\n",
    "non numeric word": "three",
    "refusal": "I cannot answer that.",
    "negative": "-3",
    "decimal": "1.5",
    "digit then prose": "3 - because it protects rights",
    "digit then sentence": "3. Because it protects rights.",
    "json wrapper": '{"choice": 3}',
    "markdown emphasis": "**3**",
    "unbalanced bracket": "(3",
    "trailing bracket mismatch": "[3)",
    "none": None,
}


@pytest.mark.parametrize("label,case", sorted(ACCEPTED.items()))
def test_anchored_parser_accepts_valid_forms(label, case):
    text, option = case
    res = I.parse_option(text)
    assert res.ok and res.reason == I.PARSE_OK, label
    assert res.option == option
    assert res.index == option - 1                       # 0-based, as parse_choice returns
    assert I.parse_choice_anchored(text) == option - 1


@pytest.mark.parametrize("label,text", sorted(REJECTED.items(), key=lambda kv: kv[0]))
def test_anchored_parser_rejects_every_invalid_form(label, text):
    res = I.parse_option(text)
    assert not res.ok, label
    assert res.index is None and res.option is None      # never guessed, never clamped
    assert res.reason in (I.PARSE_EMPTY, I.PARSE_NOT_ANCHORED, I.PARSE_OUT_OF_RANGE)
    assert I.parse_choice_anchored(text) is None


@pytest.mark.parametrize("text,reason", [
    (None, I.PARSE_EMPTY),
    ("", I.PARSE_EMPTY),
    ("   ", I.PARSE_EMPTY),
    ("I choose 3", I.PARSE_NOT_ANCHORED),
    ("34", I.PARSE_NOT_ANCHORED),
    ("3 or 4", I.PARSE_NOT_ANCHORED),
    ("three", I.PARSE_NOT_ANCHORED),
    ("0", I.PARSE_OUT_OF_RANGE),
    ("5", I.PARSE_OUT_OF_RANGE),
])
def test_anchored_parser_reports_the_fail_closed_reason(text, reason):
    assert I.parse_option(text).reason == reason


def test_anchored_parser_never_clamps_out_of_range_digits():
    assert I.parse_choice_anchored("5") is None          # not clamped to option 4
    assert I.parse_choice_anchored("0") is None          # not clamped to option 1
    assert I.parse_choice_anchored("9") is None


def test_anchored_parser_respects_n_options():
    assert I.parse_choice_anchored("3", n_options=2) is None
    assert I.parse_choice_anchored("2", n_options=2) == 1


def test_anchored_parser_validates_n_options():
    for bad in (0, -1, 10, 4.0, True, "4"):
        with pytest.raises(I.IdentityError):
            I.parse_option("3", bad)                     # type: ignore[arg-type]


def test_anchored_parser_rejects_non_string_replies():
    with pytest.raises(I.IdentityError):
        I.parse_option(3)                                # type: ignore[arg-type]
    with pytest.raises(I.IdentityError):
        I.parse_option(["3"])                            # type: ignore[arg-type]


def test_anchored_parser_is_strictly_stricter_than_the_unanchored_one():
    """S-F4: the old `re.search` rule extracts the first integer anywhere in the reply."""
    from alignment.instrument.measure import parse_choice
    for text in ("I choose 3", "The answer is 3", "Option 3", "3 or 4"):
        assert parse_choice(text, 4) is not None         # old behavior: accepted
        assert I.parse_choice_anchored(text) is None     # S-F4: fails closed
    for text, _ in ACCEPTED.values():
        if parse_choice(text, 4) is not None:            # anything the new rule accepts,
            assert parse_choice(text, 4) == I.parse_choice_anchored(text)   # the old one agrees
