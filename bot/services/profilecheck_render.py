"""Small, bounded cache of completed profile reviews, keyed by current assets."""

from __future__ import annotations

from collections import OrderedDict
import logging
from time import monotonic

from bot.services.profile_aesthetic import ProfileVisual, profilecheck_analysis
from bot.services.profile_cards import profilecheck_media, PROFILE_MEDIA_BYTES
from bot.utils.image_work import BoundedImageGate, animation_work

logger = logging.getLogger(__name__)

type _ProfileCheckResult = tuple[ProfileVisual, bytes, str]
type _CacheKey = tuple[
    str, int, int, int, int, str, tuple[str, ...], int, str
]


def _render(visual: ProfileVisual, max_bytes: int) -> _ProfileCheckResult:
    started = monotonic()
    visual = profilecheck_analysis(visual)
    analyzed = monotonic()
    data, extension = profilecheck_media(visual, max_bytes=max_bytes)
    logger.debug("profilecheck analysis_ms=%.1f render_ms=%.1f", (analyzed-started)*1000, (monotonic()-analyzed)*1000)
    return visual, data, extension


class ProfileCheckRenderer:
    def __init__(self, max_bytes: int = 8 * 1024 * 1024, ttl: int = 300) -> None:
        self.cache: OrderedDict[_CacheKey, tuple[float, _ProfileCheckResult, int]] = OrderedDict()
        self.bytes = 0
        self.max_bytes = max_bytes
        self.ttl = ttl
        self.gate = BoundedImageGate()

    def _cached(self, key: _CacheKey) -> _ProfileCheckResult | None:
        entry = self.cache.get(key)
        if entry is None:
            return None
        created, result, size = entry
        if monotonic() - created >= self.ttl:
            del self.cache[key]
            self.bytes -= size
            return None
        self.cache.move_to_end(key)
        return result

    async def render(
        self, visual: ProfileVisual, *, max_bytes: int = PROFILE_MEDIA_BYTES
    ) -> _ProfileCheckResult:
        # Fingerprint includes name, asset URLs, accent and scoring metadata.
        # Content hashes distinguish a failed download from a later recovery.
        max_bytes = min(max_bytes, PROFILE_MEDIA_BYTES)
        key = (visual.asset_fingerprint, hash(visual.avatar), hash(visual.banner), hash(visual.decoration), max_bytes, visual.server_tag, visual.badge_names, hash(visual.nameplate), visual.username)
        cached = self._cached(key)
        if cached is not None:
            return cached
        async with self.gate:
            now = monotonic()
            for old_key, (created, _, size) in list(self.cache.items()):
                if now - created >= self.ttl:
                    del self.cache[old_key]
                    self.bytes -= size
            cached = self._cached(key)
            if cached is not None:
                return cached
            # Waiting callers recheck the cache after the first render finishes.
            result = await animation_work(_render, visual, max_bytes)
            size = len(result[1]) + sum(len(asset) for asset in (visual.avatar, visual.banner, visual.decoration, visual.nameplate) if asset)
            if size <= self.max_bytes:
                while self.cache and (self.bytes + size > self.max_bytes or len(self.cache) >= 16):
                    _, (_, _, removed) = self.cache.popitem(last=False)
                    self.bytes -= removed
                self.cache[key] = (monotonic(), result, size)
                self.bytes += size
            return result
