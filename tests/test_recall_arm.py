"""MP-79 - the detection arm must not be able to report a number it did not measure.

MP-75 spent four rounds hardening the FALSE-POSITIVE arm and left the DETECTION arm inline in
`main()`, where no test reaches. `[M]` bug-reproducer 2026-08-23 ran the same mutant battery
against it. **Eight of nine mutants survived a full green suite:**

    detected += int(caught)  ->  detected += 1                  302 passed
    caught = kind == "fp"    ->  caught = True                   302 passed
    caught = kind == "fp"    ->  caught = kind != "unmeasured"   302 passed   (same mutant:
                                   the abstention has already `continue`d, so it is always True)
    checked += 1             ->  checked += 2                    302 passed
    checked += 1 hoisted above the abstention `continue`         302 passed
    delete the `unmeasured` exclusion block (ADR-0018)           302 passed
    whole per-scenario body  ->  `continue`  (-20 lines, 0/0)    302 passed
    delete both closing print() calls                            302 passed
    classify(r.verdict)      ->  fp_outcome(r)                   1 FAILED  <- the only kill

The single kill came from a source grep, and it landed on the mutant with the LEAST effect on
the published numbers: after the abstention `continue`, `classify`'s "clean" and `fp_outcome`'s
"no-effect" both score a MISS anyway. Every mutant that actually moved a number survived.

So the harness could have printed `Detection: 3/3 injected regressions caught` for an engine
that flagged nothing at all - and since #46 withdrew the false-positive claim (ADR-0022),
detection is the only half of the DoD the project still asserts.

No provider is needed for any of this: ADR-0006 forbids a live call from the suite, which is
why the arm is a pure function over rows and why `main()` itself is pinned by grep.
"""

import inspect
import sys
from pathlib import Path
from types import CodeType

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelpin.diff import DiffVerdict  # noqa: E402
from scripts.fp_measurement import (  # noqa: E402
    FP_OUTCOMES,
    RECALL_OUTCOMES,
    build_row,
    fp_outcome,
    main,
    recall_outcome,
    recall_report,
    recall_summary,
    recall_tally,
)


class _Res:
    """The three fields the recall arm reads off a DiffResult."""

    def __init__(self, verdict, confidence, explanation="why"):
        self.verdict, self.confidence, self.explanation = verdict, confidence, explanation


_REP = {"tools": 1, "args": 1, "text": 1}

#: Confidences spanning the engine's whole observed range, including the two extremes that
#: matter: 1.0 (the FP arm's exclusion trigger) and 0.0.
_CONFIDENCES = (0.0, 0.5, 0.952, 0.992, 0.996, 1.0)


class TestRecallOutcome:
    """The per-scenario decision. Every mutant below lived here and survived."""

    def test_a_flagged_verdict_is_a_detection_at_every_confidence(self):
        for verdict in (DiffVerdict.regression, DiffVerdict.changed_minor):
            for conf in _CONFIDENCES:
                assert recall_outcome(_Res(verdict, conf)) == "detected", (
                    f"{verdict.value} at confidence {conf} was not credited as a detection; "
                    "the injected perturbation was caught and must count."
                )

    def test_a_perturbed_scenario_that_still_reads_unchanged_is_a_miss(self):
        assert recall_outcome(_Res(DiffVerdict.unchanged, 0.95)) == "missed"

    def test_an_INVARIANT_perturbed_scenario_is_a_MISS_not_an_exclusion(self):
        """THE test this file exists for. ADR-0022's closing paragraph, made executable.

        `unchanged` at confidence 1.0 is precisely the trial the FP arm EXCLUDES - nothing
        could have fired. The recall arm must score it as a MISS anyway, because the
        perturbation was a real injected behaviour change and the candidate answered
        identically regardless. Excluding it lets a dead engine post `0/0` recall, which
        reads as "nothing to report" rather than "the engine caught nothing".

        [M] fp-guardian, the MP-75 review recorded in ADR-0022: inserting
        `if not measurable(r): continue` into the recall arm left all 281 tests green.
        """
        r = _Res(DiffVerdict.unchanged, 1.0)
        assert recall_outcome(r) == "missed", (
            "an invariant perturbed trial was excluded from the detection denominator. That "
            "is the FP arm's exclusion adopted by the wrong arm: it converts every miss on a "
            "deterministic model into a non-event, and a dead engine then reports 0/0."
        )
        # ...and the SAME trial is excluded by the FP arm. Both readings are correct; they
        # are different questions. If these two ever agree, one arm has adopted the other's.
        assert fp_outcome(r) == "no-effect"

    def test_an_abstention_is_excluded_rather_than_scored_as_a_miss(self):
        """ADR-0018, which is a different exclusion from ADR-0022's and the only one this
        arm has. A run that reached no verdict measured nothing, so it is neither a
        detection nor a miss. [M] deleting this branch entirely left all 302 green."""
        assert recall_outcome(_Res(DiffVerdict.insufficient_evidence, 0.5)) == "unmeasured"

    def test_the_three_outcomes_are_distinguishable(self):
        """Guards the wiring, not just the predicate: collapse any branch and this fails."""
        outcomes = {
            recall_outcome(_Res(DiffVerdict.regression, 0.99)),
            recall_outcome(_Res(DiffVerdict.unchanged, 1.0)),
            recall_outcome(_Res(DiffVerdict.insufficient_evidence, 0.5)),
        }
        assert outcomes == {"detected", "missed", "unmeasured"}, outcomes


