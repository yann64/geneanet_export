# ExportGeneanet

Export a public [Geneanet](https://www.geneanet.org/) tree to a GEDCOM 5.5.1
file, using only data that is publicly displayed on the site.

Given a Geneanet username, the tool can:

- List every individual reachable from one or more seed individuals via
  family links.
- Export the entire tree (individuals, families, events, notes, sources,
  media), or just the **ascendants** of one or more selected individuals.

A Typer-based CLI (`exportgeneanet`) and an optional PySide6 (Qt6) GUI
(`exportgeneanet-gui`) both sit on top of the same library code — the GUI has
CLI parity, adding a search-based picker in place of hand-typing individual
identifiers.

## How it talks to Geneanet

`gw.geneanet.org`'s HTML pages sit behind a Cloudflare "managed challenge"
that reliably blocks automated access — headless browsers are detected and
challenge-walled outright, and even a real, human-operated browser couldn't
get consistently past it during this project's development.

Instead, this tool calls **Geneanet's own internal API**
(`https://gw.geneanet.org/setup/api/`) — the same protobuf-based API
Geneanet's own frontend calls after a page's shell loads. That subpath has no
such protection: plain HTTP requests reach it immediately. This approach was
discovered via [jmichault/gramps-kromprogramoj](https://github.com/jmichault/gramps-kromprogramoj)
(GPL-3.0), a real, actively-maintained Gramps addon that talks to Geneanet
the same way.

Two things worth knowing:

- **This is an unofficial, internal API**, not a documented public one.
  It's openly and anonymously reachable with no technical access barrier,
  and Geneanet's own `.proto` schema files are served right at that same
  path — but Geneanet could change or restrict it without notice.
- **This tool never authenticates.** Every call is made exactly as an
  anonymous visitor's browser would make it. The API includes explicit
  `name_is_hidden` / `name_is_restricted` / `visible_for_visitors` flags on
  every person it returns — the same flags Geneanet's own frontend uses to
  decide whether to render a name — and this tool treats them as
  authoritative, silently dropping any reference that isn't publicly
  visible rather than including it.

## Respecting Geneanet's usage

- Only data an anonymous visitor could see is ever fetched or exported.
- Requests are strictly sequential (never concurrent) and separated by a
  **randomized** delay (`--min-delay`/`--max-delay`, default 4-10s) so as not
  to burden Geneanet's servers. Because a single `graph_v2` call can fetch
  several generations of ascendants at once, this approach also needs far
  fewer total requests than crawling one HTML page per person would.
- A full-tree export of a large tree can still take a while under this
  pacing — that's expected, not a bug. Interrupted crawls checkpoint progress
  to a `crawl-state-*.json` file and can be continued with `--resume` instead
  of starting over.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional: the exportgeneanet-gui desktop app (PySide6/Qt6)
pip install -e ".[gui]"
```

No browser, no browser profile, nothing to solve by hand — it's a plain
HTTP client (`requests`).

## Usage

```bash
# List every individual reachable from a seed via family links
exportgeneanet list --username yann64 --individual "etienne.barbel.0"

# Export the whole tree, starting discovery from a known individual
exportgeneanet export --username yann64 --scope all \
    --individual "etienne.barbel.0" --output yann64.ged

# A tree isn't guaranteed to be one connected family graph — pass
# --individual more than once to cover multiple branches in one export
exportgeneanet export --username yann64 --scope all \
    --individual "etienne.barbel.0" --individual "anne.cathala.0" \
    --output yann64.ged

# Export only the ascendants of one individual
exportgeneanet export --username yann64 --scope ascendants \
    --individual "etienne.barbel.0" --nb-asc 20 --output yann64_ascendants.ged

# Resume an interrupted export
exportgeneanet export --username yann64 --scope all \
    --individual "etienne.barbel.0" --output yann64.ged --resume
```

`--individual` uses the form `given.surname[.oc]`, where `oc` is GeneWeb's
occurrence number disambiguating people with the same name (defaults to `0`).
It's always required (at least one) and repeatable: there's no confirmed API
call for "the tree's default person" or "every individual in the tree" the
way the old HTML pages exposed, so both `list` and `--scope all` use the
given individual(s) as starting points and discover the rest by following
family links (parents, spouses, children).

**A tree is not guaranteed to be a single connected family graph** — a real,
full-scale `--scope all` run against a live tree reached only a third of its
individuals from one seed, missing several of the tree's most common
surnames entirely (almost certainly an unconnected branch, e.g. a spouse's
family with no recorded link back). If `--scope all` looks incomplete, pass
`--individual` again for a person in the missing branch — every seed's
reachable set gets merged into the same export.

### GUI

```bash
exportgeneanet-gui
```

Search by surname/given name to pick seed individual(s) instead of typing
`given.surname.oc` by hand, then the same scope/output/resume/rate-limit
options as the CLI. Running it without the `gui` extra installed prints a
`pip install exportgeneanet[gui]` hint instead of a traceback. The GUI and
CLI share checkpoint files (`crawl-state-<username>-<scope>.json`), so an
export started in one can be resumed in the other.

#### Standalone GUI download (no Python required)

Each tagged release publishes a portable, single-file `exportgeneanet-gui`
executable for Linux and Windows on the repo's
[GitHub Releases](../../releases) page — download and run, no Python or
`pip install` needed. A few things to know:

- It's unsigned: Windows SmartScreen will warn on first run ("more info" →
  "run anyway"); on Linux, mark the file executable first
  (`chmod +x exportgeneanet-gui-linux-x86_64`).
- The CLI isn't packaged this way — it stays a normal `pip install`, since
  its users already have Python.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .    # lint
ruff format .   # format
```

CI (`.github/workflows/ci.yml`) runs all three on every push/PR to `main`,
against Python 3.10 (the declared minimum) and 3.12.

Tests in `tests/` cover the GEDCOM writer, protobuf-response mapping,
person identifiers, and crawl-state checkpointing — all without network
access.

`src/exportgeneanet/proto/` holds generated Python bindings for Geneanet's
own `.proto` schemas, committed to the repo like the reference addon does so
normal installs never need a protobuf compiler. Regenerate them (only needed
if Geneanet changes its API schema) with:

```bash
python scripts/generate_proto.py
```

This uses `grpc_tools.protoc` (a pip package, part of the `dev` extra) —
no system-level `protoc` install needed.

### Building the standalone GUI executable

```bash
pip install -e ".[gui,build]"
python scripts/build_executable.py
```

Produces `dist/exportgeneanet-gui` (`.exe` on Windows) via PyInstaller.
`.github/workflows/release.yml` runs the same script on `ubuntu-latest` and
`windows-latest` whenever a `v*` tag is pushed, and attaches both
executables to a GitHub Release.
