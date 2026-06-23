"""Unit tests for the Google (Gemini) adapter — fully mocked, no network, no key.

The fake client mimics the google-genai response shape: ``candidates[0].content.parts``
with ``.text`` / ``.function_call`` (``.name`` + ``.args`` dict), ``usage_metadata``,
``candidates[0].finish_reason`` (with a ``.name``), and ``prompt_feedback``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modelpin.models import Scenario
from modelpin.providers import ProviderError, get_adapter
from modelpin.providers.google import GoogleAdapter

# --- fakes mirroring the google-genai response shape ------------------------------


def _fn_part(name, args):
    return SimpleNamespace(text=None, function_call=SimpleNamespace(name=name, args=args))


def _text_part(text):
    return SimpleNamespace(text=text, function_call=None)


def _response(parts, finish="STOP", prompt_tokens=9, out_tokens=5, block_reason=None):
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=parts),
        finish_reason=SimpleNamespace(name=finish),
    )
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=out_tokens)
    return SimpleNamespace(
        candidates=[candidate],
        usage_metadata=usage,
        prompt_feedback=SimpleNamespace(block_reason=block_reason),
    )


class FakeClient:
    """Returns canned responses in sequence (clamps to the last); records create kwargs."""

    def __init__(self, responses):
        self._responses = responses if isinstance(responses, list) else [responses]
        self.last_kwargs: dict | None = None
        self.calls = 0
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.last_kwargs = kwargs
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


def _scenario(**input_kwargs) -> Scenario:
    base = {"messages": [{"role": "user", "content": "hi"}]}
    base.update(input_kwargs)
    return Scenario(id="g1", name="demo", input=base)


# --- tests ------------------------------------------------------------------------


def test_basic_text_completion():
    client = FakeClient(_response([_text_part("Hello from Gemini")]))
    trace = GoogleAdapter(client=client).run(_scenario(), "gemini-2.0-flash", run_idx=1)

    assert trace.model_id == "gemini-2.0-flash"
    assert trace.run_idx == 1
    assert trace.final_output == "Hello from Gemini"
    assert trace.refused is False
    assert trace.tokens_in == 9 and trace.tokens_out == 5
    assert trace.tool_calls == []


def test_function_call_args_are_already_a_dict():
    # Gemini gives parsed args (no JSON-string parsing needed, unlike OpenAI).
    turn1 = _response([_fn_part("lookup_order", {"order_id": "A-1042"})], finish="STOP")
    final = _response([_text_part("Your order shipped.")])
    client = FakeClient([turn1, final])
    scenario = _scenario(
        tools=["lookup_order"], tool_results={"lookup_order": {"status": "shipped"}}
    )
    trace = GoogleAdapter(client=client).run(scenario, "gemini-2.0-flash")

    assert [tc.name for tc in trace.tool_calls] == ["lookup_order"]
    assert trace.tool_calls[0].arguments == {"order_id": "A-1042"}
    assert trace.final_output == "Your order shipped."


def test_multi_step_trajectory_emerges():
    t1 = _response([_fn_part("lookup_order", {})])
    t2 = _response([_fn_part("issue_refund", {})])
    final = _response([_text_part("Refund done.")])
    client = FakeClient([t1, t2, final])
    scenario = _scenario(tools=["lookup_order", "issue_refund"])
    trace = GoogleAdapter(client=client).run(scenario, "gemini-2.0-flash")

    assert [tc.name for tc in trace.tool_calls] == ["lookup_order", "issue_refund"]
    assert client.calls == 3
    # the function-response turn was appended to the conversation
    assert any(
        any("function_response" in p for p in m.get("parts", []) if isinstance(p, dict))
        for m in trace.messages
    )


def test_refusal_via_safety_finish_reason():
    client = FakeClient(_response([_text_part("")], finish="SAFETY"))
    trace = GoogleAdapter(client=client).run(_scenario(), "gemini-2.0-flash")
    assert trace.refused is True


def test_refusal_via_prompt_block():
    client = FakeClient(_response([_text_part("")], block_reason="SAFETY"))
    trace = GoogleAdapter(client=client).run(_scenario(), "gemini-2.0-flash")
    assert trace.refused is True


def test_system_message_becomes_system_instruction():
    client = FakeClient(_response([_text_part("ok")]))
    scenario = _scenario(
        messages=[
            {"role": "system", "content": "You are terse."},
            {"role": "user", "content": "hi"},
        ]
    )
    GoogleAdapter(client=client).run(scenario, "gemini-2.0-flash")
    assert client.last_kwargs["config"]["system_instruction"] == "You are terse."
    # the user turn is sent as Gemini contents, system is NOT a content turn
    assert [c["role"] for c in client.last_kwargs["contents"]] == ["user"]


def test_string_tools_become_function_declarations():
    client = FakeClient(_response([_text_part("ok")]))
    GoogleAdapter(client=client).run(_scenario(tools=["cancel_subscription"]), "gemini-2.0-flash")
    tools = client.last_kwargs["config"]["tools"]
    assert tools[0]["function_declarations"][0]["name"] == "cancel_subscription"


def test_missing_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="GEMINI_API_KEY is not set"):
        GoogleAdapter().preflight()


def test_api_error_is_wrapped_key_safe():
    class ClientError(Exception):
        def __init__(self):
            self.code = 400
            self.message = "bad request with key AIzaSyABCDEF1234567890xyz embedded"

    def _boom(**_):
        raise ClientError()

    client = SimpleNamespace(models=SimpleNamespace(generate_content=_boom))
    with pytest.raises(ProviderError) as exc_info:
        GoogleAdapter(client=client).run(_scenario(), "gemini-2.0-flash")
    msg = str(exc_info.value)
    assert "AIza" not in msg  # Google key fragment scrubbed
    assert "Gemini call for model" in msg


def test_empty_candidates_raises():
    resp = _response([_text_part("x")])
    resp.candidates = []
    client = FakeClient(resp)
    with pytest.raises(ProviderError, match="no candidates"):
        GoogleAdapter(client=client).run(_scenario(), "gemini-2.0-flash")


def test_get_adapter_returns_google_adapter():
    assert isinstance(get_adapter("google"), GoogleAdapter)