class TestRecallTally:
    """The accounting. [M] `detected += 1` - the mutant the row was filed on - lives here."""

    def test_only_detections_reach_the_numerator(self):
        t = recall_tally(["detected", "missed", "missed", "unmeasured"])
        assert t == {"checked": 3, "detected": 1, "unmeasured": 1}, t

    def test_a_dead_engine_scores_zero_not_the_number_of_scenarios(self):
        """The headline mutant, at the tally level: `detected += 1` would return 3 here."""
        t = recall_tally(["missed", "missed", "missed"])
        assert t["detected"] == 0, (
            f"three missed regressions were credited as {t['detected']} detections. This is "
            "`detected += 1`: the arm reports 100% detection for an engine that flagged "
            "nothing."
        )
        assert t["checked"] == 3, "a miss must stay in the denominator"

    def test_an_abstention_is_in_neither_numerator_nor_denominator(self):
        t = recall_tally(["unmeasured"] * 4)
        assert (t["detected"], t["checked"]) == (0, 0), t
        assert t["unmeasured"] == 4, "the exclusion must still be published"

    def test_no_outcome_reaches_the_numerator_without_the_denominator(self):
        """A numerator-without-denominator row would let detection exceed 1.0, or divide by
        zero on a run whose only outcome was that row."""
        for name, (in_denom, in_numer, _bucket, _label) in RECALL_OUTCOMES.items():
            assert not (in_numer and not in_denom), (
                f"outcome {name!r} counts toward the detection numerator but not the "
                "denominator, which makes the published fraction meaningless."
            )

    def test_every_outcome_recall_outcome_can_return_is_in_the_table(self):
        """A returned outcome the table lacks would KeyError mid-run, after the API calls
        were paid for."""
        produced = {recall_outcome(_Res(v, c)) for v in DiffVerdict for c in (0.5, 1.0)}
        assert produced <= set(RECALL_OUTCOMES), produced - set(RECALL_OUTCOMES)

    def test_the_two_arms_vocabularies_are_not_interchangeable(self):
        """Why swapping one arm's decision function for the other's cannot pass silently.

        [M] the equivalent swap in the FP arm (`classify` for `fp_outcome`) restored the
        withdrawn `0/8 = 0%` with 281 tests green, precisely because every string `classify`
        returned was a valid FP_OUTCOMES key. These two tables must never acquire that
        property: "clean" / "fp" / "no-effect" have to be KeyErrors here.
        """
        assert set(FP_OUTCOMES) & set(RECALL_OUTCOMES) == {"unmeasured"}
        for foreign in ("clean", "fp", "no-effect"):
            with pytest.raises(KeyError):
                recall_tally([foreign])


