"""Discord V2 stage cards: persistent opening GIF and transient mask animations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import discord

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "elation"
MEDIA_SECONDS: dict[str, float] = {"intro": 3.61, "mask": 3.91}


def scene_view(title: str, body: str, kind: str | None = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container: discord.ui.Container[Any] = discord.ui.Container(accent_color=0xCF78B7)
    text: discord.ui.TextDisplay[Any] = discord.ui.TextDisplay(f"## {title}\n{body}")
    if kind != "intro":
        container.add_item(text)
    if kind:
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    f"attachment://elation-{kind}.gif",
                    description="Meyaya's Elation performance",
                )
            )
        )
    if kind == "intro":
        container.add_item(text)
    view.add_item(container)
    return view
