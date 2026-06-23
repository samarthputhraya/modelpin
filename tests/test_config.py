from modelpin.config import ModelpinConfig, load_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert isinstance(cfg, ModelpinConfig)
    assert cfg.runs == 3
    assert cfg.scenarios_dir == "scenarios"
    assert cfg.providers == ["openai", "anthropic"]  # google removed (no adapter)


def test_parses_yaml(tmp_path):
    p = tmp_path / "modelpin.yaml"
    p.write_text("models:\n  - m1\nruns: 7\nproviders:\n  - anthropic\n")
    cfg = load_config(p)
    assert cfg.models == ["m1"]
    assert cfg.runs == 7
    assert cfg.providers == ["anthropic"]
