"""Redis client helpers."""

from __future__ import annotations

from redis.asyncio import Redis


def build_redis_client(redis_url: str) -> Redis:
    """Create an async Redis client."""

    return Redis.from_url(redis_url, decode_responses=True)
