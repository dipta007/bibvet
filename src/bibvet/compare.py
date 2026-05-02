"""Pure decision logic: (UserEntry, list[CanonicalRecord]) → EntryReport.

Implements the rules from spec section 'Compare decision logic'.
"""
from __future__ import annotations

from bibvet.models import (
    CanonicalRecord,
    EntryReport,
    EntryStatus,
    FieldDiff,
    UserEntry,
)
from bibvet.normalize import fuzzy_ratio, normalize_doi, normalize_string

PAPER_TYPES = frozenset({"article", "inproceedings", "conference", "incollection"})
NON_PAPER_TYPES = frozenset({
    "book", "manual", "booklet", "phdthesis", "mastersthesis", "techreport", "misc", "unpublished",
})

TITLE_ERROR_THRESHOLD = 92
TITLE_WARNING_THRESHOLD = 97
VENUE_WARNING_THRESHOLD = 80
CROSS_CHECK_THRESHOLD = 90


def compare_entry(entry: UserEntry, records: list[CanonicalRecord]) -> EntryReport:
    """Apply spec compare logic to one entry's worth of source records."""
    if not records:
        status: EntryStatus = (
            "unverified" if entry.entry_type in PAPER_TYPES else "skipped"
        )
        return EntryReport(
            entry=entry, status=status, canonical=None,
            sources_consulted=(), diffs=(), paper_url=None, notes=(),
        )

    id_record = _pick_by_match_kind(records, ("doi", "arxiv"))
    title_record = _pick_by_match_kind(records, ("title_query",))
    if id_record is not None and title_record is not None:
        if not _records_agree(id_record, title_record):
            return EntryReport(
                entry=entry, status="cross_check_failed", canonical=None,
                sources_consulted=tuple(records), diffs=(),
                paper_url=_paper_url(id_record),
                notes=(
                    f"DOI/arXiv lookup found '{id_record.title}'; "
                    f"title search found '{title_record.title}'.",
                ),
            )

    canonical = _reconcile(records)
    diffs = _compute_diffs(entry, canonical)
    has_error = any(d.severity == "error" for d in diffs)
    status = "fixable" if has_error else "verified"

    notes: list[str] = []
    user_citing_preprint = (
        entry.fields.get("eprint") is not None
        or entry.fields.get("archiveprefix", "").lower() == "arxiv"
    )
    if user_citing_preprint:
        published = next(
            (r for r in records if r.source != "arxiv" and r.doi is not None and r.venue),
            None,
        )
        if published is not None:
            notes.append(
                f"Published version exists at {published.venue} ({published.year}); "
                f"you cited the arXiv preprint."
            )

    return EntryReport(
        entry=entry, status=status, canonical=canonical,
        sources_consulted=tuple(records), diffs=tuple(diffs),
        paper_url=_paper_url(canonical), notes=tuple(notes),
    )


def _pick_by_match_kind(records: list[CanonicalRecord], kinds: tuple[str, ...]) -> CanonicalRecord | None:
    for r in records:
        if r.matched_via.kind in kinds:
            return r
    return None


def _records_agree(a: CanonicalRecord, b: CanonicalRecord) -> bool:
    if a.doi and b.doi:
        return normalize_doi(a.doi) == normalize_doi(b.doi)
    return fuzzy_ratio(a.title, b.title) >= CROSS_CHECK_THRESHOLD


def _reconcile(records: list[CanonicalRecord]) -> CanonicalRecord:
    has_doi = [r for r in records if r.doi]
    if has_doi:
        crossref = next((r for r in has_doi if r.source == "crossref"), None)
        if crossref is not None:
            return crossref
        s2 = next((r for r in has_doi if r.source == "semantic_scholar"), None)
        if s2 is not None:
            return s2
        return has_doi[0]
    s2 = next((r for r in records if r.source == "semantic_scholar"), None)
    if s2 is not None:
        return s2
    arxiv = next((r for r in records if r.source == "arxiv"), None)
    if arxiv is not None:
        return arxiv
    return records[0]


