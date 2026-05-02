import json
from pathlib import Path

import pytest

from bibvet.cache import DiskCache
from bibvet.http import HttpClient
from bibvet.models import LookupKey
from bibvet.sources.crossref import CrossRefSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "crossref"


@pytest.fixture
def source(tmp_path):
    return CrossRefSource(
        http=HttpClient(initial_backoff=0.001, max_backoff=0.01, jitter=0.0),
        cache=DiskCache(tmp_path),
    )


def test_supports_doi_and_title(source):
    assert source.supports(LookupKey(kind="doi", value="10.1/x"))
    assert source.supports(LookupKey(kind="title_query", value="x"))
    assert not source.supports(LookupKey(kind="arxiv", value="x"))


@pytest.mark.asyncio
async def test_fetch_by_doi(source, respx_mock):
    respx_mock.get(url__startswith="https://api.crossref.org/works/").respond(
        json=json.loads((FIXTURES / "doi_found.json").read_text())
    )
    async with source.http:
        rec = await source.fetch(LookupKey(kind="doi", value="10.5555/3295222.3295349"))
    assert rec is not None
    assert rec.source == "crossref"
    assert rec.doi == "10.5555/3295222.3295349"
    assert rec.year == 2017
    assert rec.authors[0].family == "Vaswani"
    assert rec.entry_type_hint == "proceedings-article"


@pytest.mark.asyncio
async def test_fetch_by_doi_404_returns_none(source, respx_mock):
    respx_mock.get(url__startswith="https://api.crossref.org/works/").respond(404)
    async with source.http:
        rec = await source.fetch(LookupKey(kind="doi", value="10.1/fake"))
    assert rec is None


@pytest.mark.asyncio
async def test_fetch_by_title(source, respx_mock):
    respx_mock.get(url__startswith="https://api.crossref.org/works").respond(
        json=json.loads((FIXTURES / "title_match.json").read_text())
    )
    async with source.http:
        rec = await source.fetch(
            LookupKey(kind="title_query", value="attention is all you need", extras={"first_author": "vaswani", "year": 2017})
        )
    assert rec is not None
    assert rec.title == "Attention Is All You Need"
