from pathlib import Path

from bibvet.models import (
    EntryReport,
    FieldDiff,
    FileReport,
    UserEntry,
)
from bibvet.render.markdown import render_markdown


def _entry(citekey="x", **f):
    return UserEntry(citekey=citekey, entry_type="article", fields=f, source_file=Path("x.bib"), source_line=1)


def test_renders_header_per_file():
    fr = FileReport(path=Path("a.bib"), entries=())
    md = render_markdown([fr])
    assert "## a.bib" in md or "# a.bib" in md


def test_renders_diffs_in_problem_entries():
    diff = FieldDiff(field="year", user_value="2018", canonical_value="2017", severity="error", rationale="r")
    er = EntryReport(
        entry=_entry("bad", title="T"),
        status="fixable",
        canonical=None, sources_consulted=(),
        diffs=(diff,),
        paper_url="https://doi.org/10.1/x",
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    md = render_markdown([fr])
    assert "bad" in md
    assert "2018" in md
    assert "2017" in md
    assert "https://doi.org/10.1/x" in md
