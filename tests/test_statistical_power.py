"""A run that could not have reported a regression must not claim it found none (MP-55).

`[M] 2026-08-26` reproduced on the SHIPPED demo, offline, before the fix:

    $ mp check ... --runs 2
    warning: only 2 runs/scenario; 5+ gives the statistical diff real power ...
    OK 4 scenario(s) unchanged                                          exit 0
    last-report.md: "-> No behavioral regressions found; `demo-model-v2` looks safe to adopt."

    $ mp check ... --runs 5          # THE SAME FIXTURES
    REGRESSION angry_customer   REGRESSION refund_request   MINOR invoice_parse

Two regressions and a minor, present in the data both times, reported as "safe to adopt"
because an exact permutation test over C(4,2) = 6 relabelings has a hard p-floor of 1/6 =
0.167 and cannot return anything at or below ALPHA = 0.05. The warning said the run had less
POWER; it did not say the run was incapable of a conclusion, and the report said the opposite.

This is the north-star failure from the false-NEGATIVE side, on the first-run path, in the
demo a brand-new user runs -- and it is the same rule ADR-0018 already draws for a run that
measured nothing, applied one level up to a run that measured but could not conclude.

Deliberately NOT changed here: `MIN_RUNS`, the effect-size floors, and the exit code. Those
are sensitivity surfaces (ADR-0016, ADR-0002) and moving one needs its own calibration and
its own fp-guardian review. This governs only what the tool CLAIMS.
"""

from __future__ import annotations

import json
import tempfile
from math import comb
from pathlib import Path

from typer.testing import CliRunner

from modelpin.cli import app
from modelpin.demo import DEMO_DIRNAME, DEMO_FIXTURES, DEMO_FROM, DEMO_TO, write_demo
from modelpin.diff import ALPHA
from modelpin.diff.stats import (
    min_achievable_pvalue_distribution,
    min_achievable_pvalue_mean,
)
from modelpin.models import DiffResult, DiffVerdict
from modelpin.report import render_cli, render_pr_comment

_DEMO_ROOT = Path(tempfile.mkdtemp(prefix="modelpin-power-demo-"))
write_demo(_DEMO_ROOT)
_DEMO = _DEMO_ROOT / DEMO_DIRNAME
FIXTURES = str(_DEMO / DEMO_FIXTURES)
SCEN = str(_DEMO / "scenarios")
CONFIG = str(_DEMO / "modelpin.yaml")

runner = CliRunner()


# --- the floors themselves ----------------------------------------------------------------


def test_the_floors_are_the_exact_combinatorial_minimum():
    """Not an approximation and not a fitted constant: an exact permutation test over
    `C(nb+nc, nc)` relabelings cannot score below `1/C` one-sided, or `2/C` two-sided."""
    for n in range(2, 9):
        total = comb(2 * n, n)
        assert min_achievable_pvalue_mean(n, n) == 1 / total, n
        assert min_achievable_pvalue_distribution(n, n) == 2 / total, n


def test_no_signal_can_fire_at_two_runs_a_side():
    """The MP-55 headline. At N=2 the product cannot report a regression, ever."""
    assert min_achievable_pvalue_mean(2, 2) > ALPHA
    assert min_achievable_pvalue_distribution(2, 2) > ALPHA


def test_at_three_runs_the_tool_signal_is_dead_but_refusal_is_not():
    """The dead zone is MODE-dependent, and this asymmetry is load-bearing: `strict` and
    `unordered` route the tool/argument signals through the two-sided distribution test
    (floor 2/C), while refusal and format drift use the one-sided mean test (floor 1/C)."""
    assert min_achievable_pvalue_mean(3, 3) == ALPHA  # fires, exactly at the boundary
    assert min_achievable_pvalue_distribution(3, 3) > ALPHA  # cannot fire


def test_the_floor_depends_on_BOTH_sides_not_on_the_candidate_alone():
    """`baseline --runs 5` then `check --runs 2` gives 5 vs 2 -- a real, reachable regime
    that a floor computed from `--runs` alone would price wrong."""
    assert min_achievable_pvalue_mean(5, 2) != min_achievable_pvalue_mean(2, 2)
    assert min_achievable_pvalue_mean(5, 2) == 1 / comb(7, 2)


def test_the_floors_are_measured_from_the_real_test_not_restated():
    """The helpers drive the shipped permutation functions on their most extreme input, so a
    change to the test's tie handling or epsilon moves the published floor with it. A
    hand-written formula would silently keep agreeing with a test that had changed."""
    from modelpin.diff.stats import permutation_pvalue_mean

    assert min_achievable_pvalue_mean(4, 4) == permutation_pvalue_mean([0.0] * 4, [1.0] * 4)


# --- what the tool is then allowed to say -------------------------------------------------


def _unchanged(sid):
    return DiffResult(
        scenario_id=sid,
        from_model="a",
        to_model="b",
        verdict=DiffVerdict.unchanged,
        explanation="no statistically significant behavior change",
        confidence=1.0,
    )


def test_an_all_underpowered_run_never_says_safe_to_adopt():
    results = [_unchanged("s1"), _unchanged("s2")]
    md = render_pr_comment(results, "a", "b", 2, None, ["s1", "s2"])
    assert "safe to adopt" not in md, md
    assert "NOT cleared" in md, md
    assert "could not have reported a regression" in md, md


def test_an_all_underpowered_run_does_not_lead_with_a_green_header():
    """A green tick over a run that could not have gone red is the worst header we ship."""
    results = [_unchanged("s1")]
    md = render_pr_comment(results, "a", "b", 2, None, ["s1"])
    assert "no behavioral change" not in md.lower(), md
    assert "could not measure" in md.lower(), md


