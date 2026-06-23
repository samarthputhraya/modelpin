"""Load and validate modelpin.yaml. See spec sections 3-4."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

DEFAULT_CONFIG_FILE = "modelpin.yaml"

#: The default provider when none is given. OpenAI is the implemented adapter; the
#: Anthropic adapter is still a stub, so zero-config must not route to it.
DEFAULT_PROVIDER = "openai"


class ConfigError(Exception):
    """modelpin.yaml is malformed or fails validation. Carries a user-facing message."""


class ModelpinConfig(BaseModel):
    models: list[str] = Field(default_factory=list)
    scenarios_dir: str = "scenarios"
    providers: list[str] = Field(default_factory=lambda: [DEFAULT_PROVIDER])
    runs: int = Field(default=3, ge=1)
    judge_model: Optional[str] = None
    regression_threshold: float = 0.2


def load_config(path: str | Path = DEFAULT_CONFIG_FILE) -> ModelpinConfig:
    p = Path(path)
    if not p.exists():
        return ModelpinConfig()
    try:
        data: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{p} is not valid YAML: {exc}") from exc
    if data is None:
        return ModelpinConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"{p} must be a YAML mapping (got {type(data).__name__}).")
    try:
        return ModelpinConfig(**data)
    except ValidationError as exc:
        raise ConfigError(f"{p} has invalid settings: {exc}") from exc
