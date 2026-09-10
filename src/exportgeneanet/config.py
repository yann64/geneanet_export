"""Default configuration values for exportgeneanet."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def tool_version() -> str:
    """The installed package version — shared by the CLI's `--version`,
    the GUI's window title, and the Gramps header's `<created version=...>`
    (a genuine install metadata lookup, not a hardcoded string, so it can
    never drift out of sync with `pyproject.toml`). Falls back to a clearly
    fake version rather than raising if metadata isn't found at all (e.g. a
    frozen build missing `copy_metadata` — a real gap to fix in the
    packaging spec, not something worth crashing over here)."""
    try:
        return version("exportgeneanet")
    except PackageNotFoundError:
        return "0.0.0"


STATE_DIR = Path.home() / ".exportgeneanet"

API_BASE_URL = "https://gw.geneanet.org/setup/api"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)

# Base for citation URLs pointing at a person's page on gw.geneanet.org —
# built for GEDCOM SOUR/PAGE references only. This project never fetches
# these URLs itself (see CLAUDE.md "Critical constraint: how data is
# fetched"); they exist purely so a human reading the exported GEDCOM can
# click through to the source page.
GENEANET_WEB_BASE_URL = "https://gw.geneanet.org"
GENEANET_REPOSITORY_NAME = "Geneanet"
GENEANET_REPOSITORY_WWW = "https://www.geneanet.org/"

# Sequential requests only; a random delay in this range is applied before every
# API call so as not to burden Geneanet's servers.
DEFAULT_MIN_DELAY_SECONDS = 4.0
DEFAULT_MAX_DELAY_SECONDS = 10.0

DEFAULT_LANG = "fr"


@dataclass(frozen=True)
class RunConfig:
    """Options shared by every command that talks to Geneanet."""

    username: str
    min_delay: float = DEFAULT_MIN_DELAY_SECONDS
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS
    lang: str = DEFAULT_LANG
