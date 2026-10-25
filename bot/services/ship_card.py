"""Validated avatar decoding and routing for local social cards."""

from io import BytesIO
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
    first, second, name_one, name_two, percentage=50, verdict="A cute little maybe", *, theme="ship"
):
    if theme == "besties":
        from bot.services.bestie_scrapbook import render_scrapbook

        return render_scrapbook(first, second, name_one, name_two, percentage, verdict)
    from bot.services.ship_letter import render_letter

    return render_letter(first, second, name_one, name_two, percentage, verdict)
