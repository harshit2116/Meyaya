"""Small process-local cache with shared loads and safe invalidation."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import time
from typing import Any


class AsyncTTLCache:
    def __init__(self, capacity: int = 64) -> None:
        self.capacity = capacity
        self.values: dict[Any, tuple[float, Any]] = {}
        self.pending: dict[Any, asyncio.Task[Any]] = {}
        self.revision = 0

    def clear(self) -> None:
        self.revision += 1
        self.values.clear()
        self.pending.clear()

    async def get[T](self, key: Any, loader: Callable[[], Awaitable[T]], ttl: float) -> T:
        entry = self.values.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]  # type: ignore[no-any-return]
        task = self.pending.get(key)
        if task is None:
            revision = self.revision

            async def load() -> T:
                try:
                    value = await loader()
                    if revision == self.revision:
                        if len(self.values) >= self.capacity:
                            self.values.pop(next(iter(self.values)))
                        self.values[key] = (time.monotonic() + ttl, value)
                    return value
                finally:
                    if self.pending.get(key) is asyncio.current_task():
                        self.pending.pop(key, None)

            task = self.pending[key] = asyncio.create_task(load())
        return await asyncio.shield(task)
