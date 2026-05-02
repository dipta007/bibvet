import json
from pathlib import Path

import pytest
import respx

from bibvet.cache import DiskCache
from bibvet.http import HttpClient
from bibvet.models import LookupKey
from bibvet.sources.semantic_scholar import SemanticScholarSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "semantic_scholar"


@pytest.fixture
def source(tmp_path):
    return SemanticScholarSource(
        http=HttpClient(initial_backoff=0.001, max_backoff=0.01, jitter=0.0),
        cache=DiskCache(tmp_path),
    )


def test_supports_all_key_kinds(source):
    assert source.supports(LookupKey(kind="doi", value="10.1/x"))
    assert source.supports(LookupKey(kind="arxiv", value="1706.03762"))
    assert source.supports(LookupKey(kind="title_query", value="x"))


@pytest.mark.asyncio
async def test_fetch_by_doi(source, respx_mock):
    respx_mock.get(url__startswith="https://api.semanticscholar.org/graph/v1/paper/").respond(
        json=json.loads((FIXTURES / "doi_found.json").read_text())
    )
    async with source.http:
        rec = await source.fetch(LookupKey(kind="doi", value="10.5555/3295222.3295349"))
    assert rec is not None
    assert rec.source == "semantic_scholar"
    assert rec.doi == "10.5555/3295222.3295349"
    assert rec.arxiv_id == "1706.03762"
    assert rec.year == 2017


@pytest.mark.asyncio
async def test_fetch_by_arxiv(source, respx_mock):
    respx_mock.get(url__startswith="https://api.semanticscholar.org/graph/v1/paper/arXiv:").respond(
        json=json.loads((FIXTURES / "doi_found.json").read_text())
    )
    async with source.http:
        rec = await source.fetch(LookupKey(kind="arxiv", value="1706.03762"))
    assert rec is not None
    assert rec.arxiv_id == "1706.03762"


@pytest.mark.asyncio
async def test_fetch_by_title(source, respx_mock):
    respx_mock.get(url__startswith="https://api.semanticscholar.org/graph/v1/paper/search").respond(
        json=json.loads((FIXTURES / "title_match.json").read_text())
    )
    async with source.http:
        rec = await source.fetch(
            LookupKey(kind="title_query", value="attention is all you need", extras={"first_author": "vaswani", "year": 2017})
        )
    assert rec is not None
    assert rec.title == "Attention Is All You Need"


@pytest.mark.asyncio
async def test_fetch_404_returns_none(source, respx_mock):
    respx_mock.get(url__startswith="https://api.semanticscholar.org/graph/v1/paper/").respond(404)
    async with source.http:
        rec = await source.fetch(LookupKey(kind="doi", value="10.1/fake"))
    assert rec is None
