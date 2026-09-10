"""Downloads a `Media.url` file to a user-chosen folder — opt-in
(`--download-media`/the GUI's "Download media" checkbox); the default
behavior everywhere else in this project is to just link the remote URL,
never fetch it.

Reuses the crawl's own `requests.Session` + `RateLimiter` rather than a
separate, unthrottled path — media downloads go through the exact same
sequential, paced request budget as every other Geneanet call this project
makes (see `rate_limiter.py`'s docstring: "not a tunable nicety").
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .identifiers import PersonKey
from .rate_limiter import RateLimiter

_DEFAULT_EXTENSION = ".jpg"
_SAFE_EXTENSION_RE = re.compile(r"^\.[A-Za-z0-9]{1,5}$")


def _force_https(url: str) -> str:
    """Media downloads must be made over HTTPS — rewrite a plain-HTTP URL
    rather than ever issuing the actual request over HTTP, regardless of
    what scheme happened to come back from Geneanet's API."""
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    return url


def _filename_for(key: PersonKey, index: int, url: str) -> str:
    """A filename derived from the owning individual + a per-person index —
    never the remote URL's own path, so nothing about the URL's content
    (e.g. a `../`-style path, or an unexpected/executable extension) ever
    reaches the local filesystem path."""
    suffix = Path(urlsplit(url).path).suffix
    if not _SAFE_EXTENSION_RE.match(suffix):
        suffix = _DEFAULT_EXTENSION
    return f"{key}-{index}{suffix}"


def download_media(
    session: requests.Session,
    rate_limiter: RateLimiter,
    url: str,
    key: PersonKey,
    index: int,
    dest_dir: Path,
) -> Path:
    """Downloads `url` (forced to HTTPS) into `dest_dir`, sequentially
    rate-limited. Returns the absolute local path actually written."""
    https_url = _force_https(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / _filename_for(key, index, https_url)

    rate_limiter.wait()
    response = session.get(https_url, timeout=30, stream=True)
    response.raise_for_status()
    with dest_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest_path.resolve()
