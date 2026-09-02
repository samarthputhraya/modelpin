"""User-facing error text must reach the user unchanged (MP-161 + MP-170).

`_fail` renders its message through rich markup with no escaping, so any `[...]` in an error
message is parsed as a style tag. Two failure modes, both `[M] 2026-09-02` reproduced by
calling `cli._fail` directly:

    in : pip install 'modelpin[providers]'
    out: error: pip install 'modelpin'          <- the extra is EATEN

    in : scenario [bold]alpha[/] failed
    out: error: scenario alpha failed           <- SILENTLY REWRITTEN, no exception

The first is MP-161 and it is the worst one in the product: `providers/openai.py` tells a
user whose install lacks the SDK to run `pip install 'modelpin[providers]'`, and the console
prints the command they have already run. It is the FIRST error a stranger without the extra
hits, and it is an infinite loop.

The second is MP-170's sharpened half. A crash at least stops you; this one prints a
plausible message naming something that does not exist and exits as if it had explained
itself. `Scenario.id` has no pattern validator and provider messages are remote text, so
neither is under our control.

`[M]` This class has now been found FIVE times in this codebase, each time at one call site,
and four separate comments have claimed the last one was closed. `_fail_no_scenarios` even
carries a comment explaining the hazard and escaping its own argument -- the symptom patched
where the root cause lives one function away. So the fix is in `_fail` itself, and the local
workaround is removed in the same commit (leaving both would double-escape and print literal
backslashes at the one place that had been careful).

Not covered here: model ids interpolated into markup OUTSIDE error paths (MP-174).
"""

from __future__ import annotations

import pytest
import typer

import modelpin.cli as cli

#: The exact string `providers/openai.py` raises. If this drifts, the guard is measuring a
#: message the product no longer sends -- so it is asserted against the source, not copied.
_INSTALL_HINT = "pip install 'modelpin[providers]'"


def _printed(monkeypatch, message: str) -> str:
    """Whatever `_fail` actually puts on the terminal, with rich's markup applied."""
    captured: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda *a, **k: captured.append(str(a[0])))
    with pytest.raises(typer.Exit):
        cli._fail(message)
    # Render the markup the way a real console would, so the assertion is about what a user
    # READS, not about the markup string we happened to build.
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=400, no_color=True).print(captured[0])
    return buf.getvalue()


def test_the_install_hint_is_not_corrupted_into_the_command_already_run(monkeypatch):
    """MP-161. The single message whose whole job is to unstick a blocked user."""
    out = _printed(
        monkeypatch, f"The OpenAI SDK is not installed. Install it with: {_INSTALL_HINT}"
    )
    assert "modelpin[providers]" in out, (
        "MP-161: rich ate `[providers]`, so a user missing the SDK is told to run the command "
        f"they already ran. Printed: {out!r}"
    )
    assert "install 'modelpin'" not in out, out


def test_the_hint_this_test_pins_is_the_one_the_product_actually_sends(monkeypatch):
    """A guard on a string the code no longer emits guards nothing. `[M]` MP-152 shipped a
    README naming a retired model for exactly this reason: the doc and the code drifted."""
    from pathlib import Path

    src = Path(cli.__file__).parent / "providers" / "openai.py"
    assert _INSTALL_HINT in src.read_text(encoding="utf-8"), (
        f"{_INSTALL_HINT!r} is no longer in providers/openai.py -- this suite is pinning a "
        "message the product does not send."
    )


def test_a_message_shaped_like_a_style_tag_is_not_silently_rewritten(monkeypatch):
    """MP-170's sharper half: not a crash, a LIE. The user is sent after `alpha` when the
    thing that failed was `[bold]alpha[/]`, and nothing indicates the message was altered."""
    out = _printed(monkeypatch, "scenario [bold]alpha[/] could not be replayed")
    assert "[bold]alpha[/]" in out, f"the id was rewritten: {out!r}"


def test_a_bracketed_path_reaches_the_user_intact(monkeypatch):
    """Paths are the other user-supplied text on this path -- `--store-dir`, `--scenarios-dir`
    -- and a directory called `[wip]` is not exotic."""
    out = _printed(monkeypatch, "no scenarios found in /home/me/[wip]/scenarios")
    assert "[wip]" in out, out


def test_an_unclosed_tag_in_a_provider_message_does_not_crash_the_error_path(monkeypatch):
    """Provider messages are remote text. An error path that raises `MarkupError` replaces an
    answerable message with a traceback -- the failure mode is worse than the failure."""
    out = _printed(monkeypatch, "groq: 400 tool_use_failed (called `[/]`, not a declared tool)")
    assert "[/]" in out, out


def test_the_no_scenarios_message_is_not_double_escaped(monkeypatch, tmp_path):
    """The counterpart. `_fail_no_scenarios` escaped its own argument because `_fail` did not;
    with the root cause fixed, leaving that in place prints literal backslashes at the one
    call site that had been careful."""
    captured: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda *a, **k: captured.append(str(a[0])))
    with pytest.raises(typer.Exit):
        cli._fail_no_scenarios(str(tmp_path / "[wip]"), "flag", "modelpin.yaml")
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=400, no_color=True).print(captured[0])
    out = buf.getvalue()
    # Compare against the REAL resolved path, not a backslash heuristic: on Windows the
    # separator before the bracket is itself a backslash, so `\[wip]` is what a correct
    # render looks like there. The only sound assertion is that the path round-trips.
    expected = str((tmp_path / "[wip]").resolve())
    assert expected in out, "path corrupted. expected " + repr(expected) + " printed " + repr(out)
