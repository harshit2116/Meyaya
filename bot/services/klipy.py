"""Klipy GIF lookup with Redis caching."""

from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass
from random import SystemRandom
import time
import re
from urllib.parse import urlsplit
from weakref import WeakValueDictionary

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
KLIPY_TIMEOUT = aiohttp.ClientTimeout(total=10)
SECURE_RANDOM = SystemRandom()
SEARCH_CACHE_TTL_SECONDS = 600
MAX_SEARCH_CACHE_ENTRIES = 64

ACTION_RELEVANCE_TERMS: dict[str, tuple[str, ...]] = {
    "hug": ("hug", "embrace"),
    "kiss": ("kiss", "kissing"),
    "pat": ("headpat", "head pat", "patting"),
    "cuddle": ("cuddle", "cuddling", "snuggle"),
    "headpat": ("headpat", "head pat"),
    "boop": ("boop", "nose poke"),
    "poke": ("poke", "poking"),
    "bite": ("bite", "biting", "nibble"),
    "slap": ("slap", "slapping", "smack"),
    "bonk": ("bonk", "bonking"),
    "tickle": ("tickle", "tickling"),
    "highfive": ("highfive", "high five", "high-five"),
    "handhold": ("handhold", "holding hands", "hold hands"),
    "wave": ("wave", "waving"),
    "dance": ("dance", "dancing"),
    "laugh": ("laugh", "laughing"),
    "cry": ("cry", "crying", "tears"),
    "smile": ("smile", "smiling"),
    "blush": ("blush", "blushing"),
    "cheer": ("cheer", "cheering", "celebrate"),
    "facepalm": ("facepalm", "face palm"),
}

ACTION_NEGATIVE_TERMS: dict[str, tuple[str, ...]] = {
    "slap": ("kiss", "hug", "love", "valentine", "cuddle", "romance"),
    "bonk": ("kiss", "love", "valentine", "cuddle"),
    "bite": ("kiss", "love", "valentine"),
    "poke": ("kiss", "love", "valentine"),
}


@dataclass(frozen=True, slots=True)
class GifResult:
    """A resolved GIF URL."""

    url: str | None


