"""Giphy GIF lookup with Redis caching."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from random import Random

import aiohttp
from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class GifResult:
    """A resolved GIF URL."""

    url: str | None


class GiphyService:
    """Resolve GIFs from Giphy and cache selections in Redis."""

    def __init__(self, api_key: str, rating: str, http_session: aiohttp.ClientSession, cache: Redis) -> None:
        self.api_key = api_key
        self.rating = rating
        self.http_session = http_session
        self.cache = cache

    async def random_gif(self, query: str) -> GifResult:
        """Return a cached or freshly fetched GIF result for a query."""

        if not self.api_key:
            return GifResult(url=None)

        cache_key = f"giphy:{sha256(query.encode('utf-8')).hexdigest()}"
        cached_url = await self.cache.get(cache_key)
        if cached_url:
            return GifResult(url=cached_url)

        endpoint = "https://api.giphy.com/v1/gifs/search"
        params = {"api_key": self.api_key, "q": query, "limit": 25, "rating": self.rating}
        async with self.http_session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            payload = await response.json()

        data = payload.get("data", [])
        if not data:
            return GifResult(url=None)

        rng = Random(query)
        chosen = rng.choice(data)
        url = chosen.get("images", {}).get("original", {}).get("url")
        if url:
            await self.cache.set(cache_key, url, ex=60 * 60)
        return GifResult(url=url)
