"""Tool response cache on top of store.cache_get/cache_set (no-op without a DB)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from trip_planner import store


async def cached(
    namespace: str,
    args: dict,
    fetch: Callable[[], Awaitable[Any]],
    ttl_hours: float | None = None,
) -> Any:
    """Return the cached JSON value for (namespace, args), or fetch, store and return it."""
    raw = namespace + json.dumps(args, sort_keys=True, default=str)
    key = hashlib.sha256(raw.encode()).hexdigest()
    value = await store.cache_get(key)
    if value is None:
        value = await fetch()
        await store.cache_set(key, value, ttl_hours)
    return value
