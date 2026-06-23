"""Golden tests for the behavioral diff engine.

Two jobs:
1. catch the four canonical regressions — (a) no change, (b) tool-call regression,
   (c) refusal spike, (d) format drift;
2. PROVE the north-star property — a low false-positive rate. The engine must NOT
   cry wolf on model non-determinism: a single odd run, or a majority that flips
   between two equally-likely behaviors, is noise, not a regression.

Traces are constructed inline and deterministically — no network, no recorded
fixtures needed, so CI stays cheap and reproducible.
"""

from modelpin.diff import diff_scenario
from modelpin.diff.stats import (
    permutation_pvalue_distribution,
    permutation_pvalue_mean,
)
from modelpin.diff.structural import trajectory_match
from modelpin.models import Assertion, DiffVerdict, Scenario, ToolCall, Trace

RUNS = 5  # spec default is 3-5; 5 gives the permutation test enough power to be decisive.


def trace(seq=(), refused=False, output="ok", run=0):
    return Trace(
        scenario_id="s",
        model_id="m",
        run_idx=run,
        tool_calls=[ToolCall(name=n) for n in seq],
        refused=refused,
        final_output=output,
    )


def runs(seqs, refused=False, output="ok"):
    """Build a list of traces, one per element of ``seqs`` (each a tool-name list)."""
    return [trace(seq=s, refused=refused, output=output, run=i) for i, s in enumerate(seqs)]


# --------------------------------------------------------------------------- #
# (a)-(d): the four canonical cases the engine MUST catch (or correctly ignore)
# --------------------------------------------------------------------------- #


def test_a_no_change_is_unchanged():
    base = runs([["lookup_order"]] * RUNS)
    cand = runs([["lookup_order"]] * RUNS)
    r = diff_scenario("s", "old", "new", base, cand)
    assert r.verdict == DiffVerdict.unchanged
    assert r.signals.tool_call_match == 1.0
    assert r.confidence == 1.0


def test_b_consistent_tool_call_change_is_regression():
    base = runs([["lookup_order"]] * RUNS)
    cand = runs([["lookup_order", "lookup_order"]] * RUNS)  # now calls it twice, every run
    r = diff_scenario("s", "old", "new", base, cand)
    assert r.verdict == DiffVerdict.regression
    assert r.signals.tool_call_match < 1.0
    assert r.confidence >= 0.9
    assert "tool-call" in r.explanation


def test_c_refusal_spike_is_regression():
    base = runs([["cancel_subscription"]] * RUNS, refused=False)
    cand = runs([["cancel_subscription"]] * RUNS, refused=True)  # now refuses every run
    r = diff_scenario("s", "old", "new", base, cand)
    assert r.verdict == DiffVerdict.regression
    assert r.signals.refusal_delta == 1.0
    assert r.confidence >= 0.9


def test_d_format_drift_is_minor():
    sc = Scenario(
        id="s", name="invoice", input={"messages": []}, assertions=Assertion(must_contain=["$"])
    )
    base = runs([[]] * RUNS, output="Total: $5")
    cand = runs([[]] * RUNS, output="Total: 5")  # consistently drops the "$"
    r = diff_scenario("s", "old", "new", base, cand, scenario=sc)
    assert r.verdict == DiffVerdict.changed_minor
    assert r.signals.format_valid is False


# --------------------------------------------------------------------------- #
# False-positive guards: the whole point of the multi-run statistics
# --------------------------------------------------------------------------- #


def test_single_refusal_blip_is_not_a_regression():
    """One refusing run out of five is sampling noise, not a regression. The old
    'refusal_delta >= 0.3' rule wrongly flagged this — the permutation test must not."""
    base = runs([["cancel_subscription"]] * RUNS, refused=False)
    cand = [trace(["cancel_subscription"], refused=(i == 0), run=i) for i in range(RUNS)]
    r = diff_scenario("s", "old", "new", base, cand)
    assert r.verdict != DiffVerdict.regression


def test_noisy_but_equivalent_distribution_is_unchanged():
    """Both models exhibit the SAME bimodal behavior (sometimes one call, sometimes
    two); only the per-run majority happens to flip. A naive majority comparison
    would flag a regression — the distributional test must call it unchanged."""
    one, two = ["lookup_order"], ["lookup_order", "lookup_order"]
    base = runs([one, one, one, two, two])  # majority = one call
    cand = runs([two, two, two, one, one])  # majority = two calls, same distribution
    r = diff_scenario("s", "old", "new", base, cand)
    assert r.verdict == DiffVerdict.unchanged


