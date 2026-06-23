"""OpenAI adapter. TODO (Phase 0): implement using the official `openai` SDK.

Read the key from OPENAI_API_KEY (the END USER's key). Capture messages, tool calls,
final output, refusal, tokens, latency into a Trace. Keep the SDK import inside run()
so the package imports without the optional dependency installed.
"""

from __future__ import annotations

from modelpin.models import Scenario, Trace
from modelpin.providers.base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def run(self, scenario: Scenario, model_id: str, run_idx: int = 0) -> Trace:
        # import os, time; from openai import OpenAI  # noqa: ERA001
        raise NotImplementedError("TODO: implement OpenAI replay (see spec section 4.4).")
