# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python tool that exports a public [Geneanet](https://www.geneanet.org/) tree
to a GEDCOM 5.5.1 file — either the whole tree or just the ascendants of one
selected individual. Two front ends on the same library code: a Typer CLI
(`exportgeneanet`) and an optional PySide6 (Qt6) GUI (`exportgeneanet-gui`,
the `gui` extra — see `src/exportgeneanet/gui/`). The GUI is CLI parity, not
a separate feature set: same scope/seed/output/resume/rate-limit options,
just a search-based picker instead of hand-typing `given.surname.oc`.

Test accounts for manual verification: `yann64` (primary), `jpmanzinali`,
`jloger`.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gui]"       # gui extra is optional; CLI-only needs just [dev]

pytest                            # full test suite (no network); GUI tests skip via
                                   # pytest.importorskip("PySide6") if the gui extra isn't installed
pytest tests/test_mapping.py::test_individual_from_person_maps_events_and_relations  # single test

ruff check .                      # lint
ruff format .                     # format (run before committing)

exportgeneanet list --username yann64 --individual "etienne.barbel.0"
exportgeneanet export --username yann64 --scope all --individual "etienne.barbel.0" -o yann64.ged
exportgeneanet export --username yann64 --scope ascendants --individual "etienne.barbel.0" -o out.ged
exportgeneanet-gui                 # optional Qt6 GUI, same options as export above

python scripts/generate_proto.py   # regenerate src/exportgeneanet/proto/, only if Geneanet's API schema changes
```

Ruff (lint + format) is configured in `pyproject.toml` — `[tool.ruff]`/
`[tool.ruff.lint]`. `src/exportgeneanet/proto/` (generated code) is excluded
from both. `cli.py` has a per-file lint ignore for `B008`
("function call in argument default"): Typer's API requires calling
`typer.Option()`/`typer.Argument()` as argument defaults, so that's the
framework's intended pattern there, not a bug.

## Critical constraint: how data is fetched

`gw.geneanet.org`'s HTML pages sit behind a Cloudflare "managed challenge"
that reliably blocks automated access — confirmed during this project's
development that even a real, human-operated browser couldn't get
consistently past it (headless is blocked outright, even with a valid
session cookie). **Do not build any code path that scrapes rendered HTML
from `gw.geneanet.org` pages, and never add stealth/fingerprint-spoofing to
try to defeat that protection** — that's detection-evasion territory, not
something this project does.

Instead, everything goes through Geneanet's own internal protobuf API at
`https://gw.geneanet.org/setup/api/` — the same API Geneanet's own frontend
calls via XHR after a page's shell loads. That subpath has no such
protection: plain `requests` calls reach it immediately, no cookies or
browser needed. This was discovered via
[jmichault/gramps-kromprogramoj](https://github.com/jmichault/gramps-kromprogramoj)
(GPL-3.0), a real, actively-maintained Gramps addon (`fontoj/PersonGN/geneanet.py`)
that talks to Geneanet the same way — `api_client.py` is modeled on its `Api`
class, including the response-decoding quirk (protobuf bytes need
`.decode("utf-8").encode("raw_unicode_escape")` before `ParseFromString` in
some cases).

Two things worth remembering when touching this code:

- **This is an unofficial, internal API**, not a documented public one. It
  could change or be restricted without notice — if `api_client.py` calls
  start failing, that's the first thing to suspect (compare live responses
  against the `.proto` schemas in `src/exportgeneanet/proto/`, or
  re-fetch/re-diff them with `scripts/generate_proto.py`).
- **This tool never authenticates.** No login flow exists and none should be
  added — every call must be anonymous, matching what a visitor's browser
  would see. See "Privacy enforcement" below.

## Privacy enforcement

Every person reference the API returns carries `name_is_hidden` /
`name_is_restricted` / `visible_for_visitors` flags — the same signal
Geneanet's own frontend uses to decide whether to render a name (e.g. the
"Cette personne est masquée" placeholder on the HTML site). `mapping.py`'s
`is_publicly_visible()` is the single place that checks these flags, and
every function that turns an API response into a `PersonKey`/`Individual`
routes through it (`person_key_from_summary`/`person_ref_from_summary` are
the *unchecked* raw extractors — only call them after an
`is_publicly_visible()` check, as the existing code does). Never bypass this
check to "get more data" — it's the ethical core of the project (see
README's "Respecting Geneanet's usage").

