"""Tiny in-process TTL cache for async endpoint results.

Why not ``functools.lru_cache``: it does not expire entries and is not
async-aware. Why not ``cachetools.TTLCache``: avoiding the extra
dependency for ~30 lines of code.

Design constraints:
- Single-process only (we have one uvicorn worker in dev/QA). A
  distributed deployment would swap this for Redis.
- Absolute expiry via ``time.monotonic`` — not subject to wall-clock jumps.
- Size-bounded so a pathological test input cannot OOM the process. When
  the bound is hit we drop the oldest entry (insertion order via dict).
- Cache key is the tuple of kwargs passed to the wrapped coroutine; the
  caller is responsible for not mixing positional args when decorating.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncTTLCache:
    """Lock-guarded TTL cache keyed by hashable tuples."""

    __slots__ = ("_ttl", "_max_entries", "_store", "_lock")

    def __init__(self, *, ttl_seconds: float, max_entries: int = 128) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        self._store.clear()

    async def get_or_compute(self, key: tuple[Any, ...], compute: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        async with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                expires_at, value = entry
                if expires_at > now:
                    # Move to end so LRU eviction drops truly stale entries first.
                    self._store.move_to_end(key)
                    return value
                # Expired — drop and recompute below.
                del self._store[key]

        # Compute outside the lock so concurrent requests for different keys
        # do not serialize on each other. Callers for the *same* key may
        # redundantly compute; that trade-off is fine for short TTLs.
        value = await compute()

        async with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)
        return value


def _hashable_or_id(value: Any) -> Any:
    """Return ``value`` if it is hashable, otherwise a marker based on its id().

    FastAPI passes a Request object into every route; it is unhashable and
    per-request unique, which would defeat caching. We want to key on the
    semantically meaningful query-params only, so we ignore values that are
    not hashable.
    """
    try:
        hash(value)
        return value
    except TypeError:
        return None  # explicitly drop unhashable inputs from the key


def cache_ttl(
    *, seconds: float, max_entries: int = 128, include: tuple[str, ...] | None = None
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator: cache the coroutine's return value by kwargs for TTL seconds.

    Parameters:
        seconds: TTL per cache entry.
        max_entries: Upper bound on cached entries (LRU eviction past this).
        include: If provided, only these kwargs contribute to the cache key.
                 Otherwise every hashable kwarg contributes.

    The ``Request`` argument (and any other unhashable input) is dropped from
    the key automatically so FastAPI's per-request dependency injection does
    not defeat the cache.
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        cache = AsyncTTLCache(ttl_seconds=seconds, max_entries=max_entries)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if include is not None:
                key_items = tuple((k, kwargs.get(k)) for k in include)
            else:
                key_items = tuple(
                    sorted(
                        (k, _hashable_or_id(v))
                        for k, v in kwargs.items()
                        if _hashable_or_id(v) is not None
                    )
                )
            return await cache.get_or_compute(key_items, lambda: func(*args, **kwargs))

        wrapper.cache = cache  # type: ignore[attr-defined]  # exposed for tests/invalidation
        return wrapper

    return decorator
