"""Embed helpers used by multiple cogs."""

from __future__ import annotations

import discord


def build_interaction_embed(
    *,
    title: str,
    description: str,
    color: int,
    actor_avatar: str,
    target_avatar: str,
    gif_url: str | None,
    count_label: str,
    count: int,
) -> discord.Embed:
    """Create a polished interaction embed."""

    embed = discord.Embed(title=title, description=description, color=color)
    embed.add_field(name="Shared Count", value=f"**{count_label}: {count}**", inline=False)
    embed.set_author(name="Actor", icon_url=actor_avatar)
    embed.set_thumbnail(url=target_avatar)
    if gif_url:
        embed.set_image(url=gif_url)
    return embed
