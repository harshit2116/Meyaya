"""Klipy GIF lookup with Redis caching."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from random import SystemRandom
import time

import aiohttp
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

FALLBACK_GIF_URLS = (
    "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
    "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
    "https://media.giphy.com/media/26BRv0ThflsHCqDrG/giphy.gif",
)
FALLBACK_GIF_URL = FALLBACK_GIF_URLS[0]
ANIME_QUERY_PREFIX = "anime"
KLIPY_BASE_URL = "https://api.klipy.com/api/v1"


@dataclass(frozen=True, slots=True)
class GifResult:
    """A resolved GIF URL."""

    url: str | None


class KlipyService:
    """Resolve GIFs from Klipy and return a fresh random result each time."""

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
            return GifResult(url=self._fallback_gif_url())

        normalized_query = query.strip().lower() or "reaction"

        search_result = await self._search_gifs(normalized_query)
        if search_result.url is None:
            search_result = await self._random_gif(normalized_query)

        return GifResult(url=search_result.url or self._fallback_gif_url())

    async def random_anime_gif(self, query: str) -> GifResult:
        """Return a random anime GIF for a specific action or mood."""
        normalized_query = self._normalize_anime_query(query)
        # Prefer anime but allow non-anime occasionally for variety/coverage.
        # Use the new wrapper to get weighted behavior.
        return await self.random_gif(normalized_query, prefer_anime=True)

    async def _search_gifs(self, query: str) -> GifResult:
        """Search Klipy for a query and return a random GIF from the result set."""

        if not self.api_key:
            return GifResult(url=None)

        endpoint = f"{KLIPY_BASE_URL}/{self.api_key}/gifs/search"
        # Fetch a modest number of results for speed; randomize page a bit
        params = {"q": query, "page": 1, "per_page": 12}
        # choose a small random page window to spread results without hurting relevancy
        try:
            page = SystemRandom().randint(1, 2)
            params["page"] = page
        except Exception:
            params["page"] = 1
        try:
            async with self.http_session.get(
                endpoint,
                params=params,
                headers={"Accept": "application/json", "User-Agent": "Meyaya/1.0"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                payload = await response.json()
                logger.debug(
                    "KLIPY search status=%s query=%s result=%s",
                    response.status,
                    query,
                    payload.get("result") if isinstance(payload, dict) else None,
                )
                if response.status != 200:
                    return GifResult(url=None)
        except Exception:
            logger.exception("KLIPY search failed for query=%s", query)
            return GifResult(url=None)

        items = self._extract_items(payload)
        if not items:
            return GifResult(url=None)

        # Build (item, url) pairs and prefer items not recently used.
        pairs: list[tuple[dict[str, object], str]] = []
        for it in items:
            url = self._extract_url(it)
            if isinstance(url, str) and url:
                pairs.append((it, url))

        rng = SystemRandom()

        # Try to avoid recently-used URLs tracked in Redis to increase diversity.
        chosen_item: dict[str, object] | None = None
        try:
            if self.cache is not None and pairs:
                KEY = "klipy:recent_urls"
                recent = await self.cache.zrange(KEY, 0, -1)
                recent_set = {r.decode() if isinstance(r, (bytes, bytearray)) else str(r) for r in recent}
                candidates = [p for p, u in pairs if u not in recent_set]
                if candidates:
                    chosen_item = rng.choice(candidates)
                    logger.debug("KLIPY picked non-recent candidate for query=%s", query)

        except Exception:
            # Non-fatal: if Redis fails, fall back to unbiased selection
            logger.exception("Failed to consult Redis recent set for Klipy diversity")

        if chosen_item is None:
            # If we didn't find a candidate that avoids recent URLs, pick from pairs
            if pairs:
                chosen_item = rng.choice([p for p, u in pairs])
            else:
                chosen_item = rng.choice(items)

        chosen_url = self._extract_url(chosen_item)
        logger.debug("KLIPY chosen_url=%s for query=%s", chosen_url, query)

        # Record the chosen URL to recent set to reduce near-term repeats.
        try:
            if self.cache is not None and isinstance(chosen_url, str) and chosen_url:
                KEY = "klipy:recent_urls"
                now = int(time.time())
                await self.cache.zadd(KEY, {chosen_url: now})
                count = await self.cache.zcard(KEY)
                if count > 200:
                    # remove oldest entries, keep the newest 200
                    await self.cache.zremrangebyrank(KEY, 0, count - 201)
        except Exception:
            logger.exception("Failed to update Redis recent set for Klipy")

        return GifResult(url=chosen_url)

    async def random_gif(self, query: str, prefer_anime: bool = False) -> GifResult:
        """Compatibility wrapper: prefer anime queries optionally, without enforcing.

        This keeps callers simple: they can ask to prefer anime but still get
        non-anime results when the provider lacks anime content.
        """

        # preserve legacy behavior when api key is missing
        if not self.api_key:
            return GifResult(url=self._fallback_gif_url())

        normalized = query.strip().lower() or "reaction"

        if prefer_anime:
            # 95% chance to add anime prefix, 5% plain — bias strongly toward anime
            if SystemRandom().random() < 0.95:
                logger.debug("KLIPY prefer_anime: using anime-prefixed query=%s", f"{ANIME_QUERY_PREFIX} {normalized}")
                result = await self._search_gifs(f"{ANIME_QUERY_PREFIX} {normalized}")
            else:
                result = await self._search_gifs(normalized)
        else:
            result = await self._search_gifs(normalized)

        # If search returned nothing, try a looser random fallback
        if result.url is None:
            result = await self._random_gif(normalized)

        return GifResult(url=result.url or self._fallback_gif_url())

    async def _random_gif(self, query: str) -> GifResult:
        """Ask Klipy for a random GIF as a fallback when search returns nothing."""

        return await self._search_gifs(query)

    def _extract_items(self, payload: object) -> list[dict[str, object]]:
        """Flatten the current KLIPY response structure into a list of media objects."""

        if not isinstance(payload, dict):
            return []

        data = payload.get("data")
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        results = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]

        return []

    def _extract_url(self, payload: object) -> str | None:
        """Extract a usable GIF URL from a KLIPY response payload."""

        if not isinstance(payload, dict):
            return None

        file_data = payload.get("file")
        if isinstance(file_data, dict):
            # prefer medium-sized GIFs for a balance of quality and speed
            for size in ("md", "sm", "hd"):
                size_data = file_data.get(size)
                if isinstance(size_data, dict):
                    gif_data = size_data.get("gif")
                    if isinstance(gif_data, dict):
                        url = gif_data.get("url")
                        if isinstance(url, str) and url:
                            return url

        images = payload.get("images")
        if isinstance(images, dict):
            original = images.get("original")
            if isinstance(original, dict):
                url = original.get("url")
                if isinstance(url, str) and url:
                    return url

            fixed = images.get("fixed_height")
            if isinstance(fixed, dict):
                url = fixed.get("url")
                if isinstance(url, str) and url:
                    return url

        url = payload.get("image_original_url")
        if isinstance(url, str) and url:
            return url

        url = payload.get("image_url")
        if isinstance(url, str) and url:
            return url

        fallback_url = payload.get("url")
        if isinstance(fallback_url, str) and fallback_url:
            return fallback_url

        return None

    def _fallback_gif_url(self) -> str:
        """Return a valid fallback animation if Klipy is unavailable or empty."""

        return SystemRandom().choice(FALLBACK_GIF_URLS)

    def _normalize_anime_query(self, query: str) -> str:
        """Keep bot GIF searches anime-focused and action-specific."""

        normalized = " ".join(query.lower().strip().split())
        if not normalized:
            return f"{ANIME_QUERY_PREFIX} reaction"
        if ANIME_QUERY_PREFIX in normalized.split():
            return normalized
        return f"{ANIME_QUERY_PREFIX} {normalized}"
