from pathlib import Path

from bibvet.models import UserEntry
from bibvet.resolve import resolve_lookup_keys


def _entry(**fields: str) -> UserEntry:
    return UserEntry(
        citekey="test",
        entry_type=fields.pop("_type", "article"),
        fields=fields,
        source_file=Path("x.bib"),
        source_line=1,
    )


def test_doi_field_produces_doi_key():
    keys = resolve_lookup_keys(_entry(doi="10.1234/abc"))
    assert any(k.kind == "doi" and k.value == "10.1234/abc" for k in keys)


def test_doi_url_is_normalized():
    keys = resolve_lookup_keys(_entry(doi="https://doi.org/10.1234/ABC"))
    assert any(k.kind == "doi" and k.value == "10.1234/abc" for k in keys)


def test_eprint_with_arxiv_prefix_produces_arxiv_key():
    keys = resolve_lookup_keys(_entry(eprint="2005.00683", archiveprefix="arXiv"))
    assert any(k.kind == "arxiv" and k.value == "2005.00683" for k in keys)


def test_eprint_with_arxiv_prefix_in_value():
    keys = resolve_lookup_keys(_entry(eprint="arXiv:2005.00683"))
    assert any(k.kind == "arxiv" and k.value == "2005.00683" for k in keys)


def test_title_and_author_produce_title_query():
    keys = resolve_lookup_keys(
        _entry(title="Attention Is All You Need", author="Vaswani, Ashish and Shazeer, Noam", year="2017")
    )
    title_keys = [k for k in keys if k.kind == "title_query"]
    assert len(title_keys) == 1
    assert "attention" in title_keys[0].value.lower()
    assert title_keys[0].extras["first_author"] == "vaswani"
    assert title_keys[0].extras["year"] == 2017


def test_emits_all_available_keys():
    keys = resolve_lookup_keys(
        _entry(
            doi="10.1/abc",
            eprint="2005.00683",
            archiveprefix="arXiv",
            title="A Title",
            author="Doe, Jane",
            year="2020",
        )
    )
    kinds = {k.kind for k in keys}
    assert kinds == {"doi", "arxiv", "title_query"}


def test_no_keys_when_nothing_useful():
    keys = resolve_lookup_keys(_entry(year="2020"))
    assert keys == []


def test_short_title_does_not_produce_query():
    keys = resolve_lookup_keys(_entry(title="A"))
    assert all(k.kind != "title_query" for k in keys)
