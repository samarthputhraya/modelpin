"""Semantic signal (LLM-as-judge). See spec section 6B.

TODO (Phase 0/1): when outputs differ textually, ask a judge model whether the two
answers accomplish the same task / mean the same thing. Low temperature; calibrate the
judge on a small labeled set and track its error rate. Returns a 0..1 score.
"""

from __future__ import annotations

from modelpin.models import Trace


def semantic_equivalence(
    baseline: Trace, candidate: Trace, judge_model: str | None = None
) -> float | None:
    """Return 0..1 'same meaning' score, or None if not evaluated. TODO: implement."""
    return None