class TestRecallReport:
    """The CALL SITE - the layer MP-75 needed three separate rounds to learn to pin.
    [M] replacing this loop's inline body with `continue` left all 302 tests green."""

    def test_an_engine_that_flags_nothing_reports_zero_over_three(self):
        """The whole point. Three injected regressions, engine silent on all three."""
        rows = [(f"s{i}", _Res(DiffVerdict.unchanged, 1.0), _REP, _REP) for i in range(3)]
        t, lines = recall_report(rows)
        assert (t["detected"], t["checked"]) == (0, 3), (
            f"a dead engine reported {t['detected']}/{t['checked']} detection. Either the "
            "numerator is unconditional or the invariant trials were excluded; both let the "
            "harness certify an engine that caught nothing."
        )
        assert t["unmeasured"] == 0, "a miss is not an exclusion"
        assert len(lines) == 3

    def test_a_working_engine_scores_every_flag(self):
        rows = [("a", _Res(DiffVerdict.regression, 0.99), _REP, _REP)]
        rows.append(("b", _Res(DiffVerdict.changed_minor, 0.97), _REP, _REP))
        t, _ = recall_report(rows)
        assert (t["detected"], t["checked"]) == (2, 2), t

    def test_a_mixed_run_reports_the_real_fraction(self):
        rows = [
            ("caught", _Res(DiffVerdict.regression, 0.99), _REP, _REP),
            ("missed", _Res(DiffVerdict.unchanged, 0.9), _REP, _REP),
            ("invariant", _Res(DiffVerdict.unchanged, 1.0), _REP, _REP),
            ("abstained", _Res(DiffVerdict.insufficient_evidence, 0.5), _REP, _REP),
        ]
        t, lines = recall_report(rows)
        assert (t["detected"], t["checked"], t["unmeasured"]) == (1, 3, 1), t
        assert len(lines) == 4, "every scenario gets a line, exclusions included"

    def test_the_per_scenario_lines_name_what_happened(self):
        """Kills the body-to-`continue` mutant at the line level: a silent arm prints
        nothing, and an operator watching a paid run sees no per-scenario evidence."""
        _, lines = recall_report([("refund_request", _Res(DiffVerdict.unchanged, 1.0), _REP, _REP)])
        assert "refund_request" in lines[0]
        assert "MISSED" in lines[0], lines[0]

    def test_provider_errors_are_counted_not_silently_dropped(self):
        """`main()` used to `continue` past these, so a run where every perturbed scenario
        failed to reach the API printed `Detection: 0/0` with nothing explaining why."""
        t, lines = recall_report([("a", None, None, None), ("b", None, None, None)])
        assert t["errors"] == 2, t
        assert (t["checked"], t["detected"]) == (0, 0)
        assert lines == []

    def test_swapping_in_the_fp_arms_decision_cannot_pass_quietly(self):
        """The mutant the old source-grep guard caught, now caught behaviourally.

        `recall_outcome` and `fp_outcome` disagree on exactly the trial ADR-0022 is about,
        and the disagreement is a KeyError rather than a wrong number - so this cannot decay
        into a silently-plausible substitution the way the FP arm's did.
        """
        r = _Res(DiffVerdict.unchanged, 1.0)
        assert recall_outcome(r) == "missed" and fp_outcome(r) == "no-effect"
        assert recall_tally([recall_outcome(r)])["checked"] == 1
        with pytest.raises(KeyError):
            recall_tally([fp_outcome(r)])


