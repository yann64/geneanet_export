"""Default configuration values for exportgeneanet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATE_DIR = Path.home() / ".exportgeneanet"

API_BASE_URL = "https://gw.geneanet.org/setup/api"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)

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
