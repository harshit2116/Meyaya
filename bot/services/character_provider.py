"""Transient character display lookup providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from urllib.parse import urlparse
from weakref import WeakValueDictionary

import aiohttp

ANILIST_ENDPOINT = "https://graphql.anilist.co/"
ANILIST_QUERY = """
query ($id: Int!) {
  Character(id: $id) {
    id
    name { full }
    image { large }
    siteUrl
    media(perPage: 5, sort: POPULARITY_DESC) {
      nodes { type isAdult title { english romaji } }
    }
  }
}
"""
CACHE_TTL_SECONDS = 3 * 60 * 60
MAX_CACHE_ENTRIES = 256


class CharacterProviderError(RuntimeError):
    pass


class CharacterNotFound(CharacterProviderError):
    pass


@dataclass(frozen=True, slots=True)
class CharacterDisplay:
    provider_id: int
    name: str
    image_url: str | None
    series: str
    source_url: str


def safe_anilist_image(url: str | None) -> bool:
    parsed = urlparse(url or "")
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"s4.anilist.co", "s5.anilist.co"}
        and not parsed.username
        and not parsed.password
    )


class AniListCharacterProvider:
    """Fetch one explicit character and retain it only in an expiring memory cache."""

    name = "anilist"

    def __init__(self, http_session: aiohttp.ClientSession, *, cache_ttl: int = CACHE_TTL_SECONDS):
        self.http_session = http_session
        self.cache_ttl = cache_ttl
        self._cache: dict[int, tuple[float, CharacterDisplay]] = {}
        # Retain a lock only while requests for that character are active.
        self._locks = WeakValueDictionary()

    async def fetch(self, provider_id: int) -> CharacterDisplay:
        provider_id = int(provider_id)
        now = time.monotonic()
        cached = self._cache.get(provider_id)
        if cached and cached[0] > now:
            return cached[1]
        lock = self._locks.setdefault(provider_id, asyncio.Lock())
        async with lock:
            cached = self._cache.get(provider_id)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            result = await self._request(provider_id)
            self._prune()
            self._cache[provider_id] = (time.monotonic() + self.cache_ttl, result)
            return result

    async def _request(self, provider_id: int) -> CharacterDisplay:
        try:
            async with self.http_session.post(
                ANILIST_ENDPOINT,
                json={"query": ANILIST_QUERY, "variables": {"id": provider_id}},
                headers={"Accept": "application/json", "User-Agent": "Meyaya Discord Bot"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                payload = await response.json(content_type=None)
                if response.status == 429:
                    retry = response.headers.get("Retry-After", "60")
                    raise CharacterProviderError(f"AniList is rate limited. Try again in {retry}s.")
                if response.status >= 500:
                    raise CharacterProviderError("AniList is temporarily unavailable.")
                if response.status >= 400 or payload.get("errors"):
                    raise CharacterNotFound("That AniList character is unavailable.")
        except asyncio.TimeoutError as exc:
            raise CharacterProviderError("AniList lookup timed out.") from exc
        except aiohttp.ClientError as exc:
            raise CharacterProviderError("AniList could not be reached.") from exc

        row = (payload.get("data") or {}).get("Character")
        if not row or int(row.get("id", 0)) != provider_id:
            raise CharacterNotFound("That AniList character is unavailable.")
        media = (row.get("media") or {}).get("nodes") or []
        safe_media = [item for item in media if item and item.get("isAdult") is False]
        if not safe_media:
            raise CharacterProviderError("This character has no suitable series metadata.")
        primary = next((item for item in safe_media if item.get("type") == "ANIME"), safe_media[0])
        title = primary.get("title") or {}
        series = title.get("english") or title.get("romaji") or "Unknown series"
        image = (row.get("image") or {}).get("large")
        return CharacterDisplay(
            provider_id=provider_id,
            name=(row.get("name") or {}).get("full") or "Unknown character",
            image_url=image if safe_anilist_image(image) else None,
            series=series,
            source_url=f"https://anilist.co/character/{provider_id}",
        )

    def clear_cache(self, provider_id: int | None = None) -> None:
        if provider_id is None:
            self._cache.clear()
        else:
            self._cache.pop(int(provider_id), None)

    def _prune(self) -> None:
        now = time.monotonic()
        for key in [key for key, (expiry, _) in self._cache.items() if expiry <= now]:
            self._cache.pop(key, None)
        while len(self._cache) >= MAX_CACHE_ENTRIES:
            self._cache.pop(next(iter(self._cache)))
