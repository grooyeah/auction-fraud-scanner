"""Radar CLI entry point.

Day 1: structure only. Every command below is a stub — the real
implementations land with the checklist items noted in each docstring
(see /Users/grooyeah/.claude/plans/i-m-building-radar-kind-dragon.md
or, once merged, docs/decisions/ and the project checklist).
"""

from __future__ import annotations

from pathlib import Path

import typer

from radar.sicap.capture import format_inventory, run_capture

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
    curl_file: Path = typer.Option(
        ..., "--curl-file", help="Path to a saved 'Copy as cURL (bash)' command", exists=True
    ),
    fixtures_dir: Path = typer.Option(Path("tests/fixtures"), "--fixtures-dir", hidden=True),
) -> None:
    """Replay a captured cURL request, save the response as a fixture, and
    print a field inventory.

    Workflow: in Chrome DevTools → Network, right-click the request →
    Copy → Copy as cURL (bash). Paste it into a file, then:

        radar capture --name direct-list --curl-file /tmp/curl.txt

    Saves tests/fixtures/<name>.json (the response) and
    tests/fixtures/<name>.meta.json (the request that produced it), and
    prints a field inventory so you can eyeball VAT/currency/id-grain
    questions without reading raw JSON by hand. See docs/sicap-endpoints.md.
    """
    result = run_capture(name=name, curl_text=curl_file.read_text(), fixtures_dir=fixtures_dir)
    typer.echo(f"saved {result.fixture_path} (HTTP {result.status_code})")
    typer.echo(f"saved {result.meta_path}")
    typer.echo("")
    typer.echo(format_inventory(result.inventory))


if __name__ == "__main__":
    app()
