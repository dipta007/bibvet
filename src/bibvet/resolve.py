"""UserEntry → list[LookupKey].

Emits every key we can plausibly use. Title queries require a title at least 5 chars long.
"""
from __future__ import annotations

import re

from bibvet.models import LookupKey, UserEntry
from bibvet.normalize import normalize_doi, normalize_string

_ARXIV_PREFIX_RE = re.compile(r"^\s*arxiv:\s*", re.IGNORECASE)


def resolve_lookup_keys(entry: UserEntry) -> list[LookupKey]:
    keys: list[LookupKey] = []
    fields = entry.fields

    if doi := fields.get("doi"):
        keys.append(LookupKey(kind="doi", value=normalize_doi(doi), extras={}))

    eprint = fields.get("eprint", "")
    archive = fields.get("archiveprefix", "").lower()
    if eprint:
        cleaned = _ARXIV_PREFIX_RE.sub("", eprint).strip()
        if archive == "arxiv" or eprint.lower().startswith("arxiv:"):
            keys.append(LookupKey(kind="arxiv", value=cleaned, extras={}))

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
