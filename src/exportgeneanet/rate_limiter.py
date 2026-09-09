"""Randomized, sequential pacing between requests to Geneanet.

Geneanet only tolerates being crawled if requests are spaced out and never sent
concurrently. This module is the single choke point every fetch goes through.
"""

from __future__ import annotations

import random
import time


class RateLimiter:
    """Sleeps a random duration before each call to `wait()`.

    Not thread-safe by design: the crawler is expected to fetch pages one at a
    time, never in parallel.
    """

    def __init__(self, min_delay: float, max_delay: float) -> None:
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("require 0 <= min_delay <= max_delay")
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_request_at: float | None = None

    def wait(self) -> float:
        """Block for a random delay, then record the request time. Returns the delay."""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
        self._last_request_at = time.monotonic()
        return delay
