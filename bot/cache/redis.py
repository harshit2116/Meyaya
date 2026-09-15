"""Redis client helpers."""

from __future__ import annotations

from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.asyncio.retry import Retry


def build_redis_client(redis_url: str, *, verify_tls: bool = True) -> Redis:
    """Create an async Redis client."""

    tls = (
        {"ssl_cert_reqs": "required" if verify_tls else "none"}
        if redis_url.startswith("rediss://")
        else {}
    )
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        socket_keepalive=True,
        health_check_interval=30,
        max_connections=30,
        # Avoid replaying increments after an ambiguous network timeout.
        retry=Retry(NoBackoff(), 0),
        **tls,
    )