class TestRecallSummary:
    """What reaches the operator. [M] deleting both closing print() calls left 302 green."""

    @staticmethod
    def _t(detected=0, checked=0, unmeasured=0, errors=0):
        return {
            "detected": detected,
            "checked": checked,
            "unmeasured": unmeasured,
            "errors": errors,
        }

    def test_the_detection_fraction_reaches_the_operator(self):
        out = "\n".join(recall_summary(self._t(detected=1, checked=3)))
        assert "Detection: 1/3 injected perturbations caught" in out, out
        # SINGULAR, deliberately: it subsumes the plural. [M] fp-guardian 2026-08-23 -
        # the first version of this pin read "injected regressions" and the CHECKED-NOTHING
        # banner ("no injected regression reached a verdict") walked straight past it. A
        # guard that reads as a vocabulary pin and is really a plural-string pin.
        for tally in (self._t(detected=1, checked=3), self._t(), self._t(errors=2)):
            body = " ".join(recall_summary(tally))
            assert "injected regression" not in body, (
                f"the arm calls the injected instructions `regressions`, asserting the very "
                f"premise it exists to test: {body!r}. That is the overclaim fp-guardian "
                "blocked in the MISSED note."
            )

    def test_a_run_that_checked_nothing_says_so_loudly(self):
        """`0/0` is the number a dead engine plus a wrong exclusion produces together. It
        must never read as a quiet pass."""
        out = "\n".join(recall_summary(self._t(unmeasured=3)))
        assert "Detection: 0/0" in out
        assert "CHECKED NOTHING" in out, out

    def test_an_all_error_run_blames_the_network_not_the_engine(self):
        out = "\n".join(recall_summary(self._t(errors=3)))
        assert "REACHED NO VERDICT" in out, out
        assert "connectivity" in out

    def test_a_miss_is_named_without_claiming_the_behaviour_changed(self):
        """Operator-facing wording carries ADR-0022's distinction, because the number alone
        does not: `2/3` looks like a rounding problem unless the miss is named.

        [M] fp-guardian 2026-08-23 BLOCKED the first version of this note, which read "the
        perturbation did change the behaviour, whatever the candidate did about it". The
        perturbation changes the INSTRUCTION; whether behaviour changed is the thing being
        measured. `decline_pii` is 1 of the 3 entries in PERTURBATIONS and on the run of
        record returned `unchanged` because the model RESISTED it - so that sentence printed
        "real failure to detect" over a correct true negative.

        Why this is a test and not merely a careful author: that sentence is direct pressure
        to loosen MIN_SEMANTIC_DELTA until the "miss" converts into a detection, and MP-80
        records that the semantic sweep is FLAT from 0.1 to 0.9 - the slack is there to take.
        The accounting must not change; only the claim about what a miss proves.
        """
        out = "\n".join(recall_summary(self._t(detected=1, checked=3)))
        assert "2 perturbation(s) MISSED" in out, out
        assert "never" in out and "excluded" in out, out
        assert "ignored the injected instruction" in out, (
            f"the note no longer offers the resisted-instruction reading: {out!r}. The miss "
            "is counted either way, but the operator must not be told behaviour changed."
        )
        for overclaim in ("did change the behaviour", "real failure to detect"):
            assert overclaim not in out, (
                f"the note asserts {overclaim!r} as fact. The perturbation changes the "
                "INSTRUCTION; whether behaviour changed is what this arm is measuring."
            )

    def test_the_exclusion_counter_is_always_published_beside_the_fraction(self):
        out = "\n".join(recall_summary(self._t(detected=2, checked=2, unmeasured=5)))
        assert "Unmeasured (excluded): 5" in out, out

    def test_provider_errors_are_surfaced_when_present_and_silent_when_not(self):
        assert any("Provider errors" in x for x in recall_summary(self._t(checked=1, errors=2)))
        assert not any("Provider errors" in x for x in recall_summary(self._t(checked=1)))

    def test_a_full_run_does_not_print_a_percentage(self):
        """[M] ADR-0022 withdrew `0/8 = 0%` because a rate over a handful of trials reads as
        a property of the engine. `3/3 = 100%` is the same error mirrored, and this arm
        publishes no interval yet (MP-82). Print the fraction; let the reader see n=3.

        [M] fp-guardian computed what the withheld interval would say, which is why MP-82
        exists rather than nothing: `3/3` bounds the true detection rate at only 36.8%, and
        `2/3` - the actual run of record - at 13.5%. The bare fraction is weak evidence too;
        it is just not weak in a way that reads as a claim."""
        out = "\n".join(recall_summary(self._t(detected=3, checked=3)))
        assert "100%" not in out, (
            f"the detection arm published a percentage over 3 trials: {out!r}. Either print "
            "an interval with it (MP-82) or leave the fraction to speak for itself."
        )


