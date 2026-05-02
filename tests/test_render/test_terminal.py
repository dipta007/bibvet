from io import StringIO
from pathlib import Path

from rich.console import Console

from bibvet.models import (
    CanonicalRecord,
    EntryReport,
    FieldDiff,
    FileReport,
    LookupKey,
    UserEntry,
)
from bibvet.render.terminal import render_terminal


def _entry(citekey="x", entry_type="article", **f):
    return UserEntry(citekey=citekey, entry_type=entry_type, fields=f, source_file=Path("x.bib"), source_line=1)


def _capture(file_reports, **kwargs):
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    render_terminal(file_reports, console=console, **kwargs)
    return buf.getvalue()


def test_summary_line_counts():
    fr = FileReport(path=Path("a.bib"), entries=(
        EntryReport(entry=_entry("x"), status="verified", canonical=None, sources_consulted=(), diffs=(), paper_url=None),
        EntryReport(entry=_entry("y"), status="fixable", canonical=None, sources_consulted=(), diffs=(), paper_url=None),
        EntryReport(entry=_entry("z"), status="unverified", canonical=None, sources_consulted=(), diffs=(), paper_url=None),
    ))
    out = _capture([fr])
    assert "3 entries" in out
    assert "1" in out
    assert "fixable" in out.lower() or "❌" in out
    assert "unverified" in out.lower() or "❓" in out


def test_problems_shown_inline():
    diff = FieldDiff(field="year", user_value="2018", canonical_value="2017", severity="error", rationale="r")
    er = EntryReport(
        entry=_entry("bad", title="T"),
        status="fixable",
        canonical=CanonicalRecord(
            source="crossref", matched_via=LookupKey(kind="doi", value="x"),
            title="T", authors=(), year=2017, venue=None, doi="10.1/x", arxiv_id=None,
            entry_type_hint="article", raw={},
        ),
        sources_consulted=(),
        diffs=(diff,),
        paper_url="https://doi.org/10.1/x",
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    out = _capture([fr])
    assert "bad" in out
    assert "year" in out
    assert "2018" in out
    assert "2017" in out


def test_verified_silent_by_default():
    er = EntryReport(
        entry=_entry("good", title="T"),
        status="verified", canonical=None,
        sources_consulted=(), diffs=(), paper_url=None,
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    out = _capture([fr])
    assert "good" not in out


def test_verified_shown_with_verbose():
    er = EntryReport(
        entry=_entry("good", title="T"),
        status="verified", canonical=None,
        sources_consulted=(), diffs=(), paper_url=None,
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    out = _capture([fr], verbose=True)
    assert "good" in out


def test_combined_total_when_multiple_files():
    fr1 = FileReport(path=Path("a.bib"), entries=(
        EntryReport(entry=_entry("x"), status="verified", canonical=None, sources_consulted=(), diffs=(), paper_url=None),
    ))
    fr2 = FileReport(path=Path("b.bib"), entries=(
        EntryReport(entry=_entry("y"), status="verified", canonical=None, sources_consulted=(), diffs=(), paper_url=None),
    ))
    out = _capture([fr1, fr2])
    assert "total" in out.lower() or "2 entries" in out
