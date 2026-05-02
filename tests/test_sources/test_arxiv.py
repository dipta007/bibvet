from pathlib import Path

import pytest

from bibvet.cache import DiskCache
from bibvet.http import HttpClient
from bibvet.models import LookupKey
from bibvet.sources.arxiv import ArxivSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "arxiv"


@pytest.fixture
def source(tmp_path):
    return ArxivSource(
        http=HttpClient(initial_backoff=0.001, max_backoff=0.01, jitter=0.0),
        cache=DiskCache(tmp_path),
    )


def test_supports_arxiv_keys(source):
    assert source.supports(LookupKey(kind="arxiv", value="1706.03762"))
    # arXiv title-search is intentionally not used: weaker than S2/CrossRef
    # and aggressively rate-limited.
    assert not source.supports(LookupKey(kind="title_query", value="x"))
    assert not source.supports(LookupKey(kind="doi", value="10.1/x"))


@pytest.mark.asyncio
async def test_fetch_by_arxiv_id(source, respx_mock):
    respx_mock.get(url__startswith="http://export.arxiv.org/api/query").respond(
        content=(FIXTURES / "found.xml").read_text()
    )
    async with source.http:
        rec = await source.fetch(LookupKey(kind="arxiv", value="1706.03762"))
    assert rec is not None
    assert rec.source == "arxiv"
    assert rec.title == "Attention Is All You Need"
    assert rec.year == 2017
    assert rec.arxiv_id == "1706.03762"
    assert rec.authors[0].family == "Vaswani"


@pytest.mark.asyncio
async def test_fetch_not_found_returns_none(source, respx_mock):
    respx_mock.get(url__startswith="http://export.arxiv.org/api/query").respond(
        content=(FIXTURES / "not_found.xml").read_text()
    )
    async with source.http:
        rec = await source.fetch(LookupKey(kind="arxiv", value="0000.00000"))
    assert rec is None


@pytest.mark.asyncio
async def test_fetch_uses_cache(source, respx_mock):
    route = respx_mock.get(url__startswith="http://export.arxiv.org/api/query").respond(
        content=(FIXTURES / "found.xml").read_text()
    )
    async with source.http:
        await source.fetch(LookupKey(kind="arxiv", value="1706.03762"))
        await source.fetch(LookupKey(kind="arxiv", value="1706.03762"))
    assert route.call_count == 1
