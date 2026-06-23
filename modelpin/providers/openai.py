"""OpenAI adapter — replay a Scenario on an OpenAI model via the Chat Completions API.

Why Chat Completions (not the Responses API): the milestone compares an *older* vs a
*newer* GPT, and Chat Completions is the surface every GPT model supports. The shapes
here are verified against the official `openai` Python SDK (v1.x):
``response.choices[0].message.{content,tool_calls,refusal}`` and ``response.usage``.

Guardrails (see CLAUDE.md / spec §9):
- Use the END USER's key from ``OPENAI_API_KEY``. Never hardcode, ship, or log it.
- The SDK is an *optional* dependency; its import stays inside the run path so the
  package imports without it. Tests inject a fake client and never touch the network.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from modelpin.models import Scenario, ToolCall, Trace
from modelpin.providers.base import ProviderAdapter, ProviderError

#: Generation params we pass through from ``scenario.input`` when present. Anything
#: else in ``input`` (``messages``, ``tools``) is handled explicitly below.
_GEN_PARAM_KEYS: tuple[str, ...] = (
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "tool_choice",
    "seed",
    "response_format",
)

#: o-series reasoning models reject a non-default ``temperature``/``top_p`` and require
#: ``max_completion_tokens`` instead of ``max_tokens``. GPT-family models are unaffected,
#: so we keep this set narrow to avoid silently dropping params a GPT model accepts.
_REASONING_PREFIXES: tuple[str, ...] = ("o1", "o3", "o4")

#: Conservative refusal markers. Refusal is a per-run 0/1 signal that then goes through
#: the distributional test (diff/stats.py), so an occasional miss washes out — only a
#: shift in the *refusal rate* between baseline and candidate is ever flagged.
_REFUSAL_MARKERS: tuple[str, ...] = (
    "i can't",
    "i cannot",
    "i can not",
    "i'm not able",
    "i am not able",
    "i'm unable",
    "i am unable",
    "i won't",
    "i will not",
    "i'm sorry, but i can",
)

#: Friendly, actionable hints per OpenAI SDK error class. Keyed by class name so we
#: don't need to import the SDK's exception types at module scope.
_API_ERROR_HINTS: dict[str, str] = {
    "AuthenticationError": "your OPENAI_API_KEY was rejected (invalid or revoked)",
    "PermissionDeniedError": "your key lacks access to this model or resource",
    "NotFoundError": "the model id was not found — check it exists and you have access",
    "RateLimitError": "rate limit or quota exceeded — slow down or check billing",
    "BadRequestError": "the request was rejected (often an unsupported param for this model)",
    "APITimeoutError": "the OpenAI request timed out",
    "APIConnectionError": "could not reach OpenAI (network/connection error)",
    "InternalServerError": "OpenAI returned a server error — retry later",
}

#: Errors whose message text may embed a redacted key fragment — don't echo it at all.
_KEY_BEARING_ERRORS: frozenset[str] = frozenset({"AuthenticationError", "PermissionDeniedError"})

#: Key-shaped tokens to redact from ANY text before it is shown or logged. OpenAI keys
#: all start with ``sk-`` (incl. ``sk-proj-``); ``Bearer <token>`` covers raw auth headers.
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{4,}|Bearer\s+\S+", re.IGNORECASE)


def _scrub_secrets(text: str) -> str:
    """Redact key-shaped tokens so a secret can never reach the terminal or a log."""
    return _SECRET_RE.sub("[redacted]", text)


def _explain_api_error(exc: Exception, model_id: str) -> str:
    """Turn a raw SDK/network exception into a concise, key-safe message.

    Default-deny on the secret surface: auth/permission errors drop their text
    entirely, and every other error's text is scrubbed of key-shaped tokens before
    it is interpolated — so a renamed/unlisted error class can't leak a key either.
    """
    name = type(exc).__name__
    hint = _API_ERROR_HINTS.get(name, "the OpenAI API call failed")
    base = f"OpenAI call for model {model_id!r} failed: {hint}"
    if name in _KEY_BEARING_ERRORS:
        return f"{base} [{name}]."
    detail = _scrub_secrets(str(exc))[:300]
    return f"{base} [{name}: {detail}]."


def _is_reasoning_model(model_id: str) -> bool:
    return model_id.startswith(_REASONING_PREFIXES)


def _to_tools(raw: Any) -> list[dict[str, Any]] | None:
    """Normalize a scenario's ``tools`` into OpenAI function-tool specs.

    Accepts bare tool *names* (the common case in our scenarios) and wraps each as a
    minimal function with no parameters; passes already-shaped dicts through untouched.
    """
    if not raw:
        return None
    if not isinstance(raw, list):
        raise ProviderError(f"scenario 'tools' must be a list, got {type(raw).__name__}")
    tools: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": item,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
        elif isinstance(item, dict):
            if item.get("type") == "function" and "function" in item:
                tools.append(item)  # already a full tool spec
            elif "name" in item:
                tools.append({"type": "function", "function": item})  # bare function def
            else:
                tools.append(item)  # trust an explicit caller-supplied shape
    return tools or None


def _build_request(
    model_id: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, gen: dict
) -> dict[str, Any]:
    """Assemble create() kwargs, honoring o-series param restrictions."""
    req: dict[str, Any] = {"model": model_id, "messages": messages}
    if tools:
        req["tools"] = tools
    reasoning = _is_reasoning_model(model_id)
    for key in ("temperature", "top_p"):
        if key in gen and not reasoning:
            req[key] = gen[key]
    for key in ("tool_choice", "seed", "response_format"):
        if key in gen:
            req[key] = gen[key]
    max_tokens = gen.get("max_completion_tokens", gen.get("max_tokens"))
    if max_tokens is not None:
        req["max_completion_tokens" if reasoning else "max_tokens"] = max_tokens
    return req


def _parse_tool_calls(message: Any) -> list[ToolCall]:
    raw_calls = getattr(message, "tool_calls", None) or []
    calls: list[ToolCall] = []
    for call in raw_calls:
        fn = getattr(call, "function", None)
        name = getattr(fn, "name", None)
        if not name:
            continue  # partial/malformed call — skip rather than crash the whole run
        try:
            raw_args = fn.arguments
            arguments = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, TypeError):
            arguments = {}  # partial/malformed args — record the call, drop the payload
        if not isinstance(arguments, dict):
            arguments = {"_value": arguments}
        calls.append(ToolCall(name=name, arguments=arguments))
    return calls


def _detect_refusal(message: Any, finish_reason: str | None, text: str) -> bool:
    """True if the model declined or was filtered. Combines hard signals (content
    filter, the SDK's structured-output ``refusal`` field) with a phrase heuristic."""
    if finish_reason == "content_filter":
        return True
    if getattr(message, "refusal", None):
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in _REFUSAL_MARKERS)


