"""Semantic Scholar Graph API client.

By DOI:    GET https://api.semanticscholar.org/graph/v1/paper/DOI:<doi>?fields=...
By arXiv:  GET https://api.semanticscholar.org/graph/v1/paper/arXiv:<id>?fields=...
By title:  GET https://api.semanticscholar.org/graph/v1/paper/search?query=<...>&limit=5&fields=...

Optional API key: env SEMANTIC_SCHOLAR_API_KEY → x-api-key header.
"""
from __future__ import annotations

import os
from urllib.parse import quote, urlencode

from bibvet.http import TerminalNegative
from bibvet.models import Author, CanonicalRecord, LookupKey
from bibvet.normalize import fuzzy_ratio, normalize_doi, title_match_score
from bibvet.ratelimit import RateLimiter
from bibvet.sources.base import Source

BASE = "https://api.semanticscholar.org/graph/v1/paper"
FIELDS = "title,year,venue,authors,externalIds,publicationTypes"
TITLE_MATCH_THRESHOLD = 90
# Unauthenticated S2 allows ~100/5min = 1 per 3s. With API key, much higher.
S2_MIN_INTERVAL_NO_KEY = 1.0
S2_MIN_INTERVAL_WITH_KEY = 0.05


class SemanticScholarSource(Source):
    name = "semantic_scholar"

    def __init__(self, http, cache):
        super().__init__(http, cache)
        interval = (
            S2_MIN_INTERVAL_WITH_KEY
            if os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
            else S2_MIN_INTERVAL_NO_KEY
        )
        self._rate_limiter = RateLimiter(interval)

    def supports(self, key: LookupKey) -> bool:
        return key.kind in ("doi", "arxiv", "title_query")

    async def fetch(self, key: LookupKey) -> CanonicalRecord | None:
        cache_key = f"{key.kind}:{key.value}"
        cached = self.cache.get(self.name, cache_key)
        if cached is not None:
            if cached.get("_not_found"):
                return None
            return _from_dict(cached, key)

        try:
            data = await self._http_fetch(key)
        except TerminalNegative:
            self.cache.set(self.name, cache_key, {"_not_found": True})
            return None

        record = _select(data, key)
        if record is None:
            self.cache.set(self.name, cache_key, {"_not_found": True})
            return None
        as_dict = _to_dict(record)
        self.cache.set(self.name, cache_key, as_dict)
        return _from_dict(as_dict, key)

    def _headers(self) -> dict[str, str]:
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        return {"x-api-key": api_key} if api_key else {}

    async def _http_fetch(self, key: LookupKey) -> dict:
        if key.kind == "doi":
            url = f"{BASE}/DOI:{quote(key.value, safe='')}?fields={FIELDS}"
        elif key.kind == "arxiv":
            url = f"{BASE}/arXiv:{quote(key.value, safe='')}?fields={FIELDS}"
        else:
            url = f"{BASE}/search?{urlencode({'query': key.value, 'limit': 5, 'fields': FIELDS})}"
        await self._rate_limiter.acquire()
        resp = await self.http.get(url, headers=self._headers())
        return resp.json()


def _select(data: dict, key: LookupKey) -> dict | None:
    if key.kind in ("doi", "arxiv"):
        if not data or "title" not in data:
            return None
        return data
    items = data.get("data", []) or []
    if not items:
        return None

    def _score(it: dict) -> int:
        title = it.get("title", "")
        year = int(it.get("year") or 0)
        authors = it.get("authors") or []
        first_family = _split_name(authors[0].get("name", ""))[0] if authors else ""
        return title_match_score(title, year, first_family, key.value, key.extras)

    best = max(items, key=_score)
    if fuzzy_ratio(best.get("title", ""), key.value) < TITLE_MATCH_THRESHOLD:
        return None
    return best


def _split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _to_dict(msg: dict) -> dict:
    ids = msg.get("externalIds") or {}
    return {
        "doi": (ids.get("DOI") or "").lower() or None,
        "arxiv_id": ids.get("ArXiv") or None,
        "title": msg.get("title", ""),
        "authors": [
            {"family": _split_name(a.get("name", ""))[0], "given": _split_name(a.get("name", ""))[1]}
            for a in msg.get("authors", []) or []
        ],
        "year": msg.get("year") or 0,
        "venue": msg.get("venue") or None,
        "type": ",".join(msg.get("publicationTypes") or []),
    }


def _from_dict(d: dict, key: LookupKey) -> CanonicalRecord:
    authors = tuple(Author(family=a["family"], given=a.get("given", "")) for a in d["authors"])
    return CanonicalRecord(
        source="semantic_scholar",
        matched_via=key,
        title=d["title"],
        authors=authors,
        year=d["year"],
        venue=d.get("venue"),
        doi=normalize_doi(d["doi"]) if d.get("doi") else None,
        arxiv_id=d.get("arxiv_id"),
        entry_type_hint=d["type"],
        raw=d,
    )
