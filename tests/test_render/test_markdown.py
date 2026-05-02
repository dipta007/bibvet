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


def test_paper_url_is_an_autolink():
    er = EntryReport(
        entry=_entry("p", title="T"),
        status="fixable", canonical=None, sources_consulted=(), diffs=(),
        paper_url="https://doi.org/10.5555/3295222.3295349",
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    md = render_markdown([fr])
    # CommonMark autolink: <URL> is rendered as a clickable link in every renderer.
    assert "<https://doi.org/10.5555/3295222.3295349>" in md


def test_doi_diff_value_is_a_clickable_link():
    diff = FieldDiff(
        field="doi",
        user_value="10.1234/fake",
        canonical_value="10.5555/3295222.3295349",
        severity="error",
        rationale="DOI does not match",
    )
    er = EntryReport(
        entry=_entry("p"),
        status="fixable", canonical=None, sources_consulted=(),
        diffs=(diff,), paper_url=None,
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    md = render_markdown([fr])
    # Both the wrong and the canonical DOI should be clickable.
    assert "[`10.1234/fake`](https://doi.org/10.1234/fake)" in md
    assert "[`10.5555/3295222.3295349`](https://doi.org/10.5555/3295222.3295349)" in md


def test_doi_with_url_prefix_is_normalized_in_link_target():
    diff = FieldDiff(
        field="doi",
        user_value="https://doi.org/10.1234/abc",
        canonical_value="10.1234/abc",
        severity="error",
        rationale="r",
    )
    er = EntryReport(
        entry=_entry("p"),
        status="fixable", canonical=None, sources_consulted=(),
        diffs=(diff,), paper_url=None,
    )
    fr = FileReport(path=Path("a.bib"), entries=(er,))
    md = render_markdown([fr])
    # Display preserves the user's exact text, but the link URL is canonical.
    assert "[`https://doi.org/10.1234/abc`](https://doi.org/10.1234/abc)" in md
