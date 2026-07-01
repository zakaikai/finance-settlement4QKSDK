"""FK name-to-ID resolver with async-safe caching.

Resolves human-readable names (channel name, publisher name, etc.) to
database primary keys. Results are cached per resolver instance to avoid
repeated queries within a batch. Each instance is isolated — tests can
create their own instance for parallel-safe isolation.

Usage:
    # Context manager (auto-reset on exit)
    async with FKResolver() as r:
        ch_id = await r.resolve(db, ChannelCategory, "channel_name", name, "cats")

    # Manual lifecycle
    r = FKResolver()
    await r.reset()
    ch_id = await r.resolve(...)

    # Module-level default (legacy, kept for backward compat)
    await fk_resolver.reset()
    await fk_resolver.resolve(...)
"""
import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FKResolver:
    """Isolated name→ID cache. One instance per batch."""
    __slots__ = ("_cache", "_lock")

    def __init__(self):
        self._cache: dict[tuple, int | None] = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "FKResolver":
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def resolve(
        self,
        session: AsyncSession,
        model_class,
        name_field: str,
        name_value: str | None,
        cache_key: str,
    ) -> int | None:
        if name_value is None:
            return None
        key = (cache_key, name_value)
        async with self._lock:
            if key not in self._cache:
                tbl = model_class.__table__
                col = getattr(tbl.c, name_field)
                row = (await session.execute(select(tbl.c).where(col == name_value))).one_or_none()
                self._cache[key] = row[0] if row is not None else None
            return self._cache[key]

    async def resolve_raw(
        self,
        key: tuple,
        query: Callable[[], Coroutine[Any, Any, Any]],
    ) -> int | None:
        async with self._lock:
            if key not in self._cache:
                result = await query()
                self._cache[key] = result
            return self._cache[key]

    async def cache_set(self, key: tuple, pk: int) -> None:
        async with self._lock:
            self._cache[key] = pk

    async def cache_get(self, key: tuple) -> int | None:
        async with self._lock:
            return self._cache.get(key)

    async def reset(self) -> None:
        async with self._lock:
            self._cache.clear()


# Module-level default instance for backward compatibility.
_default = FKResolver()

# Delegating module-level functions
async def resolve(session, model_class, name_field, name_value, cache_key) -> int | None:
    return await _default.resolve(session, model_class, name_field, name_value, cache_key)

async def resolve_raw(key, query) -> int | None:
    return await _default.resolve_raw(key, query)

async def cache_set(key, pk) -> None:
    await _default.cache_set(key, pk)

async def cache_get(key) -> int | None:
    return await _default.cache_get(key)

async def reset() -> None:
    await _default.reset()
