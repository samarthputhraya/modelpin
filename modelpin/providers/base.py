"""Provider adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from modelpin.models import Scenario, Trace


class ProviderAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def run(self, scenario: Scenario, model_id: str, run_idx: int = 0) -> Trace:
        """Execute the scenario on the model once and return a Trace."""
        raise NotImplementedError
