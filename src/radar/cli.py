"""Radar CLI entry point.

Day 1: structure only. Every command below is a stub — the real
implementations land with the checklist items noted in each docstring
(see /Users/grooyeah/.claude/plans/i-m-building-radar-kind-dragon.md
or, once merged, docs/decisions/ and the project checklist).
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="radar",
    help="Risk-indicator engine over Romanian public procurement data.",
    no_args_is_help=True,
)


@app.command()
def ingest(date: str = typer.Option(..., "--date", help="YYYY-MM-DD")) -> None:
    """Fetch one day of awards into data/raw/. Lands with W1-15/W1-16."""
    raise NotImplementedError("ingest lands with W1-15/W1-16 — see checklist")


@app.command()
def backfill(
    date_from: str = typer.Option(..., "--from", help="YYYY-MM-DD"),
    date_to: str = typer.Option(..., "--to", help="YYYY-MM-DD"),
) -> None:
    """Resumable backfill over a date range. Lands with W1-16."""
    raise NotImplementedError("backfill lands with W1-16 — see checklist")


@app.command()
def capture(
    name: str = typer.Option(..., "--name", help="Fixture name, e.g. direct-list"),
    curl_file: str = typer.Option(..., "--curl-file", help="Path to a saved 'Copy as cURL'"),
) -> None:
    """Replay a captured cURL request, save the response as a fixture, and
    print a field inventory. Lands with W1-07 — this is the tool you'll use
    to turn the Day 2 DevTools pass (W1-08) into committed fixtures.
    """
    raise NotImplementedError("capture lands with W1-07 — see checklist")


if __name__ == "__main__":
    app()
