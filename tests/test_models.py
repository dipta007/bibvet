from pathlib import Path

from bibvet.models import (
    Author,
    CanonicalRecord,
    EntryReport,
    FieldDiff,
    FileReport,
    LookupKey,
    UserEntry,
)


def test_user_entry_is_frozen():
    entry = UserEntry(
        citekey="x",
        entry_type="article",
        fields={"title": "T"},
        source_file=Path("x.bib"),
        source_line=1,
    )
    import pytest
    with pytest.raises(Exception):  # FrozenInstanceError
        entry.citekey = "y"  # type: ignore[misc]


def test_lookup_key_kinds():
    LookupKey(kind="doi", value="10.1/abc", extras={})
    LookupKey(kind="arxiv", value="2005.00683", extras={})
    LookupKey(kind="title_query", value="some title", extras={"first_author": "lin", "year": 2020})


def test_canonical_record_minimum_fields():
    rec = CanonicalRecord(
        source="crossref",
        matched_via=LookupKey(kind="doi", value="10.1/abc", extras={}),
        title="T",
        authors=(Author(family="Doe", given="Jane", orcid=None),),
        year=2020,
        venue=None,
        doi=None,
        arxiv_id=None,
        entry_type_hint="journal-article",
        raw={},
    )
    assert rec.title == "T"


def test_entry_report_status_values():
    entry = UserEntry(
        citekey="x", entry_type="article", fields={}, source_file=Path("x.bib"), source_line=1
    )
    for status in ("verified", "fixable", "cross_check_failed", "unverified", "skipped"):
        EntryReport(
            entry=entry,
            status=status,  # type: ignore[arg-type]
            canonical=None,
            sources_consulted=(),
            diffs=(),
            paper_url=None,
            notes=(),
        )


def test_field_diff_severity_values():
    for sev in ("error", "warning", "info"):
        FieldDiff(field="year", user_value="2020", canonical_value="2021", severity=sev, rationale="r")  # type: ignore[arg-type]


def test_file_report_holds_entries():
    fr = FileReport(path=Path("x.bib"), entries=())
    assert fr.entries == ()