## Architecture

Everything lives in `src/exportgeneanet/`:

- **`proto/`** — generated Python protobuf bindings for Geneanet's own
  `.proto` schemas (`api`, `api_app`, `api_stats`, `api_saisie_read`,
  `api_saisie_write`), committed to the repo (like the reference addon does)
  so normal installs never need a protobuf compiler. Regenerate with
  `scripts/generate_proto.py`, which uses `grpc_tools.protoc` (pip-installable,
  no system `protoc`/sudo needed).
- **`identifiers.py`** — `PersonKey(p, n, oc)`: given name, surname, GeneWeb
  occurrence number disambiguating same-name people. Stringifies as
  `given.surname.oc`, the CLI's `--individual` format. The stable,
  human-meaningful identifier used everywhere outside the API layer.
- **`api_client.py`** — `GeneanetApiClient`: anonymous, rate-limited HTTP
  client for `/setup/api/`. `search_persons` (name search, results embed
  father/mother/spouses), `get_graph` (ascendants/descendants graph —
  `nb_asc`/`nb_desc` generations *in one call*), `get_person` (full detail:
  events, notes, sources, families — needed per-person since graph nodes are
  lightweight summaries only). Every call goes through `rate_limiter.py`
  first; never add concurrency here.
- **`rate_limiter.py`** — sleeps a random `[min_delay, max_delay]` duration
  before every single request. Hard requirement, not a tunable nicety.
- **`mapping.py`** — translates protobuf API responses (as plain dicts via
  `google.protobuf.json_format.MessageToDict(..., preserving_proto_field_name=True)`)
  into `models.py` dataclasses. Holds several enum → GEDCOM lookup tables,
  all following the same pattern (map to a specific tag when there's a good
  match, else fall back to a generic tag + a human-readable `TYPE`/label
  rather than silently dropping the distinction): `EVENT_TAG_MAP`
  (`EPERS_*`/`EFAM_*` → tag, adapted from the reference addon's
  `gn_constants.py`), `MARRIAGE_TYPE_TAG_MAP`, `DIVORCE_TYPE_TAG_MAP`,
  `WITNESS_TYPE_LABEL`. Also holds `gedcom_date()` (see below) and the
  privacy check described above. `_text()`/`_html_to_text()` unescape HTML
  entities that show up even in plain fields like place names (e.g.
  `"Prud&#39;Homie"`) — apply one of these to any new string field pulled
  from an API response.

  Source citations are `SourceCitation(title, page, is_geneanet_source)` on
  `Event.sources`/`Individual.sources`/`Family.sources` (each a *list* —
  every fact carries the Geneanet-attribution citation described just below
  in addition to whatever archival citation it has); `gedcom_writer.py`
  dedupes them into `SOUR` records keyed by `title`, so the same archival
  record cited on several facts becomes one record referenced by pointer.
  Geneanet's own archival citation text (`src`/`psources`/`fsources`/
  `marriage_src`, all free text — there's no separate repository/archive
  structure for these in the API) is wrapped as a plain
  `SourceCitation(title=...)`, `is_geneanet_source` left `False`.

  Every mapped individual/family/event also gets a *second*, shared
  citation from `geneanet_tree_citation(username, page)`: `title` is the
  same string for every call with the same tree (so it dedupes to one SOUR
  record naming the tree owner and the tree's base URL), `page` is that
  particular citation's own `person_citation_url(username, key)` — a
  `gw.geneanet.org` URL built for citation purposes only, **never
  fetched** by this project (see "Critical constraint" above — constructing
  a reference URL a human could click is not the same thing as scraping it).
  `is_geneanet_source=True` on this one citation is what tells
  `gedcom_writer.py` to link its `SOUR` record to the "Geneanet" `REPO`
  record it emits. `crawl_ascendants`'s synthesized families (not produced
  by `individual_from_person`) attach this themselves, once per family at
  creation, using the discovering child's own `source_url`.

  Event witnesses (`WitnessEvent`: type + a `SimplePerson` + a note) become
  `Witness` objects on `Event.witnesses`, privacy-checked like any other
  person reference — `gedcom_writer.py` only emits an `ASSO` pointer for a
  witness that's actually present in the export, never a fabricated `INDI`.
  Geneanet's `reason` field on events was never observed populated in any
  real tree checked so far and its semantics are unconfirmed, so it's
  folded into the event's `NOTE` as labeled text ("Reason: ...") instead of
  being asserted as a specific (possibly wrong) GEDCOM tag like `CAUS`.

  `Person.rparents`/`Person.related` (godparent/adoptive/foster/recognized
  relations — `RELATION_TYPE_LABEL`) map through `_relations_from` into
  `Individual.associations`, reusing the same `Witness` shape and the same
  "`gedcom_writer.py` only links an `ASSO` if the person is actually in the
  export" rule (`_write_associations` is shared by both). Confirmed real
  (`RPARENT_GOD_PARENT`) in `jpmanzinali`'s tree, including a masked
  godparent correctly dropped by the privacy check. `Person.qualifiers`
  (confirmed real, e.g. "Cyr") join into `Individual.nickname`; `titles`
  (nobility, schema-confirmed only) become `Individual.titles` (`TITL`).
  `aliases`/`public_name`/`firstname_aliases`/`surname_aliases` become
  alternate `AlternateName`s on `Individual.names` (GEDCOM alternate `NAME`
  records, `TYPE aka`) — `aliases`/`public_name` are single free-text
  strings Geneanet doesn't split into given/surname (confirmed real, e.g.
  "Marguerite Chauzy"), so `AlternateName.surname` stays `None` and
  `gedcom_writer.py` emits them unslashed rather than risk a wrong split;
  `firstname_aliases`/`surname_aliases` vary only one component, so the
  other comes from the person's own primary name and can be slashed
  normally.
