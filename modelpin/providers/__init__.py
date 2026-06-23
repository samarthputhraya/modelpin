"""Provider adapters — turn a Scenario into a Trace by calling a model.
See spec sections 4.4 and 9.

RULES:
- Use the END USER's API key from the environment. Never hardcode or ship keys.
- Each adapter returns a Trace.
"""

from __future__ import annotations

from modelpin.providers.base import ProviderAdapter
from modelpin.providers.fake import FakeProvider

__all__ = ["ProviderAdapter", "FakeProvider", "get_adapter"]


def get_adapter(provider: str) -> ProviderAdapter:
    provider = provider.lower()
    if provider == "fake":
        return FakeProvider()
    if provider == "openai":
        from modelpin.providers.openai import OpenAIAdapter

        return OpenAIAdapter()
    if provider == "anthropic":
        from modelpin.providers.anthropic import AnthropicAdapter

        return AnthropicAdapter()
    raise ValueError(f"Unknown provider: {provider}")