def _compute_diffs(entry: UserEntry, canonical: CanonicalRecord) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    f = entry.fields

    user_year = f.get("year", "").strip()
    if user_year and canonical.year and user_year != str(canonical.year):
        diffs.append(FieldDiff(
            field="year", user_value=user_year, canonical_value=str(canonical.year),
            severity="error", rationale=f"year mismatch — canonical source says {canonical.year}",
        ))

    if "title" in f and canonical.title:
        ratio = fuzzy_ratio(f["title"], canonical.title)
        if ratio < TITLE_ERROR_THRESHOLD:
            diffs.append(FieldDiff(
                field="title", user_value=f["title"], canonical_value=canonical.title,
                severity="error", rationale=f"title similarity {ratio} below threshold",
            ))
        elif ratio < TITLE_WARNING_THRESHOLD:
            diffs.append(FieldDiff(
                field="title", user_value=f["title"], canonical_value=canonical.title,
                severity="warning", rationale=f"title differs cosmetically (similarity {ratio})",
            ))

    diffs.extend(_compare_authors(f.get("author", ""), canonical))

    venue_field = "booktitle" if "booktitle" in f else ("journal" if "journal" in f else None)
    if venue_field and canonical.venue:
        ratio = fuzzy_ratio(f[venue_field], canonical.venue)
        if ratio < VENUE_WARNING_THRESHOLD:
            diffs.append(FieldDiff(
                field=venue_field, user_value=f[venue_field], canonical_value=canonical.venue,
                severity="warning", rationale=f"venue differs (similarity {ratio})",
            ))

    if "doi" in f and canonical.doi:
        if normalize_doi(f["doi"]) != normalize_doi(canonical.doi):
            diffs.append(FieldDiff(
                field="doi", user_value=f["doi"], canonical_value=canonical.doi,
                severity="error", rationale="DOI does not match canonical record",
            ))

    return diffs


def _compare_authors(user_author: str, canonical: CanonicalRecord) -> list[FieldDiff]:
    if not user_author or not canonical.authors:
        return []

    user_list = _parse_author_field(user_author)
    canonical_list = [(a.family, a.given) for a in canonical.authors]

    if len(user_list) != len(canonical_list):
        return [FieldDiff(
            field="author", user_value=user_author,
            canonical_value=_format_canonical_authors(canonical_list),
            severity="error",
            rationale=f"author count mismatch ({len(user_list)} vs {len(canonical_list)})",
        )]

    diffs: list[FieldDiff] = []
    for i, ((u_fam, u_giv), (c_fam, c_giv)) in enumerate(zip(user_list, canonical_list)):
        if normalize_string(u_fam) != normalize_string(c_fam):
            diffs.append(FieldDiff(
                field="author", user_value=user_author,
                canonical_value=_format_canonical_authors(canonical_list),
                severity="error",
                rationale=f"author position {i+1}: '{u_fam}' != '{c_fam}'",
            ))
            return diffs
        if u_giv and c_giv and not _given_names_compatible(u_giv, c_giv):
            diffs.append(FieldDiff(
                field="author", user_value=u_giv, canonical_value=c_giv,
                severity="info",
                rationale=f"author position {i+1}: given name differs ('{u_giv}' vs '{c_giv}')",
            ))
    return diffs


def _parse_author_field(s: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in s.split(" and "):
        raw = raw.strip()
        if not raw:
            continue
        if "," in raw:
            fam, _, giv = raw.partition(",")
            out.append((fam.strip(), giv.strip()))
        else:
            parts = raw.split()
            if len(parts) == 1:
                out.append((parts[0], ""))
            else:
                out.append((parts[-1], " ".join(parts[:-1])))
    return out


def _format_canonical_authors(pairs: list[tuple[str, str]]) -> str:
    return " and ".join(f"{fam}, {giv}" if giv else fam for fam, giv in pairs)


def _given_names_compatible(a: str, b: str) -> bool:
    """True if a and b are 'compatible' (initial of one matches full of other, or equal)."""
    a_n = normalize_string(a)
    b_n = normalize_string(b)
    if a_n == b_n:
        return True
    a_init = a_n.split(" ")[0][:1] if a_n else ""
    b_init = b_n.split(" ")[0][:1] if b_n else ""
    if a_init and b_init and a_init == b_init:
        return True
    return False


def _paper_url(record: CanonicalRecord) -> str | None:
    if record.doi:
        return f"https://doi.org/{normalize_doi(record.doi)}"
    if record.arxiv_id:
        return f"https://arxiv.org/abs/{record.arxiv_id}"
    return None
