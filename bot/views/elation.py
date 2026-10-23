"""Discord V2 stage cards: persistent opening GIF and transient mask animations."""
from pathlib import Path
import discord

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "elation"
MEDIA_SECONDS = {"intro": 3.61, "mask": 3.91}


def scene_view(title, body, kind=None):
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xCF78B7)
    text = discord.ui.TextDisplay(f"## {title}\n{body}")
    if kind != "intro":
        container.add_item(text)
    if kind:
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(
            f"attachment://elation-{kind}.gif", description="Meyaya's Elation performance")))
    if kind == "intro":
        container.add_item(text)
    view.add_item(container)
    return view
