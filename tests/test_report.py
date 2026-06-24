from modelpin.models import DiffResult, DiffVerdict
from modelpin.report import render_cli, render_pr_comment


def _r(sid, verdict, expl="x", conf=0.9):
    return DiffResult(
        scenario_id=sid,
        from_model="a",
        to_model="b",
        verdict=verdict,
        explanation=expl,
        confidence=conf,
    )


def test_pr_comment_groups_buckets_with_spec_emoji():
    results = [
        _r("reg1", DiffVerdict.regression, "tool-call changed"),
        _r("min1", DiffVerdict.changed_minor, "format drift"),
        _r("ok1", DiffVerdict.unchanged, "no change"),
    ]
    md = render_pr_comment(results, "claude-opus-4-6", "claude-opus-4-7", 5)
    assert "REGRESSIONS (1)" in md
    assert "MINOR CHANGES (1)" in md
    assert "UNCHANGED (1)" in md
    assert "❌" in md and "⚠️" in md and "✅" in md
    assert "claude-opus-4-6" in md and "claude-opus-4-7" in md
    assert "confidence 0.90" in md
    assert "Pin to" in md


def test_pr_comment_is_clean_when_nothing_changed():
    results = [_r("ok1", DiffVerdict.unchanged), _r("ok2", DiffVerdict.unchanged)]
    md = render_pr_comment(results, "a", "b", 3)
    assert "REGRESSIONS" not in md
    assert "safe to adopt" in md


def test_pr_comment_header_is_calm_when_unchanged():
    # The dogfood surfaced this: an all-unchanged result must NOT lead with 🚨 "model change
    # detected" and then say "safe to adopt" — that's contradictory/alarmist.
    md = render_pr_comment([_r("ok1", DiffVerdict.unchanged)], "a", "b", 3)
    assert md.startswith("✅")
    assert "no behavioral change" in md
    assert "🚨" not in md  # never alarmist when nothing regressed


def test_pr_comment_header_alarms_only_on_regression():
    md = render_pr_comment([_r("reg1", DiffVerdict.regression, "boom")], "a", "b", 5)
    assert md.startswith("🚨")
    assert "behavioral regression" in md


def test_pr_comment_header_warns_on_minor_only():
    md = render_pr_comment([_r("min1", DiffVerdict.changed_minor, "format drift")], "a", "b", 5)
    assert md.startswith("⚠️")
    assert "minor changes" in md
    assert "🚨" not in md


def test_render_cli_lists_changed_scenarios():
    out = render_cli([_r("reg1", DiffVerdict.regression, "boom")], "a", "b", 5)
    assert "reg1" in out and "boom" in out
