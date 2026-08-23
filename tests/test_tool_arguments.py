"""Tool-call ARGUMENTS are captured but never diffed (MP-04, spec 6A).

`structural.py:27-29` collapses a run to `tuple(tc.name for tc in trace.tool_calls)` --
names only -- while `models.py:72-74` faithfully stores `arguments` on every ToolCall. So a
candidate that calls the RIGHT tool with a catastrophically WRONG argument reads as
`unchanged` at confidence 1.00: `issue_refund(amount=49.99)` -> `issue_refund(amount=4999.00)`
is a 100x financial error the engine cannot see.

The tool signal is the ONLY place arguments could ever matter: the judge reads `final_output`
(`semantic.py:68-69`), the assertion signal reads `final_output`
(`structural.py:122`), and refusal reads `refused`. When only an argument changes the output
text is identical, so `semantic.py:64` short-circuits and the judge is never even called.

The guard tests below fix the sensitivity ceiling BEFORE the fix raises it: arguments arrive
as a parsed dict whose key order is whatever the model emitted (`openai.py:150` json.loads),
so any encoding that is not order-insensitive turns provider jitter into a false positive --
the one thing this engine must never do. They pass today only because arguments are ignored
entirely; they must still pass afterwards.
"""

from __future__ import annotations

from modelpin.config import DEFAULT_RUNS
from modelpin.diff import diff_scenario
from modelpin.models import DiffVerdict, ToolCall, Trace

RUNS = DEFAULT_RUNS  # 5 since MP-03; below N=4 the tool signal cannot fire at all.


def _runs(model: str, args: dict, n: int = RUNS, tool: str = "issue_refund") -> list[Trace]:
    return [
        Trace(
            scenario_id="refund",
            model_id=model,
            run_idx=i,
            tool_calls=[ToolCall(name=tool, arguments=dict(args))],
            final_output="Refund issued.",
        )
        for i in range(n)
    ]


# --- the headline ------------------------------------------------------------------------


def test_a_hundredfold_argument_change_is_not_unchanged():
    """The row's claim: same tool name, 100x the money, reported as `unchanged` @ 1.00."""
    r = diff_scenario(
        "refund", "old", "new", _runs("old", {"amount": 49.99}), _runs("new", {"amount": 4999.00})
    )
    assert r.verdict == DiffVerdict.regression, (
        f"a 100x refund amount reported {r.verdict.value} @ {r.confidence} "
        f"(tool_call_match={r.signals.tool_call_match})"
    )


def test_the_tool_signal_does_not_score_a_changed_argument_as_a_perfect_match():
    """`tool_call_match: 1.0` means "identical distributions" -- it is a positive claim of
    sameness, and here it is false."""
    r = diff_scenario(
        "refund", "old", "new", _runs("old", {"amount": 49.99}), _runs("new", {"amount": 4999.00})
    )
    assert r.signals.tool_call_match is not None and r.signals.tool_call_match < 1.0


def test_a_changed_argument_is_caught_in_every_match_mode():
    """`strict`/`unordered` bucket a run into a key; `subset`/`superset` score it against a
    relation. Arguments are dropped on the way into BOTH paths, so neither can see the change."""
    for mode in ("strict", "unordered", "subset", "superset"):
        r = diff_scenario(
            "refund",
            "old",
            "new",
            _runs("old", {"amount": 49.99}),
            _runs("new", {"amount": 4999.00}),
            mode=mode,
        )
        assert r.verdict == DiffVerdict.regression, f"mode={mode} reported {r.verdict.value}"


def test_a_new_argument_key_is_a_behavior_change():
    """Not just changed values: a candidate that stops passing `dry_run` is executing for real."""
    r = diff_scenario(
        "refund",
        "old",
        "new",
        _runs("old", {"amount": 49.99, "dry_run": True}),
        _runs("new", {"amount": 49.99}),
    )
    assert r.verdict == DiffVerdict.regression


# --- the false-positive ceiling: these must pass BEFORE and AFTER the fix ----------------


def test_the_same_arguments_in_a_different_key_order_are_not_a_regression():
    """`openai.py:150` json.loads preserves the model's emission order, which is jitter, not
    behavior. Passes today only because arguments are ignored."""
    r = diff_scenario(
        "refund",
        "old",
        "new",
        _runs("old", {"amount": 49.99, "order_id": "A1"}),
        _runs("new", {"order_id": "A1", "amount": 49.99}),
    )
    assert r.verdict == DiffVerdict.unchanged


def test_int_and_float_spellings_of_the_same_number_are_not_a_regression():
    """`1` and `1.0` are equal in Python and unequal under json.dumps/repr; the OpenAI adapter
    parses JSON while the Google adapter passes the SDK's dict through, so the two can disagree
    on the same call."""
    r = diff_scenario("refund", "old", "new", _runs("old", {"qty": 1}), _runs("new", {"qty": 1.0}))
    assert r.verdict == DiffVerdict.unchanged


def test_one_odd_argument_in_five_runs_is_noise_not_a_regression():
    """ADR-0001: a single run never decides. Arguments must enter through the same
    distributional test as every other signal, not as a per-run equality check."""
    cand = _runs("new", {"amount": 49.99}, n=RUNS - 1) + _runs("new", {"amount": 4999.00}, n=1)
    r = diff_scenario("refund", "old", "new", _runs("old", {"amount": 49.99}), cand)
    assert r.verdict == DiffVerdict.unchanged


# --- blast radius: nothing else is watching ----------------------------------------------


def test_no_other_signal_sees_an_argument_only_change():
    """With the output text identical, the judge is never even billed -- so the tool signal is
    the sole place an argument change could ever register."""
    billed: list[tuple[str, str]] = []

    class _ParanoidJudge:
        """Says nothing is ever equivalent; if it is ever asked, it flags."""

        def equivalent(self, reference: str, candidate: str, task: str | None = None) -> bool:
            billed.append((reference, candidate))
            return False

    r = diff_scenario(
        "refund",
        "old",
        "new",
        _runs("old", {"amount": 49.99}),
        _runs("new", {"amount": 4999.00}),
        judge=_ParanoidJudge(),
    )
    assert billed == [], "judge saw the outputs differ; the premise of this file is wrong"
    assert r.signals.semantic_score == 1.0
    assert r.signals.refusal_delta == 0.0
    assert r.signals.format_valid is True
