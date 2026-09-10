"""Command-line interface for exportgeneanet."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer

from .api_client import GeneanetApiClient
from .config import DEFAULT_LANG, DEFAULT_MAX_DELAY_SECONDS, DEFAULT_MIN_DELAY_SECONDS, tool_version
from .gedcom_writer import write_gedcom_file
from .gramps_writer import write_gramps_file
from .identifiers import PersonKey
from .media_downloader import download_media
from .rate_limiter import RateLimiter
from .tree_crawler import CrawlState, crawl_ascendants, crawl_full

app = typer.Typer(
    help="Export a public Geneanet (gw.geneanet.org) tree to GEDCOM or Gramps XML, "
    "respecting Geneanet's usage rules: public data only, paced with randomized delays."
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"exportgeneanet {tool_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    pass


class Scope(str, Enum):
    all = "all"
    ascendants = "ascendants"


class ExportFormat(str, Enum):
    gedcom = "gedcom"
    gramps = "gramps"


def _individual_option(help_extra: str = "") -> list[str]:
    return typer.Option(
        ...,
        help="A known individual in the tree, as 'given.surname[.oc]' (oc is "
        "GeneWeb's occurrence number disambiguating same-name people, default 0). "
        "Repeatable (pass --individual more than once) — a real Geneanet tree isn't "
        "guaranteed to be a single connected family graph, so one seed per known "
        "branch may be needed to cover the whole tree. " + help_extra,
    )


@app.command("list")
def list_individuals(
    username: str = typer.Option(..., help="Geneanet username, e.g. 'yann64'."),
    individual: list[str] = _individual_option(
        "Used as the starting point(s) to discover the rest of the tree via family "
        "links (there is no 'list everyone' API call, so at least one seed is required)."
    ),
    lang: str = typer.Option(DEFAULT_LANG),
    min_delay: float = typer.Option(DEFAULT_MIN_DELAY_SECONDS),
    max_delay: float = typer.Option(DEFAULT_MAX_DELAY_SECONDS),
) -> None:
    """List every individual reachable from the given seed(s) via family links."""
    limiter = RateLimiter(min_delay, max_delay)
    client = GeneanetApiClient(username, limiter, lang=lang)
    seeds = [PersonKey.parse(i) for i in individual]

    def on_progress(ind, done=None, total=None) -> None:
        typer.echo(f"{ind.key}\t{ind.given_name} {ind.surname}")

    crawl_full(client, seeds, on_progress=on_progress)


@app.command()
def export(
    username: str = typer.Option(..., help="Geneanet username, e.g. 'yann64'."),
    scope: Scope = typer.Option(Scope.ascendants, help="'all' or 'ascendants'."),
    individual: list[str] = _individual_option(
        "For --scope ascendants these are the root(s) of the lineage(s); for --scope "
        "all they're just starting points for discovering the rest of the tree."
    ),
    format: ExportFormat = typer.Option(ExportFormat.gedcom, help="'gedcom' (.ged) or 'gramps' (.gramps)."),
    output: Path = typer.Option(..., "--output", "-o", help="Path to the export file to write."),
    lang: str = typer.Option(DEFAULT_LANG),
    min_delay: float = typer.Option(DEFAULT_MIN_DELAY_SECONDS),
    max_delay: float = typer.Option(DEFAULT_MAX_DELAY_SECONDS),
    nb_asc: int = typer.Option(20, help="--scope ascendants only: how many generations up to fetch."),
    include_notes: bool = typer.Option(True),
    include_media: bool = typer.Option(True),
    download_media_files: bool = typer.Option(
        False,
        "--download-media",
        help="Download media files to --media-dir instead of just linking the remote URL.",
    ),
    media_dir: Path | None = typer.Option(
        None, help="Folder to save downloaded media files to (required with --download-media)."
    ),
    resume: bool = typer.Option(False, help="Resume from a previous interrupted run's checkpoint."),
    state_file: Path | None = typer.Option(
        None, help="Checkpoint file path (default: crawl-state-<username>-<scope>.json)."
    ),
) -> None:
    """Crawl the tree (fully, or one or more lineages' ascendants) and write a GEDCOM or Gramps XML file."""
    if download_media_files and not include_media:
        typer.echo("Error: --download-media requires --include-media.", err=True)
        raise typer.Exit(1)
    if download_media_files and media_dir is None:
        typer.echo("Error: --media-dir is required with --download-media.", err=True)
        raise typer.Exit(1)

    limiter = RateLimiter(min_delay, max_delay)
    client = GeneanetApiClient(username, limiter, lang=lang)
    roots = [PersonKey.parse(i) for i in individual]
    state_path = state_file or Path.cwd() / f"crawl-state-{username}-{scope.value}.json"

    state = CrawlState.load(state_path) if resume and state_path.exists() else None

    def on_progress(ind, done=None, total=None) -> None:
        progress = f"[{done}/{total}] " if total is not None else ""
        typer.echo(f"{progress}fetched {ind.given_name} {ind.surname}")

    if scope is Scope.all:
        state = crawl_full(client, roots, state=state, state_path=state_path, on_progress=on_progress)
    else:
        state = crawl_ascendants(
            client, roots, nb_asc=nb_asc, state=state, state_path=state_path, on_progress=on_progress
        )

    if download_media_files:
        for ind in state.individuals.values():
            for i, media in enumerate(ind.media):
                try:
                    media.local_path = download_media(
                        client.session, limiter, media.url, ind.key, i, media_dir
                    )
                except Exception as exc:  # noqa: BLE001 - one bad media URL shouldn't abort the export
                    typer.echo(f"Warning: failed to download media for {ind.key}: {exc}", err=True)

    write_file = write_gedcom_file if format is ExportFormat.gedcom else write_gramps_file
    write_file(
        output, state.individuals, state.families, include_notes=include_notes, include_media=include_media
    )
    typer.echo(f"Wrote {len(state.individuals)} individuals / {len(state.families)} families to {output}")


if __name__ == "__main__":
    app()
