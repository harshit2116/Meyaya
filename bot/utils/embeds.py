"""Embed helpers used by multiple cogs."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import discord


class MeyayaColors:
    """Shared palette for a consistent, soft Meyaya visual style."""

    PINK = 0xF48FB1
    BLUSH = 0xFFB3C6
    LAVENDER = 0xB197FC
    SKY = 0x74C0FC
    MINT = 0x63E6BE
    SUN = 0xFFD43B
    PEACH = 0xFFA94D
    CORAL = 0xFF6B6B
    MUTED = 0x8D99AE


TONE_COLORS: dict[str, int] = {
    "primary": MeyayaColors.PINK,
    "soft": MeyayaColors.BLUSH,
    "magic": MeyayaColors.LAVENDER,
    "info": MeyayaColors.SKY,
    "success": MeyayaColors.MINT,
    "warning": MeyayaColors.SUN,
    "danger": MeyayaColors.CORAL,
    "muted": MeyayaColors.MUTED,
}


def meyaya_embed(
    title: str,
    description: str | None = None,
    *,
    tone: str = "primary",
    color: int | None = None,
    icon: str | None = None,
) -> discord.Embed:
    """Build a compact themed embed without decorative footer clutter."""

    visible_title = f"{icon} {title}" if icon else title
    return discord.Embed(
        title=visible_title,
        description=description,
        color=color if color is not None else TONE_COLORS.get(tone, MeyayaColors.PINK),
    )


def score_bar(score: int, *, segments: int = 10) -> str:
    """Render the original filled-block score bar for 0-100 results."""

    bounded = min(100, max(0, score))
    filled = min(segments, max(0, (bounded * segments + 50) // 100))
    return "`" + "▰" * filled + "▱" * (segments - filled) + "`"


class ProfileSummaryLike(Protocol):
    """Profile data needed to render a user profile."""

    total_given: int
    total_received: int
    total_interactions: int
    favorite_interaction: str | None
    most_interacted_member_id: int | None
    meyaya: "MeyayaProfileStateLike"
    marriage: "MarriageSummaryLike | None"
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


class MarriageSummaryLike(Protocol):
    partner_id: int
    married_at: datetime
    days_together: int
    next_anniversary: datetime
    days_until_anniversary: int


def build_interaction_embed(
    *,
    title: str,
    description: str,
    color: int,
    gif_url: str | None,
) -> discord.Embed:
    """Create a clean, character-focused social interaction embed."""

    embed = meyaya_embed(title, description, color=color)
    if gif_url:
        embed.set_image(url=gif_url)
    return embed


def build_profile_embed(
    target: discord.Member,
    summary: ProfileSummaryLike,
    visual=None,
) -> discord.Embed:
    """Create a unified profile across Discord, Meyaya, social, and marriage data."""

    best_friend = (
        f"<@{summary.most_interacted_member_id}>"
        if summary.most_interacted_member_id
        else "No one yet"
    )
    favorite = summary.favorite_interaction or "None yet"
    nickname = f'\nNickname - **"{summary.meyaya.nickname}"**' if summary.meyaya.nickname else ""
    mood_emoji = {
        "normal": "🌸",
        "happy": "😊",
        "sleepy": "😴",
        "annoyed": "😤",
        "chaotic": "😈",
        "jealous": "💚",
    }.get(summary.meyaya.mood, "🌸")

    embed = meyaya_embed(
        f"{target.display_name}'s Profile",
        f"{target.mention}\n" + "  •  ".join(summary.titles),
        icon="🌸",
    )
    if visual is not None:
        embed.color = discord.Color(int(visual.palette[0][1:], 16))
    embed.add_field(
        name="Meyaya's bond",
        value=(
            f"**{summary.meyaya.relationship.capitalize()}**{nickname}\n\n"
            f"Familiarity  {_profile_bar(summary.meyaya.familiarity)} `{summary.meyaya.familiarity}%`\n"
            f"Affection    {_profile_bar(summary.meyaya.affection)} `{summary.meyaya.affection}%`\n"
            f"Tension      {_profile_bar(summary.meyaya.user_annoyance)} `{summary.meyaya.user_annoyance}%`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Meyaya right now",
        value=(
            f"{mood_emoji} **{summary.meyaya.mood.title()}**\n"
            f"Energy `{summary.meyaya.energy}%`  •  Irritation `{summary.meyaya.global_annoyance}%`"
        ),
        inline=True,
    )
    embed.add_field(
        name="Social activity",
        value=(
            f"**{summary.total_interactions:,}** total interactions\n"
            f"Given **{summary.total_given:,}**  •  Received **{summary.total_received:,}**\n"
            f"Favorite: **{favorite.title()}**\nClosest: {best_friend}"
        ),
        inline=True,
    )
    if summary.marriage is None:
        marriage_value = "Single in the Meyaya universe"
    else:
        marriage_value = (
            f"Married to <@{summary.marriage.partner_id}>\n"
            f"Together **{summary.marriage.days_together:,} days**\n"
            f"Since <t:{int(summary.marriage.married_at.timestamp())}:D>\n"
            f"Anniversary <t:{int(summary.marriage.next_anniversary.timestamp())}:R>"
        )
    embed.add_field(name="Marriage", value=marriage_value, inline=False)
    joined = (
        f"<t:{int(target.joined_at.timestamp())}:D>" if target.joined_at is not None else "Unknown"
    )
    embed.add_field(
        name="Discord",
        value=(
            f"Joined server {joined}\n"
            f"Account created <t:{int(target.created_at.timestamp())}:D>"
        ),
        inline=False,
    )
    if visual is not None:
        style_parts = [
            f"Aura **{visual.palette[0].upper()}**",
            "Decoration ✓" if visual.has_decoration else "No avatar decoration",
            "Banner ✓" if visual.has_banner else "No banner",
        ]
        embed.add_field(name="Profile style", value="  •  ".join(style_parts), inline=False)
    embed.set_thumbnail(url=str(target.display_avatar.url))
    return embed


def _profile_bar(value: int) -> str:
    return score_bar(value, segments=5)


def build_ship_embed(
    user_a: "discord.Member | discord.User",
    user_b: "discord.Member | discord.User",
    percentage: int,
    label: str,
    attachment_filename: str | None,
) -> "discord.Embed":
    """Build a compact ship result with one fresh score and no external GIF."""

    if percentage >= 70:
        color = 0xFF4D6D
    elif percentage >= 40:
        color = 0xFF8FA3
    else:
        color = 0x6C757D

    embed = meyaya_embed(
        f"{user_a.display_name} × {user_b.display_name}",
        description=(
            f"## {percentage}% compatibility\n"
            f"{score_bar(percentage)}\n\n"
            f"**Meyaya says:** {label}"
        ),
        color=color,
        icon="💞",
    )
    if attachment_filename:
        embed.title = None
        embed.description = None
        embed.set_image(url=f"attachment://{attachment_filename}")
    return embed