class TestBuildRow:
    """The one path feeding BOTH denominators.

    [M] fp-guardian 2026-08-23: as a closure inside `main()` this was unreachable by any test,
    and a poisoned version blanks the false-positive rate and the detection fraction at once
    while leaving the suite green. `verdict_fn` is injected so it can be exercised without a
    provider (ADR-0006).
    """

    def test_a_verdict_is_passed_through_with_its_repertoires(self):
        assert build_row("s", "B", "C", lambda b, c, sid: ("R", "BR", "CR")) == (
            "s",
            "R",
            "BR",
            "CR",
        )

    def test_the_base_and_candidate_reach_the_verdict_in_that_order(self):
        """A base/candidate swap is SILENT in the FP arm, which passes the same scenario
        twice. It would surface only in the recall arm, as a perturbed base against an
        unperturbed candidate - which still produces an entirely plausible verdict."""
        seen = []
        build_row("sid", "BASE", "CAND", lambda b, c, sid: seen.append((b, c, sid)) or None)
        assert seen == [("BASE", "CAND", "sid")], seen

    def test_a_provider_error_becomes_a_row_both_arms_read_as_an_error(self):
        row = build_row("s", "B", "C", lambda b, c, sid: None)
        assert row == ("s", None, None, None)
        # ...and both reporters must count it as an error rather than score it.
        assert recall_report([row])[0]["errors"] == 1
        assert recall_report([row])[0]["checked"] == 0


def _called_names(fn) -> set[str]:
    """Every global name a function's compiled code can reference, nested scopes included.

    Compiled names rather than source text. `recall_outcome`'s docstring has to MENTION
    `measurable()` in order to explain why it must never call it, and a grep cannot tell the
    two apart - [M] the first version of the guard below failed on its own explanation.
    """
    out, stack = set(), [fn.__code__]
    while stack:
        code = stack.pop()
        out |= set(code.co_names)
        stack += [c for c in code.co_consts if isinstance(c, CodeType)]
    return out


def _recall_arm_source() -> str:
    """`main()`'s recall slice. Grepped, because `main()` calls `adapter.preflight()` and
    ADR-0006 forbids a live call from the suite - the same technique the FP arm's call-site
    guard uses. `inspect.getsource(main)` rather than the whole file, so this cannot be
    fooled by moving a function above or below the banner."""
    src = inspect.getsource(main)
    return src[src.index("[ARM:RECALL]") :]


def test_each_arm_marker_occurs_exactly_once():
    """The slice markers are load-bearing for three guards across two files, and a SECOND
    occurrence silently truncates a slice to nothing rather than erroring.

    [M] 2026-08-23: introducing these markers, the explanatory comment beside them contained
    the literal tokens, so `src.index("[ARM:RECALL]")` matched the COMMENT - inside the FP
    arm - and cut the FP arm's slice down to 40 characters. It surfaced only because MP-75's
    call-site guard went red. A future edit that mentions a marker in prose gets caught here
    instead.
    """
    src = inspect.getsource(main)
    for marker in ("[ARM:FP]", "[ARM:RECALL]"):
        assert src.count(marker) == 1, (
            f"{marker} occurs {src.count(marker)} times in main(). Every source-slicing "
            "guard keys on the FIRST occurrence, so a duplicate silently shrinks a slice "
            "and the guard passes over an empty window."
        )


