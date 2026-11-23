"""Short, fail-soft budgets for optional read-only chat context."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import time

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class OptionalContext:
    def __init__(self, timeout: float = 2.0, cooldown: float = 15.0) -> None:
        self.timeout, self.cooldown = timeout, cooldown
        self._retry_at: dict[str, float] = {}

    async def read[T](self, source: str, factory: Callable[[], Awaitable[list[T]]]) -> list[T]:
        if time.monotonic() < self._retry_at.get(source, 0):
            return []
        try:
            async with asyncio.timeout(self.timeout):
                result = await factory()
            self._retry_at.pop(source, None)
            return result
        except (SQLAlchemyError, RedisError, TimeoutError, OSError) as error:
            self._retry_at[source] = time.monotonic() + self.cooldown
            logger.warning('Optional chat context unavailable source=%s reason=%s', source, type(error).__name__)
            return []