def build_openai_client(api_key_env: str = "OPENAI_API_KEY") -> Any:
    """Construct a real OpenAI client: validate the BYO-key, then lazily import the SDK.

    Shared by the adapter and the semantic judge so key/SDK handling lives in one place.
    Raises ``ProviderError`` (never a raw traceback) if the key or SDK is missing.
    """
    api_key = (os.environ.get(api_key_env) or "").strip()
    if not api_key:
        raise ProviderError(
            f"{api_key_env} is not set. Modelpin uses YOUR own API key "
            "(cost + provider ToS) — export it and retry."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:  # optional dependency
        raise ProviderError(
            "The OpenAI SDK is not installed. Install it with: pip install 'modelpin[providers]'"
        ) from exc
    return OpenAI(api_key=api_key)


class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self, client: Any | None = None, api_key_env: str = "OPENAI_API_KEY") -> None:
        # An injected client makes the adapter unit-testable with no network or key.
        self._client = client
        self._api_key_env = api_key_env

    def preflight(self) -> None:
        """Validate the key + SDK before any replay runs — no network call."""
        self._get_client()

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = build_openai_client(self._api_key_env)
        return self._client

    def run(self, scenario: Scenario, model_id: str, run_idx: int = 0) -> Trace:
        messages = list(scenario.input.get("messages", []))
        tools = _to_tools(scenario.input.get("tools"))
        gen = {k: scenario.input[k] for k in _GEN_PARAM_KEYS if k in scenario.input}
        request = _build_request(model_id, messages, tools, gen)

        client = self._get_client()
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(**request)
        except ProviderError:
            raise
        except Exception as exc:  # SDK/network error → friendly, key-safe ProviderError
            raise ProviderError(_explain_api_error(exc, model_id)) from exc
        latency_ms = (time.perf_counter() - started) * 1000.0

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ProviderError(
                f"OpenAI returned no choices for scenario {scenario.id!r} on {model_id!r}."
            )
        choice = choices[0]
        message = choice.message
        text = message.content or ""
        tool_calls = _parse_tool_calls(message)
        refused = _detect_refusal(message, choice.finish_reason, text)

        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0

        return Trace(
            scenario_id=scenario.id,
            model_id=model_id,
            run_idx=run_idx,
            messages=messages + [_message_dict(message)],
            tool_calls=tool_calls,
            final_output=text,
            refused=refused,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )


def _message_dict(message: Any) -> dict[str, Any]:
    """Serialize the assistant reply for the trace record, tolerating non-SDK fakes."""
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True)
    return {"role": "assistant", "content": getattr(message, "content", "") or ""}
