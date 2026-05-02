"""arXiv API client.

Endpoint: http://export.arxiv.org/api/query
- By id: ?id_list=<id>
- By title: ?search_query=ti:%22<title>%22&max_results=5
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from bibvet.http import TerminalNegative
from bibvet.models import Author, CanonicalRecord, LookupKey
from bibvet.normalize import fuzzy_ratio, title_match_score
from bibvet.sources.base import Source

ATOM_NS = "{http://www.w3.org/2005/Atom}"
BASE_URL = "http://export.arxiv.org/api/query"
TITLE_MATCH_THRESHOLD = 90


class ArxivSource(Source):
    name = "arxiv"

    def supports(self, key: LookupKey) -> bool:
        return key.kind in ("arxiv", "title_query")

    async def fetch(self, key: LookupKey) -> CanonicalRecord | None:
        cache_key = f"{key.kind}:{key.value}"
        cached = self.cache.get(self.name, cache_key)
        if cached is not None:
            return _record_from_cached(cached, key)

        try:
            xml_text = await self._http_fetch(key)
        except TerminalNegative:
            self.cache.set(self.name, cache_key, {"_not_found": True})
            return None

        candidates = _parse_feed(xml_text)
        chosen = _pick(candidates, key)
        if chosen is None:
            self.cache.set(self.name, cache_key, {"_not_found": True})
            return None
        record_dict = _record_to_dict(chosen)
        self.cache.set(self.name, cache_key, record_dict)
        return _record_from_cached(record_dict, key)

    async def _http_fetch(self, key: LookupKey) -> str:
        if key.kind == "arxiv":
            url = f"{BASE_URL}?{urlencode({'id_list': key.value})}"
        else:
            query = f'ti:"{key.value}"'
            url = f"{BASE_URL}?{urlencode({'search_query': query, 'max_results': 5})}"
        resp = await self.http.get(url)
        return resp.text


def _parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    results: list[dict] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        id_el = entry.find(f"{ATOM_NS}id")
        title_el = entry.find(f"{ATOM_NS}title")
        published_el = entry.find(f"{ATOM_NS}published")
        if id_el is None or title_el is None:
            continue
        arxiv_id = _extract_arxiv_id(id_el.text or "")
        title = (title_el.text or "").strip().replace("\n", " ").replace("  ", " ")
        year = 0
        if published_el is not None and published_el.text:
            year = int(published_el.text[:4])
        authors: list[dict] = []
        for a in entry.findall(f"{ATOM_NS}author"):
            n = a.find(f"{ATOM_NS}name")
            if n is not None and n.text:
                family, given = _split_name(n.text)
                authors.append({"family": family, "given": given})
        results.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "year": year,
            "authors": authors,
        })
    return results


_ID_RE = re.compile(r"abs/([^v\s]+)")


def _extract_arxiv_id(s: str) -> str:
    m = _ID_RE.search(s)
    return m.group(1) if m else s


def _split_name(full: str) -> tuple[str, str]:
    """arXiv gives 'First Last' (or 'First Middle Last'). Treat last whitespace token as family."""
    parts = full.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _pick(candidates: list[dict], key: LookupKey) -> dict | None:
    if not candidates:
        return None
    if key.kind == "arxiv":
        return candidates[0]

    def _score(c: dict) -> int:
        first_family = c["authors"][0]["family"] if c.get("authors") else ""
        return title_match_score(c["title"], c.get("year") or 0, first_family, key.value, key.extras)

    best = max(candidates, key=_score)
    if fuzzy_ratio(best["title"], key.value) < TITLE_MATCH_THRESHOLD:
        return None
    return best


def _record_to_dict(c: dict) -> dict:
    return c


def _record_from_cached(d: dict, key: LookupKey) -> CanonicalRecord | None:
    if d.get("_not_found"):
        return None
    authors = tuple(Author(family=a["family"], given=a.get("given", "")) for a in d["authors"])
    return CanonicalRecord(
        source="arxiv",
        matched_via=key,
        title=d["title"],
        authors=authors,
        year=d["year"],
        venue=None,
        doi=None,
        arxiv_id=d.get("arxiv_id"),
        entry_type_hint="preprint",
        raw=d,
    )