- **`models.py`** — plain dataclasses mirroring GEDCOM concepts (`Individual`,
  `Family`, `Event`, `Note`, `Media`, `Place`), API-agnostic. Keeps
  `gedcom_writer.py` a thin serializer instead of a second place that
  understands genealogy or the API shape.
- **`tree_crawler.py`** — the two crawl strategies behind `--scope`, both
  taking a **list** of seeds/roots (merged into one `CrawlState`) rather
  than one:
  - `crawl_ascendants`: one `get_graph(nb_asc=N)` call per root discovers
    every ancestor's index in that lineage at once, then one `get_person`
    call per discovered ancestor for full detail. Family records are
    synthesized from each person's own `father`/`mother` fields —
    deliberately ignores their own spouse/children
    (`individual_from_person`'s `families` return value), keeping an
    ascendants export to exactly the lineage(s).
  - `crawl_full`: BFS over the whole family graph (parents, spouses,
    children) via the `related` set every `get_person` call returns, from
    every seed (`_resolve_seed_index` per seed, `dict.fromkeys(seeds)`
    deduped). There is no confirmed "list every individual" API action
    (several candidate action names were tried and silently no-opped —
    Geneanet's API doesn't 404 on unknown actions, it just returns an empty
    body, making trial-and-error unreliable), so at least one seed is
    required. **Multi-seed exists specifically because a real tree is NOT
    guaranteed to be one connected component**: a real full-scale run
    against yann64's tree from a single seed reached only 175 of ~546
    individuals, missing 15 of the tree's 24 most common surnames
    entirely — almost certainly an unconnected branch. Don't revert to a
    single `PersonKey` parameter here without re-confirming that's no
    longer an issue.
  - Both checkpoint `CrawlState` (visited set, pending `(PersonKey, index)`
    queue, collected individuals/families) to JSON after every individual,
    resumable with `--resume`. `state.save(state_path)` always runs *before*
    the `on_progress` callback for that individual — relied on by the GUI's
    cancellation handling (see `gui/` below) to guarantee a valid,
    resumable checkpoint exists the moment `on_progress` raises to cancel.
  - `on_progress(individual, done, total)`: `total` is a known int for
    `crawl_ascendants` (the discovered queue length, known right after the
    `get_graph` call, before the per-person loop starts) but always `None`
    for `crawl_full` (no "list everyone" API, so the eventual total is
    genuinely unknowable mid-crawl). `cli.py`'s two `on_progress` closures
    accept and ignore `done`/`total` where they don't need them; the GUI's
    `crawl_worker.py` uses them to drive a real percentage progress bar for
    ascendants exports and a count-only indicator for full-tree ones.
- **`gedcom_writer.py`** — pure function `generate_gedcom(individuals, families, ...)
  -> str`. Computes `FAMC` (family-as-child) by inverting `Family.children`
  lists, since `Individual` only stores `father`/`mother` keys directly.
  `_collect_source_ids` does a first pass over every `Event.sources`/
  `Individual.sources`/`Family.sources` to dedupe citations sharing a
  `title` into one `@S<n>@` record referenced by pointer, and separately
  tracks which titles are the Geneanet-attribution citation
  (`is_geneanet_source`) — those, and only those, get a `1 REPO @R1@` link;
  a single `@R1@ REPO` "Geneanet" record is emitted once if any citation
  needs it. `include_notes=False` suppresses event notes and witness notes
  too, not just top-level `Individual`/`Family` notes — keep that
  consistent if adding another note-bearing field.
- **`cli.py`** — Typer app wiring `list` / `export`. `--individual` is
  required (at least one) and repeatable (`list[str]`) for both — no
  default-person fallback exists over the API, and repeatable is what lets
  one export cover multiple disconnected tree branches (see
  `tree_crawler.py` above).
- **`gui/`** — the optional `exportgeneanet-gui` PySide6 front end, CLI
  parity only (no feature the CLI lacks). `[project.scripts]` registers the
  entry point unconditionally, so `app.py`'s `main()` imports PySide6
  lazily and prints an install hint (`pip install exportgeneanet[gui]`)
  instead of a raw traceback when it's missing — `[project.optional-
  dependencies] gui` stays opt-in for CLI-only installs.
  `crawl_worker.py`'s `CrawlWorker(QThread)` owns exactly one
  `GeneanetApiClient`+`RateLimiter` per GUI session; both "search for a
  person" (`search_persons`) and "run the export" (`crawl_full`/
  `crawl_ascendants` + `write_gedcom_file`) are tasks pushed onto the same
  internal `queue.Queue` and processed one at a time in `run()` — this is
  what keeps the GUI honoring the same never-concurrent,
  always-rate-limited guarantee as the CLI, not just a threading
  convenience. Cancellation is a `CrawlCancelled` exception raised from the
  `on_progress` callback when the user clicks Cancel; it unwinds out of the
  crawl function mid-loop, and the handler reloads `CrawlState.load(state_path)`
  from disk rather than trusting the outer (never-reassigned,
  exception-unwound) `state` variable — safe because of the
  save-before-on_progress ordering noted under `tree_crawler.py` above.
  `search_widget.py`'s `search_result_rows()` (pure function, unit-tested
  in `tests/test_gui_search_widget.py`) and `main_window.py`'s
  `default_state_path()` (matches `cli.py`'s own
  `crawl-state-<username>-<scope>.json` convention exactly, so a checkpoint
  started in one front end resumes in the other) are the only
  GUI-adjacent logic worth testing without a display; the widgets
  themselves are exercised by manual testing only (see README's GUI
  section), not by the automated suite.
- **`packaging/run_gui.py`** + **`scripts/build_executable.py`** — produce
  the standalone `exportgeneanet-gui` executable (PyInstaller, `build`
  extra) that `.github/workflows/release.yml` attaches to a GitHub Release
  on every `v*` tag push, for users without Python (CLI parity only — the
  CLI itself stays pip-install-only). `run_gui.py` exists specifically
  because PyInstaller runs its entry script as `__main__`, and `gui/app.py`
  itself does a relative import (`from .main_window import MainWindow`)
  that only works when imported as part of the `exportgeneanet` package —
  exactly how the pip-installed console script already runs it
  (`from exportgeneanet.gui.app import main`). `run_gui.py` does that same
  absolute import instead of being frozen directly, so don't point
  PyInstaller at `gui/app.py` itself.

### Data flow for `export`

`cli.export` → `tree_crawler.crawl_full` or `crawl_ascendants` (driving
`GeneanetApiClient` + `RateLimiter` + `mapping.individual_from_person`) →
accumulates a `CrawlState` →
`gedcom_writer.write_gedcom_file(state.individuals, state.families, ...)`.

## Testing against real data

Unlike the project's original HTML-scraping approach, this sandbox *can*
reach `gw.geneanet.org/setup/api/` directly (confirmed: plain `curl`/
`requests`, no Cloudflare challenge) — real end-to-end verification against
`yann64` is possible directly in a session, no need to hand off to the user.
`tests/` fixtures use hand-built dicts shaped like real `MessageToDict`
output rather than saved HTML, since the API shape is stable and typed.
