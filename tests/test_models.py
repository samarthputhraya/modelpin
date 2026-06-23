import pytest

from modelpin.models import DiffVerdict, Scenario, Trace, ToolCall


def test_scenario_roundtrip():
    s = Scenario(id="s1", name="demo", input={"messages": []})
    assert Scenario(**s.model_dump()).id == "s1"


def test_scenario_allows_empty_messages_for_offline_path():
    # The fake/offline provider ignores messages, so an empty list must stay valid.
    assert Scenario(id="s1", name="demo", input={"messages": []}).input["messages"] == []


def test_scenario_rejects_missing_messages():
    with pytest.raises(ValueError, match="messages must be a list"):
        Scenario(id="s1", name="demo", input={})


def test_scenario_rejects_non_list_messages():
    with pytest.raises(ValueError, match="messages must be a list"):
        Scenario(id="s1", name="demo", input={"messages": "hi"})


def test_scenario_rejects_non_list_tools():
    with pytest.raises(ValueError, match="tools must be a list"):
        Scenario(id="s1", name="demo", input={"messages": [], "tools": "lookup"})


def test_trace_defaults():
    t = Trace(scenario_id="s1", model_id="m", tool_calls=[ToolCall(name="lookup_order")])
    assert t.tool_calls[0].name == "lookup_order"
    assert t.refused is False


def test_verdict_enum():
    assert DiffVerdict("regression") == DiffVerdict.regression
