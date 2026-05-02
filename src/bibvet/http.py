"""Async HTTP client with retry-until-terminal-answer.

Transient failures (429, 5xx, network errors) are retried with exponential backoff
and jitter, honoring `Retry-After` when given. Definitive 4xx (404, etc.) raise
TerminalNegative — the caller treats this as a real "not found" signal.
"""
from __future__ import annotations

import asyncio
import logging
import random
import sys
from types import TracebackType
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Threshold above which we surface retries to stderr (per spec: don't spam for short waits).
_NOTICE_WAIT_SEC = 4.0


class TerminalNegative(Exception):
    """The server gave a definitive negative answer (e.g., 404). Don't retry."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"{status_code} from {url}")


_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_TERMINAL_4XX = {400, 401, 403, 404, 410}


class HttpClient:
    """httpx.AsyncClient wrapper that retries forever until terminal answer.

    Use as an async context manager.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        jitter: float = 0.2,
        user_agent: str = "bibvet/0.0.1 (+https://github.com/dipta007/bibvet)",
    ):
        self._timeout = timeout
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._jitter = jitter
        self._user_agent = user_agent
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HttpClient:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
            follow_redirects=True,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        assert self._client is not None, "Use as async context manager"
        backoff = self._initial_backoff
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.get(url, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                wait = self._next_wait(backoff, None)
                _notify_retry(url, f"network error: {type(e).__name__}", wait)
                await asyncio.sleep(wait)
                backoff = min(backoff * 2, self._max_backoff)
                continue

            if resp.status_code == 200:
                return resp
            if resp.status_code in _TERMINAL_4XX:
                raise TerminalNegative(resp.status_code, url)
            if resp.status_code in _RETRY_STATUSES:
                wait = self._next_wait(backoff, resp.headers.get("Retry-After"))
                _notify_retry(url, f"http {resp.status_code}", wait)
                await asyncio.sleep(wait)
                backoff = min(backoff * 2, self._max_backoff)
                continue

            # Unexpected status — treat as terminal so we don't loop forever
            raise TerminalNegative(resp.status_code, url)

    def _next_wait(self, backoff: float, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        if self._jitter > 0:
            return backoff * (1 + random.uniform(-self._jitter, self._jitter))
        return backoff


def _notify_retry(url: str, reason: str, wait: float) -> None:
    """Log retries always; surface to stderr only for long waits to avoid spam."""
    logger.info("retrying %s in %.1fs (%s)", url, wait, reason)
    if wait >= _NOTICE_WAIT_SEC:
        host = url.split("/")[2] if "://" in url else url
        print(f"  bibvet: {reason} on {host}, retrying in {wait:.0f}s", file=sys.stderr, flush=True)
