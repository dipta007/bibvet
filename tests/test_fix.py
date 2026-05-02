from pathlib import Path

import pytest

from bibvet.fix import write_fixed_bib
from bibvet.models import (
    Author,
    CanonicalRecord,
    EntryReport,
    FileReport,
    LookupKey,
    UserEntry,
)
from bibvet.parser import parse_bib_file


def _entry(citekey, entry_type="article", **fields):
    return UserEntry(
        citekey=citekey, entry_type=entry_type, fields=fields,
        source_file=Path("x.bib"), source_line=1,
    )


def _verified_report(entry):
    return EntryReport(
        entry=entry, status="verified", canonical=None,
        sources_consulted=(), diffs=(), paper_url=None, notes=(),
    )


def _fixable_report(entry, canonical):
    return EntryReport(
        entry=entry, status="fixable", canonical=canonical,
        sources_consulted=(canonical,), diffs=(),
        paper_url=f"https://doi.org/{canonical.doi}", notes=(),
    )


def _unverified_report(entry):
    return EntryReport(
        entry=entry, status="unverified", canonical=None,
        sources_consulted=(), diffs=(), paper_url=None, notes=(),
    )


def _cc_failed_report(entry):
    return EntryReport(
        entry=entry, status="cross_check_failed", canonical=None,
        sources_consulted=(), diffs=(),
        paper_url=None, notes=("DOI -> X, title -> Y",),
    )


def test_verified_entries_pass_through_unchanged(tmp_path):
    entry = _entry("good", title="Good", author="A, B", year="2020", journal="J")
    fr = FileReport(path=tmp_path / "x.bib", entries=(_verified_report(entry),))
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))
    text = out.read_text()
    assert "@article{good," in text
    assert "Good" in text
    assert "% bibvet:" not in text


def test_fixable_entries_get_canonical_fields(tmp_path):
    entry = _entry(
        "bad", entry_type="inproceedings",
        title="Old Title", author="A, B", year="2020",
    )
    canonical = CanonicalRecord(
        source="crossref",
        matched_via=LookupKey(kind="doi", value="10.1/x"),
        title="Real Title",
        authors=(Author(family="Smith", given="John"),),
        year=2021, venue="Real Venue", doi="10.1/x",
        arxiv_id=None, entry_type_hint="proceedings-article", raw={},
    )
    fr = FileReport(path=tmp_path / "x.bib", entries=(_fixable_report(entry, canonical),))
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))
    text = out.read_text()
    assert "@inproceedings{bad," in text
    assert "Real Title" in text
    assert "10.1/x" in text
    assert "Smith, John" in text
    assert "2021" in text
    assert "Real Venue" in text


def test_unverified_entries_get_comment_marker(tmp_path):
    entry = _entry("ghost", title="Ghost Paper", author="A, B", year="2099")
    fr = FileReport(path=tmp_path / "x.bib", entries=(_unverified_report(entry),))
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))
    text = out.read_text()
    assert "% bibvet: UNVERIFIED" in text
    assert "@article{ghost," in text


def test_cross_check_failed_entries_get_comment_marker(tmp_path):
    entry = _entry("conf", title="X", author="A, B", year="2020")
    fr = FileReport(path=tmp_path / "x.bib", entries=(_cc_failed_report(entry),))
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))
    text = out.read_text()
    assert "% bibvet: CROSS-CHECK FAILED" in text


def test_refuses_overwrite_without_force(tmp_path):
    out = tmp_path / "x.fixed.bib"
    out.write_text("existing")
    fr = FileReport(path=tmp_path / "x.bib", entries=())
    with pytest.raises(FileExistsError):
        write_fixed_bib(fr, out, original_text="", force=False)


def test_force_overwrites(tmp_path):
    out = tmp_path / "x.fixed.bib"
    out.write_text("existing")
    fr = FileReport(path=tmp_path / "x.bib", entries=())
    write_fixed_bib(fr, out, original_text="", force=True)
    assert out.read_text() != "existing"


def _render_input(fr: FileReport) -> str:
    lines = []
    for er in fr.entries:
        e = er.entry
        lines.append(f"@{e.entry_type}{{{e.citekey},")
        for k, v in e.fields.items():
            lines.append(f"  {k} = {{{v}}},")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def _canonical(
    title="Real Title",
    authors=(("Smith", "John"),),
    year=2021,
    venue="Real Venue",
    doi="10.1/x",
    arxiv_id=None,
    source="crossref",
) -> CanonicalRecord:
    return CanonicalRecord(
        source=source,
        matched_via=LookupKey(kind="doi", value=doi or "x"),
        title=title,
        authors=tuple(Author(family=f, given=g) for f, g in authors),
        year=year,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        entry_type_hint="proceedings-article",
        raw={},
    )


# ---------------------------------------------------------------------------
# Round-trip: write fixed bib → parse it back
# ---------------------------------------------------------------------------

def test_round_trip_fixed_bib_is_parseable(tmp_path):
    """Write a fixed bib and verify parse_bib_file can re-read all citekeys."""
    entry = _entry(
        "bad", entry_type="inproceedings",
        title="Old Title", author="A, B", year="2020",
        booktitle="Old Conference",
    )
    canonical = _canonical(
        title="Corrected Title",
        authors=(("Jones", "Alice"),),
        year=2021,
        venue="Real Conference",
        doi="10.1/round",
    )
    fr = FileReport(
        path=tmp_path / "x.bib",
        entries=(_fixable_report(entry, canonical),),
    )
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))

    parsed = parse_bib_file(out)
    assert len(parsed) == 1
    fixed = parsed[0]
    assert fixed.citekey == "bad"
    assert fixed.entry_type == "inproceedings"
    assert fixed.fields.get("title") == "Corrected Title"
    assert fixed.fields.get("doi") == "10.1/round"
    assert fixed.fields.get("year") == "2021"


