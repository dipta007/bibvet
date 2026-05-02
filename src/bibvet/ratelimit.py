"""Per-source rate limiting.

Each source declares its minimum interval between requests. The limiter
serializes acquire() calls and waits until the next allowed time.
"""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async rate limiter enforcing a minimum interval between acquires.

    Acquires serialize through an internal lock; concurrent callers wait their turn.
    Cache hits should NOT call acquire() — only wrap actual HTTP requests.
    """

    def __init__(self, min_interval_sec: float):
        self._min_interval = max(0.0, min_interval_sec)
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed_at = now + self._min_interval