def test_the_recall_arm_publishes_only_through_the_pinned_helpers():
    """MP-75's landmine, applied to the other arm BEFORE it costs four rounds.

    Pinning a pure function does not pin its caller, and every extraction creates a new
    caller. `recall_report` and `recall_summary` are fully covered above - and all of that
    coverage is worth nothing if `main()` stops calling them, or recomputes the numbers
    inline beside them.
    """
    arm = _recall_arm_source()
    assert "recall_report(" in arm, "the recall arm stopped going through recall_report()"
    assert "recall_summary(" in arm, "the recall arm stopped publishing through recall_summary()"
    # BOTH loops, by name and by count. [M] mutation-sentinel 2026-08-23: a bare
    # `assert "print(line)" in arm` is satisfied by the SUMMARY loop alone, so deleting the
    # per-scenario loop left all 332 green - and the MISSED note tells the operator to "read
    # the per-scenario explanation above", which under that mutant does not exist. The
    # content of those lines was pinned; their CONSUMPTION was not. MP-75's lesson, one notch
    # further out than MP-75 took it.
    # The BINDING as well as the loop: [M] pinning only the loop left `rt, _discard =
    # recall_report(...)` alive - the per-scenario lines silently discarded, and `main()` then
    # raising NameError at the end of a PAID run. No test runs main() (it needs a provider,
    # ADR-0006), so the producer/consumer wiring has to be asserted as a pair.
    assert "recall_lines = recall_report(" in arm, "recall_report's lines are no longer bound"
    assert "for line in recall_lines:" in arm, "the per-scenario lines are no longer printed"
    assert "for line in recall_summary(" in arm, "the summary lines are no longer printed"
    assert arm.count("print(line)") == 2, (
        f"the recall arm has {arm.count('print(line)')} print loops, expected 2 (per-scenario "
        "evidence, then summary). One of them has been dropped."
    )
    # [M] mutation-sentinel: the banner is operator-facing stdout that no test read, so the
    # vocabulary X2/X3 forbid stayed freely reachable here - including `expect regression/
    # changed_minor`, which announces the arm's conclusion before the arm runs. That is a
    # worse overclaim than either string already pinned, and ADR-0023 exists to refuse it.
    assert "injected regression" not in arm.lower(), (
        "the recall arm's printed banner calls the injected instructions `regressions`. The "
        "summary was pinned against this and the banner was not."
    )
    assert (
        "expect regression" not in arm
    ), "the banner tells the operator what to expect before the arm has measured anything."
    assert "INJECTED PERTURBATIONS" in arm, "the arm's header no longer names itself"
    for inline in ("detected +=", "checked +="):
        assert inline not in arm, (
            f"`{inline}` is back inline in main()'s recall arm. That is the shape [M] "
            "bug-reproducer found eight surviving mutants in; nothing below main() can pin it."
        )
    # The SELECTION expression, over the whole of main(): [M] fp-guardian 2026-08-23 -
    # asserting bare "PERTURBATIONS" inside the sliced window does NOT close this, because
    # the selection sits above the marker and the assertion is satisfied by the unrelated
    # `PERTURBATIONS[s.id]` lookup inside the comprehension. `perturbed = []` survived all
    # 72 tests in fp-guardian's mirror.
    assert "for s in scenarios if s.id in PERTURBATIONS" in inspect.getsource(main), (
        "main() no longer selects the perturbed scenarios from PERTURBATIONS. An empty "
        "selection is the one remaining way to make this arm report 0/0 - loud rather than "
        "silent (the CHECKED NOTHING banner fires), but nothing below main() can see it."
    )
    assert "_perturb(" in arm, "the candidate side is no longer perturbed at all"
    names = _called_names(main)
    assert "recall_tally" not in names, "main() bypasses recall_report() to tally directly"
    assert "classify" not in names, (
        "main() classifies verdicts itself again. Both arms must go through their own "
        "outcome function; classify() alone knows about neither exclusion."
    )


def test_the_recall_arm_never_adopts_the_fp_arms_exclusion():
    """ADR-0022's stated invariant, guarded across every layer that could reintroduce it.

    The behavioural test above proves `recall_outcome` returns "missed" for an invariant
    trial. This proves nobody added a second, earlier exclusion on top of it - a
    `if not measurable(r): continue` in the reporter or the caller would drop the row before
    the decision function ever saw it, and no assertion about `recall_outcome` would move.
    """
    for fn in (recall_outcome, recall_report, recall_tally, main):
        names = _called_names(fn)
        assert "measurable" not in names, (
            f"{fn.__name__} consults measurable(). A perturbed scenario that still reads "
            "`unchanged` is a MISS, not an unmeasurable trial; excluding it lets a dead "
            "engine report 0/0 recall. See ADR-0022."
        )
    for fn in (recall_outcome, recall_report, recall_tally):
        assert "fp_outcome" not in _called_names(fn), (
            f"{fn.__name__} uses the FP arm's decision function, whose vocabulary this arm "
            "does not share."
        )
