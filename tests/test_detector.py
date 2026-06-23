from modelpin.detector import models_used


def test_detects_model_strings(tmp_path):
    (tmp_path / "app.py").write_text('MODEL = "claude-opus-4-6"\nOTHER = "gpt-5.2"\n')
    (tmp_path / "cfg.yaml").write_text("model: gemini-2.5-pro\n")
    found = models_used(tmp_path)
    assert "claude-opus-4-6" in found
    assert "gpt-5.2" in found
    assert "gemini-2.5-pro" in found
