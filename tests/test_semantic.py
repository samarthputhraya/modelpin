"""Unit tests for the semantic divergence-flag computation (no network)."""

from __future__ import annotations

from modelpin.diff.semantic import _normalize, reference_output, semantic_divergence_flags
from modelpin.models import Trace


class FakeJudge:
    """Records calls; returns equivalence per an injected rule(reference, candidate)."""

    def __init__(self, rule):
        self.rule = rule
        self.calls: list[tuple] = []

    def equivalent(self, reference, candidate, task=None):
        self.calls.append((reference, candidate, task))
        return self.rule(reference, candidate)


def _tr(out, run=0):
    return Trace(scenario_id="s", model_id="m", run_idx=run, final_output=out)


def _traces(outputs):
    return [_tr(o, i) for i, o in enumerate(outputs)]


def test_reference_is_modal_output():
    assert reference_output(_traces(["A", "A", "B"])) == "A"


def test_identical_text_skips_the_judge_entirely():
    judge = FakeJudge(lambda r, c: False)  # would flag everything if ever called
    base = _traces(["same"] * 3)
    cand = _traces(["same"] * 3)
    base_f, cand_f, score = semantic_divergence_flags(base, cand, judge)
    assert judge.calls == []  # never invoked — text matched the reference
    assert base_f == [0, 0, 0] and cand_f == [0, 0, 0]
    assert score == 1.0


def test_consistently_divergent_candidate_is_flagged():
    judge = FakeJudge(lambda r, c: False)  # judge says different whenever asked
    base = _traces(["Approved."] * 3)
    cand = _traces(["Request denied.", "We cannot proceed.", "No."])
    base_f, cand_f, score = semantic_divergence_flags(base, cand, judge)
    assert base_f == [0, 0, 0]  # baseline identical to its own mode
    assert cand_f == [1, 1, 1]  # all candidate runs judged non-equivalent
    assert score == 0.0


def test_reworded_but_equivalent_candidate_is_not_flagged():
    judge = FakeJudge(lambda r, c: True)  # different words, same meaning
    base = _traces(["The total is $5."] * 3)
    cand = _traces(["Total: 5 dollars.", "It comes to five dollars.", "$5 total."])
    base_f, cand_f, score = semantic_divergence_flags(base, cand, judge)
    assert cand_f == [0, 0, 0]  # equivalence -> no divergence
    assert score == 1.0
    assert len(judge.calls) == 3  # judge consulted once per differing candidate run


def test_baseline_natural_spread_is_measured():
    # A baseline run that differs from the mode and is judged non-equivalent counts as
    # baseline spread, so the candidate is compared against that natural variance.
    judge = FakeJudge(lambda r, c: False)
    base = _traces(["A", "A", "Z"])  # mode "A"; the "Z" run differs
    cand = _traces(["A", "A", "A"])
    base_f, cand_f, _ = semantic_divergence_flags(base, cand, judge)
    assert base_f == [0, 0, 1]
    assert cand_f == [0, 0, 0]


def test_normalize_ignores_whitespace_and_case():
    assert _normalize("  Total:  $5 ") == _normalize("total: $5")
