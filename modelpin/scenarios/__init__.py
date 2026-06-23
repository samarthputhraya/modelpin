"""Scenarios — load a repo's representative cases. See spec section 4.3.

A scenario is a JSON file: {id, name, kind, input:{messages,tools?}, assertions?}.
"""

from __future__ import annotations

import json
from pathlib import Path

from modelpin.models import Scenario


def load_scenarios(scenarios_dir: str | Path = "scenarios") -> list[Scenario]:
    d = Path(scenarios_dir)
    if not d.exists():
        return []
    out: list[Scenario] = []
    for f in sorted(d.glob("*.json")):
        out.append(Scenario(**json.loads(f.read_text())))
    return out
