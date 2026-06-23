"""Canonical typed data models (pydantic v2). See spec section 5."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModelStatus(str, Enum):
    active = "active"
    deprecated = "deprecated"
    retired = "retired"


class Model(BaseModel):
    """A provider model and its lifecycle status."""

    id: str
    provider: str
    family: Optional[str] = None
    status: ModelStatus = ModelStatus.active
    released_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    replacement_id: Optional[str] = None


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Assertion(BaseModel):
    expected_tool_calls: Optional[list[str]] = None
    output_schema: Optional[dict[str, Any]] = None
    must_contain: Optional[list[str]] = None
    must_not_contain: Optional[list[str]] = None


class Scenario(BaseModel):
    """A representative case for a user's app (a single prompt or an agent run)."""

    id: str
    name: str
    kind: Literal["single", "agent"] = "single"
    input: dict[str, Any]  # { "messages": [...], "tools": [...]? }
    assertions: Optional[Assertion] = None

    @model_validator(mode="after")
    def _check_input_shape(self) -> "Scenario":
        """Fail fast on malformed scenarios so a bad file can't reach a paid API call.

        ``messages`` must be present and a list (an empty list is allowed for the
        offline/fake path); ``tools``, when present, must be a list.
        """
        messages = self.input.get("messages")
        if not isinstance(messages, list):
            raise ValueError(
                f"scenario {self.id!r}: input.messages must be a list of message dicts"
            )
        if "tools" in self.input and not isinstance(self.input["tools"], list):
            raise ValueError(f"scenario {self.id!r}: input.tools must be a list when present")
        return self


class Trace(BaseModel):
    """The recorded behavior of one model on one scenario, for one run."""

    scenario_id: str
    model_id: str
    run_idx: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    final_output: str = ""
    refused: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    ts: datetime = Field(default_factory=_utcnow)


class Baseline(BaseModel):
    """N recorded traces of the current (known-good) model on a scenario."""

    scenario_id: str
    model_id: str
    traces: list[Trace] = Field(default_factory=list)
    summary_stats: dict[str, Any] = Field(default_factory=dict)


class DiffVerdict(str, Enum):
    unchanged = "unchanged"
    changed_minor = "changed_minor"
    regression = "regression"


class DiffSignals(BaseModel):
    tool_call_match: Optional[float] = None
    format_valid: Optional[bool] = None
    refusal_delta: Optional[float] = None
    semantic_score: Optional[float] = None
    latency_delta_ms: Optional[float] = None
    token_delta: Optional[int] = None


class DiffResult(BaseModel):
    """The behavioral-diff verdict for one scenario across two models."""

    scenario_id: str
    from_model: str
    to_model: str
    verdict: DiffVerdict
    signals: DiffSignals = Field(default_factory=DiffSignals)
    confidence: float = 0.0
    explanation: str = ""


class CheckRun(BaseModel):
    """A full migration check across scenarios (hosted phase persists these)."""

    id: str
    repo: Optional[str] = None
    from_model: str
    to_model: str
    results: list[DiffResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
