"""Small, bounded cache of completed profile reviews, keyed by current assets."""

from collections import OrderedDict
import logging
from time import monotonic

from bot.services.profile_aesthetic import profilecheck_analysis
from bot.services.profile_cards import profilecheck_media
from bot.utils.image_work import BoundedImageGate, image_work

logger = logging.getLogger(__name__)


def _render(visual):
    started = monotonic()
    visual = profilecheck_analysis(visual)
    analyzed = monotonic()
    data, extension = profilecheck_media(visual)
    logger.debug("profilecheck analysis_ms=%.1f render_ms=%.1f", (analyzed-started)*1000, (monotonic()-analyzed)*1000)
    return visual, data, extension


class ProfileCheckRenderer:
    def __init__(self, max_bytes=8 * 1024 * 1024, ttl=300):
        self.cache = OrderedDict()
        self.bytes = 0
        self.max_bytes = max_bytes
        self.ttl = ttl
        self.gate = BoundedImageGate()

    def _cached(self, key):
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

    async def render(self, visual):
        # Fingerprint includes name, asset URLs, accent and scoring metadata.
        # Content hashes distinguish a failed download from a later recovery.
        key = (visual.asset_fingerprint, hash(visual.avatar), hash(visual.banner), hash(visual.decoration))
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
            result = await image_work(_render, visual)
            size = len(result[1]) + sum(len(asset) for asset in (visual.avatar, visual.banner, visual.decoration) if asset)
            if size <= self.max_bytes:
                while self.cache and (self.bytes + size > self.max_bytes or len(self.cache) >= 16):
                    _, (_, _, removed) = self.cache.popitem(last=False)
                    self.bytes -= removed
                self.cache[key] = (monotonic(), result, size)
                self.bytes += size
            return result
