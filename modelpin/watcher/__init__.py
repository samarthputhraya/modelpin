"""Watcher — tracks model release/deprecation state. See spec section 4.1.

Phase 0: load the shipped community registry (data/models.json).
TODO (Phase 1): refresh from provider model-list endpoints + deprecation pages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from modelpin.models import Model, ModelStatus


def _registry_path() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "data" / "models.json",  # repo-root/data (editable install)
        Path.cwd() / "data" / "models.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_registry(path: Optional[Path] = None) -> list[Model]:
    p = path or _registry_path()
    raw = json.loads(p.read_text())
    return [Model(**m) for m in raw.get("models", [])]


def get_model(model_id: str, registry: Optional[list[Model]] = None) -> Optional[Model]:
    reg = registry if registry is not None else load_registry()
    return next((m for m in reg if m.id == model_id), None)


def deprecations(registry: Optional[list[Model]] = None) -> list[Model]:
    reg = registry if registry is not None else load_registry()
    return [m for m in reg if m.status in (ModelStatus.deprecated, ModelStatus.retired)]
