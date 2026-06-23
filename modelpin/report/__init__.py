"""Reporter — render DiffResults as CLI text and a Markdown PR comment. See spec section 7."""

from __future__ import annotations

from modelpin.models import DiffResult, DiffVerdict

_EMOJI = {
    DiffVerdict.regression: "X",
    DiffVerdict.changed_minor: "!",
    DiffVerdict.unchanged: "OK",
}


def render_pr_comment(results: list[DiffResult], from_model: str, to_model: str, runs: int) -> str:
    regs = [r for r in results if r.verdict == DiffVerdict.regression]
    minors = [r for r in results if r.verdict == DiffVerdict.changed_minor]
    unchanged = [r for r in results if r.verdict == DiffVerdict.unchanged]

    lines = [
        f"## Modelpin: model change detected - {from_model} -> {to_model}",
        f"Replayed {len(results)} scenarios x{runs} runs using your API key.",
        "",
    ]
    if regs:
        lines.append(f"### REGRESSIONS ({len(regs)})")
        for r in regs:
            lines.append(f"- **{r.scenario_id}** - {r.explanation} (confidence {r.confidence:.2f})")
        lines.append("")
    if minors:
        lines.append(f"### MINOR CHANGES ({len(minors)})")
        for r in minors:
            lines.append(f"- {r.scenario_id} - {r.explanation}")
        lines.append("")
    lines.append(f"### UNCHANGED ({len(unchanged)})")
    lines.append("")
    if regs:
        lines.append(
            f"> Recommendation: pin to `{from_model}` until resolved, or review the diffs above."
        )
    return "\n".join(lines)


def render_cli(results: list[DiffResult]) -> str:
    out = []
    for r in results:
        out.append(
            f"[{_EMOJI.get(r.verdict, '?')}] {r.scenario_id}: {r.verdict.value} - {r.explanation}"
        )
    return "\n".join(out)