def test_the_unchanged_bucket_does_not_wear_a_green_tick_over_blind_scenarios():
    """The footer and the bucket label must not contradict each other."""
    md = render_pr_comment([_unchanged("s1")], "a", "b", 2, None, ["s1"])
    assert "**UNCHANGED (1)** ✅" not in md, md
    assert "could not have reported a regression at this run count" in md, md


def test_a_partially_underpowered_run_is_only_partially_cleared():
    results = [_unchanged("s1"), _unchanged("s2"), _unchanged("s3")]
    md = render_pr_comment(results, "a", "b", 3, None, ["s3"])
    assert "safe to adopt" not in md, md
    assert "partially cleared" in md, md
    assert "2 scenario(s) this run could measure" in md, md


def test_a_fully_powered_run_is_unchanged_by_this_feature():
    """Backwards compatibility, stated as a test: with no underpowered scenarios the
    rendering must be byte-identical to what shipped before MP-55."""
    results = [_unchanged("s1"), _unchanged("s2")]
    assert render_pr_comment(results, "a", "b", 5, None, []) == render_pr_comment(
        results, "a", "b", 5, None
    )
    assert "safe to adopt" in render_pr_comment(results, "a", "b", 5, None)
    assert render_cli(results, "a", "b", 5, []) == render_cli(results, "a", "b", 5)


def test_the_cli_summary_never_prints_OK_over_a_blind_scenario():
    cli = render_cli([_unchanged("s1"), _unchanged("s2")], "a", "b", 2, ["s1"])
    assert "NOT a clean result" in cli, cli
    assert "1 scenario(s) unchanged" in cli, cli  # the other one is still genuinely OK


# --- end to end, on the demo a new user actually runs -------------------------------------


def _demo_check(tmp_path, n, *, baseline_runs=None):
    store = str(tmp_path / f"store{n}")
    common = [
        "--provider",
        "fake",
        "--fixtures",
        FIXTURES,
        "--scenarios-dir",
        SCEN,
        "--config",
        CONFIG,
        "--store-dir",
        store,
    ]
    base = runner.invoke(
        app, ["baseline", "--model", DEMO_FROM, *common, "--runs", str(baseline_runs or n)]
    )
    assert base.exit_code == 0, base.output
    chk = runner.invoke(
        app, ["check", "--to", DEMO_TO, "--from", DEMO_FROM, *common, "--runs", str(n)]
    )
    report = (Path(store) / "last-report.md").read_text(encoding="utf-8")
    return chk, report


def test_the_shipped_demo_at_two_runs_does_not_clear_the_candidate(tmp_path):
    """The reproduction, pinned. Before MP-55 this printed `OK 4 scenario(s) unchanged` and
    wrote "looks safe to adopt"."""
    chk, report = _demo_check(tmp_path, 2)
    assert "safe to adopt" not in report, report
    assert "NOT cleared" in report, report
    assert "OK 4 scenario(s) unchanged" not in chk.output, chk.output


def test_the_same_fixtures_at_five_runs_find_what_two_runs_could_not(tmp_path):
    """Without this the guard above is unfalsifiable -- "not cleared" would be trivially
    correct if there were nothing to find. There is: two regressions and a minor."""
    chk, report = _demo_check(tmp_path, 5)
    assert chk.exit_code == 1, chk.output
    assert report.count("❌") == 2, report
    assert "safe to adopt" not in report


def test_the_spend_disclosure_says_the_run_cannot_conclude_before_it_spends(tmp_path):
    """ADR-0019 discloses the run SIZE before spending. A size that cannot reach ALPHA is
    the same disclosure one level up, and "less power" does not say it."""
    chk, _ = _demo_check(tmp_path, 2)
    out = " ".join(chk.output.split())
    assert "cannot report a regression" in out, chk.output
    assert "0.167" in out, chk.output


def test_three_runs_warns_that_the_tool_signal_specifically_is_dead(tmp_path):
    """N=3 is the trap: refusal and format drift still fire, so the run looks alive while
    the signal the product is NAMED for cannot reach ALPHA in the default match mode."""
    chk, _ = _demo_check(tmp_path, 3)
    out = " ".join(chk.output.split())
    assert "tool-call and argument signals cannot reach" in out, chk.output
    assert "0.100" in out, chk.output


def test_an_underpowered_run_still_exits_zero(tmp_path):
    """FP-neutral, deliberately. Turning this into a non-zero exit is a sensitivity change
    that would fail builds on a configuration users are free to choose, and it belongs to
    MP-59's exit-code redesign -- not to a change about what the tool CLAIMS."""
    chk, _ = _demo_check(tmp_path, 2)
    assert chk.exit_code == 0, chk.output


def test_an_unequal_baseline_and_candidate_are_judged_on_the_pooled_floor(tmp_path):
    """`baseline --runs 5` then `check --runs 2` is 5v2, whose floor is 1/C(7,2) = 0.0476 --
    BELOW alpha. A blindness test keyed on `--runs` alone would wrongly declare this run
    incapable and refuse to clear a candidate it genuinely measured."""
    assert min_achievable_pvalue_mean(5, 2) < ALPHA
    chk, report = _demo_check(tmp_path, 2, baseline_runs=5)
    assert "NOT cleared" not in report, report


def test_the_written_report_is_valid_json_free_markdown_at_every_run_count(tmp_path):
    """Cheap total check that neither branch emits a broken document."""
    for n in (2, 3, 5):
        _, report = _demo_check(tmp_path, n)
        assert report.startswith(("🚨", "❔", "⚠️", "✅")), (n, report[:80])
        assert json.dumps(report)  # no lone surrogates / control chars
