"""Tests for baseline persistence (no network)."""

import os

import pytest

from modelpin.models import ToolCall, Trace
from modelpin.storage import BaselineError, baseline_path, load_baseline, save_baseline


def _traces():
    return {
        "s1": [
            Trace(scenario_id="s1", model_id="m", run_idx=i, tool_calls=[ToolCall(name="t")])
            for i in range(3)
        ]
    }


def test_save_then_load_roundtrip(tmp_path):
    save_baseline(_traces(), "gpt-4o-mini", tmp_path)
    loaded = load_baseline("gpt-4o-mini", tmp_path)
    assert len(loaded["s1"]) == 3
    assert loaded["s1"][0].tool_calls[0].name == "t"


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    path = save_baseline(_traces(), "gpt-4o-mini", tmp_path)
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_failed_save_leaves_prior_baseline_intact(tmp_path, monkeypatch):
    # Record a good baseline, then make the next write blow up mid-flight. Because the
    # write goes to a temp file before os.replace, the existing baseline must survive.
    save_baseline(_traces(), "gpt-4o-mini", tmp_path)

    real_replace = os.replace

    def _boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        save_baseline(_traces(), "gpt-4o-mini", tmp_path)
    monkeypatch.setattr(os, "replace", real_replace)

    # the original baseline is still loadable and uncorrupted
    loaded = load_baseline("gpt-4o-mini", tmp_path)
    assert len(loaded["s1"]) == 3


def test_model_id_with_slashes_is_sanitized(tmp_path):
    # provider/model style ids must not escape the store directory
    save_baseline(_traces(), "openai/gpt-4o", tmp_path)
    p = baseline_path("openai/gpt-4o", tmp_path)
    assert p.parent == tmp_path
    assert load_baseline("openai/gpt-4o", tmp_path)["s1"]


def test_missing_baseline_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="No baseline"):
        load_baseline("never-recorded", tmp_path)


def test_corrupt_baseline_raises_baseline_error(tmp_path):
    path = baseline_path("gpt-4o-mini", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not valid json")
    with pytest.raises(BaselineError, match="corrupt"):
        load_baseline("gpt-4o-mini", tmp_path)
