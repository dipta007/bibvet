from pathlib import Path

import pytest

from bibvet.compare import compare_entry
from bibvet.fix import write_fixed_bib
from bibvet.models import (
    Author,
    CanonicalRecord,
    EntryReport,
    FileReport,
    LookupKey,
    UserEntry,
)


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
