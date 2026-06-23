from modelpin.models import DiffVerdict, Scenario, Trace, ToolCall


def test_scenario_roundtrip():
    s = Scenario(id="s1", name="demo", input={"messages": []})
    assert Scenario(**s.model_dump()).id == "s1"


def test_trace_defaults():
    t = Trace(scenario_id="s1", model_id="m", tool_calls=[ToolCall(name="lookup_order")])
    assert t.tool_calls[0].name == "lookup_order"
    assert t.refused is False


def test_verdict_enum():
    assert DiffVerdict("regression") == DiffVerdict.regression
