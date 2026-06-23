"""Load and validate modelpin.yaml. See spec sections 3-4."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_FILE = "modelpin.yaml"


class ModelpinConfig(BaseModel):
    models: list[str] = Field(default_factory=list)
    scenarios_dir: str = "scenarios"
    providers: list[str] = Field(default_factory=lambda: ["openai", "anthropic"])
    runs: int = 3
    judge_model: Optional[str] = None
    regression_threshold: float = 0.2


def load_config(path: str | Path = DEFAULT_CONFIG_FILE) -> ModelpinConfig:
    p = Path(path)
    if not p.exists():
        return ModelpinConfig()
    data: dict[str, Any] = yaml.safe_load(p.read_text()) or {}
    return ModelpinConfig(**data)
