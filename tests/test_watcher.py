import json

from modelpin.watcher import deprecations, get_model, load_registry


def test_registry_includes_current_anthropic_ids():
    ids = {m.id for m in load_registry()}
    assert {"claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"} <= ids


def test_get_model_hit_and_miss():
    assert get_model("claude-opus-4-8") is not None
    assert get_model("totally-made-up-model") is None


def test_deprecations_filters_to_deprecated_and_retired(tmp_path):
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "a", "provider": "x", "status": "active"},
                    {"id": "b", "provider": "x", "status": "deprecated"},
                    {"id": "c", "provider": "x", "status": "retired"},
                ]
            }
        )
    )
    reg = load_registry(p)
    assert {m.id for m in deprecations(reg)} == {"b", "c"}
