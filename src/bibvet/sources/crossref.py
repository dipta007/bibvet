"""CrossRef API client.

DOI lookup: GET https://api.crossref.org/works/<doi>
Title search: GET https://api.crossref.org/works?query.bibliographic=<title>&rows=5

Honors the polite pool by setting `mailto` if env CROSSREF_MAILTO is set.
"""
from __future__ import annotations

import os
from urllib.parse import quote, urlencode

from bibvet.http import TerminalNegative
from bibvet.models import Author, CanonicalRecord, LookupKey
from bibvet.normalize import fuzzy_ratio, normalize_doi, title_match_score
from bibvet.sources.base import Source

BASE = "https://api.crossref.org/works"
TITLE_MATCH_THRESHOLD = 90


class CrossRefSource(Source):
    name = "crossref"

    def supports(self, key: LookupKey) -> bool:
        return key.kind in ("doi", "title_query")

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

    async def _http_fetch(self, key: LookupKey) -> dict:
        if key.kind == "doi":
            url = f"{BASE}/{quote(key.value, safe='')}"
        else:
            params = {"query.bibliographic": key.value, "rows": 20}
            mailto = os.environ.get("CROSSREF_MAILTO")
            if mailto:
                params["mailto"] = mailto
            url = f"{BASE}?{urlencode(params)}"
        resp = await self.http.get(url)
        return resp.json()


def _select(data: dict, key: LookupKey) -> dict | None:
    if key.kind == "doi":
        return data.get("message")
    items = data.get("message", {}).get("items", []) or []
    if not items:
        return None

    def _score(it: dict) -> int:
        title = _first(it.get("title"))
        year = _extract_year(it)
        authors = it.get("author") or []
        first_family = authors[0].get("family", "") if authors else ""
        return title_match_score(title, year, first_family, key.value, key.extras)

    best = max(items, key=_score)
    if fuzzy_ratio(_first(best.get("title")), key.value) < TITLE_MATCH_THRESHOLD:
        return None
    return best


def _first(xs):
    if not xs:
        return ""
    if isinstance(xs, list):
        return xs[0] if xs else ""
    return xs


def _extract_year(msg: dict) -> int:
    issued = msg.get("issued", {}).get("date-parts") or [[0]]
    raw = issued[0][0] if issued and issued[0] else 0
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _to_dict(msg: dict) -> dict:
    year = _extract_year(msg)
    return {
        "doi": msg.get("DOI", "").lower() or None,
        "title": _first(msg.get("title")),
        "authors": [
            {"family": a.get("family", ""), "given": a.get("given", "")}
            for a in msg.get("author", []) or []
        ],
        "year": year,
        "venue": _first(msg.get("container-title")) or None,
        "type": msg.get("type", "") or "",
    }


def _from_dict(d: dict, key: LookupKey) -> CanonicalRecord:
    authors = tuple(Author(family=a["family"], given=a.get("given", "")) for a in d["authors"])
    return CanonicalRecord(
        source="crossref",
        matched_via=key,
        title=d["title"],
        authors=authors,
        year=d["year"],
        venue=d.get("venue"),
        doi=normalize_doi(d["doi"]) if d.get("doi") else None,
        arxiv_id=None,
        entry_type_hint=d["type"],
        raw=d,
    )
