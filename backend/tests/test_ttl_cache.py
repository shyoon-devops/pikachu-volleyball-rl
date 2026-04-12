"""Unit tests for backend.app.util.ttl_cache.

Covers:
  * hit / miss behavior
  * TTL expiry forces recompute
  * LRU eviction at ``max_entries``
  * unhashable kwargs do not defeat caching
  * concurrent computes for different keys run in parallel
"""

from __future__ import annotations

import pytest

from backend.app.util.ttl_cache import AsyncTTLCache, cache_ttl


@pytest.mark.asyncio
async def test_returns_cached_value_within_ttl():
    cache = AsyncTTLCache(ttl_seconds=60)
    call_count = 0

    async def compute():
        nonlocal call_count
        call_count += 1
        return "value"

    v1 = await cache.get_or_compute(("k",), compute)
    v2 = await cache.get_or_compute(("k",), compute)
    assert v1 == v2 == "value"
    assert call_count == 1  # second call hit the cache


@pytest.mark.asyncio
async def test_distinct_keys_are_cached_independently():
    cache = AsyncTTLCache(ttl_seconds=60)
    calls: list[tuple] = []

    async def compute_a():
        calls.append(("a",))
        return "A"

    async def compute_b():
        calls.append(("b",))
        return "B"

    assert await cache.get_or_compute(("a",), compute_a) == "A"
    assert await cache.get_or_compute(("b",), compute_b) == "B"
    assert await cache.get_or_compute(("a",), compute_a) == "A"
    # 2 distinct keys → exactly 2 computes
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_ttl_expiry_triggers_recompute(monkeypatch):
    import backend.app.util.ttl_cache as mod

    t = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: t[0])
    cache = AsyncTTLCache(ttl_seconds=5.0)

    counter = {"n": 0}

    async def compute():
        counter["n"] += 1
        return counter["n"]

    v1 = await cache.get_or_compute(("k",), compute)
    # Still inside TTL
    t[0] += 4.0
    v2 = await cache.get_or_compute(("k",), compute)
    # Past TTL — value must be recomputed
    t[0] += 2.0
    v3 = await cache.get_or_compute(("k",), compute)

    assert v1 == 1
    assert v2 == 1  # cached
    assert v3 == 2  # expired then recomputed


@pytest.mark.asyncio
async def test_lru_eviction_at_max_entries():
    cache = AsyncTTLCache(ttl_seconds=60, max_entries=2)

    async def const(v):
        async def _compute():
            return v

        return _compute

    await cache.get_or_compute(("a",), await const("A"))
    await cache.get_or_compute(("b",), await const("B"))
    # Touch a to mark it most-recently-used
    await cache.get_or_compute(("a",), await const("A"))
    # Insert c — should evict b (least-recently-used)
    await cache.get_or_compute(("c",), await const("C"))

    assert ("a",) in cache._store
    assert ("c",) in cache._store
    assert ("b",) not in cache._store


@pytest.mark.asyncio
async def test_raises_on_invalid_ttl():
    with pytest.raises(ValueError):
        AsyncTTLCache(ttl_seconds=0)
    with pytest.raises(ValueError):
        AsyncTTLCache(ttl_seconds=-1)
    with pytest.raises(ValueError):
        AsyncTTLCache(ttl_seconds=5, max_entries=0)


@pytest.mark.asyncio
async def test_exception_is_not_cached():
    cache = AsyncTTLCache(ttl_seconds=60)
    attempts = {"n": 0}

    async def compute():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("boom")
        return "ok"

    with pytest.raises(RuntimeError):
        await cache.get_or_compute(("k",), compute)
    # Second call must re-attempt (exception wasn't memoized)
    assert await cache.get_or_compute(("k",), compute) == "ok"
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_decorator_caches_by_included_kwargs():
    calls: list[dict] = []

    @cache_ttl(seconds=60, include=("page", "limit"))
    async def list_things(request, page: int = 1, limit: int = 20):
        calls.append({"page": page, "limit": limit, "req": request})
        return {"page": page, "limit": limit}

    # Different request objects with identical paging kwargs must hit cache
    assert await list_things(object(), page=1, limit=20) == {"page": 1, "limit": 20}
    assert await list_things(object(), page=1, limit=20) == {"page": 1, "limit": 20}
    assert len(calls) == 1

    # Different paging → distinct cache entry
    assert await list_things(object(), page=2, limit=20) == {"page": 2, "limit": 20}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_decorator_drops_unhashable_kwargs_from_key():
    """Without an ``include`` list, unhashable inputs must be ignored."""
    calls = {"n": 0}

    @cache_ttl(seconds=60)
    async def f(*, opts: dict | None = None, page: int = 1):
        calls["n"] += 1
        return page

    await f(opts={"nested": [1, 2]}, page=1)
    await f(opts={"nested": [1, 2]}, page=1)
    # opts is unhashable and dropped — both calls key on (page=1) only
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_decorator_exposes_cache_for_invalidation():
    @cache_ttl(seconds=60)
    async def f(*, key: int = 0):
        return key

    await f(key=1)
    assert hasattr(f, "cache")
    f.cache.clear()
    assert len(f.cache._store) == 0
