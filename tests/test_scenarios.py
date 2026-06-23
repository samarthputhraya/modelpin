"""Tests for scenario loading + error handling (no network)."""

from pathlib import Path

import pytest

from modelpin.scenarios import ScenarioError, load_scenarios

REPO = Path(__file__).resolve().parents[1]


def test_missing_directory_returns_empty(tmp_path):
    assert load_scenarios(tmp_path / "nope") == []


def test_loads_valid_scenarios(tmp_path):
    (tmp_path / "a.json").write_text(
        '{"id": "a", "name": "A", "input": {"messages": [{"role": "user", "content": "hi"}]}}'
    )
    scenarios = load_scenarios(tmp_path)
    assert [s.id for s in scenarios] == ["a"]


def test_malformed_json_raises_scenario_error_naming_the_file(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{ not valid json")
    with pytest.raises(ScenarioError, match="broken.json"):
        load_scenarios(tmp_path)


def test_invalid_scenario_raises_scenario_error(tmp_path):
    # valid JSON, but the scenario fails model validation (messages not a list)
    (tmp_path / "x.json").write_text('{"id": "x", "name": "X", "input": {"messages": "nope"}}')
    with pytest.raises(ScenarioError, match="not a valid scenario"):
        load_scenarios(tmp_path)


def test_bundled_evaluation_suite_loads_and_validates():
    """The shipped examples/suite must be 8 valid scenarios with non-empty messages —
    guards the JSON + schema offline so a typo can't ship broken."""
    scenarios = load_scenarios(REPO / "examples" / "suite")
    assert len(scenarios) == 8
    ids = {s.id for s in scenarios}
    assert {"refund_request", "decline_pii", "summarize_ticket"} <= ids
    for s in scenarios:
        assert s.input.get("messages"), f"{s.id} has no messages"
    # the agent scenarios carry canned tool_results for deterministic multi-step replay
    agents = [s for s in scenarios if s.kind == "agent"]
    assert agents and all(s.input.get("tool_results") for s in agents)
