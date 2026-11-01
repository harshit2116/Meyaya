"""One native profile card, composed without fetching images or member data."""

import discord


def safe(value, limit=350):
    return discord.utils.escape_mentions(
        discord.utils.escape_markdown(" ".join(str(value).split())[:limit])
    )


def meter(value):
    value = max(0, min(100, int(value)))
    filled = round(value / 20)
    return f'`{"▰"*filled}{"▱"*(5-filled)}` **{value}%**'


def build_profile_card(target, summary, visual, *, media=True):
    """Keep artwork, live stats and metadata inside a single V2 container."""
    accent = int(visual.palette[0][1:], 16)
    state = summary.meyaya
    parts = []
    if media:
        parts.append(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    "attachment://meyaya-profile.png",
                    description=f"{target.display_name[:80]} · Meyaya profile",
                )
            )
        )
    username = getattr(visual, "username", "")
    identity = (f"## {safe(target.display_name, 80)}\n" if not media else "") + f"<@{target.id}>"
    if username:
        identity += f" · @{safe(username, 32)}"
    if summary.titles:
        identity += "\n" + " · ".join(safe(title, 60) for title in summary.titles[:3])
    parts.extend(
        (
            discord.ui.TextDisplay(identity),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "### 🌸 Meyaya’s bond\n"
                f"**{safe(state.relationship, 160)}**"
                + (f"\nShe calls you **{safe(state.nickname, 80)}**" if state.nickname else "")
                + f"\n\n📖 Familiarity  {meter(state.familiarity)}\n"
                f"💗 Affection  {meter(state.affection)}\n"
                f"⚡ Tension  {meter(state.user_annoyance)}"
            ),
        )
    )
    mood_icon = {
        "normal": "🌸",
        "happy": "😊",
        "sleepy": "😴",
        "annoyed": "😤",
        "chaotic": "😈",
        "jealous": "💚",
    }.get(state.mood, "🌸")
    parts.append(
        discord.ui.TextDisplay(
            f"### {mood_icon} Meyaya right now\n"
            f"**{safe(state.mood.title(), 24)}** · Energy **{max(0, min(100, int(state.energy)))}%** · "
            f"Irritation **{max(0, min(100, int(state.global_annoyance)))}%**"
        )
    )
    closest = (
        f"<@{summary.most_interacted_member_id}>"
        if summary.most_interacted_member_id
        else "A shared story is still beginning."
    )
    parts.extend(
        (
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "### 👥 Social activity\n"
                f"**{summary.total_interactions:,}** total interactions\n"
                f"Given **{summary.total_given:,}** · Received **{summary.total_received:,}**\n"
                f'Favorite interaction: **{safe((summary.favorite_interaction or "None yet").title(), 50)}**\n'
                f"Closest person: {closest}"
            ),
        )
    )
    marriage = summary.marriage
    marriage_text = (
        "Single in the Meyaya universe"
        if marriage is None
        else (
            f"Married to <@{marriage.partner_id}> · **{marriage.days_together:,} days** together\n"
            f"Since <t:{int(marriage.married_at.timestamp())}:D> · Anniversary <t:{int(marriage.next_anniversary.timestamp())}:R>"
        )
    )
    joined = f"<t:{int(target.joined_at.timestamp())}:D>" if target.joined_at else "Unknown"
    parts.extend(
        (
            discord.ui.TextDisplay("### 💍 Marriage\n" + marriage_text),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "### ✦ Discord\n"
                f"Joined server: {joined}\nAccount created: <t:{int(target.created_at.timestamp())}:D>"
            ),
        )
    )
    parts.extend(
        (
            discord.ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "-# 🎨 Profile style\n"
                f"-# Aura **{visual.palette[0].upper()}** · "
                f'Decoration **{"Enabled" if visual.has_decoration else "None"}** · '
                f'Banner **{"Enabled" if visual.has_banner else "None"}**'
            ),
        )
    )
    return discord.ui.Container(*parts, accent_color=accent)
