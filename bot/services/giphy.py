"""Giphy GIF lookup with Redis caching."""

from __future__ import annotations

from dataclasses import dataclass
from random import SystemRandom

import aiohttp
from redis.asyncio import Redis


FALLBACK_GIF_URL = "https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif"
ANIME_QUERY_PREFIX = "anime"


@dataclass(frozen=True, slots=True)
class GifResult:
    """A resolved GIF URL."""

    url: str | None


class GiphyService:
    """Resolve GIFs from Giphy and return a fresh random result each time."""

    def __init__(self, api_key: str, rating: str, http_session: aiohttp.ClientSession, cache: Redis) -> None:
        self.api_key = api_key
        self.rating = rating
        self.http_session = http_session
        self.cache = cache

    async def random_gif(self, query: str) -> GifResult:
        """Return a random GIF result for a query.

        The service intentionally avoids caching the selected URL so each command
        invocation can show a different GIF.
        """

        if not self.api_key:
            return GifResult(url=FALLBACK_GIF_URL)

        normalized_query = query.strip().lower() or "reaction"

        search_result = await self._search_gifs(normalized_query)
        if search_result.url is None:
            search_result = await self._random_gif(normalized_query)

        return GifResult(url=search_result.url or FALLBACK_GIF_URL)

    async def random_anime_gif(self, query: str) -> GifResult:
        """Return a random anime GIF for a specific action or mood."""

        normalized_query = self._normalize_anime_query(query)
        return await self.random_gif(normalized_query)

    async def _search_gifs(self, query: str) -> GifResult:
        """Search Giphy for a query and return a random GIF from the result set."""

        endpoint = "https://api.giphy.com/v1/gifs/search"
        params = {"api_key": self.api_key, "q": query, "limit": 50, "rating": self.rating}
        try:
            async with self.http_session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                payload = await response.json()
        except Exception:
            return GifResult(url=None)

        data = payload.get("data", [])
        if not data:
            return GifResult(url=None)

        rng = SystemRandom()
        chosen = rng.choice(data)
        return GifResult(url=self._extract_url(chosen))

    async def _random_gif(self, query: str) -> GifResult:
        """Ask Giphy for a random GIF as a fallback when search returns nothing."""

        endpoint = "https://api.giphy.com/v1/gifs/random"
        params = {"api_key": self.api_key, "tag": query, "rating": self.rating}
        try:
            async with self.http_session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                payload = await response.json()
        except Exception:
            return GifResult(url=None)

        return GifResult(url=self._extract_url(payload.get("data", {})))

    def _extract_url(self, payload: dict[str, object]) -> str | None:
        """Extract a usable GIF URL from a Giphy response payload."""

        images = payload.get("images")
        if isinstance(images, dict):
            original = images.get("original")
            if isinstance(original, dict):
                url = original.get("url")
                if isinstance(url, str) and url:
                    return url

        url = payload.get("image_original_url")
        if isinstance(url, str) and url:
            return url

        fallback_url = payload.get("url")
        if isinstance(fallback_url, str) and fallback_url:
            return fallback_url

        return None

    def _normalize_anime_query(self, query: str) -> str:
        """Keep bot GIF searches anime-focused and action-specific."""

        normalized = " ".join(query.lower().strip().split())
        if not normalized:
            return f"{ANIME_QUERY_PREFIX} reaction"
        if ANIME_QUERY_PREFIX in normalized.split():
            return normalized
        return f"{ANIME_QUERY_PREFIX} {normalized}"
