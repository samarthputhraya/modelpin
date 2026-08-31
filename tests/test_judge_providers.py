"""A cross-vendor user must have a channel that reads MEANING (MP-143).

`[M] 2026-08-31` `build_judge` rejected any judge model that was not OpenAI's. Honest -- it
said so, and said so in its docstring -- but it left a hole with teeth:

  * cross-vendor is wedge item 3, and the README documents a Groq example;
  * for a suite with no `tools` (a classifier, a summariser -- the long-tail wedge), the
    judge is the ONLY CI-failing channel that responds to a change in meaning. Without it,
    `[M]` per `_channel_census`, such a run has NO hard content channel at all: only a
    refusal could fail the build.

So a Groq- or Gemini-only user was running an engine that could not catch a
wrong-but-confident answer. These tests are offline: every client is injected.
"""

from __future__ import annotations

import pytest

from modelpin.config import ModelpinConfig
from modelpin.judge import (
    JUDGE_PROVIDERS,
    OpenAIJudge,
    build_judge,
    infer_judge_provider,
)
from modelpin.providers.base import ProviderError
from modelpin.providers.openai import OPENAI_COMPATIBLE_PROVIDERS


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Msg(content)


class FakeOpenAIClient:
    """Records the request so the test can assert what was actually asked."""

    def __init__(self, content: str = '{"equivalent": false, "reason": "different answer"}'):
        self.content = content
        self.request: dict = {}
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.request = kwargs
        return type("R", (), {"choices": [_Choice(self.content)]})()


class _Part:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeGoogleClient:
    def __init__(self, text: str = '{"equivalent": false, "reason": "different answer"}'):
        self.text = text
        self.request: dict = {}
        self.models = self

    def generate_content(self, **kwargs):
        self.request = kwargs
        content = type("C", (), {"parts": [_Part(self.text)]})()
        return type("R", (), {"candidates": [type("Cand", (), {"content": content})()]})()


# --- routing ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4o-mini", "openai"),
        ("o3-mini", "openai"),
        ("chatgpt-4o-latest", "openai"),
        ("gemini-3.1-flash-lite", "google"),
        ("models/gemini-1.5-pro", "google"),
        ("llama-3.3-70b-versatile", None),
        ("openai/gpt-oss-120b", None),
        ("meta-llama/Llama-3-70b-chat-hf", None),
    ],
)
def test_only_unambiguous_ids_are_inferred(model, expected):
    """`openai/gpt-oss-120b` is the case that forbids a `vendor/model` parse: it is an
    OpenRouter/Groq id whose first segment is a DIFFERENT vendor's name. Inferring from it
    would route a Groq run to OpenAI and spend the wrong key."""
    assert infer_judge_provider(model) == expected


@pytest.mark.parametrize("host", sorted(OPENAI_COMPATIBLE_PROVIDERS))
def test_every_openai_compatible_host_can_judge(host):
    judge = build_judge("some-model", provider=host, client=FakeOpenAIClient())
    assert isinstance(judge, OpenAIJudge)
    cfg = OPENAI_COMPATIBLE_PROVIDERS[host]
    assert judge._base_url == cfg["base_url"]
    assert judge._api_key_env == cfg["api_key_env"]


def test_the_openai_judge_still_defaults_to_openai():
    judge = build_judge("gpt-4o-mini", client=FakeOpenAIClient())
    assert judge._base_url is None
    assert judge._api_key_env == "OPENAI_API_KEY"


def test_an_unknown_host_is_named_not_guessed():
    with pytest.raises(ProviderError, match="no semantic judge available on host"):
        build_judge("some-model", provider="mistral")


def test_a_bare_ambiguous_id_asks_for_the_config_key():
    """The error has to be actionable: it names the KEY to set and the values it takes."""
    with pytest.raises(ProviderError) as exc:
        build_judge("llama-3.3-70b-versatile")
    message = str(exc.value)
    assert "judge_provider" in message
    for host in JUDGE_PROVIDERS:
        assert host in message


