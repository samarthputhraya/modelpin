"""Modelpin CLI (Typer).

Phase 0 scaffold: commands are wired and runnable; implementations that need real
provider calls or the full diff engine print a TODO pointing at the spec.
"""

from __future__ import annotations

import typer
from rich.console import Console

from modelpin import __version__

app = typer.Typer(
    help="Modelpin — Dependabot for AI models. Know before the model breaks you.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _todo(step: str) -> None:
    console.print(
        f"[yellow]TODO[/]: [bold]{step}[/] is scaffolded but not implemented yet.\n"
        "      See docs/Modelpin-Engineering-Context-Pack.md and CLAUDE.md."
    )


@app.command()
def version() -> None:
    """Print the Modelpin version."""
    console.print(f"modelpin {__version__}")


@app.command()
def init() -> None:
    """Create modelpin.yaml + scenarios/ in the current repo."""
    _todo("init")


@app.command()
def scan() -> None:
    """Detect which AI models this repo depends on."""
    _todo("scan")


@app.command()
def baseline() -> None:
    """Record current model behavior for your scenarios (N runs)."""
    _todo("baseline")


@app.command()
def check(
    to: str = typer.Option(..., "--to", help="The new model id to test against your baseline."),
) -> None:
    """Replay scenarios on a new model and report behavioral regressions."""
    _todo(f"check --to {to}")


@app.command()
def report() -> None:
    """Run the public standard suite and draft a Modelpin Report."""
    _todo("report")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
