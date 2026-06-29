"""Rationale capture + paraphrase variation + parse diagnostics (NEXT_EXPERIMENT_DESIGN 5 & 7).

These cover the elicitation upgrades:
  * the scored answer is still only the leading option number;
  * a rationale, when collected, is stored verbatim and never changes the distribution;
  * variation across samples can come from paraphrases and option order, not just temperature;
  * every elicitation carries valid/invalid parse counts and the raw answers.
"""
import numpy as np
import pytest

from alignment.instrument import measure as M

ITEM = {
    "id": "demo",
    "prompt_text": "Should the council spend more on parks?",
    "scale": {"labels": ["Definitely not", "Probably not", "Probably yes", "Definitely yes"]},
}


def test_backward_compatible_distribution_is_unchanged():
    # elicit_item_distribution must still return the same vector it always did.
    seq = iter(["3", "3", "4", "3", "4", "3"] * 4)
    dist = M.elicit_item_distribution(lambda _p: next(seq), ITEM, n_samples=24)
    assert dist.shape == (4,)
    assert abs(dist.sum() - 1.0) < 1e-9
    assert dist[2] > dist[3] > 0  # mostly "3", some "4"


def test_rationale_is_stored_but_only_the_number_is_scored():
    # The model answers "3 because ..." — option 3 (index 2) is scored, prose is kept as reason.
    answer = "3 — parks improve wellbeing and the surveyed public clearly wants more of them."
    res = M.elicit_item(lambda _p: answer, ITEM, n_samples=5, collect_rationale=True)
    assert res.distribution.tolist() == [0.0, 0.0, 1.0, 0.0]   # all mass on option 3
    assert res.valid == 5 and res.invalid == 0
    assert all(s.reason == answer for s in res.samples)         # prose preserved verbatim
    assert all(s.canonical == 2 for s in res.samples)


def test_split_choice_reason():
    idx, reason = M.split_choice_reason("2. Because services matter.", 4)
    assert idx == 1
    assert reason == "2. Because services matter."
    none_idx, none_reason = M.split_choice_reason("no number here", 4)
    assert none_idx is None
    assert none_reason == "no number here"


def test_rationale_prompt_asks_for_number_then_reason():
    p = M.forced_choice_prompt(ITEM, collect_rationale=True)
    assert "brief one-sentence reason" in p
    plain = M.forced_choice_prompt(ITEM, collect_rationale=False)
    assert "Reply with only the number." in plain


def test_paraphrases_rotate_and_are_recorded():
    seen = []
    item = {**ITEM, "paraphrases": ["Do you back more park funding?", "More money for parks?"]}

    def spy(prompt):
        seen.append(prompt)
        return "4"

    res = M.elicit_item(spy, item, n_samples=6, paraphrases=item["paraphrases"])
    # 3 wordings (canonical + 2 paraphrases) rotated across 6 samples
    assert {s.paraphrase_id for s in res.samples} == {0, 1, 2}
    assert any(item["prompt_text"] in p for p in seen)
    assert any("back more park funding" in p for p in seen)
    assert any("More money for parks" in p for p in seen)
    assert res.diagnostics(include_raw=False)["n_paraphrases"] == 3


def test_parse_diagnostics_count_invalid_answers():
    # alternate a valid "1" and an unreadable "banana"
    seq = iter(["1", "banana"] * 5)
    res = M.elicit_item(lambda _p: next(seq), ITEM, n_samples=10)
    assert res.valid == 5
    assert res.invalid == 5
    assert res.parse_rate == 0.5
    # distribution is built only from the 5 valid answers
    assert res.distribution.tolist() == [1.0, 0.0, 0.0, 0.0]


def test_diagnostics_block_is_json_friendly():
    import json
    res = M.elicit_item(lambda _p: "2 because", ITEM, n_samples=3, collect_rationale=True)
    block = res.diagnostics()
    json.dumps(block)  # must not raise
    assert block["valid"] == 3
    assert len(block["samples"]) == 3
    assert block["samples"][0]["reason"] == "2 because"


def test_fail_closed_still_raises_on_all_invalid():
    with pytest.raises(M.ElicitationError):
        M.elicit_item(lambda _p: "banana", ITEM, n_samples=8)


def test_concurrency_matches_serial_for_pure_elicitor():
    # a pure, thread-safe elicitor (answer depends only on its input) must give byte-identical
    # results whether sampled serially or through the thread pool — concurrency only parallelises
    # the calls, it must not change the planned order/paraphrase sequence or the distribution.
    calls = []

    def elic(prompt):
        return str((len(prompt) % 3) + 1)

    serial = M.elicit_item(elic, ITEM, n_samples=24, shuffle=True, seed=5, max_workers=1)
    concurrent = M.elicit_item(elic, ITEM, n_samples=24, shuffle=True, seed=5, max_workers=8)
    assert serial.distribution.tolist() == concurrent.distribution.tolist()
    assert [s.order for s in serial.samples] == [s.order for s in concurrent.samples]
    assert [s.raw for s in serial.samples] == [s.raw for s in concurrent.samples]
