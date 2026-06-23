"""Anthropic adapter. TODO (Phase 0): implement using the official `anthropic` SDK.

Read the key from ANTHROPIC_API_KEY (the END USER's key). Same Trace contract as the
OpenAI adapter. Keep the SDK import inside run().
"""

from __future__ import annotations

from modelpin.models import Scenario, Trace
from modelpin.providers.base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def run(self, scenario: Scenario, model_id: str, run_idx: int = 0) -> Trace:
        raise NotImplementedError("TODO: implement Anthropic replay (see spec section 4.4).")
