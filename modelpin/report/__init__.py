"""Reporter — render DiffResults as a Markdown PR comment and a CLI summary.

Matches the target UX in spec section 7. Framing stays measurement/opinion
("we replayed your scenarios and observed…"), never a bare "model X is worse"
(legal/trust guardrail, spec section 9).
"""

from __future__ import annotations

from modelpin.models import DiffResult, DiffVerdict

# CLI uses ASCII tokens (+ rich color) so it never hits a UnicodeEncodeError on a
# legacy Windows console (cp1252). Emoji live only in the Markdown report below.
_CLI_MARK = {
    DiffVerdict.regression: "[red]REGRESSION[/]",
    DiffVerdict.changed_minor: "[yellow]MINOR[/]",
    DiffVerdict.unchanged: "[green]OK[/]",
}
_MD_MARK = {
    DiffVerdict.regression: "❌",
    DiffVerdict.changed_minor: "⚠️",
    DiffVerdict.unchanged: "✅",
}


def _bucket(
    results: list[DiffResult],
) -> tuple[list[DiffResult], list[DiffResult], list[DiffResult]]:
    regs = [r for r in results if r.verdict == DiffVerdict.regression]
    minors = [r for r in results if r.verdict == DiffVerdict.changed_minor]
    unchanged = [r for r in results if r.verdict == DiffVerdict.unchanged]
    return regs, minors, unchanged


def render_pr_comment(results: list[DiffResult], from_model: str, to_model: str, runs: int) -> str:
    """The Markdown PR comment (spec section 7). The header reflects the actual outcome —
    only a real regression leads with 🚨, so an all-unchanged result reads calm/green and
    doesn't contradict its own "safe to adopt" line."""
    regs, minors, unchanged = _bucket(results)
    if regs:
        header = f"\U0001f6a8 **Modelpin: behavioral regression — `{from_model}` → `{to_model}`**"
    elif minors:
        header = f"⚠️ **Modelpin: minor changes — `{from_model}` → `{to_model}`**"
    else:
        header = f"✅ **Modelpin: no behavioral change — `{from_model}` → `{to_model}`**"
    lines = [
        header,
        f"Replayed {len(results)} scenario(s) ×{runs} runs using your API key.",
        "",
    ]
    if regs:
        lines.append(f"**REGRESSIONS ({len(regs)})**")
        for r in regs:
            lines.append(f"{_MD_MARK[r.verdict]} **{r.scenario_id}** — {r.explanation}")
            lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;confidence {r.confidence:.2f}")
        lines.append("")
    if minors:
        lines.append(f"**MINOR CHANGES ({len(minors)})**")
        for r in minors:
            lines.append(f"{_MD_MARK[r.verdict]} {r.scenario_id} — {r.explanation}")
        lines.append("")
    lines.append(f"**UNCHANGED ({len(unchanged)})** ✅")
    lines.append("")
    if regs or minors:
        lines.append(f"→ Pin to `{from_model}` until resolved, or review the full diff above.")
    else:
        lines.append(f"→ No behavioral regressions found; `{to_model}` looks safe to adopt.")
    return "\n".join(lines)


def render_cli(results: list[DiffResult], from_model: str, to_model: str, runs: int) -> str:
    """The CLI summary — ASCII text + rich color markup (safe on any console)."""
    regs, minors, unchanged = _bucket(results)
    lines = [
        f"[bold]Modelpin[/]: {from_model} -> {to_model}  "
        f"[dim]({len(results)} scenario(s) x{runs} runs)[/]",
        "",
    ]
    for r in regs + minors:
        lines.append(
            f"{_CLI_MARK[r.verdict]} [bold]{r.scenario_id}[/]: {r.explanation} "
            f"[dim](confidence {r.confidence:.2f})[/]"
        )
    if unchanged:
        lines.append(f"[green]OK[/] [dim]{len(unchanged)} scenario(s) unchanged[/]")
    if regs or minors:
        lines.append("")
        lines.append(f"[yellow]-> Pin to[/] [bold]{from_model}[/] until resolved.")
    return "\n".join(lines)
