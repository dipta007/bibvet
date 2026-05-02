"""UserEntry → list[LookupKey].

Emits every key we can plausibly use. Title queries require a title at least 5 chars long.
"""
from __future__ import annotations

import re

from bibvet.models import LookupKey, UserEntry
from bibvet.normalize import normalize_doi, normalize_string

_ARXIV_PREFIX_RE = re.compile(r"^\s*arxiv:\s*", re.IGNORECASE)

# Match modern arXiv ID (YYMM.NNNNN) and old-style (cs/0701001 etc).
_ARXIV_ID_RE = re.compile(
    r"(?:arxiv[:\s]*)?(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})",
    re.IGNORECASE,
)
# arXiv-style DOI: 10.48550/arXiv.<id>
_ARXIV_DOI_RE = re.compile(r"10\.48550/arXiv\.(\S+)", re.IGNORECASE)


def _extract_arxiv_id(entry_fields: dict[str, str]) -> str | None:
    """Find an arXiv ID anywhere it commonly appears: eprint, journal, doi, note, url."""
    eprint = entry_fields.get("eprint", "").strip()
    archive = entry_fields.get("archiveprefix", "").lower()
    if eprint:
        cleaned = _ARXIV_PREFIX_RE.sub("", eprint).strip()
        if archive == "arxiv" or eprint.lower().startswith("arxiv:"):
            return cleaned
        # Some entries have a bare arXiv ID in eprint with no archiveprefix.
        if _ARXIV_ID_RE.fullmatch(cleaned):
            return cleaned

    # arXiv-style DOI (preprint with no other DOI assigned).
    doi = entry_fields.get("doi", "")
    if doi:
        m = _ARXIV_DOI_RE.search(doi)
        if m:
            return m.group(1).strip()

    # Common Google-Scholar export: journal = "arXiv preprint arXiv:2005.00085"
    # Also: url = "http://arxiv.org/abs/2204.02311", note = "arXiv:2204.02311 [cs]"
    for field in ("journal", "note", "url", "howpublished"):
        value = entry_fields.get(field, "")
        if not value or "arxiv" not in value.lower():
            continue
        # Find the first arXiv-shaped ID anywhere in the value.
        m = _ARXIV_ID_RE.search(value)
        if m:
            return m.group(1)

    return None


def resolve_lookup_keys(entry: UserEntry) -> list[LookupKey]:
    keys: list[LookupKey] = []
    fields = entry.fields

    if doi := fields.get("doi"):
        # Skip DOI lookup for arXiv-style DOIs — they resolve to arXiv anyway,
        # so the arxiv key (extracted below) is a better hit.
        if not _ARXIV_DOI_RE.search(doi):
            keys.append(LookupKey(kind="doi", value=normalize_doi(doi), extras={}))

    arxiv_id = _extract_arxiv_id(fields)
    if arxiv_id:
        keys.append(LookupKey(kind="arxiv", value=arxiv_id, extras={}))

    title = fields.get("title", "").strip()
    if len(title) >= 5:
        author = fields.get("author", "")
        first_author = _first_author_lastname(author)
        year_str = fields.get("year", "").strip()
        try:
            year = int(year_str)
        except (TypeError, ValueError):
            year = 0
        keys.append(
            LookupKey(
                kind="title_query",
                value=normalize_string(title),
                extras={"first_author": first_author, "year": year},
            )
        )

    return keys


def _first_author_lastname(author_field: str) -> str:
    """Extract the lastname of the first author, normalized."""
    if not author_field:
        return ""
    # bibtex format: "Last, First and Last2, First2"
    first = author_field.split(" and ")[0].strip()
    if "," in first:
        last = first.split(",", 1)[0].strip()
    else:
        # "First Last" form — take the last token
        last = first.split()[-1] if first else ""
    return normalize_string(last)
