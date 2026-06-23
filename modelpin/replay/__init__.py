"""Replay — run a Scenario on a model N times via an adapter. See spec section 4.4."""

from __future__ import annotations

from modelpin.models import Scenario, Trace
from modelpin.providers.base import ProviderAdapter


def replay(
    scenario: Scenario, model_id: str, adapter: ProviderAdapter, runs: int = 3
) -> list[Trace]:
    """Return N Traces of the scenario on the model. N>1 is essential to handle
    model nondeterminism downstream (see diff/stats.py)."""
    return [adapter.run(scenario, model_id, run_idx=i) for i in range(runs)]
