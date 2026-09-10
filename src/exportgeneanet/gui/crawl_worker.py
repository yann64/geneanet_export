"""Background worker running Geneanet API calls off the UI thread.

Owns exactly one `GeneanetApiClient` (and therefore exactly one
`RateLimiter`) for the whole GUI session. Every task — a name search, or a
full export — is submitted to this same worker and runs to completion
before the next one starts, so search and export never run concurrently
with each other. That's not just a threading convenience: it's what keeps
the GUI honoring the same "never concurrent, always rate-limited" guarantee
`rate_limiter.py` documents as a hard requirement, not a tunable nicety.
"""

from __future__ import annotations

import queue
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from PySide6.QtCore import QThread, Signal

from ..api_client import GeneanetApiClient
from ..gedcom_writer import write_gedcom_file
from ..identifiers import PersonKey
from ..models import Individual
from ..rate_limiter import RateLimiter
from ..tree_crawler import CrawlState, crawl_ascendants, crawl_full

_STOP = object()  # sentinel telling the worker loop to exit


class CrawlCancelled(Exception):
    """Raised from the `on_progress` callback to unwind a crawl cleanly when
    the user clicks Cancel.

    Safe to do because `tree_crawler.py`'s `state.save(state_path)` always
    runs *before* `on_progress(...)` on every iteration of both crawl
    functions — so by the time this is raised, the partial `CrawlState` for
    everything done so far is already on disk. `_run_export` below reloads
    it from there rather than relying on the (never-returned, because an
    exception interrupted the call) function result.
    """


class CrawlWorker(QThread):
    """One worker per GUI session. Call `start()` once, then submit tasks."""

    search_results = Signal(list)  # list[dict] — raw PersonSearch rows from the API
    progress = Signal(object, object, object)  # Individual, done: int | None, total: int | None
    export_finished = Signal(object, object)  # CrawlState, output_path: Path | None
    export_cancelled = Signal(object)  # CrawlState (partial)
    search_failed = Signal(str)
    export_failed = Signal(str)

    def __init__(self, username: str, lang: str, min_delay: float, max_delay: float) -> None:
        super().__init__()
        self._client = GeneanetApiClient(username, RateLimiter(min_delay, max_delay), lang=lang)
        self._tasks: queue.Queue = queue.Queue()
        self._cancel_requested = False

    def stop(self) -> None:
        """Shut the worker thread down (call on app close, then `wait()`)."""
        self._tasks.put(_STOP)

    def request_cancel(self) -> None:
        """Ask the in-progress export to stop after its current individual.
        No-op if nothing is running."""
        self._cancel_requested = True

    def submit_search(self, lastname: str, firstname: str) -> None:
        self._tasks.put(("search", lastname, firstname))

    def submit_export(
        self,
        scope: str,
        seeds: list[PersonKey],
        output: Path | None,
        nb_asc: int,
        include_notes: bool,
        include_media: bool,
        state: CrawlState | None,
        state_path: Path,
    ) -> None:
        """`scope` is `"all"` or `"ascendants"`. `state_path` should always
        be set (even if the user didn't ask to resume) so a cancellation
        mid-crawl stays recoverable — see `CrawlCancelled`."""
        self._cancel_requested = False
        self._tasks.put(
            ("export", scope, seeds, output, nb_asc, include_notes, include_media, state, state_path)
        )

    def run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is _STOP:
                return
            try:
                if task[0] == "search":
                    self._run_search(task[1], task[2])
                else:
                    self._run_export(*task[1:])
            except Exception as exc:  # noqa: BLE001 - surface to the UI, never crash the worker
                target = self.search_failed if task[0] == "search" else self.export_failed
                target.emit(str(exc))

    def _run_search(self, lastname: str, firstname: str) -> None:
        result = self._client.search_persons(lastname=lastname or None, firstname=firstname or None, limit=20)
        result_dict = MessageToDict(result, preserving_proto_field_name=True)
        self.search_results.emit(result_dict.get("persons", []))

    def _run_export(
        self,
        scope: str,
        seeds: list[PersonKey],
        output: Path | None,
        nb_asc: int,
        include_notes: bool,
        include_media: bool,
        state: CrawlState | None,
        state_path: Path,
    ) -> None:
        def on_progress(individual: Individual, done: int | None = None, total: int | None = None) -> None:
            if self._cancel_requested:
                raise CrawlCancelled
            self.progress.emit(individual, done, total)

        try:
            if scope == "all":
                state = crawl_full(
                    self._client, seeds, state=state, state_path=state_path, on_progress=on_progress
                )
            else:
                state = crawl_ascendants(
                    self._client,
                    seeds,
                    nb_asc=nb_asc,
                    state=state,
                    state_path=state_path,
                    on_progress=on_progress,
                )
        except CrawlCancelled:
            partial = CrawlState.load(state_path) if state_path.exists() else (state or CrawlState())
            self.export_cancelled.emit(partial)
            return

        if output is not None:
            write_gedcom_file(
                output,
                state.individuals,
                state.families,
                include_notes=include_notes,
                include_media=include_media,
            )
        self.export_finished.emit(state, output)
