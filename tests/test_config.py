import pytest
from pydantic import ValidationError

from modelpin.config import DEFAULT_PROVIDER, ConfigError, ModelpinConfig, load_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert isinstance(cfg, ModelpinConfig)
    assert cfg.runs == 3
    assert cfg.scenarios_dir == "scenarios"
    # Zero-config must route to the implemented adapter, never the Anthropic stub.
    assert cfg.providers == [DEFAULT_PROVIDER] == ["openai"]


def test_parses_yaml(tmp_path):
    p = tmp_path / "modelpin.yaml"
    p.write_text("models:\n  - m1\nruns: 7\nproviders:\n  - anthropic\n")
    cfg = load_config(p)
    assert cfg.models == ["m1"]
    assert cfg.runs == 7
    assert cfg.providers == ["anthropic"]


def test_empty_yaml_file_yields_defaults(tmp_path):
    p = tmp_path / "modelpin.yaml"
    p.write_text("")
    cfg = load_config(p)
    assert cfg.providers == ["openai"]


def test_runs_must_be_at_least_one():
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        ModelpinConfig(runs=0)


def test_malformed_yaml_raises_config_error(tmp_path):
    p = tmp_path / "modelpin.yaml"
    p.write_text("models: [unclosed\n  : :")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(p)


def test_non_mapping_yaml_raises_config_error(tmp_path):
    p = tmp_path / "modelpin.yaml"
    p.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(p)


def test_invalid_setting_type_raises_config_error(tmp_path):
    p = tmp_path / "modelpin.yaml"
    p.write_text("runs: not-a-number\n")
    with pytest.raises(ConfigError, match="invalid settings"):
        load_config(p)