# ---------------------------------------------------------------------------
# Mixed-status file: order and comment markers
# ---------------------------------------------------------------------------

def test_mixed_status_file_preserves_order_and_marks(tmp_path):
    """Four entries with all four interesting statuses written in order.

    Checks:
    - All four citekeys appear in the output.
    - verified entry has no bibvet comment.
    - fixable entry has canonical fields applied.
    - unverified entry carries '% bibvet: UNVERIFIED'.
    - cross_check_failed entry carries '% bibvet: CROSS-CHECK FAILED'.
    """
    e_verified = _entry("ok", title="Fine Paper", author="A, B", year="2020")
    e_fixable = _entry(
        "fix", entry_type="inproceedings",
        title="Old", author="C, D", year="2019",
    )
    e_unverified = _entry("ghost", title="Ghost", author="E, F", year="2099")
    e_cc = _entry("conf", title="Conflict", author="G, H", year="2021")

    canonical = _canonical(
        title="Fixed Paper",
        authors=(("Doe", "Jane"),),
        year=2020,
        venue="Top Conf",
        doi="10.1/fixed",
    )

    entries = (
        _verified_report(e_verified),
        _fixable_report(e_fixable, canonical),
        _unverified_report(e_unverified),
        _cc_failed_report(e_cc),
    )
    fr = FileReport(path=tmp_path / "x.bib", entries=entries)
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))

    text = out.read_text()

    # All four citekeys present
    for ck in ("ok", "fix", "ghost", "conf"):
        assert ck in text, f"citekey '{ck}' missing from output"

    # Order: entry declarations appear in original order
    pos_ok = text.index("@article{ok,")
    pos_fix = text.index("@inproceedings{fix,")
    pos_ghost = text.index("@article{ghost,")
    pos_conf = text.index("@article{conf,")
    assert pos_ok < pos_fix < pos_ghost < pos_conf, (
        "entries must appear in original order in the fixed file"
    )

    # verified entry has no bibvet comment before it
    ok_pos = text.index("@article{ok,")
    preceding = text[:ok_pos]
    assert "% bibvet:" not in preceding.split("\n")[-3:], (
        "verified entry should not have a bibvet comment"
    )

    # fixable entry has canonical fields
    assert "Fixed Paper" in text
    assert "10.1/fixed" in text

    # unverified comment
    assert "% bibvet: UNVERIFIED" in text

    # cross-check-failed comment
    assert "% bibvet: CROSS-CHECK FAILED" in text


# ---------------------------------------------------------------------------
# @misc entry type is preserved through fix
# ---------------------------------------------------------------------------

def test_misc_with_arxiv_eprint_preserves_misc_type_after_fix(tmp_path):
    """Fixing a @misc entry does not change the entry type to @article.

    The canonical record comes from arXiv (source='arxiv').  After fix,
    the output must start with '@misc{' — user's entry type is always preserved.
    """
    entry = _entry(
        "arxiv2017", entry_type="misc",
        title="Attention Is All You Need",
        author="Vaswani, Ashish",
        year="2017",
        eprint="1706.03762",
        archiveprefix="arXiv",
    )
    canonical = CanonicalRecord(
        source="arxiv",
        matched_via=LookupKey(kind="arxiv", value="1706.03762"),
        title="Attention Is All You Need",
        authors=(Author(family="Vaswani", given="Ashish"),),
        year=2017,
        venue=None,
        doi=None,
        arxiv_id="1706.03762",
        entry_type_hint="preprint",
        raw={},
    )
    fr = FileReport(
        path=tmp_path / "x.bib",
        entries=(_fixable_report(entry, canonical),),
    )
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))

    text = out.read_text()
    assert "@misc{arxiv2017," in text, "entry type must stay @misc after fix"
    assert "@article{" not in text
    assert "@inproceedings{" not in text


# ---------------------------------------------------------------------------
# User-supplied pages field is kept when canonical has none
# ---------------------------------------------------------------------------

def test_fixable_entry_keeps_user_supplied_pages(tmp_path):
    """When canonical has no pages but user supplied them, pages survive the fix.

    REQUIRED_FIELDS['inproceedings'] includes 'pages'.  _rewrite_with_canonical
    falls back to entry.fields[k] when k is not present in canonical values →
    user's pages value is preserved.
    """
    entry = _entry(
        "paper", entry_type="inproceedings",
        title="Old Title",
        author="A, B",
        year="2020",
        booktitle="Old Conf",
        pages="5998--6008",
    )
    # Canonical has no pages field (no venue-supplied page range)
    canonical = CanonicalRecord(
        source="crossref",
        matched_via=LookupKey(kind="doi", value="10.1/paper"),
        title="Correct Title",
        authors=(Author(family="Smith", given="Alice"),),
        year=2021,
        venue="Top Conference",
        doi="10.1/paper",
        arxiv_id=None,
        entry_type_hint="proceedings-article",
        raw={},
    )
    fr = FileReport(
        path=tmp_path / "x.bib",
        entries=(_fixable_report(entry, canonical),),
    )
    out = tmp_path / "x.fixed.bib"
    write_fixed_bib(fr, out, original_text=_render_input(fr))

    text = out.read_text()
    assert "5998--6008" in text, "user-supplied pages must be preserved in fixed output"
    assert "Correct Title" in text
