"""Realistic LLM-hallucination scenarios for compare_entry.

Each test mimics a known failure mode when LLMs generate citations: misspelled
author names, slightly wrong titles, completely invented papers, etc.  The
expectations are derived from actual fuzzy_ratio thresholds and normalization
rules in compare.py / normalize.py.
"""
from pathlib import Path

from bibvet.compare import compare_entry
from bibvet.models import Author, CanonicalRecord, LookupKey, UserEntry
from bibvet.normalize import fuzzy_ratio


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


# ---------------------------------------------------------------------------
# 1. Misspelled author last name
# ---------------------------------------------------------------------------

def test_misspelled_author_lastname_caught_as_error():
    """LLM hallucination: 'Vaswini' instead of 'Vaswani' — a one-letter transposition.

    normalize_string differs for the two last names, so _compare_authors must
    emit an error-severity FieldDiff, making the status fixable.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswini, Ashish and Shazeer, Noam",
        year="2017",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "fixable"
    author_diffs = [d for d in report.diffs if d.field == "author"]
    assert any(d.severity == "error" for d in author_diffs), (
        f"expected an error-severity author diff; got {report.diffs}"
    )


# ---------------------------------------------------------------------------
# 2. Misspelled title (one letter dropped) — actually falls into warning tier
# ---------------------------------------------------------------------------

def test_misspelled_title_one_letter_is_warning():
    """LLM hallucination: 'Atntion Is All You Need' (two letters dropped).

    fuzzy_ratio("Atntion Is All You Need", "Attention Is All You Need") == 95,
    which is in [92, 97) → warning, not error.  Status stays verified.

    Note: a single-letter drop ('Atention') yields ratio 97 which is >= the
    warning threshold and produces *no diff at all*.  Two letters dropped is
    the minimal change that crosses into the warning band.
    """
    user_title = "Atntion Is All You Need"
    canonical_title = "Attention Is All You Need"
    ratio = fuzzy_ratio(user_title, canonical_title)
    assert 92 <= ratio < 97, (
        f"precondition: expected warning-tier ratio in [92, 97); got {ratio}"
    )

    entry = _entry(
        entry_type="inproceedings",
        title=user_title,
        author="Vaswani, Ashish and Shazeer, Noam",
        year="2017",
    )
    report = compare_entry(entry, [_record()])
    assert report.status == "verified", (
        "warning-only diffs should not change status to fixable"
    )
    title_diffs = [d for d in report.diffs if d.field == "title"]
    assert any(d.severity == "warning" for d in title_diffs), (
        f"expected a warning-severity title diff; got {report.diffs}"
    )


# ---------------------------------------------------------------------------
# 3. Completely fabricated paper — no sources return a match
# ---------------------------------------------------------------------------

def test_completely_fabricated_paper_yields_unverified():
    """LLM hallucination: a plausible-sounding but entirely invented paper title.

    When no canonical records are returned (empty list), a paper-type entry
    must be classified as unverified.
    """
    entry = _entry(
        entry_type="article",
        title="Quantum Decoherence in Distributed Systems",
        author="Feynman, Richard",
        year="2022",
    )
    report = compare_entry(entry, [])
    assert report.status == "unverified"
    assert report.canonical is None


# ---------------------------------------------------------------------------
# 4. Real-sounding author, fake paper — no canonical record returned
# ---------------------------------------------------------------------------

def test_real_authors_fake_paper_yields_unverified_when_no_match():
    """LLM hallucination: famous author attached to an invented paper.

    'Hinton, Geoffrey' + 'Synthetic Cortex Architectures' — sounds credible
    but no lookup succeeds.  Must be unverified.
    """
    entry = _entry(
        entry_type="article",
        title="Synthetic Cortex Architectures",
        author="Hinton, Geoffrey",
        year="2030",
    )
    report = compare_entry(entry, [])
    assert report.status == "unverified"
    assert report.canonical is None


# ---------------------------------------------------------------------------
# 5. Correct paper, typo in given name only — first initial matches → no diff
# ---------------------------------------------------------------------------

def test_correct_paper_with_typo_in_first_name_only_is_verified():
    """LLM hallucination: 'Ashis' instead of 'Ashish' — one letter short.

    _given_names_compatible checks whether the first initial of the normalised
    given name matches.  Both 'ashis' and 'ashish' start with 'a', so they are
    considered compatible → no author diff at all → status verified.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswani, Ashis and Shazeer, Noam",
        year="2017",
    )
    report = compare_entry(
        entry, [_record(authors=(("Vaswani", "Ashish"), ("Shazeer", "Noam")))]
    )
    assert report.status == "verified"
    author_diffs = [d for d in report.diffs if d.field == "author"]
    assert all(d.severity != "error" for d in author_diffs), (
        "first-initial-compatible given name should not cause an error"
    )


# ---------------------------------------------------------------------------
# 6. Extra fake co-author — author count mismatch → fixable
# ---------------------------------------------------------------------------

