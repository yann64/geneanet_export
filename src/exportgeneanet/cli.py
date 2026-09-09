"""Command-line interface for exportgeneanet."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer

from .api_client import GeneanetApiClient
from .config import DEFAULT_LANG, DEFAULT_MAX_DELAY_SECONDS, DEFAULT_MIN_DELAY_SECONDS
from .gedcom_writer import write_gedcom_file
from .identifiers import PersonKey
from .rate_limiter import RateLimiter
from .tree_crawler import CrawlState, crawl_ascendants, crawl_full

app = typer.Typer(
    help="Export a public Geneanet (gw.geneanet.org) tree to GEDCOM, respecting "
    "Geneanet's usage rules: public data only, paced with randomized delays."
)


class Scope(str, Enum):
    all = "all"
    ascendants = "ascendants"


def _individual_option(help_extra: str = "") -> str:
    return typer.Option(
        ...,
        help="A known individual in the tree, as 'given.surname[.oc]' (oc is "
        "GeneWeb's occurrence number disambiguating same-name people, default 0). "
        + help_extra,
    )


@app.command("list")
def list_individuals(
    username: str = typer.Option(..., help="Geneanet username, e.g. 'yann64'."),
    individual: str = _individual_option(
        "Used as the starting point to discover the rest of the tree via family "
        "links (there is no 'list everyone' API call, so a seed is required)."
    ),
    lang: str = typer.Option(DEFAULT_LANG),
    min_delay: float = typer.Option(DEFAULT_MIN_DELAY_SECONDS),
    max_delay: float = typer.Option(DEFAULT_MAX_DELAY_SECONDS),
) -> None:
    """List every individual reachable from one seed via family links."""
    limiter = RateLimiter(min_delay, max_delay)
    client = GeneanetApiClient(username, limiter, lang=lang)
    seed = PersonKey.parse(individual)

    def on_progress(ind) -> None:
        typer.echo(f"{ind.key}\t{ind.given_name} {ind.surname}")

    crawl_full(client, seed, on_progress=on_progress)


@app.command()
def export(
    username: str = typer.Option(..., help="Geneanet username, e.g. 'yann64'."),
    scope: Scope = typer.Option(Scope.ascendants, help="'all' or 'ascendants'."),
    individual: str = _individual_option(
        "For --scope ascendants this is the root of the lineage; for --scope all "
        "it's just a starting point for discovering the rest of the tree."
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Path to the .ged file to write."),
    lang: str = typer.Option(DEFAULT_LANG),
    min_delay: float = typer.Option(DEFAULT_MIN_DELAY_SECONDS),
    max_delay: float = typer.Option(DEFAULT_MAX_DELAY_SECONDS),
    nb_asc: int = typer.Option(
        20, help="--scope ascendants only: how many generations up to fetch."
    ),
    include_notes: bool = typer.Option(True),
    include_media: bool = typer.Option(True),
    resume: bool = typer.Option(False, help="Resume from a previous interrupted run's checkpoint."),
    state_file: Path | None = typer.Option(
        None, help="Checkpoint file path (default: crawl-state-<username>-<scope>.json)."
    ),
) -> None:
    """Crawl the tree (fully, or one individual's ascendants) and write a GEDCOM file."""
    limiter = RateLimiter(min_delay, max_delay)
    client = GeneanetApiClient(username, limiter, lang=lang)
    root = PersonKey.parse(individual)
    state_path = state_file or Path.cwd() / f"crawl-state-{username}-{scope.value}.json"

    state = CrawlState.load(state_path) if resume and state_path.exists() else None

    def on_progress(ind) -> None:
        typer.echo(f"fetched {ind.given_name} {ind.surname}")

    if scope is Scope.all:
        state = crawl_full(client, root, state=state, state_path=state_path, on_progress=on_progress)
    else:
        state = crawl_ascendants(
            client, root, nb_asc=nb_asc, state=state, state_path=state_path, on_progress=on_progress
        )

    write_gedcom_file(
        output, state.individuals, state.families, include_notes=include_notes, include_media=include_media
    )
    typer.echo(f"Wrote {len(state.individuals)} individuals / {len(state.families)} families to {output}")


if __name__ == "__main__":
    app()
