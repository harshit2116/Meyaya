"""Safe, off-loop Discord image attachment preparation for Gemini chat vision."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from io import BytesIO
import logging
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import aiohttp
from PIL import Image, ImageOps, UnidentifiedImageError

from bot.logging.telemetry import event
from bot.services.llm import ImageAttachment
from bot.utils.image_work import ImageBusy, image_work

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
SUPPORTED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
ALLOWED_MEDIA_HOSTS = frozenset(
    {
        "cdn.discordapp.com",
        "media.discordapp.net",
        "images-ext-1.discordapp.net",
        "images-ext-2.discordapp.net",
        "media.tenor.com",
        "media1.tenor.com",
        "c.tenor.com",
        "media.giphy.com",
        "i.imgur.com",
        "pbs.twimg.com",
        "static.klipy.com",
    }
)
MAX_RAW_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_EDGE = 1024
MAX_IMAGES_PER_TURN = 2
ATTACHMENT_READ_TIMEOUT = 4.0


def is_safe_media_url(url: str) -> bool:
    """Allow only HTTPS image URLs on trusted Discord/GIF/media CDNs (no redirects/SSRF)."""
    if not url or len(url) > 2048:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port is not None:
        return False
    host = (parsed.hostname or "").casefold()
    if host in ALLOWED_MEDIA_HOSTS:
        return True
    return host.startswith("images-ext-") and host.endswith(".discordapp.net")


def _extract_media_urls(message: Any) -> list[tuple[str, str]]:
    """Collect safe embed image/thumbnail URLs and raster sticker URLs from a Discord message."""
    urls: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(url: str | None, label: str) -> None:
        if not isinstance(url, str) or not url or url in seen:
            return
        if is_safe_media_url(url):
            seen.add(url)
            urls.append((url, label))

    for embed in getattr(message, "embeds", None) or ():
        image = getattr(embed, "image", None)
        if image is not None:
            _add(getattr(image, "proxy_url", None) or getattr(image, "url", None), "embed.png")
        thumb = getattr(embed, "thumbnail", None)
        if thumb is not None:
            _add(getattr(thumb, "proxy_url", None) or getattr(thumb, "url", None), "embed-thumb.png")

    for sticker in getattr(message, "stickers", None) or ():
        fmt = str(getattr(getattr(sticker, "format", None), "name", "") or "").casefold()
        if fmt == "lottie":
            continue
        name = str(getattr(sticker, "name", "") or "sticker")[:60]
        _add(getattr(sticker, "url", None), f"sticker-{name}.png")

    return urls


def is_image_attachment(attachment: Any) -> bool:
    """Return True when a Discord attachment is a bounded, viewable image."""
    size = getattr(attachment, "size", 0)
    if isinstance(size, int) and size > MAX_RAW_IMAGE_BYTES:
        return False
    content_type = str(getattr(attachment, "content_type", "") or "").split(";", 1)[0].strip().casefold()
    if content_type in SUPPORTED_CONTENT_TYPES:
        return True
    filename = str(getattr(attachment, "filename", "") or "")
    return PurePosixPath(filename).suffix.casefold() in SUPPORTED_IMAGE_SUFFIXES


def has_viewable_images(message: Any) -> bool:
    """Fast synchronous check for at least one viewable attachment, embed image, or sticker."""
    attachments = getattr(message, "attachments", None) or ()
    if any(is_image_attachment(att) for att in attachments):
        return True
    return bool(_extract_media_urls(message))


def _normalize_image_bytes(raw: bytes, filename: str) -> ImageAttachment | None:
    """Decode, orient, resize, and re-encode an image to compact JPEG off the event loop."""
    if not raw or len(raw) > MAX_RAW_IMAGE_BYTES:
        return None
    try:
        with Image.open(BytesIO(raw)) as opened:
            if (
                opened.width <= 0
                or opened.height <= 0
                or opened.width * opened.height > MAX_IMAGE_PIXELS
            ):
                return None
            opened.load()
            frame = ImageOps.exif_transpose(opened)
            if frame.mode in {"RGBA", "LA"} or (frame.mode == "P" and "transparency" in frame.info):
                rgba = frame.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (24, 24, 28))
                bg.paste(rgba, mask=rgba.getchannel("A"))
                rgb = bg
            else:
                rgb = frame.convert("RGB")
            rgb.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            out = BytesIO()
            rgb.save(out, format="JPEG", quality=82, optimize=True)
            encoded = out.getvalue()
            if not encoded:
                return None
            return ImageAttachment(mime_type="image/jpeg", data=encoded, filename=filename[:120])
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return None


async def _fetch_media_bytes(
    http_session: aiohttp.ClientSession,
    url: str,
) -> bytes | None:
    if not is_safe_media_url(url):
        return None
    try:
        async with http_session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=ATTACHMENT_READ_TIMEOUT),
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                return None
            length = response.content_length
            if length is not None and length > MAX_RAW_IMAGE_BYTES:
                return None
            ctype = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
            if ctype and not ctype.startswith("image/"):
                return None
            buf = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                if len(buf) + len(chunk) > MAX_RAW_IMAGE_BYTES:
                    return None
                buf.extend(chunk)
            return bytes(buf) if buf else None
    except (aiohttp.ClientError, TimeoutError):
        return None


async def extract_chat_images(
    messages: Sequence[Any],
    *,
    replied_message: Any = None,
    http_session: aiohttp.ClientSession | None = None,
    max_images: int = MAX_IMAGES_PER_TURN,
) -> list[ImageAttachment]:
    """Download and normalize up to max_images attachments, embed images, GIF frames, or stickers."""
    # Each candidate is either ("attachment", att) or ("url", (url, label)).
    candidates: list[tuple[str, Any]] = []

    def _collect(msg: Any) -> None:
        if len(candidates) >= max_images:
            return
        for att in getattr(msg, "attachments", None) or ():
            if is_image_attachment(att):
                candidates.append(("attachment", att))
                if len(candidates) >= max_images:
                    return
        if http_session is not None:
            for url_pair in _extract_media_urls(msg):
                candidates.append(("url", url_pair))
                if len(candidates) >= max_images:
                    return

    for msg in messages:
        _collect(msg)
        if len(candidates) >= max_images:
            break

    if len(candidates) < max_images and replied_message is not None:
        _collect(replied_message)

    if not candidates:
        return []

    prepared: list[ImageAttachment] = []
    for kind, item in candidates:
        try:
            if kind == "attachment":
                read_fn = getattr(item, "read", None)
                if not callable(read_fn):
                    continue
                filename = str(getattr(item, "filename", "") or "image")
                raw = await asyncio.wait_for(read_fn(), timeout=ATTACHMENT_READ_TIMEOUT)
                if not isinstance(raw, (bytes, bytearray)) or not raw:
                    continue
                raw_bytes = bytes(raw)
            else:
                if http_session is None:
                    continue
                url, filename = item
                fetched = await _fetch_media_bytes(http_session, url)
                if not fetched:
                    continue
                raw_bytes = fetched
            normalized = await image_work(_normalize_image_bytes, raw_bytes, filename)
            if normalized is not None:
                prepared.append(normalized)
        except (TimeoutError, ImageBusy, Exception) as exc:
            logger.debug("Chat image preparation skipped (%s)", type(exc).__name__)
    if prepared:
        event("chat_vision_attached", count=len(prepared))
    return prepared