def test_false_positive_rate_is_zero_on_equivalent_pairs():
    """Held-out-style check (spec DoD): across several noisy-but-equivalent pairs,
    the engine must flag ZERO regressions. This is the metric the product lives on."""
    a, b, c = ["t1"], ["t1", "t2"], ["t1", "t2", "t3"]
    equivalent_pairs = [
        (runs([a, a, b, b, c]), runs([b, c, a, b, a])),  # same 3-way mix, reshuffled
        (runs([a, a, a, a, b]), runs([a, b, a, a, a])),  # mostly a, one b, either side
        (runs([a, b, a, b, a]), runs([b, a, b, a, b])),  # alternating, balanced
        (runs([a] * 5), runs([a] * 4 + [b])),  # one stray extra call
    ]
    flagged = sum(
        diff_scenario("s", "old", "new", base, cand).verdict == DiffVerdict.regression
        for base, cand in equivalent_pairs
    )
    assert flagged == 0, f"false positives on equivalent pairs: {flagged}/{len(equivalent_pairs)}"


# --------------------------------------------------------------------------- #
# Match modes
# --------------------------------------------------------------------------- #


def test_unordered_mode_ignores_call_order():
    base = runs([["lookup_order", "issue_refund"]] * RUNS)
    cand = runs([["issue_refund", "lookup_order"]] * RUNS)  # same calls, swapped order
    assert diff_scenario("s", "o", "n", base, cand, mode="strict").verdict == DiffVerdict.regression
    assert (
        diff_scenario("s", "o", "n", base, cand, mode="unordered").verdict == DiffVerdict.unchanged
    )


def test_trajectory_match_modes():
    assert trajectory_match(["a", "b"], ["a", "b"], "strict")
    assert not trajectory_match(["a", "b"], ["b", "a"], "strict")
    assert trajectory_match(["a", "b"], ["b", "a"], "unordered")
    assert trajectory_match(["a", "b"], ["a"], "subset")  # dropped a call: allowed
    assert not trajectory_match(["a"], ["a", "b"], "subset")  # new call: forbidden
    assert trajectory_match(["a"], ["a", "b"], "superset")  # extra call: allowed
    assert not trajectory_match(["a", "b"], ["a"], "superset")  # dropped call: forbidden


# --------------------------------------------------------------------------- #
# Permutation-test sanity (the engine's foundation)
# --------------------------------------------------------------------------- #


def test_permutation_mean_blip_vs_spike():
    # one-in-five blip: not significant
    assert permutation_pvalue_mean([0, 0, 0, 0, 0], [1, 0, 0, 0, 0]) > 0.05
    # full spike: decisively significant
    assert permutation_pvalue_mean([0, 0, 0, 0, 0], [1, 1, 1, 1, 1]) < 0.05
    # a drop in the bad rate is never a regression (one-sided)
    assert permutation_pvalue_mean([1, 1, 1, 1, 1], [0, 0, 0, 0, 0]) == 1.0


def test_permutation_distribution_shift_vs_noise():
    a, b = ("t",), ("t", "t")
    # identical distributions
    assert permutation_pvalue_distribution([a] * 5, [a] * 5) == 1.0
    # clean shift
    assert permutation_pvalue_distribution([a] * 5, [b] * 5) < 0.05
    # same balanced mix, reshuffled -> not significant
    assert permutation_pvalue_distribution([a, a, a, b, b], [b, b, b, a, a]) > 0.05


# --------------------------------------------------------------------------- #
# Large-N sampling path (>16 total runs): the fallback must stay statistically
# valid — a regression guard for the observed-split bug an audit caught, where a
# clean spike wrongly returned p == 0.0 (impossible) and biased toward FALSE
# POSITIVES.
# --------------------------------------------------------------------------- #


def test_large_n_sampling_pvalue_is_positive_and_significant():
    # 20 total runs -> sampling fallback. A clean 0->100% spike must be flagged,
    # with a SMALL BUT STRICTLY POSITIVE p (a valid permutation p is never 0.0).
    p = permutation_pvalue_mean([0] * 10, [1] * 10)
    assert 0.0 < p < 0.05


def test_large_n_sampling_does_not_false_positive_on_equivalent():
    a, b = ("t",), ("t", "t")
    base = [a] * 6 + [b] * 4
    cand = [a] * 4 + [b] * 6  # same two behaviors, modest mix shift; 20 total -> sampling
    assert permutation_pvalue_distribution(base, cand) > 0.05
