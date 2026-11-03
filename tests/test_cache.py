import asyncio

from hn_browser.cache import TtlCache


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


async def test_cache_loads_once_within_ttl():
    clock = Clock()
    loads = []

    async def loader():
        loads.append(1)
        return "value"

    cache = TtlCache(ttl_seconds=180, clock=clock)

    assert await cache.get(loader) == "value"
    clock.t += 179
    assert await cache.get(loader) == "value"
    assert len(loads) == 1


async def test_cache_reloads_after_ttl():
    clock = Clock()
    loads = []

    async def loader():
        loads.append(1)
        return len(loads)

    cache = TtlCache(ttl_seconds=180, clock=clock)

    assert await cache.get(loader) == 1
    clock.t += 181
    assert await cache.get(loader) == 2


async def test_concurrent_misses_share_a_single_load():
    loads = []

    async def loader():
        loads.append(1)
        await asyncio.sleep(0.01)
        return "v"

    cache = TtlCache(ttl_seconds=60, clock=Clock())

    results = await asyncio.gather(*(cache.get(loader) for _ in range(5)))

    assert results == ["v"] * 5
    assert len(loads) == 1


async def test_failed_load_keeps_serving_stale_value():
    clock = Clock()
    calls = []

    async def loader():
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("upstream down")
        return "fresh"

    cache = TtlCache(ttl_seconds=10, clock=clock)
    await cache.get(loader)
    clock.t += 11

    assert await cache.get(loader) == "fresh"
    assert len(calls) == 2