def test_real_paper_with_extra_fake_coauthor_yields_fixable():
    """LLM hallucination: adding a non-existent third author.

    User has [Vaswani, Shazeer, FakeAuthor]; canonical has [Vaswani, Shazeer].
    Author count mismatch (3 vs 2) → error → fixable.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswani, Ashish and Shazeer, Noam and FakeAuthor, Joe",
        year="2017",
    )
    report = compare_entry(
        entry, [_record(authors=(("Vaswani", "Ashish"), ("Shazeer", "Noam")))]
    )
    assert report.status == "fixable"
    assert any(
        d.field == "author" and d.severity == "error" for d in report.diffs
    )


# ---------------------------------------------------------------------------
# 7. Partial DOI match — same prefix, different suffix → error → fixable
# ---------------------------------------------------------------------------

def test_partial_doi_match_treated_as_mismatch():
    """LLM hallucination: DOI with the right publisher prefix but wrong suffix.

    normalize_doi('10.1109/ICCV.1234567') != normalize_doi('10.1109/ICCV.7654321'),
    so a DOI error diff is emitted → fixable.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswani, Ashish and Shazeer, Noam",
        year="2017",
        doi="10.1109/ICCV.1234567",
    )
    rec = _record(doi="10.1109/ICCV.7654321")
    report = compare_entry(entry, [rec])
    assert report.status == "fixable"
    assert any(d.field == "doi" and d.severity == "error" for d in report.diffs)


# ---------------------------------------------------------------------------
# 8. Swapped first two authors → fixable
# ---------------------------------------------------------------------------

def test_swapped_first_two_authors_yields_fixable():
    """LLM hallucination: reversing the first two authors.

    Author at position 1 in user is 'Shazeer' but canonical has 'Vaswani' →
    last-name mismatch at position 1 → error → fixable.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Shazeer, Noam and Vaswani, Ashish",
        year="2017",
    )
    report = compare_entry(
        entry, [_record(authors=(("Vaswani", "Ashish"), ("Shazeer", "Noam")))]
    )
    assert report.status == "fixable"
    assert any(d.field == "author" and d.severity == "error" for d in report.diffs)


# ---------------------------------------------------------------------------
# 9. Year off by one → fixable
# ---------------------------------------------------------------------------

def test_year_off_by_one_yields_fixable():
    """LLM hallucination: citing arXiv year (2018) instead of proceedings year (2017).

    Year mismatch is exact equality check: '2018' != '2017' → error → fixable.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswani, Ashish and Shazeer, Noam",
        year="2018",
    )
    report = compare_entry(
        entry, [_record(year=2017)]
    )
    assert report.status == "fixable"
    assert any(d.field == "year" and d.severity == "error" for d in report.diffs)


# ---------------------------------------------------------------------------
# 10. Unicode-accented author name matches ASCII via NFKC + initial check
# ---------------------------------------------------------------------------

def test_unicode_accented_author_matches_ascii_author():
    """LLM hallucination guard: canonical has accented 'Yóshua', user has 'Yoshua'.

    normalize_string applies NFKC + lowercase.  'Yóshua' → 'yoshua' after
    stripping the accent via NFKC ('ó' → 'o' + combining, then normalized,
    actually 'ó' remains 'o' after NFKC+casefold).  In practice the first
    initials both normalise to 'y', so _given_names_compatible returns True →
    no author error → verified.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Deep Learning",
        author="Bengio, Yoshua",
        year="2015",
    )
    rec = _record(
        title="Deep Learning",
        authors=(("Bengio", "Yóshua"),),
        year=2015,
        venue="MIT Press",
        doi="10.1/deep",
    )
    report = compare_entry(entry, [rec])
    # Last names are identical; given initials both 'y' → compatible → no error
    assert report.status == "verified"
    author_diffs = [d for d in report.diffs if d.field == "author"]
    assert all(d.severity != "error" for d in author_diffs)


# ---------------------------------------------------------------------------
# 11. Same first author across three papers — compare picks the right one
# ---------------------------------------------------------------------------

def test_three_real_papers_same_first_author_disambiguated_by_year():
    """LLM hallucination guard: multiple Vaswani papers found via DOI lookup;
    reconcile() picks crossref over semantic_scholar.

    Simulates a scenario where the same first author has several papers and all
    three lookup results arrive with matched_via=doi (e.g. multiple DOI hits
    from different sources for the same query).  reconcile() prefers crossref →
    semantic_scholar → others, so the crossref record with year=2017 is chosen.
    The user year '2017' matches → no year error → verified.
    """
    entry = _entry(
        entry_type="inproceedings",
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
    )
    # All three records come from doi-kind lookups (no cross-check is triggered)
    rec_right = _record(
        source="crossref",
        title="Attention Is All You Need",
        authors=(("Vaswani", "Ashish"),),
        year=2017,
        doi="10.5555/3295222.3295349",
        matched_via_kind="doi",
    )
    rec_s2_old = _record(
        source="semantic_scholar",
        title="Attention Is All You Need",
        authors=(("Vaswani", "Ashish"),),
        year=2015,
        doi="10.5555/3295222.3295349",
        matched_via_kind="doi",
    )
    rec_s2_new = _record(
        source="semantic_scholar",
        title="Attention Is All You Need",
        authors=(("Vaswani", "Ashish"),),
        year=2018,
        doi="10.5555/3295222.3295349",
        matched_via_kind="doi",
    )
    # reconcile: crossref wins → year=2017 → user year '2017' matches → verified
    report = compare_entry(entry, [rec_right, rec_s2_old, rec_s2_new])
    assert report.canonical is not None
    assert report.canonical.source == "crossref"
    assert report.canonical.year == 2017
    # Year matches the crossref record → no year error
    assert not any(d.field == "year" and d.severity == "error" for d in report.diffs)
