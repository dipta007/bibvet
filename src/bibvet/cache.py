"""Disk cache for source responses.

Layout: <root>/v<schema>/<source>/<sha256(key)>.json
File format: {"stored_at": <unix>, "value": <data>}

TTL is enforced on read (lazy expiry). Corrupted files are deleted on read.
If the cache root is unwritable, falls back to in-memory for this process.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


class DiskCache:
    """File-backed cache, namespaced by source name."""

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        schema_version: int = CACHE_SCHEMA_VERSION,
    ):
        self._root = Path(root) / f"v{schema_version}"
        self._ttl = ttl_seconds
        self._memory: dict[tuple[str, str], dict[str, Any]] = {}
        self._writable = self._ensure_dir()

    def _ensure_dir(self) -> bool:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            return True
        except OSError as e:
            logger.warning("cache root %s unwritable (%s); using in-memory only", self._root, e)
            return False

    def _path(self, source: str, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / source / f"{h}.json"

    def get(self, source: str, key: str) -> dict[str, Any] | None:
        if not self._writable:
            mem = self._memory.get((source, key))
            if mem is not None and mem["stored_at"] + self._ttl >= time.time():
                return mem["value"]
            return None

        path = self._path(source, key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("corrupt cache entry %s (%s); deleting", path, e)
            self._memory.pop((source, key), None)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        if not isinstance(data, dict) or "stored_at" not in data:
            self._memory.pop((source, key), None)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        if data["stored_at"] + self._ttl < time.time():
            return None
        return data["value"]

    def set(self, source: str, key: str, value: dict[str, Any]) -> None:
        record = {"stored_at": time.time(), "value": value}
        self._memory[(source, key)] = record
        if not self._writable:
            return
        path = self._path(source, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record), encoding="utf-8")
        except OSError as e:
            logger.warning("cache write failed (%s); continuing in-memory only", e)
            self._writable = False

    def get_or_set(
        self, source: str, key: str, factory: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        cached = self.get(source, key)
        if cached is not None:
            return cached
        value = factory()
        self.set(source, key, value)
        return value

    def clear(self) -> None:
        self._memory.clear()
        if not self._writable:
            return
        for child in self._root.rglob("*.json"):
            try:
                child.unlink()
            except OSError:
                pass


def default_cache_root() -> Path:
    """Return the platform-appropriate cache directory for bibvet."""
    from platformdirs import user_cache_dir

    return Path(user_cache_dir("bibvet"))
