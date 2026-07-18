"""Command-line interface for agent-usage."""

from __future__ import annotations

import typer

app = typer.Typer(
    help="Collect privacy-conscious local agent usage summaries.",
    no_args_is_help=True,
)


@app.callback()
def command_group() -> None:
    """Commands for collecting and reviewing agent usage."""


def main() -> None:
    """Run the command-line application."""
    app()
