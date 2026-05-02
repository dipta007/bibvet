"""Abstract source interface.

Every source converts a LookupKey into zero or more CanonicalRecords. They share
an HTTP client and a cache; the source itself doesn't manage either.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from bibvet.cache import DiskCache
from bibvet.http import HttpClient
from bibvet.models import CanonicalRecord, LookupKey, SourceName


class Source(ABC):
    """A data source. Subclasses implement `fetch` and declare which key kinds they support."""

    name: SourceName

    def __init__(self, http: HttpClient, cache: DiskCache):
        self.http = http
        self.cache = cache

    @abstractmethod
    def supports(self, key: LookupKey) -> bool:
        """Return True if this source can handle the given lookup key."""

    @abstractmethod
    async def fetch(self, key: LookupKey) -> CanonicalRecord | None:
        """Return a canonical record for the key, or None if not found."""
