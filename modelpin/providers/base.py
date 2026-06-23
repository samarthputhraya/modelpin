"""Provider adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from modelpin.models import Scenario, Trace


class ProviderError(Exception):
    """A replay could not proceed: missing key, SDK not installed, or an API error.

    The CLI catches this and prints a friendly, key-safe message instead of a raw
    traceback. Sibling domain errors (``ConfigError``, ``ScenarioError``,
    ``BaselineError``) likewise subclass ``Exception`` directly.
    """


class ProviderAdapter(ABC):
    name: str = "base"

    def preflight(self) -> None:
        """Cheap, no-network readiness check (key present, SDK importable).

        Called once before the replay loop so a misconfigured run fails *before*
        spending any tokens. Default is a no-op (e.g. the fake/offline provider).
        """
        return None

    @abstractmethod
    def run(self, scenario: Scenario, model_id: str, run_idx: int = 0) -> Trace:
        """Execute the scenario on the model once and return a Trace."""
        raise NotImplementedError
