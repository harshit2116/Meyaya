"""Run `python -m bot.check_redis` on the host to verify the configured Redis."""

import asyncio
from uuid import uuid4
from urllib.parse import urlsplit

from bot.cache.redis import build_redis_client
from bot.config.settings import get_settings


async def check():
    settings = get_settings()
    target = urlsplit(settings.redis_url)
    if target.scheme not in {"redis", "rediss"}:
        raise ValueError("REDIS_URL must be a Redis TCP URL")
    if (target.hostname or "").endswith(".upstash.io") and (
        target.scheme != "rediss" or not settings.redis_tls_verify
    ):
        raise ValueError("Upstash requires rediss:// and REDIS_TLS_VERIFY=true")
    client = build_redis_client(settings.redis_url, verify_tls=settings.redis_tls_verify)
    key = f"meyaya:deployment-check:{uuid4().hex}"
    try:
        if not await client.ping():
            raise RuntimeError("Redis did not answer PING")
        # Exercise the same transaction/expiration behavior used by moderation.
        async with client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60)
            values = await pipe.execute()
        if values != [1, True] or await client.get(key) != "1" or await client.ttl(key) <= 0:
            raise RuntimeError("Redis transaction or expiration check failed")
        await client.delete(key)
        print("Redis OK: authenticated connection, PING, transaction, read/write and expiry.")
        print("Host:", target.hostname, "TLS:", target.scheme == "rediss")
    finally:
        # The unique probe key expires in 60 seconds if a network failure prevents cleanup.
        await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception as error:
        # Exceptions may contain credential-bearing connection URLs; keep output safe.
        print(f"Redis check failed ({type(error).__name__}). Check REDIS_URL, TLS and outbound connectivity.")
        raise SystemExit(1) from None
