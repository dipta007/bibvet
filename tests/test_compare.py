from pathlib import Path

import pytest

from bibvet.compare import NON_PAPER_TYPES, PAPER_TYPES, compare_entry
from bibvet.models import Author, CanonicalRecord, LookupKey, UserEntry


def _entry(citekey="x", entry_type="article", **fields) -> UserEntry:
    return UserEntry(
        citekey=citekey,
        entry_type=entry_type,
        fields=fields,
        source_file=Path("x.bib"),
        source_line=1,
    )


def _record(
    source="crossref",
    title="Attention Is All You Need",
    authors=(("Vaswani", "Ashish"), ("Shazeer", "Noam")),
    year=2017,
    venue="NeurIPS",
    doi="10.5555/3295222.3295349",
    arxiv_id=None,
    type_hint="proceedings-article",
    matched_via_kind="doi",
) -> CanonicalRecord:
    return CanonicalRecord(
        source=source,
        matched_via=LookupKey(kind=matched_via_kind, value="x"),
        title=title,
        authors=tuple(Author(family=f, given=g) for f, g in authors),
        year=year,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        entry_type_hint=type_hint,
        raw={},
    )


# === No matches ===

def test_no_matches_paper_type_is_unverified():
    entry = _entry(entry_type="article", title="Unknown", author="X, Y", year="2020")
    report = compare_entry(entry, [])
    assert report.status == "unverified"


def test_no_matches_book_type_is_skipped():
    entry = _entry(entry_type="book", title="Unknown", author="X, Y", year="2020")
    report = compare_entry(entry, [])
    assert report.status == "skipped"


@pytest.mark.parametrize("typ", list(NON_PAPER_TYPES))
def test_all_non_paper_types_skipped_when_no_match(typ):
    entry = _entry(entry_type=typ, title="X")
    report = compare_entry(entry, [])
    assert report.status == "skipped"


@pytest.mark.parametrize("typ", list(PAPER_TYPES))
def test_all_paper_types_unverified_when_no_match(typ):
    entry = _entry(entry_type=typ, title="X")
    report = compare_entry(entry, [])
    assert report.status == "unverified"


# === Verified ===

def test_perfect_match_is_verified():
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswani, Ashish and Shazeer, Noam",
        year="2017",
        booktitle="NeurIPS",
        doi="10.5555/3295222.3295349",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "verified"
    assert report.diffs == ()


def test_latex_braces_dont_cause_diff():
    entry = _entry(
        entry_type="article",
        title="{BERT}: Pre-training",
        author="Devlin, Jacob",
        year="2019",
        journal="NAACL",
    )
    rec = _record(
        title="BERT: Pre-training",
        authors=(("Devlin", "Jacob"),),
        year=2019,
        venue="NAACL",
        doi="10.18653/v1/N19-1423",
        type_hint="proceedings-article",
    )
    report = compare_entry(entry, [rec])
    assert report.status == "verified"


# === Fixable: errors ===

def test_wrong_year_is_fixable():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2018",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "fixable"
    assert any(d.field == "year" and d.severity == "error" for d in report.diffs)


def test_swapped_authors_is_fixable():
    entry = _entry(
        title="Attention Is All You Need",
        author="Shazeer, Noam and Vaswani, Ashish",
        year="2017",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "fixable"
    assert any(d.field == "author" and d.severity == "error" for d in report.diffs)


def test_missing_author_is_fixable():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "fixable"
    assert any(d.field == "author" and d.severity == "error" for d in report.diffs)


def test_initial_vs_full_first_name_is_info():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, A. and Shazeer, N.",
        year="2017",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "verified"
    assert all(d.severity == "info" for d in report.diffs if d.field == "author")


def test_hallucinated_doi_is_fixable():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
        doi="10.1234/fake",
    )
    title_record = _record(matched_via_kind="title_query")
    report = compare_entry(entry, [title_record])
    assert report.status == "fixable"
    assert any(d.field == "doi" and d.severity == "error" for d in report.diffs)


def test_venue_mismatch_is_warning_not_error():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
        booktitle="ICML",  # wrong venue
    )
    report = compare_entry(entry, [_record(authors=(("Vaswani", "Ashish"),))])
    assert report.status == "verified"
    assert any(d.field == "booktitle" and d.severity == "warning" for d in report.diffs)


# === Cross-check failed ===

def test_doi_resolves_to_different_paper_than_title():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
        doi="10.18653/v1/N19-1423",  # BERT's DOI
    )
    doi_record = _record(
        title="BERT: Pre-training",
        authors=(("Devlin", "Jacob"),),
        year=2019,
        doi="10.18653/v1/N19-1423",
        matched_via_kind="doi",
    )
    title_record = _record(matched_via_kind="title_query")
    report = compare_entry(entry, [doi_record, title_record])
    assert report.status == "cross_check_failed"


def test_doi_and_title_agree_no_cross_check_fail():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
        doi="10.5555/3295222.3295349",
    )
    doi_record = _record(matched_via_kind="doi", authors=(("Vaswani", "Ashish"),))
    title_record = _record(matched_via_kind="title_query", authors=(("Vaswani", "Ashish"),))
    report = compare_entry(entry, [doi_record, title_record])
    assert report.status == "verified"


# === Source preference ===

def test_doi_paper_prefers_crossref_over_s2():
    entry = _entry(
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
    )
    cr = _record(source="crossref", venue="CrossRef Venue")
    s2 = _record(source="semantic_scholar", venue="S2 Venue")
    report = compare_entry(entry, [cr, s2])
    assert report.canonical is not None
    assert report.canonical.source == "crossref"


# === arXiv-only ===

def test_misc_with_arxiv_eprint_verifies():
    entry = _entry(
        entry_type="misc",
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
        eprint="1706.03762",
        archiveprefix="arXiv",
    )
    arxiv_rec = _record(
        source="arxiv",
        authors=(("Vaswani", "Ashish"),),
        venue=None,
        doi=None,
        arxiv_id="1706.03762",
        type_hint="preprint",
        matched_via_kind="arxiv",
    )
    report = compare_entry(entry, [arxiv_rec])
    assert report.status == "verified"


# === Paper URL ===

def test_paper_url_uses_doi_when_present():
    entry = _entry(title="x", author="y", year="2020")
    rec = _record()
    report = compare_entry(entry, [rec])
    assert report.paper_url == "https://doi.org/10.5555/3295222.3295349"


def test_paper_url_uses_arxiv_when_no_doi():
    entry = _entry(entry_type="misc", title="x", author="y", year="2020")
    rec = _record(source="arxiv", doi=None, arxiv_id="1706.03762", type_hint="preprint", matched_via_kind="arxiv")
    report = compare_entry(entry, [rec])
    assert report.paper_url == "https://arxiv.org/abs/1706.03762"


# === Notes for arXiv→published ===

def test_published_version_note_when_user_cites_preprint():
    entry = _entry(
        entry_type="misc",
        title="x", author="y", year="2020",
        eprint="1706.03762",
    )
    arxiv_rec = _record(
        source="arxiv",
        venue=None, doi=None, arxiv_id="1706.03762",
        type_hint="preprint", matched_via_kind="arxiv",
    )
    cr_rec = _record(source="crossref", matched_via_kind="title_query")
    report = compare_entry(entry, [arxiv_rec, cr_rec])
    assert any("published version" in n.lower() for n in report.notes)
