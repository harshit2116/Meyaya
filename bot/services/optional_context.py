"""Short, fail-soft budgets for optional read-only chat context."""
import asyncio
import logging
import time

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class OptionalContext:
    def __init__(self, timeout=2.0, cooldown=15.0):
        self.timeout, self.cooldown = timeout, cooldown
        self._retry_at = {}

    async def read(self, source, factory):
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
