"""Validated avatar decoding and routing for local social cards."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from typing import cast

from PIL import Image


def valid_avatar(data: bytes) -> bool:
    """Reject broken CDN responses before they enter the ten-minute cache."""
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > 4_000_000:
                return False
            source.load()
        return True
    except (OSError, ValueError):
        return False


def render_ship_card(
    first: bytes,
    second: bytes,
    name_one: str,
    name_two: str,
    percentage: int = 50,
    verdict: str = "A cute little maybe",
    *,
    theme: str = "ship",
) -> bytes:
    if theme == "besties":
        from bot.services.bestie_scrapbook import render_scrapbook

        renderer = cast(Callable[[bytes, bytes, str, str, int, str], bytes], render_scrapbook)
        return renderer(first, second, name_one, name_two, percentage, verdict)
    from bot.services.ship_letter import render_letter

    return render_letter(first, second, name_one, name_two, percentage, verdict)
