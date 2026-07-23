"""The /init-deck question-spec walker (design §3): one branch rule, tested."""
from __future__ import annotations

from slidecraft.scripts import init_interview as iv

SPEC = {
    "questions": [
        {"id": "topic", "prompt": "Topic", "options": ["Skip"]},          # leaf
        {"id": "audience", "prompt": "Who?",
         "options": ["Students", "Experts"],
         "follow_up": {"Students": {"id": "deck_subtype", "prompt": "Kind?",
                                    "options": ["Lecture", "Class"]}}},    # branching
    ]
}


def test_branching_preset_with_followup_returns_it():
    fu = iv.follow_up(SPEC, "audience", "Students")
    assert isinstance(fu, dict) and fu["id"] == "deck_subtype"


def test_branching_preset_without_followup_returns_none():
    assert iv.follow_up(SPEC, "audience", "Experts") is None


def test_branching_other_defers_to_llm():
    assert iv.follow_up(SPEC, "audience", "Investors") is iv.LLM_DECIDES


def test_leaf_preset_returns_none():
    assert iv.follow_up(SPEC, "topic", "Skip") is None


def test_leaf_other_triggers_nothing():
    # The whole point of §3.1: a leaf "Other" is just the answer — never LLM.
    assert iv.follow_up(SPEC, "topic", "Object Tracking") is None


def test_unknown_question_raises():
    import pytest
    with pytest.raises(KeyError):
        iv.follow_up(SPEC, "nope", "x")


def test_shipped_spec_loads_and_has_audience_branch():
    spec = iv.load_spec()
    assert iv.follow_up(spec, "audience", "Students")["id"] == "deck_subtype"
    assert iv.follow_up(spec, "topic", "anything") is None
