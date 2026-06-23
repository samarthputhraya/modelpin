"""Semantic signal (LLM-as-judge). See spec section 6B.

When a candidate's output differs *textually* from the baseline, ask a judge model
whether the two answers accomplish the same task / mean the same thing. The judge is
OPTIONAL and injected: with no judge the diff stays purely structural (and fully
offline). The signal is wired into the verdict through the SAME distributional
permutation test as the other signals (see ``diff/__init__.py``), so a single divergent
run is noise — only a *consistent* candidate-side semantic drift, beyond the baseline's
own natural spread, is flagged. This protects the false-positive north-star: reworded
but equivalent answers must not raise an alarm.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional, Protocol

from modelpin.models import Trace


class Judge(Protocol):
    """An equivalence oracle. Implementations call an LLM; tests inject a fake."""

    def equivalent(self, reference: str, candidate: str, task: Optional[str] = None) -> bool:
        """True if ``candidate`` accomplishes the same task / means the same as ``reference``."""
        ...


_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", (text or "").strip().lower())


def reference_output(traces: list[Trace]) -> str:
    """The modal ``final_output`` across runs — the representative 'expected' answer."""
    outputs = [t.final_output or "" for t in traces]
    if not outputs:
        return ""
    return Counter(outputs).most_common(1)[0][0]


def semantic_divergence_flags(
    baseline_traces: list[Trace],
    candidate_traces: list[Trace],
    judge: Judge,
    task: Optional[str] = None,
) -> tuple[list[int], list[int], float]:
    """Per-run semantic-divergence flags (0/1) for baseline and candidate, and the mean
    candidate equivalence score (1.0 == every candidate run matches the baseline meaning).

    Every output is compared to the *modal baseline output*. Text identical to the
    reference (after whitespace/case normalization) skips the judge call and counts as
    equivalent — the judge runs only when text differs (spec 6B). Baseline runs are scored
    against their own mode too, so the candidate is judged relative to the baseline's
    natural semantic spread, not an absolute bar.
    """
    reference = reference_output(baseline_traces)
    ref_norm = _normalize(reference)

    def flag(output: str) -> int:
        if _normalize(output) == ref_norm:
            return 0  # textually identical to the reference -> equivalent, no judge call
        return 0 if judge.equivalent(reference, output, task) else 1

    base_flags = [flag(t.final_output or "") for t in baseline_traces]
    cand_flags = [flag(t.final_output or "") for t in candidate_traces]
    cand_score = 1.0 - (sum(cand_flags) / len(cand_flags)) if cand_flags else 1.0
    return base_flags, cand_flags, round(cand_score, 3)
