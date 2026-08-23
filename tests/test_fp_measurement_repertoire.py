"""MP-75 - the FP rate must publish whether the run measured anything.

`scripts/fp_measurement.py` reported verdicts only. A scenario the model answers identically
on every run scores `unchanged` and was counted `clean`, so a suite of deterministic
scenarios printed `False-positive rate: 0/8 = 0%` - which reads as "the engine did not cry
wolf" but means "there was nothing to cry wolf about".

`[M]` `diff/stats.py:128-129` early-exits at `p=1.0` when the two sides are DISTRIBUTIONALLY
IDENTICAL, so such a scenario scores `unchanged` REGARDLESS of any change to the engine.
Crediting it to the north-star metric credits a trial that could not have failed.

The exclusion predicate itself is the dangerous part, and `test_measurable` below is the
reason this file exists. [M] fp-guardian blocked the first attempt: it decided from PER-SIDE
variance ("each side is unimodal, so nothing varied"), which is a different claim from
"the sides are identical". Two internally-invariant sides that DIFFER are the engine's
highest-confidence firing configuration, so that predicate deleted the most confident false
positives from both numerator and denominator. It also showed the tests were not pinning the
decision at all: replacing it with `if False:` left all 271 green.

No provider is needed for any of this - ADR-0006 forbids a live call from the suite.
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelpin.diff import DiffVerdict  # noqa: E402
from modelpin.models import ToolCall, Trace  # noqa: E402
from scripts.fp_measurement import (  # noqa: E402
    FP_OUTCOMES,
    fp_outcome,
    fp_tally,
    measurable,
    repertoire,
)


def _t(out="ok", tool="lookup", args=None):
    return Trace(
        scenario_id="s",
        model_id="m",
        tool_calls=[ToolCall(name=tool, arguments=args if args is not None else {"q": "x"})],
        final_output=out,
        latency_ms=1,
        tokens_in=1,
        tokens_out=1,
    )


class TestRepertoire:
    def test_identical_runs_count_as_one_behaviour_per_channel(self):
        assert repertoire([_t(), _t(), _t()]) == {"tools": 1, "args": 1, "text": 1}

    def test_text_jitter_is_counted_on_the_text_channel_only(self):
        rep = repertoire([_t(out="a"), _t(out="b"), _t(out="a")])
        assert rep == {"tools": 1, "args": 1, "text": 2}

    def test_argument_jitter_is_counted_even_when_the_prose_is_identical(self):
        # The MP-04 premise: a model can be word-perfect while its ARGUMENTS move. If this
        # channel were folded into `text`, the calibration set MP-54 exists for would read
        # as invariant and be excluded from the very rate it was built to measure.
        rep = repertoire([_t(args={"kg": 3.36}), _t(args={"kg": 3.357}), _t(args={"kg": 3.36})])
        assert rep["args"] == 2, rep
        assert rep["text"] == 1, rep

    def test_tool_trajectory_change_is_its_own_channel(self):
        assert repertoire([_t(tool="a"), _t(tool="b")])["tools"] == 2

    def test_text_is_compared_verbatim_because_a_gating_signal_is_byte_exact(self):
        # [M] fp-guardian: `structural.py:123-126` `violates_text_assertions` does a
        # byte-exact, case-SENSITIVE `s in out`, and flags "Order shipped" vs "order
        # shipped" at confidence 0.996. A canonicalising diagnostic would print `text: 1`
        # for that pair. A diagnostic may be finer than the engine, never coarser.
        assert repertoire([_t(out="Logged"), _t(out="logged")])["text"] == 2
        assert repertoire([_t(out="a b"), _t(out="a  b")])["text"] == 2

    def test_unhashable_argument_values_do_not_crash_the_measurement(self):
        # Arguments are model-authored JSON: nested dicts and lists are ordinary. A crash
        # here would abort a paid run at the last step.
        rep = repertoire([_t(args={"a": [1, {"b": 2}]}), _t(args={"a": [1, {"b": 3}]})])
        assert rep["args"] == 2

    def test_argument_key_order_is_not_mistaken_for_variance(self):
        # Same payload, different serialisation order -> one behaviour, not two.
        assert repertoire([_t(args={"a": 1, "b": 2}), _t(args={"b": 2, "a": 1})])["args"] == 1


class TestMeasurable:
    """The exclusion predicate. Getting this wrong silently deletes false positives."""

    class _R:
        def __init__(self, verdict, confidence):
            self.verdict, self.confidence = verdict, confidence

    def test_a_trial_with_no_measured_effect_is_excluded(self):
        # `unchanged` at confidence 1.0 means min(p) == 1.0 across every signal (ADR-0001):
        # no channel measured anything, so nothing could have fired.
        assert measurable(self._R(DiffVerdict.unchanged, 1.0)) is False

    def test_a_trial_where_something_could_have_fired_is_scored(self):
        assert measurable(self._R(DiffVerdict.unchanged, 0.95)) is True

    def test_a_FLAGGED_verdict_is_never_excluded_however_confident(self):
        """The safety property. THIS is the test that must never be deleted.

        [M] fp-guardian: the rejected per-side predicate excluded `regression` at conf 0.992
        and 0.996 on four separate channels - the engine's most confident false positives,
        removed from the rate that exists to count them. Any future predicate must keep
        every one of these scored.
        """
        for verdict in (DiffVerdict.regression, DiffVerdict.changed_minor):
            for conf in (0.0, 0.5, 0.952, 0.992, 0.996, 1.0):
                assert measurable(self._R(verdict, conf)) is True, (
                    f"{verdict.value} at confidence {conf} was excluded from the "
                    "false-positive rate. A flagged verdict is a false positive in the FP "
                    "arm by construction; removing it deletes the thing being measured."
                )

    def test_two_internally_invariant_but_DIFFERENT_sides_are_scored(self):
        """The exact case the first implementation got wrong.

        Each side is unimodal, so a per-side variance test says "nothing varied" - but the
        sides differ, which is `stats.py`'s lowest p and the engine's highest confidence.
        Building the pools here rather than mocking, so the claim is about real traces.
        """
        base = [_t(tool="lookup") for _ in range(5)]
        cand = [_t(tool="escalate") for _ in range(5)]
        assert repertoire(base) == {"tools": 1, "args": 1, "text": 1}
        assert repertoire(cand) == {"tools": 1, "args": 1, "text": 1}
        # Per-side variance says "measured nothing". The engine says regression at 0.992.
        from modelpin.diff import diff_scenario
        from modelpin.models import Scenario

        scn = Scenario(id="s", name="s", kind="agent", input={"messages": []})
        r = diff_scenario("s", "m", "m", base, cand, scn, "strict", judge=None)
        assert r.verdict is DiffVerdict.regression, r.verdict
        assert measurable(r) is True, (
            "a flagged, internally-invariant pair was excluded from the FP rate - this is "
            "the defect fp-guardian blocked, reintroduced."
        )

    def test_argument_only_jitter_is_excluded_while_the_engine_cannot_see_arguments(self):
        """[M] no gating signal on this branch reads `tc.arguments` (argkey.py is on the
        unmerged MP-04 branch), so an args-only trial is guaranteed `unchanged` at 1.0. It
        must not inflate the denominator with a trial that cannot fail. When MP-04 lands
        this stops being vacuous on its own - the engine starts measuring the channel."""
        from modelpin.diff import diff_scenario
        from modelpin.models import Scenario

        base = [_t(args={"kg": 3.36}) for _ in range(5)]
        cand = [_t(args={"kg": 3.357}) for _ in range(5)]
        assert repertoire(base + cand)["args"] == 2, "the pools really do differ on args"
        scn = Scenario(id="s", name="s", kind="agent", input={"messages": []})
        r = diff_scenario("s", "m", "m", base, cand, scn, "strict", judge=None)
        assert measurable(r) is False, (
            f"args-only jitter was scored as a real trial, but the engine returned "
            f"{r.verdict.value} at {r.confidence} because it reads no argument signal."
        )


class TestFpOutcome:
    """The FP arm's actual decision. [M] fp-guardian: with this logic inline in `main()`,
    replacing it with `if False:` deleted the entire point of MP-75 and 271 tests stayed
    green. These are the tests that would have gone red."""

    class _R:
        def __init__(self, verdict, confidence):
            self.verdict, self.confidence = verdict, confidence

    def test_a_trial_with_no_measured_effect_is_excluded_not_counted_clean(self):
        assert fp_outcome(self._R(DiffVerdict.unchanged, 1.0)) == "no-effect"

    def test_a_real_clean_trial_is_counted(self):
        assert fp_outcome(self._R(DiffVerdict.unchanged, 0.95)) == "clean"

    def test_an_abstention_stays_unmeasured(self):
        # ADR-0018: neither a false alarm nor a detection. Must not be re-routed by MP-75.
        assert fp_outcome(self._R(DiffVerdict.insufficient_evidence, 0.5)) == "unmeasured"

    def test_every_flagged_verdict_reaches_the_rate_at_every_confidence(self):
        """THE safety property, at the decision level rather than the helper level.

        A flagged verdict must reach the numerator no matter how the exclusion is written.
        [M] the predicate fp-guardian blocked excluded `regression` at conf 0.992/0.996 -
        the engine's most confident false positives - from both numerator and denominator.
        """
        for verdict in (DiffVerdict.regression, DiffVerdict.changed_minor):
            for conf in (0.0, 0.5, 0.952, 0.992, 0.996, 1.0):
                assert fp_outcome(self._R(verdict, conf)) == "fp", (
                    f"{verdict.value} at confidence {conf} did not reach the rate. A flagged "
                    "verdict in the FP arm IS a false positive; excluding it deletes the "
                    "measurement."
                )

    def test_the_exclusion_cannot_be_deleted_without_this_going_red(self):
        """Guards the arm wiring, not just the predicate: a `clean` and a `no-effect` trial
        must be distinguishable outcomes. If someone collapses the branch, this fails."""
        outcomes = {
            fp_outcome(self._R(DiffVerdict.unchanged, 1.0)),
            fp_outcome(self._R(DiffVerdict.unchanged, 0.95)),
        }
        assert outcomes == {"no-effect", "clean"}, (
            f"the no-effect exclusion collapsed into {outcomes} - MP-75's whole point is that "
            "these two are not the same trial."
        )


class TestFpTally:
    """The accounting. What lands in the numerator and the denominator IS the metric."""

    def test_only_trials_that_could_have_fired_reach_the_denominator(self):
        t = fp_tally(["clean", "clean", "fp", "no-effect", "no-effect", "unmeasured"])
        assert t == {
            "scored": 3,
            "false_positives": 1,
            "no_effect": 2,
            "unmeasured": 1,
        }, t

    def test_a_run_where_nothing_could_fire_scores_zero_over_zero_not_zero_percent(self):
        # The headline case. Before MP-75 this printed `0/8 = 0%` - a good-looking number
        # over eight trials that could not have failed.
        t = fp_tally(["no-effect"] * 8)
        assert t["scored"] == 0, "invariant trials inflated the denominator"
        assert t["false_positives"] == 0

    def test_a_false_positive_is_in_BOTH_numerator_and_denominator(self):
        t = fp_tally(["fp"])
        assert (t["false_positives"], t["scored"]) == (1, 1), t

    def test_no_outcome_can_reach_the_numerator_without_the_denominator(self):
        """Guards the table directly: a numerator-without-denominator row would let the rate
        exceed 1.0, or divide by zero on a run whose only outcome was that row."""
        for name, (in_denom, in_numer, _) in FP_OUTCOMES.items():
            assert not (in_numer and not in_denom), (
                f"outcome {name!r} counts toward the false-positive numerator but not the "
                "denominator, which makes the published rate meaningless."
            )

    def test_every_outcome_fp_outcome_can_return_is_in_the_table(self):
        """A new outcome that fp_outcome returns but the table lacks would KeyError mid-run,
        after the API calls were paid for."""
        produced = {
            fp_outcome(TestFpOutcome._R(DiffVerdict.unchanged, 1.0)),
            fp_outcome(TestFpOutcome._R(DiffVerdict.unchanged, 0.9)),
            fp_outcome(TestFpOutcome._R(DiffVerdict.regression, 0.99)),
            fp_outcome(TestFpOutcome._R(DiffVerdict.changed_minor, 0.99)),
            fp_outcome(TestFpOutcome._R(DiffVerdict.insufficient_evidence, 0.5)),
        }
        assert produced <= set(FP_OUTCOMES), produced - set(FP_OUTCOMES)
