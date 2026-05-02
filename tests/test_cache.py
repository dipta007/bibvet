import json
import time
from pathlib import Path

import pytest

from bibvet.cache import DiskCache, CACHE_SCHEMA_VERSION


def test_miss_returns_none(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.get("crossref", "10.1/abc") is None


def test_set_then_get(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("crossref", "10.1/abc", {"title": "T"})
    assert cache.get("crossref", "10.1/abc") == {"title": "T"}


def test_persists_across_instances(tmp_path):
    DiskCache(tmp_path).set("arxiv", "2005.00683", {"title": "T"})
    assert DiskCache(tmp_path).get("arxiv", "2005.00683") == {"title": "T"}


def test_ttl_expiry(tmp_path):
    cache = DiskCache(tmp_path, ttl_seconds=0)
    cache.set("crossref", "10.1/abc", {"x": 1})
    time.sleep(0.01)
    assert cache.get("crossref", "10.1/abc") is None


def test_corrupted_file_self_heals(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("crossref", "10.1/abc", {"x": 1})
    files = list((tmp_path).rglob("*.json"))
    assert len(files) == 1
    files[0].write_text("not valid json {")
    assert cache.get("crossref", "10.1/abc") is None


def test_schema_version_invalidates(tmp_path):
    cache = DiskCache(tmp_path)
    files_dir = tmp_path / f"v{CACHE_SCHEMA_VERSION}"
    cache.set("crossref", "10.1/abc", {"x": 1})
    new_cache = DiskCache(tmp_path, schema_version=CACHE_SCHEMA_VERSION + 1)
    assert new_cache.get("crossref", "10.1/abc") is None


def test_get_or_set_calls_factory_on_miss(tmp_path):
    cache = DiskCache(tmp_path)
    calls = []

    def factory():
        calls.append(1)
        return {"x": 42}

    assert cache.get_or_set("crossref", "key", factory) == {"x": 42}
    assert cache.get_or_set("crossref", "key", factory) == {"x": 42}
    assert len(calls) == 1


def test_clear(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("crossref", "10.1/abc", {"x": 1})
    cache.clear()
    assert cache.get("crossref", "10.1/abc") is None


def test_unwritable_falls_back_to_memory(tmp_path, caplog):
    bad = tmp_path / "readonly"
    bad.mkdir()
    bad.chmod(0o500)
    try:
        cache = DiskCache(bad)
        cache.set("crossref", "10.1/abc", {"x": 1})
        assert cache.get("crossref", "10.1/abc") == {"x": 1}
    finally:
        bad.chmod(0o700)
