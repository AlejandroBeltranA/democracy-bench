"""End-to-end smoke test of the policy-delegate Inspect task with a deterministic mock model.

Proves the policy axis runs on the standard Inspect task/solver/scorer framework (the
"measurable with existing tooling" claim) and produces real representation / protective-mass
scores with no network — the mock returns numeric answers on a fixed pattern.
"""
import pytest

inspect_ai = pytest.importorskip("inspect_ai")
from inspect_ai import eval as inspect_eval  # noqa: E402
from inspect_ai.model import ModelOutput, get_model  # noqa: E402

from alignment.policy_inspect import policy_delegate  # noqa: E402


def _eval_for_test(task, model):
    return inspect_eval(task, model=model, display="none", log_realtime=False, ctl_server=False)


def _mock_model(pattern):
    state = {"i": 0}

    def fn(input, tools, tool_choice, config):
        s = pattern[state["i"] % len(pattern)]
        state["i"] += 1
        return ModelOutput.from_content("mockllm/model", s)

    return get_model("mockllm/model", custom_outputs=fn)


def test_task_builds_with_full_item_set():
    t = policy_delegate(mode="default")
    assert len(t.dataset) >= 60  # 50 contestable + 12 floor


def test_all_seven_modes_build():
    for mode in __import__("alignment.policy_delegate_stress", fromlist=["PROMPT_MODES"]).PROMPT_MODES:
        assert len(policy_delegate(mode=mode).dataset) >= 60


def test_contestable_eval_scores_representation():
    model = _mock_model(["3", "3", "4", "2", "3", "4"])
    logs = _eval_for_test(policy_delegate(item_class="contestable", samples=6), model)
    log = logs[0]
    assert log.status == "success"
    assert log.results.scores
    for s in log.samples:
        rep = float(s.scores["policy_scorer"].value)
        assert 0.0 <= rep <= 1.0


def test_floor_eval_scores_protective_mass():
    model = _mock_model(["4", "4", "3", "4"])  # leans to high index = protective for floor_dir +1
    logs = _eval_for_test(policy_delegate(item_class="floor", samples=6), model)
    log = logs[0]
    assert log.status == "success"
    floor_sample = log.samples[0]
    meta = floor_sample.scores["policy_scorer"].metadata
    assert "protective_mass" in meta
    assert 0.0 <= meta["protective_mass"] <= 1.0


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        policy_delegate(mode="not_a_mode")


def test_matched_reflex_runs_and_reports_actor_effect():
    from alignment.policy_inspect import matched_reflex
    t = matched_reflex(samples=6)
    assert len(t.dataset) >= 12  # >= 6 matched pairs x 2 actors
    model = _mock_model(["4", "4", "3", "4"])  # protective answers
    log = _eval_for_test(matched_reflex(samples=6), model)[0]
    assert log.status == "success"
    # the matched_ai_excess metric is computed and surfaced in the scorer results
    metric_names = [m for sc in log.results.scores for m in sc.metrics]
    assert "matched_ai_excess" in metric_names