class KlipyService:
    """Resolve GIFs from Klipy and return a fresh random result each time."""

    def __init__(
        self,
        api_key: str,
        rating: str,
        http_session: aiohttp.ClientSession,
        cache: Redis | None,
    ) -> None:
        self.api_key = api_key
        self.rating = rating
        self.http_session = http_session
        self.cache = cache
        self._search_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
        self._last_url_by_query: dict[str, str] = {}
        self._search_locks = WeakValueDictionary()

    async def random_anime_gif(self, query: str) -> GifResult:
        """Return an action-relevant anime GIF or no GIF at all."""

        if not self.api_key:
            return GifResult(url=None)

        normalized_query = self._normalize_anime_query(query)
        return await self._search_gifs(normalized_query, strict_action=True)

    async def exact_gif(self, share_url: str) -> GifResult:
        """Resolve a specific Klipy share slug, never scrape HTML or substitute GIFs."""
        parsed = urlsplit(share_url)
        slug = parsed.path.removeprefix("/gifs/")
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"klipy.com", "www.klipy.com"}
            or not parsed.path.startswith("/gifs/")
            or not re.fullmatch(r"[a-z0-9-]{1,150}", slug)
        ):
            return GifResult(None)
        if not self.api_key:
            return GifResult(None)
        key = "exact:" + slug
        lock = self._search_locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._get_cached_search(key)
            if cached:
                return GifResult(cached[0])
            try:
                async with self.http_session.get(
                    f"{KLIPY_BASE_URL}/{self.api_key}/gifs/items",
                    params={"slugs": slug},
                    headers={"Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=4),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "KLIPY exact GIF unavailable status=%s slug=%s", response.status, slug
                        )
                        return GifResult(None)
                    payload = await response.json()
                for item in self._extract_items(payload):
                    if item.get("slug") == slug:
                        url = self._extract_url(item)
                        if url:
                            self._put_cached_search(key, (url,))
                            return GifResult(url)
            except Exception as error:
                logger.warning(
                    "KLIPY exact GIF failed slug=%s error=%s", slug, type(error).__name__
                )
            return GifResult(None)

    async def _search_gifs(self, query: str, *, strict_action: bool = False) -> GifResult:
        cache_key = f"{query.casefold()}|{int(strict_action)}"
        cached_urls = self._get_cached_search(cache_key)
        if cached_urls and self.api_key:
            return GifResult(url=self._choose_cached_url(cache_key, cached_urls))
        # Only one cold search per query; each waiting caller still chooses
        # its own result once the first request has populated the cache.
        lock = self._search_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            return await self._search_gifs_once(query, strict_action=strict_action)

    async def _search_gifs_once(self, query: str, *, strict_action: bool = False) -> GifResult:
        """Search Klipy for a query and return a random GIF from the result set."""

        if not self.api_key:
            return GifResult(url=None)

        cache_key = f"{query.casefold()}|{int(strict_action)}"
        cached_urls = self._get_cached_search(cache_key)
        if cached_urls:
            return GifResult(url=self._choose_cached_url(cache_key, cached_urls))

        endpoint = f"{KLIPY_BASE_URL}/{self.api_key}/gifs/search"
        # Search engines rank page one most strongly. Going deeper randomly can
        # return visually popular but unrelated results.
        params = {"q": query, "page": 1, "per_page": 24}
        try:
            async with self.http_session.get(
                endpoint,
                params=params,
                headers={"Accept": "application/json", "User-Agent": "Meyaya/1.0"},
                timeout=KLIPY_TIMEOUT,
            ) as response:
                payload = await response.json()
                logger.debug(
                    "KLIPY search status=%s query=%s result=%s",
                    response.status,
                    query,
                    payload.get("result") if isinstance(payload, dict) else None,
                )
                if response.status != 200:
                    logger.warning(
                        "KLIPY media unavailable status=%s query=%s", response.status, query
                    )
                    return GifResult(url=None)
        except Exception as error:
            # The API key is part of the endpoint path; exception URLs can expose it.
            logger.warning("KLIPY search failed query=%s error=%s", query, type(error).__name__)
            return GifResult(url=None)

        items = self._extract_items(payload)
        if not items:
            logger.warning("KLIPY media unavailable reason=empty_results query=%s", query)
            return GifResult(url=None)

        # Build (item, url) pairs and prefer items not recently used.
        pairs: list[tuple[dict[str, object], str]] = []
        for it in items:
            url = self._extract_url(it)
            if isinstance(url, str) and url:
                pairs.append((it, url))

        pairs = self._rank_action_candidates(query, pairs, strict_action=strict_action)
        if not pairs:
            logger.warning("KLIPY returned no relevant action GIF query=%s", query)
            return GifResult(url=None)
        self._put_cached_search(cache_key, tuple(url for _, url in pairs[:8]))

        # Try to avoid recently-used URLs tracked in Redis to increase diversity.
        chosen_item: dict[str, object] | None = None
        try:
            if self.cache is not None and pairs:
                KEY = "klipy:recent_urls"
                async with asyncio.timeout(0.25):
                    recent = await self.cache.zrange(KEY, -200, -1)
                recent_set = {
                    r.decode() if isinstance(r, (bytes, bytearray)) else str(r) for r in recent
                }
                candidates = [p for p, u in pairs[:8] if u not in recent_set]
                if candidates:
                    chosen_item = SECURE_RANDOM.choice(candidates)
                    logger.debug("KLIPY picked non-recent candidate for query=%s", query)

        except Exception:
            # Non-fatal: if Redis fails, fall back to unbiased selection
            logger.exception("Failed to consult Redis recent set for Klipy diversity")

        if chosen_item is None:
            # If we didn't find a candidate that avoids recent URLs, pick from pairs
            if pairs:
                chosen_item = SECURE_RANDOM.choice([p for p, u in pairs[:8]])
            else:
                chosen_item = SECURE_RANDOM.choice(items)

        chosen_url = self._extract_url(chosen_item)
        if isinstance(chosen_url, str) and chosen_url:
            self._last_url_by_query[cache_key] = chosen_url
        logger.debug("KLIPY chosen_url=%s for query=%s", chosen_url, query)

        # Record the chosen URL to recent set to reduce near-term repeats.
        try:
            if self.cache is not None and isinstance(chosen_url, str) and chosen_url:
                KEY = "klipy:recent_urls"
                now = int(time.time())
                async with asyncio.timeout(0.25):
                    async with self.cache.pipeline(transaction=True) as pipe:
                        pipe.zadd(KEY, {chosen_url: now})
                        # Trim to 200 entries without a separate count round trip.
                        pipe.zremrangebyrank(KEY, 0, -201)
                        await pipe.execute()
        except Exception:
            logger.exception("Failed to update Redis recent set for Klipy")

        return GifResult(url=chosen_url)

    def _get_cached_search(self, key: str) -> tuple[str, ...] | None:
        entry = self._search_cache.get(key)
        if entry is None:
            return None
        expires_at, urls = entry
        if expires_at <= time.monotonic():
            self._search_cache.pop(key, None)
            self._last_url_by_query.pop(key, None)
            return None
        return urls

    def _put_cached_search(self, key: str, urls: tuple[str, ...]) -> None:
        if not urls:
            return
        now = time.monotonic()
        if len(self._search_cache) >= MAX_SEARCH_CACHE_ENTRIES and key not in self._search_cache:
            expired = [
                cache_key for cache_key, (expiry, _) in self._search_cache.items() if expiry <= now
            ]
            for cache_key in expired:
                self._search_cache.pop(cache_key, None)
                self._last_url_by_query.pop(cache_key, None)
            if len(self._search_cache) >= MAX_SEARCH_CACHE_ENTRIES:
                oldest = next(iter(self._search_cache))
                self._search_cache.pop(oldest, None)
                self._last_url_by_query.pop(oldest, None)
        self._search_cache[key] = (now + SEARCH_CACHE_TTL_SECONDS, urls)

    def _choose_cached_url(self, key: str, urls: tuple[str, ...]) -> str:
        previous = self._last_url_by_query.get(key)
        candidates = [url for url in urls if url != previous] or list(urls)
        chosen = SECURE_RANDOM.choice(candidates)
        self._last_url_by_query[key] = chosen
        return chosen

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
            anime_query = self._normalize_anime_query(normalized)
            logger.debug("KLIPY prefer_anime: using query=%s", anime_query)
            result = await self._search_gifs(anime_query)
        else:
            result = await self._search_gifs(normalized)

        return GifResult(url=result.url or self._fallback_gif_url())

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
                        if self._valid_media_url(url):
                            return url.strip()

        media_formats = payload.get("media_formats")
        if isinstance(media_formats, dict):
            for name in ("mediumgif", "tinygif", "gif", "nanogif"):
                media = media_formats.get(name)
                if isinstance(media, dict):
                    url = media.get("url")
                    if self._valid_media_url(url):
                        return url.strip()

        images = payload.get("images")
        if isinstance(images, dict):
            original = images.get("original")
            if isinstance(original, dict):
                url = original.get("url")
                if self._valid_media_url(url):
                    return url.strip()

            fixed = images.get("fixed_height")
            if isinstance(fixed, dict):
                url = fixed.get("url")
                if self._valid_media_url(url):
                    return url.strip()

        url = payload.get("image_original_url")
        if self._valid_media_url(url):
            return url.strip()

        url = payload.get("image_url")
        if self._valid_media_url(url):
            return url.strip()

        fallback_url = payload.get("url")
        # A top-level URL is often a share page, not an embeddable image.
        if self._valid_media_url(fallback_url, require_extension=True):
            return fallback_url.strip()

        return None

    @staticmethod
    def _valid_media_url(value, *, require_extension=False):
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            url = urlsplit(value.strip())
        except ValueError:
            return False
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            return False
        # Known share sites are HTML even when the post title ends with '.gif'.
        if url.hostname.lower() in {
            "klipy.com",
            "www.klipy.com",
            "tenor.com",
            "www.tenor.com",
            "giphy.com",
            "www.giphy.com",
        }:
            return False
        return not require_extension or url.path.lower().endswith(
            (".gif", ".webp", ".png", ".jpg", ".jpeg")
        )

    def _rank_action_candidates(
        self,
        query: str,
        pairs: list[tuple[dict[str, object], str]],
        *,
        strict_action: bool,
    ) -> list[tuple[dict[str, object], str]]:
        """Keep action GIFs relevant using provider titles, tags, and result rank."""

        normalized_query = query.casefold().replace("-", " ")
        query_tokens = set(normalized_query.split())
        action = next(
            (
                name
                for name, terms in ACTION_RELEVANCE_TERMS.items()
                if name in query_tokens
                or any(term.replace("-", " ") in normalized_query for term in terms)
            ),
            None,
        )
        if action is None:
            return pairs

        positives = ACTION_RELEVANCE_TERMS[action]
        negatives = ACTION_NEGATIVE_TERMS.get(action, ())
        ranked: list[tuple[int, bool, tuple[dict[str, object], str]]] = []
        has_metadata = False
        for index, pair in enumerate(pairs):
            metadata = self._item_search_text(pair[0])
            has_metadata = has_metadata or bool(metadata)
            positive_match = any(term in metadata for term in positives)
            score = max(0, 12 - index)
            if positive_match:
                score += 100
            if any(term in metadata for term in negatives):
                score -= 150
            ranked.append((score, positive_match, pair))

        if strict_action and has_metadata:
            ranked = [candidate for candidate in ranked if candidate[1] and candidate[0] > 0]
        ranked.sort(key=lambda candidate: candidate[0], reverse=True)
        return [pair for _, _, pair in ranked]

    @staticmethod
    def _item_search_text(item: dict[str, object]) -> str:
        """Flatten common KLIPY metadata fields for relevance checks."""

        values: list[str] = []
        for key in ("title", "slug", "description", "content_description", "name"):
            value = item.get(key)
            if isinstance(value, str):
                values.append(value)
        tags = item.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    values.append(tag)
                elif isinstance(tag, dict):
                    value = tag.get("name")
                    if isinstance(value, str):
                        values.append(value)
        return " ".join(values).casefold().replace("-", " ")

    def _fallback_gif_url(self) -> str:
        """Return a valid fallback animation if Klipy is unavailable or empty."""

        return SECURE_RANDOM.choice(FALLBACK_GIF_URLS)

    def _normalize_anime_query(self, query: str) -> str:
        """Keep bot GIF searches anime-focused and action-specific."""

        normalized = " ".join(query.lower().strip().split())
        if not normalized:
            return f"{ANIME_QUERY_PREFIX} reaction"
        if ANIME_QUERY_PREFIX in normalized.split():
            return normalized
        return f"{ANIME_QUERY_PREFIX} {normalized}"