# --- behaviour -------------------------------------------------------------------------


def test_a_groq_judge_reaches_groq_and_returns_a_verdict():
    client = FakeOpenAIClient()
    judge = build_judge("llama-3.3-70b-versatile", provider="groq", client=client)
    assert judge.equivalent("the total is $5", "the total is $500", task="sum it") is False
    assert client.request["model"] == "llama-3.3-70b-versatile"
    assert client.request["temperature"] == 0  # deterministic judging, all hosts
    assert "the total is $500" in client.request["messages"][1]["content"]


def test_a_gemini_judge_returns_a_verdict():
    client = FakeGoogleClient()
    judge = build_judge("gemini-3.1-flash-lite", client=client)
    assert judge.equivalent("yes, refunded", "no, I cannot refund that") is False
    assert client.request["model"] == "gemini-3.1-flash-lite"
    assert client.request["config"]["temperature"] == 0


def test_the_gemini_judge_puts_the_rubric_in_system_instruction():
    """The adapter's verified shape: instructions go in `config.system_instruction`, not as a
    fake `system` turn in `contents`, which Gemini has no role for."""
    client = FakeGoogleClient()
    build_judge("gemini-3.1-flash-lite", client=client).equivalent("a", "b")
    assert "behaviorally EQUIVALENT" in client.request["config"]["system_instruction"]
    assert client.request["contents"][0]["role"] == "user"


def test_every_judge_asks_the_SAME_question():
    """LOAD-BEARING. The semantic channel's calibration (`docs/fp-measurement.md`) is measured
    against one rubric; two judges asking different questions would make a cross-vendor
    comparison of their verdicts meaningless."""
    openai_client, google_client = FakeOpenAIClient(), FakeGoogleClient()
    build_judge("gpt-4o-mini", client=openai_client).equivalent("a", "b", task="t")
    build_judge("gemini-3.1-flash-lite", client=google_client).equivalent("a", "b", task="t")
    assert (
        openai_client.request["messages"][0]["content"]
        == google_client.request["config"]["system_instruction"]
    )
    assert (
        openai_client.request["messages"][1]["content"]
        == google_client.request["contents"][0]["parts"][0]["text"]
    )


def test_a_gemini_judge_that_says_nothing_is_read_as_equivalent():
    """FP-safe, the same rule `_parse_equivalent` follows: silence must never be read as
    'not equivalent'. A judge outage manufacturing regressions is the worst failure this
    tool has -- the north-star metric is the false-positive rate."""

    class Empty(FakeGoogleClient):
        def generate_content(self, **kwargs):
            return type("R", (), {"candidates": []})()

    assert build_judge("gemini-3.1-flash-lite", client=Empty()).equivalent("a", "b") is True


def test_a_gemini_sdk_error_becomes_a_key_safe_provider_error():
    class Boom(FakeGoogleClient):
        def generate_content(self, **kwargs):
            raise RuntimeError("401 invalid api key sk-abc123secret")

    with pytest.raises(ProviderError) as exc:
        build_judge("gemini-3.1-flash-lite", client=Boom()).equivalent("a", "b")
    assert "sk-abc123secret" not in str(exc.value)


# --- config ----------------------------------------------------------------------------


def test_judge_provider_is_a_config_key():
    cfg = ModelpinConfig(judge_model="llama-3.3-70b-versatile", judge_provider="groq")
    assert cfg.judge_provider == "groq"
    assert ModelpinConfig().judge_provider is None


def test_config_judge_provider_wins_over_the_model_prefix():
    """A user pointing an OpenAI-named model at a proxy must not be overridden by a guess."""
    judge = build_judge("gpt-4o-mini", provider="openrouter", client=FakeOpenAIClient())
    assert judge._base_url == OPENAI_COMPATIBLE_PROVIDERS["openrouter"]["base_url"]
