from pathlib import Path

import pytest

from bibvet.parser import ParseError, parse_bib_file

FIXTURES = Path(__file__).parent / "fixtures" / "bib"


def test_parses_clean_bib():
    entries = parse_bib_file(FIXTURES / "clean.bib")
    assert len(entries) == 2
    assert entries[0].citekey == "vaswani2017attention"
    assert entries[0].entry_type == "inproceedings"
    assert entries[0].fields["year"] == "2017"
    assert "Vaswani" in entries[0].fields["author"]


def test_preserves_latex_in_fields():
    entries = parse_bib_file(FIXTURES / "clean.bib")
    bert = next(e for e in entries if e.citekey == "devlin2019bert")
    assert "{BERT}" in bert.fields["title"]


def test_parses_mixed_entry_types():
    entries = parse_bib_file(FIXTURES / "mixed_types.bib")
    types = {e.entry_type for e in entries}
    assert types == {"article", "book", "misc", "phdthesis"}


def test_records_source_file_and_line():
    entries = parse_bib_file(FIXTURES / "clean.bib")
    assert entries[0].source_file == FIXTURES / "clean.bib"
    assert entries[0].source_line >= 1


def test_malformed_strict_raises():
    with pytest.raises(ParseError) as ei:
        parse_bib_file(FIXTURES / "malformed.bib", lenient=False)
    assert "malformed.bib" in str(ei.value)


def test_malformed_lenient_skips_bad_entry(caplog):
    entries = parse_bib_file(FIXTURES / "malformed.bib", lenient=True)
    citekeys = {e.citekey for e in entries}
    assert "good1" in citekeys
    assert "good2" in citekeys
    assert "broken" not in citekeys


def test_file_not_found_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        parse_bib_file(FIXTURES / "does_not_exist.bib")


def test_empty_file_returns_empty_list(tmp_path):
    f = tmp_path / "empty.bib"
    f.write_text("")
    assert parse_bib_file(f) == []
