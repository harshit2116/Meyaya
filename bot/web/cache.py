"""Small process-local cache with shared loads and safe invalidation."""
import asyncio
import time


class AsyncTTLCache:
    def __init__(self, capacity=64):
        self.capacity = capacity
        self.values = {}
        self.pending = {}
        self.revision = 0

    def clear(self):
        self.revision += 1
        self.values.clear()
        self.pending.clear()

    async def get(self, key, loader, ttl):
        entry = self.values.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        task = self.pending.get(key)
        if task is None:
            revision = self.revision
            async def load():
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
