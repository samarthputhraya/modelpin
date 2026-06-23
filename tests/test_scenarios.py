"""Tests for scenario loading + error handling (no network)."""

import pytest

from modelpin.scenarios import ScenarioError, load_scenarios


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
