"""Safe, off-loop Discord image attachment preparation for Gemini chat vision."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from io import BytesIO
import logging
from pathlib import PurePosixPath
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from bot.logging.telemetry import event
from bot.services.llm import ImageAttachment
from bot.utils.image_work import ImageBusy, image_work

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
SUPPORTED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
MAX_RAW_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_EDGE = 1024
MAX_IMAGES_PER_TURN = 2
ATTACHMENT_READ_TIMEOUT = 4.0


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
    """Fast synchronous check for at least one viewable image on a Discord message."""
    attachments = getattr(message, "attachments", None) or ()
    return any(is_image_attachment(att) for att in attachments)


def _normalize_image_bytes(raw: bytes, filename: str) -> ImageAttachment | None:
    """Decode, orient, resize, and re-encode an image to compact JPEG off the event loop."""
    if not raw or len(raw) > MAX_RAW_IMAGE_BYTES:
        return None
    try:
        with Image.open(BytesIO(raw)) as opened:
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
    except (UnidentifiedImageError, OSError, ValueError):
        return None


async def extract_chat_images(
    messages: Sequence[Any],
    *,
    replied_message: Any = None,
    max_images: int = MAX_IMAGES_PER_TURN,
) -> list[ImageAttachment]:
    """Download and normalize up to max_images Discord attachments for one chat turn."""
    candidates: list[Any] = []
    for msg in messages:
        for att in getattr(msg, "attachments", None) or ():
            if is_image_attachment(att):
                candidates.append(att)
                if len(candidates) >= max_images:
                    break
        if len(candidates) >= max_images:
            break

    if len(candidates) < max_images and replied_message is not None:
        for att in getattr(replied_message, "attachments", None) or ():
            if is_image_attachment(att):
                candidates.append(att)
                if len(candidates) >= max_images:
                    break

    if not candidates:
        return []

    prepared: list[ImageAttachment] = []
    for att in candidates:
        read_fn = getattr(att, "read", None)
        if not callable(read_fn):
            continue
        filename = str(getattr(att, "filename", "") or "image")
        try:
            raw = await asyncio.wait_for(read_fn(), timeout=ATTACHMENT_READ_TIMEOUT)
            if not isinstance(raw, (bytes, bytearray)) or not raw:
                continue
            normalized = await image_work(_normalize_image_bytes, bytes(raw), filename)
            if normalized is not None:
                prepared.append(normalized)
        except (TimeoutError, ImageBusy, Exception) as exc:
            logger.debug("Chat image preparation skipped (%s)", type(exc).__name__)
    if prepared:
        event("chat_vision_attached", count=len(prepared))
    return prepared
