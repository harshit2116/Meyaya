"""Discord profile collection and deterministic visual analysis."""

from __future__ import annotations

import asyncio
from bot.utils.image_work import image_work, BoundedImageGate
from collections import OrderedDict
from dataclasses import dataclass, replace
from hashlib import blake2s
from io import BytesIO
import math
import logging
import time
import colorsys
from weakref import WeakValueDictionary

import aiohttp
import discord
from PIL import Image, ImageEnhance, ImageStat

MAX_ASSET_BYTES = 6 * 1024 * 1024
CACHE_TTL_SECONDS = 30 * 60
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProfileVisual:
    user_id: int
    name: str
    avatar: bytes | None
    banner: bytes | None
    decoration: bytes | None
    palette: tuple[str, ...]
    avatar_score: int
    styling_score: int
    harmony_score: int
    originality_score: int
    overall_score: int
    has_banner: bool
    has_decoration: bool
    has_nameplate: bool
    has_server_tag: bool
    has_server_avatar: bool
    badge_count: int
    animated_avatar: bool
    accent_color: str | None
    asset_fingerprint: str
    animated_banner: bool = False
    banner_available: bool = False


class ProfileAestheticService:
    """Fetch only public Discord assets and cache analysis by their immutable URLs."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self._cache: OrderedDict[str, tuple[float, ProfileVisual]] = OrderedDict()
        self._user_cache: OrderedDict[int, tuple[float, discord.User | None]] = OrderedDict()
        self._cache_bytes = 0
        self._asset_cache = OrderedDict()
        self._asset_cache_bytes = 0
        # Overlap two network inspections, but keep CPU/Pillow work serialized.
        self._inspect_slots = BoundedImageGate(concurrency=2)
        self._asset_locks = WeakValueDictionary()
        # Fixed-size locks coalesce repeated requests without an unbounded lock table.
        self._member_locks = [asyncio.Lock() for _ in range(32)]

    async def inspect(self, member: discord.Member, *, refresh: bool = False, animated: bool = False) -> ProfileVisual:
        async with self._inspect_slots:
            async with self._member_locks[member.id % len(self._member_locks)]:
                if refresh:
                    # Server avatars/banners and global profile data can change
                    # independently of the gateway's cached Member object.
                    started = time.monotonic()
                    member, fetched = await asyncio.gather(
                        member.guild.fetch_member(member.id), self.bot.fetch_user(member.id))
                    logger.info("profile_metadata fetch_ms=%.0f", (time.monotonic() - started) * 1000)
                    return await self._inspect(member, refresh=True, fetched_user=fetched, animated=animated)
                return await self._inspect(member, refresh=refresh, animated=animated)

    async def _inspect(self, member: discord.Member, *, refresh: bool = False, fetched_user=None, animated: bool = False) -> ProfileVisual:
        now = time.monotonic()
        cached_user = self._user_cache.get(member.id)
        if fetched_user is not None:
            fetched = fetched_user
            self._user_cache[member.id] = (now, fetched)
            self._user_cache.move_to_end(member.id)
            while len(self._user_cache) > 128:
                self._user_cache.popitem(last=False)
        elif not refresh and cached_user and now - cached_user[0] < CACHE_TTL_SECONDS:
            fetched = cached_user[1]
        else:
            try:
                fetched = await self.bot.fetch_user(member.id)
            except discord.HTTPException:
                if refresh:
                    raise
                fetched = None
            self._user_cache[member.id] = (now, fetched)
            self._user_cache.move_to_end(member.id)
            while len(self._user_cache) > 128:
                self._user_cache.popitem(last=False)

        avatar_asset = (member.guild_avatar or getattr(fetched, "display_avatar", None) or member.display_avatar).with_size(512).with_static_format("png")
        banner_asset = getattr(member, "guild_banner", None) or getattr(fetched, "banner", None)
        decoration_asset = getattr(member, "avatar_decoration", None) or getattr(fetched, "avatar_decoration", None)
        banner_asset = (
            banner_asset.with_size(1024).with_static_format("png") if banner_asset else None
        )
        decoration_asset = decoration_asset.with_size(512) if decoration_asset else None
        animated_banner = bool(banner_asset and banner_asset.is_animated())
        if not animated:
            avatar_asset = avatar_asset.with_format("png")
            banner_asset = banner_asset.with_format("png") if banner_asset else None
            decoration_asset = decoration_asset.with_format("png") if decoration_asset else None
        urls = tuple(
            str(asset) if asset is not None else ""
            for asset in (avatar_asset, banner_asset, decoration_asset)
        )
        collectibles = getattr(fetched, "collectibles", None) or getattr(
            member, "collectibles", None
        )
        public_flags = getattr(fetched, "public_flags", None) or member.public_flags
        badge_count = len(public_flags.all()) if public_flags else 0
        nameplate = any(getattr(getattr(item, "type", None), "value", getattr(item, "type", None)) == "nameplate"
                        for item in (collectibles or []))
        primary_guild = getattr(fetched, "primary_guild", None)
        server_tag = bool(primary_guild and getattr(primary_guild, "tag", None))
        accent = getattr(fetched, "accent_color", None)
        cache_key = "|".join(
            (
                str(member.id),
                member.display_name,
                *urls,
                str(nameplate),
                str(server_tag),
                str(badge_count),
                str(getattr(accent, "value", "")),
                str(bool(member.guild_avatar)),
            )
        )
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

        started = time.monotonic()
        avatar, banner, decoration = await asyncio.gather(
            self._download(urls[0]),
            self._download(urls[1]),
            self._download(urls[2]),
        )
        downloaded = time.monotonic()
        visual = await image_work(
            self._analyze,
            member,
            avatar=avatar,
            banner=banner,
            decoration=decoration,
            has_nameplate=nameplate,
            has_server_tag=server_tag,
            badge_count=badge_count,
            accent_value=getattr(accent, "value", None),
            fingerprint=blake2s(cache_key.encode("utf-8"), digest_size=8).hexdigest(),
        )
        visual = replace(visual, animated_banner=animated_banner,
                         banner_available=banner_asset is not None)
        logger.info("profile_assets download_ms=%.0f analysis_and_queue_ms=%.0f",
                    (downloaded - started) * 1000, (time.monotonic() - downloaded) * 1000)
        # Do not preserve a transient failed asset download for half an hour.
        if all(not url or data is not None for url, data in zip(urls, (avatar, banner, decoration))):
            self._store(cache_key, visual)
        return visual

    @staticmethod
    def _asset_size(visual: ProfileVisual) -> int:
        return sum(len(data) for data in (visual.avatar, visual.banner, visual.decoration) if data)

    def _store(self, key: str, visual: ProfileVisual) -> None:
        now = time.monotonic()
        for old_key, (created, old_visual) in list(self._cache.items()):
            if old_key == key or now - created >= CACHE_TTL_SECONDS:
                self._cache.pop(old_key)
                self._cache_bytes -= self._asset_size(old_visual)
        self._cache[key] = (now, visual)
        self._cache_bytes += self._asset_size(visual)
        while len(self._cache) > 16 or self._cache_bytes > 8 * 1024 * 1024:
            _, (_, removed) = self._cache.popitem(last=False)
            self._cache_bytes -= self._asset_size(removed)

    async def _download(self, url: str) -> bytes | None:
        if not url:
            return None
        lock = self._asset_locks.setdefault(url, asyncio.Lock())
        async with lock:
            return await self._download_once(url)

    async def _download_once(self, url: str) -> bytes | None:
        # Discord asset URLs include their content hash. A changed banner
        # should not force a second download of an unchanged avatar.
        now = time.monotonic()
        for key, (created, data) in list(self._asset_cache.items()):
            if now - created >= 600:
                del self._asset_cache[key]
                self._asset_cache_bytes -= len(data)
        cached = self._asset_cache.get(url)
        if cached is not None:
            self._asset_cache.move_to_end(url)
            return cached[1]
        data = await self._fetch_asset(url)
        budget = 2 * 1024 * 1024
        if data and len(data) <= budget:
            # Recheck after awaiting: avatar and banner can share a URL.
            previous = self._asset_cache.pop(url, None)
            if previous:
                self._asset_cache_bytes -= len(previous[1])
            while self._asset_cache and (len(self._asset_cache) >= 32 or self._asset_cache_bytes + len(data) > budget):
                _, (_, removed) = self._asset_cache.popitem(last=False)
                self._asset_cache_bytes -= len(removed)
            self._asset_cache[url] = (time.monotonic(), data)
            self._asset_cache_bytes += len(data)
        return data

    async def _fetch_asset(self, url: str) -> bytes | None:
        if not url or self.bot.http_session is None:
            return None
        try:
            async with self.bot.http_session.get(
                url, timeout=aiohttp.ClientTimeout(total=8)
            ) as response:
                if response.status != 200:
                    return None
                length = response.content_length
                if length is not None and length > MAX_ASSET_BYTES:
                    return None
                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    if len(data) + len(chunk) > MAX_ASSET_BYTES:
                        return None
                    data.extend(chunk)
                return bytes(data)
        except (aiohttp.ClientError, TimeoutError):
            return None

    @classmethod
    def _analyze(
        cls,
        member: discord.Member,
        *,
        avatar: bytes | None,
        banner: bytes | None,
        decoration: bytes | None,
        has_nameplate: bool,
        has_server_tag: bool,
        badge_count: int,
        accent_value: int | None,
        fingerprint: str,
    ) -> ProfileVisual:
        avatar_image = cls._open(avatar)
        banner_image = cls._open(banner)
        decoration_image = cls._open(decoration)
        sources = [image for image in (avatar_image, banner_image) if image is not None]
        if accent_value is not None:
            sources.append(Image.new("RGB", (32, 32), cls._hex(accent_value)))
        palette = cls._palette(sources)
        sample = avatar_image or (sources[0] if sources else Image.new("RGB", (32, 32), "#75617f"))
        colorfulness = cls._colorfulness(sample)
        contrast = min(100, int(sum(ImageStat.Stat(sample.resize((96, 96))).stddev) / 3 * 1.6))
        harmony = cls._harmony(palette)
        custom_avatar = member.avatar is not None or member.guild_avatar is not None
        # Keep the review deliberately strict: simply uploading an avatar is the
        # baseline, while composition, contrast, and colour direction earn the score.
        avatar_score = cls._clamp(
            20 + int(colorfulness * 0.28) + int(contrast * 0.32) + (14 if custom_avatar else 0)
        )
        styling = cls._clamp(
            10
            + (18 if banner else 0)
            + (18 if decoration else 0)
            + (8 if has_nameplate else 0)
            + (4 if has_server_tag else 0)
            + (5 if member.guild_avatar else 0)
            + (5 if member.display_avatar.is_animated() else 0)
            + min(5, badge_count)
        )
        variation = int(fingerprint[:4], 16) % 31
        originality = cls._clamp(
            32
            + variation
            + (8 if decoration else 0)
            + (6 if banner else 0)
            + (5 if member.guild_avatar else 0)
            + (5 if member.display_avatar.is_animated() else 0)
        )
        overall = round(avatar_score * 0.30 + styling * 0.30 + harmony * 0.25 + originality * 0.15)
        return ProfileVisual(
            user_id=member.id,
            name=member.display_name,
            avatar=avatar,
            banner=banner,
            decoration=decoration,
            palette=palette,
            avatar_score=avatar_score,
            styling_score=styling,
            harmony_score=harmony,
            originality_score=originality,
            overall_score=overall,
            has_banner=bool(banner),
            has_decoration=bool(decoration),
            has_nameplate=has_nameplate,
            has_server_tag=has_server_tag,
            has_server_avatar=member.guild_avatar is not None,
            badge_count=badge_count,
            animated_avatar=member.display_avatar.is_animated(),
            accent_color=cls._hex(accent_value) if accent_value is not None else None,
            asset_fingerprint=fingerprint,
        )

    @staticmethod
    def _open(data: bytes | None) -> Image.Image | None:
        if not data:
            return None
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 4_000_000:
                    return None
                image.thumbnail((1024, 1024))
                rgba = image.convert("RGBA")
                flattened = Image.new("RGBA", rgba.size, (18, 15, 25, 255))
                flattened.alpha_composite(rgba)
                return ImageEnhance.Color(flattened.convert("RGB")).enhance(1.05)
        except (OSError, ValueError):
            return None

    @classmethod
    def _palette(cls, images: list[Image.Image]) -> tuple[str, ...]:
        if not images:
            return ("#75617f", "#c694b0", "#ead8e4", "#2c2533", "#a788b5")
        strips = [image.resize((96, 96)).convert("RGB") for image in images]
        canvas = Image.new("RGB", (96 * len(strips), 96))
        for index, image in enumerate(strips):
            canvas.paste(image, (index * 96, 0))
        quantized = canvas.quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("RGB")
        colors = sorted(quantized.getcolors(quantized.width * quantized.height) or [], reverse=True)
        selected: list[tuple[int, int, int]] = []
        for _, color in colors:
            if all(cls._distance(color, existing) >= 42 for existing in selected):
                selected.append(color)
            if len(selected) == 5:
                break
        while len(selected) < 5:
            base = selected[0] if selected else (117, 97, 127)
            factor = 0.55 + len(selected) * 0.14
            selected.append(tuple(min(255, int(channel * factor + 28)) for channel in base))
        return tuple("#%02x%02x%02x" % color for color in selected)

    @staticmethod
    def _colorfulness(image: Image.Image) -> int:
        stat = ImageStat.Stat(image.resize((96, 96)).convert("RGB"))
        spread = max(stat.mean) - min(stat.mean)
        deviation = sum(stat.stddev) / 3
        return min(100, int(spread * 0.45 + deviation * 1.15))

    @classmethod
    def _harmony(cls, palette: tuple[str, ...]) -> int:
        colors = [cls._rgb(color) for color in palette[:3]]
        distances = [cls._distance(colors[index], colors[index + 1]) for index in range(2)]
        average = sum(distances) / len(distances)
        # Both indistinguishable colors and visual noise score below a balanced spread.
        return cls._clamp(100 - int(abs(average - 145) * 0.45))

    @staticmethod
    def _distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))

    @staticmethod
    def _rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    @staticmethod
    def _hex(value: int) -> str:
        return f"#{value & 0xFFFFFF:06x}"

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, value))


def profilecheck_analysis(visual: ProfileVisual) -> ProfileVisual:
    """Review visible assets without identity randomness or accessory-count scores."""
    service = ProfileAestheticService
    avatar = service._open(visual.avatar)
    banner = service._open(visual.banner)
    decoration = service._open(visual.decoration)
    if banner is None and not visual.banner_available and visual.accent_color is not None:
        banner = Image.new("RGB", (32, 32), visual.accent_color)
    if avatar is None:
        return visual
    avatar_palette = service._palette([avatar])
    matches = []
    for asset in (banner, decoration):
        if asset is None:
            continue
        if asset is decoration and visual.decoration:
            # Transparent pixels are not a dark design choice. Inspect only ink.
            with Image.open(BytesIO(visual.decoration)) as raw:
                raw.thumbnail((96, 96))
                pixels = [p[:3] for p in raw.convert("RGBA").getdata() if p[3] >= 128]
            if not pixels:
                continue
            asset = Image.new("RGB", (len(pixels), 1))
            asset.putdata(pixels)
        other = service._palette([asset])
        # Compare each prominent asset color to its nearest avatar color.
        distance = sum(min(service._distance(service._rgb(color), service._rgb(base))
                           for base in avatar_palette[:3]) for color in other[:3]) / 3
        match = service._clamp(round(96 - distance * 0.35))
        # Solid neutral backdrops coordinate by contrast, not hue matching.
        stat = ImageStat.Stat(asset.convert("RGB"))
        if asset is banner and max(stat.stddev) < 8 and max(stat.mean) - min(stat.mean) < 18:
            contrast_gap = abs(sum(stat.mean)/3 - sum(ImageStat.Stat(avatar).mean)/3)
            match = max(match, min(92, round(68 + contrast_gap * .12)))
        matches.append(match)
    harmony = round(sum(matches) / len(matches)) if matches else visual.harmony_score
    contrast = min(100, sum(ImageStat.Stat(avatar.resize((96, 96))).stddev) / 3 * 1.6)
    detail = service._clamp(round(25 + min(1, avatar.convert('L').entropy() / 7.5) * 55 + contrast * .15))
    styling = service._clamp(round(visual.avatar_score * .4 + harmony * .6))
    overall = round(visual.avatar_score * .35 + styling * .20 + harmony * .30 + detail * .15)
    return replace(visual, styling_score=styling, harmony_score=harmony,
                   originality_score=detail, overall_score=overall)


def profile_affinity(visual: ProfileVisual) -> str:
    """Map the dominant public-profile color to one stable fantasy affinity."""

    red, green, blue = (
        channel / 255 for channel in ProfileAestheticService._rgb(visual.palette[0])
    )
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    if saturation < 0.16:
        return "Moonlight"
    degrees = hue * 360
    if degrees < 25 or degrees >= 340:
        return "Ember"
    if degrees < 70:
        return "Solar"
    if degrees < 165:
        return "Verdant"
    if degrees < 250:
        return "Tidal"
    if degrees < 300:
        return "Astral"
    return "Bloom"


def profile_class(visual: ProfileVisual) -> str:
    """Choose a lightweight fantasy class from visible profile composition."""

    affinity = profile_affinity(visual)
    classes = {
        "Moonlight": "Moon Scribe",
        "Ember": "Flame Vanguard",
        "Solar": "Sunweaver",
        "Verdant": "Grove Warden",
        "Tidal": "Tide Oracle",
        "Astral": "Star Arcanist",
        "Bloom": "Heart Enchanter",
    }
    return classes[affinity]


def style_compatibility(left: ProfileVisual, right: ProfileVisual) -> int:
    """Strictly score palette chemistry, quality, harmony, and styling balance."""

    left_rgb = ProfileAestheticService._rgb(left.palette[0])
    right_rgb = ProfileAestheticService._rgb(right.palette[0])
    primary_distance = sum(abs(a - b) for a, b in zip(left_rgb, right_rgb, strict=True)) / 765
    palette_distances = []
    for left_color, right_color in zip(left.palette[:4], right.palette[:4], strict=True):
        left_channels = ProfileAestheticService._rgb(left_color)
        right_channels = ProfileAestheticService._rgb(right_color)
        palette_distances.append(
            sum(abs(a - b) for a, b in zip(left_channels, right_channels, strict=True)) / 765
        )
    palette_distance = sum(palette_distances) / len(palette_distances)

    # A controlled contrast scores better than either identical palettes or a
    # completely unrelated clash. Perfect chemistry is intentionally difficult.
    color_chemistry = max(
        0,
        100 - abs((primary_distance * 0.6 + palette_distance * 0.4) - 0.32) * 145,
    )
    quality = (left.overall_score + right.overall_score) / 2
    harmony = (left.harmony_score + right.harmony_score) / 2
    balance = 100 - abs(left.overall_score - right.overall_score)
    raw_score = color_chemistry * 0.40 + quality * 0.25 + harmony * 0.20 + balance * 0.15
    return max(10, min(96, round(raw_score * 0.90)))
