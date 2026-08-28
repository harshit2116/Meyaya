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
    meyaya: "MeyayaProfileStateLike"
    titles: tuple[str, ...]


class MeyayaProfileStateLike(Protocol):
    """Meyaya System data shown on a member profile."""

    mood: str
    energy: int
    global_annoyance: int
    relationship: str
    familiarity: int
    affection: int
    user_annoyance: int
    nickname: str | None
    is_parent: bool
    is_favorite: bool


def build_interaction_embed(
    *,
    title: str,
    description: str,
    color: int,
    gif_url: str | None,
) -> discord.Embed:
    """Create a clean, character-focused social interaction embed."""

    embed = discord.Embed(title=title, description=description, color=color)
    if gif_url:
        embed.set_image(url=gif_url)
    embed.set_footer(text="Meyaya • Share the moment 🌸")
    return embed


def build_profile_embed(target: discord.Member, summary: ProfileSummaryLike) -> discord.Embed:
    """Create the profile embed shared by slash and text commands."""

    best_friend = (
        f"<@{summary.most_interacted_member_id}>"
        if summary.most_interacted_member_id
        else "*No one yet...*"
    )
    favorite = summary.favorite_interaction or "None yet"
    nickname = f'\n**Nickname** - "{summary.meyaya.nickname}"' if summary.meyaya.nickname else ""
    mood_emoji = {
        "normal": "🌸",
        "happy": "😊",
        "sleepy": "😴",
        "annoyed": "😤",
        "chaotic": "😈",
        "jealous": "💚",
    }.get(summary.meyaya.mood, "🌸")

    embed = discord.Embed(
        title=f"🌸 {target.display_name}'s Profile",
        color=0xF48FB1,
        description=f"How Meyaya knows {target.mention} and their shared server story.",
    )
    embed.add_field(
        name="💗 Meyaya's bond",
        value=(
            f"**{summary.meyaya.relationship.capitalize()}**{nickname}\n"
            f"Familiarity - `{summary.meyaya.familiarity}%`\n"
            f"Affection - `{summary.meyaya.affection}%`\n"
            f"Tension - `{summary.meyaya.user_annoyance}%`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🏅 Titles",
        value="\n".join(summary.titles),
        inline=False,
    )
    embed.add_field(
        name="✨ Meyaya right now",
        value=(
            f"{mood_emoji} Mood - **{summary.meyaya.mood.title()}**\n"
            f"⚡ Energy - `{summary.meyaya.energy}%`\n"
            f"💢 Irritation - `{summary.meyaya.global_annoyance}%`"
        ),
        inline=False,
    )
    embed.add_field(
        name="📊 Interactions",
        value=(
            f"Given - **{summary.total_given:,}** | Received - **{summary.total_received:,}**\n"
            f"Favorite - **{favorite}**\n"
            f"Closest interaction partner - {best_friend}"
        ),
        inline=False,
    )
    embed.set_thumbnail(url=str(target.display_avatar.url))
    embed.set_footer(
        text="Meyaya - Mood and relationships 🌸",
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
            f"**{percentage}% love**\n"
            f"{label}"
        ),
        color=color,
    )
    embed.set_image(url=f"attachment://{attachment_filename}")
    if gif_url:
        embed.set_thumbnail(url=gif_url)
    embed.set_footer(text="A tiny love calculation from Meyaya")
    return embed
