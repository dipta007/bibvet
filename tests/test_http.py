import asyncio

import httpx
import pytest

from bibvet.http import HttpClient, TerminalNegative


@pytest.fixture
def fast_client():
    """HttpClient with near-zero backoff for fast tests."""
    return HttpClient(initial_backoff=0.001, max_backoff=0.01, jitter=0.0)


@pytest.mark.asyncio
async def test_200_returns_response(fast_client, respx_mock):
    respx_mock.get("https://example.com/").respond(json={"ok": True})
    async with fast_client:
        resp = await fast_client.get("https://example.com/")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_404_raises_terminal_negative(fast_client, respx_mock):
    respx_mock.get("https://example.com/").respond(404)
    async with fast_client:
        with pytest.raises(TerminalNegative):
            await fast_client.get("https://example.com/")


@pytest.mark.asyncio
async def test_429_retries_then_succeeds(fast_client, respx_mock):
    route = respx_mock.get("https://example.com/")
    route.side_effect = [httpx.Response(429), httpx.Response(429), httpx.Response(200, json={"ok": True})]
    async with fast_client:
        resp = await fast_client.get("https://example.com/")
    assert resp.status_code == 200
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_503_retries(fast_client, respx_mock):
    route = respx_mock.get("https://example.com/")
    route.side_effect = [httpx.Response(503), httpx.Response(200, json={})]
    async with fast_client:
        await fast_client.get("https://example.com/")
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_network_error_retries(fast_client, respx_mock):
    route = respx_mock.get("https://example.com/")
    route.side_effect = [httpx.ConnectError("nope"), httpx.Response(200, json={})]
    async with fast_client:
        await fast_client.get("https://example.com/")
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_honors_retry_after_header(respx_mock):
    client = HttpClient(initial_backoff=10.0, max_backoff=10.0, jitter=0.0)
    route = respx_mock.get("https://example.com/")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={}),
    ]
    async with client:
        await asyncio.wait_for(client.get("https://example.com/"), timeout=1.0)
    assert route.call_count == 2
