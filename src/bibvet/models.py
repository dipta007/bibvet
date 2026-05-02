"""Frozen dataclasses for bibvet's pipeline.

These are the contracts between modules. Keep them small and immutable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

LookupKind = Literal["doi", "arxiv", "title_query"]
SourceName = Literal["crossref", "semantic_scholar", "arxiv"]
Severity = Literal["error", "warning", "info"]
EntryStatus = Literal["verified", "fixable", "cross_check_failed", "unverified", "skipped"]


@dataclass(frozen=True)
class UserEntry:
    """One bibtex entry as parsed from the user's .bib file."""

    citekey: str
    entry_type: str  # lowercase, e.g. "article", "inproceedings"
    fields: dict[str, str]  # raw field values, LaTeX preserved
    source_file: Path
    source_line: int


@dataclass(frozen=True)
class LookupKey:
    """A way to look up a paper. Multiple keys can resolve to the same paper."""

    kind: LookupKind
    value: str
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Author:
    """Parsed author name. `family` is the last name."""

    family: str
    given: str  # may be empty if only last name known
    orcid: str | None = None


@dataclass(frozen=True)
class CanonicalRecord:
    """A paper as returned by one source. Multiple records may describe the same paper."""

    source: SourceName
    matched_via: LookupKey
    title: str
    authors: tuple[Author, ...]  # tuple for hashability
    year: int
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    entry_type_hint: str  # source-specific, e.g. "journal-article", "proceedings-article"
    raw: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True)
class FieldDiff:
    """A discrepancy between a user-supplied field and the canonical value."""

    field: str
    user_value: str
    canonical_value: str
    severity: Severity
    rationale: str


@dataclass(frozen=True)
class EntryReport:
    """The verdict for one .bib entry."""

    entry: UserEntry
    status: EntryStatus
    canonical: CanonicalRecord | None
    sources_consulted: tuple[CanonicalRecord, ...]
    diffs: tuple[FieldDiff, ...]
    paper_url: str | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileReport:
    """All entries from one input file, with their verdicts."""

    path: Path
    entries: tuple[EntryReport, ...]
