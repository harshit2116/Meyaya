"""Embed helpers used by multiple cogs."""

from __future__ import annotations

from typing import Protocol

import discord


class ProfileSummaryLike(Protocol):
    """Profile data needed to render a user profile."""

    total_given: int
    total_received: int
    favorite_interaction: str | None
    most_interacted_member_id: int | None


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


def build_profile_embed(target: discord.Member, summary: ProfileSummaryLike) -> discord.Embed:
    """Create the profile embed shared by slash and text commands."""

    best_friend = (
        f"<@{summary.most_interacted_member_id}>"
        if summary.most_interacted_member_id
        else "*No one yet...*"
    )
    favorite = summary.favorite_interaction or "None yet"

    embed = discord.Embed(
        color=0xF48FB1,
        description=(
            "## 🌸 Profile\n\n"
            f"### {target.display_name}\n\n"
            f"❤️ **Given Interaction** • **{summary.total_given:,}**\n"
            f"💌 **Received Interaction** • **{summary.total_received:,}**\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🏆 **Favorite**\n"
            f"> 💋 {favorite}\n\n"
            "💕 **Favorite Person**\n"
            f"> {best_friend}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✨ *{target.display_name} has shared lots of affection!*"
        ),
    )
    embed.set_thumbnail(url=str(target.display_avatar.url))
    embed.set_footer(
        text="Meyaya • Spread love 🌸",
        icon_url=str(target.display_avatar.url),
    )
    return embed


def build_ship_embed(
    user_a: "discord.Member | discord.User",
    user_b: "discord.Member | discord.User",
    percentage: int,
    label: str,
    gif_url: str,
    attachment_filename: str,
) -> "discord.Embed":
    """Builds the big embed for /ship. Expects the composite side-by-side
    avatar image to already be attached to the message as `attachment_filename`.
    """
    filled = "❤️" * (percentage // 10)
    empty = "🤍" * (10 - percentage // 10)
    bar = filled + empty

    if percentage >= 70:
        color = 0xFF4D6D
    elif percentage >= 40:
        color = 0xFF8FA3
    else:
        color = 0x6C757D

    embed = discord.Embed(
        title="💘 Ship Result",
        description=(
            f"**{user_a.display_name}** × **{user_b.display_name}**\n\n"
            f"{bar}\n"
            f"**{percentage}%** — {label}"
        ),
        color=color,
    )
    embed.set_image(url=f"attachment://{attachment_filename}")
    return embed