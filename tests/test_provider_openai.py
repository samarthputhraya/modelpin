"""Unit tests for the OpenAI adapter — fully mocked, no network, no API key.

The adapter takes an injected client, so we hand it a fake whose response objects
mirror the real `openai` SDK shapes (attribute access, `arguments` as a JSON string,
`usage.prompt_tokens`/`completion_tokens`). This keeps CI free and deterministic.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modelpin.models import Scenario
from modelpin.providers import ProviderError, get_adapter
from modelpin.providers.openai import OpenAIAdapter

# --- fakes that mimic the openai SDK response shape -------------------------------


def _fn_tool_call(name: str, arguments: str):
    return SimpleNamespace(
        id="call_1", type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


def _message(content=None, tool_calls=None, refusal=None):
    def _dump(exclude_none=False):
        data = {"role": "assistant", "content": content, "tool_calls": tool_calls}
        return {k: v for k, v in data.items() if v is not None} if exclude_none else data

    return SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls,
        refusal=refusal,
        model_dump=_dump,
    )


def _response(message, finish_reason="stop", prompt_tokens=11, completion_tokens=7):
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


class FakeClient:
    """Records the kwargs of the last create() call and returns a canned response."""

    def __init__(self, response):
        self._response = response
        self.last_kwargs: dict | None = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


def _scenario(**input_kwargs) -> Scenario:
    base = {"messages": [{"role": "user", "content": "hi"}]}
    base.update(input_kwargs)
    return Scenario(id="s1", name="demo", input=base)


# --- tests ------------------------------------------------------------------------


def test_basic_completion_populates_trace():
    client = FakeClient(_response(_message(content="Hello there")))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(), "gpt-4o-mini", run_idx=2)

    assert trace.scenario_id == "s1"
    assert trace.model_id == "gpt-4o-mini"
    assert trace.run_idx == 2
    assert trace.final_output == "Hello there"
    assert trace.refused is False
    assert trace.tokens_in == 11
    assert trace.tokens_out == 7
    assert trace.latency_ms >= 0.0
    assert trace.tool_calls == []


def test_tool_calls_parsed_with_json_arguments():
    msg = _message(
        content=None,
        tool_calls=[
            _fn_tool_call("lookup_order", '{"order_id": 123}'),
            _fn_tool_call("issue_refund", '{"amount": 5.0}'),
        ],
    )
    client = FakeClient(_response(msg, finish_reason="tool_calls"))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(tools=["lookup_order", "issue_refund"]), "gpt-4o")

    assert [tc.name for tc in trace.tool_calls] == ["lookup_order", "issue_refund"]
    assert trace.tool_calls[0].arguments == {"order_id": 123}
    assert trace.tool_calls[1].arguments == {"amount": 5.0}
    assert trace.final_output == ""  # content was None


def test_string_tools_are_wrapped_into_function_specs():
    client = FakeClient(_response(_message(content="ok")))
    adapter = OpenAIAdapter(client=client)

    adapter.run(_scenario(tools=["cancel_subscription"]), "gpt-4o")

    tools = client.last_kwargs["tools"]
    assert tools == [
        {
            "type": "function",
            "function": {
                "name": "cancel_subscription",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_refusal_detected_via_content_filter():
    client = FakeClient(_response(_message(content=""), finish_reason="content_filter"))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(), "gpt-4o")

    assert trace.refused is True


def test_refusal_detected_via_structured_refusal_field():
    client = FakeClient(_response(_message(content=None, refusal="I won't do that.")))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(), "gpt-4o")

    assert trace.refused is True


def test_refusal_detected_via_phrase_heuristic():
    client = FakeClient(_response(_message(content="I'm not able to cancel that for you.")))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(), "gpt-4o")

    assert trace.refused is True


def test_benign_ai_self_reference_is_not_a_refusal():
    # North-star: low false-positive rate. A normal answer that mentions AI identity
    # must NOT be flagged as a refusal.
    client = FakeClient(_response(_message(content="As an AI, here is the code you asked for.")))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(), "gpt-4o")

    assert trace.refused is False


def test_empty_choices_raises_clear_error():
    response = _response(_message(content="ok"))
    response.choices = []
    client = FakeClient(response)
    adapter = OpenAIAdapter(client=client)

    with pytest.raises(ProviderError, match="no choices"):
        adapter.run(_scenario(), "gpt-4o")


def test_tool_call_missing_function_is_skipped():
    good = _fn_tool_call("issue_refund", "{}")
    broken = SimpleNamespace(id="call_x", type="function")  # no .function attribute
    msg = _message(content=None, tool_calls=[broken, good])
    client = FakeClient(_response(msg, finish_reason="tool_calls"))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(tools=["issue_refund"]), "gpt-4o")

    assert [tc.name for tc in trace.tool_calls] == ["issue_refund"]


def test_reasoning_model_drops_temperature_and_renames_max_tokens():
    client = FakeClient(_response(_message(content="ok")))
    adapter = OpenAIAdapter(client=client)

    adapter.run(_scenario(temperature=0.2, max_tokens=256), "o3-mini")

    kwargs = client.last_kwargs
    assert "temperature" not in kwargs  # o-series rejects non-default temperature
    assert "max_tokens" not in kwargs
    assert kwargs["max_completion_tokens"] == 256


def test_gpt_model_passes_temperature_and_max_tokens():
    client = FakeClient(_response(_message(content="ok")))
    adapter = OpenAIAdapter(client=client)

    adapter.run(_scenario(temperature=0.2, max_tokens=256), "gpt-4o")

    kwargs = client.last_kwargs
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 256
    assert "max_completion_tokens" not in kwargs


def test_malformed_tool_arguments_degrade_gracefully():
    msg = _message(content=None, tool_calls=[_fn_tool_call("do_thing", "{not valid json")])
    client = FakeClient(_response(msg, finish_reason="tool_calls"))
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(tools=["do_thing"]), "gpt-4o")

    assert trace.tool_calls[0].name == "do_thing"
    assert trace.tool_calls[0].arguments == {}


def test_missing_usage_yields_zero_tokens():
    response = _response(_message(content="ok"))
    response.usage = None
    client = FakeClient(response)
    adapter = OpenAIAdapter(client=client)

    trace = adapter.run(_scenario(), "gpt-4o")

    assert trace.tokens_in == 0
    assert trace.tokens_out == 0


def test_missing_api_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = OpenAIAdapter()  # no injected client -> must build a real one

    with pytest.raises(ProviderError, match="OPENAI_API_KEY is not set"):
        adapter.run(_scenario(), "gpt-4o")


def test_blank_api_key_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")  # whitespace only
    adapter = OpenAIAdapter()

    with pytest.raises(ProviderError, match="OPENAI_API_KEY is not set"):
        adapter.preflight()


def test_preflight_passes_with_injected_client():
    adapter = OpenAIAdapter(client=FakeClient(_response(_message(content="ok"))))
    adapter.preflight()  # must not raise


def test_api_error_is_wrapped_in_provider_error():
    class Boom:
        chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: (_ for _ in ()).throw(RuntimeError("network down"))
            )
        )

    adapter = OpenAIAdapter(client=Boom())
    with pytest.raises(ProviderError, match="OpenAI call for model 'gpt-4o' failed"):
        adapter.run(_scenario(), "gpt-4o")


def test_auth_error_message_does_not_echo_the_raw_exception():
    # An AuthenticationError's text can embed a redacted key fragment; we must not echo it.
    class AuthenticationError(Exception):
        pass

    def _raise(**_):
        raise AuthenticationError("Incorrect API key provided: sk-abc...secret")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_raise)))
    adapter = OpenAIAdapter(client=client)
    with pytest.raises(ProviderError) as exc_info:
        adapter.run(_scenario(), "gpt-4o")
    msg = str(exc_info.value)
    assert "sk-abc" not in msg
    assert "AuthenticationError" in msg  # the class name is safe to surface


def test_generic_api_error_message_is_secret_scrubbed():
    # The generic (non-allowlisted) branch DOES interpolate the error text, so it must
    # scrub key-shaped tokens — otherwise a key fragment in an error body reaches the
    # terminal via cli._fail. This guards the BYO-key north-star guardrail.
    class BadRequestError(Exception):
        pass

    def _raise(**_):
        raise BadRequestError("Invalid value near key sk-proj-ABCDEF1234567890 in body")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_raise)))
    adapter = OpenAIAdapter(client=client)
    with pytest.raises(ProviderError) as exc_info:
        adapter.run(_scenario(), "gpt-4o")
    msg = str(exc_info.value)
    assert "sk-" not in msg
    assert "ABCDEF1234567890" not in msg
    assert "BadRequestError" in msg  # class name + redaction marker still informative


def test_non_list_tools_raises_provider_error():
    client = FakeClient(_response(_message(content="ok")))
    adapter = OpenAIAdapter(client=client)
    bad = Scenario(id="s1", name="demo", input={"messages": [{"role": "user", "content": "hi"}]})
    # bypass model validation by mutating after construction to simulate a bad shape
    object.__setattr__(bad, "input", {"messages": [], "tools": "lookup_order"})

    with pytest.raises(ProviderError, match="tools' must be a list"):
        adapter.run(bad, "gpt-4o")


def test_get_adapter_returns_openai_adapter():
    assert isinstance(get_adapter("openai"), OpenAIAdapter)
