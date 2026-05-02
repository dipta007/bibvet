import asyncio
import time

import pytest

from bibvet.ratelimit import RateLimiter


@pytest.mark.asyncio
async def test_zero_interval_is_no_op():
    rl = RateLimiter(0.0)
    start = time.monotonic()
    for _ in range(5):
        await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_serial_acquires_respect_interval():
    rl = RateLimiter(0.05)
    start = time.monotonic()
    for _ in range(3):
        await rl.acquire()
    elapsed = time.monotonic() - start
    # 3 acquires with 50ms between -> minimum ~100ms (first is free)
    assert elapsed >= 0.09


@pytest.mark.asyncio
async def test_concurrent_acquires_serialize():
    rl = RateLimiter(0.05)
    completion_times: list[float] = []

    async def acquirer():
        await rl.acquire()
        completion_times.append(time.monotonic())

    start = time.monotonic()
    await asyncio.gather(*(acquirer() for _ in range(4)))
    elapsed = time.monotonic() - start
    # 4 acquires, 50ms gap between → at least 150ms total
    assert elapsed >= 0.14
    # And they should be roughly evenly spaced
    completion_times.sort()
    gaps = [completion_times[i + 1] - completion_times[i] for i in range(len(completion_times) - 1)]
    assert all(g >= 0.04 for g in gaps)
