"""Native profile sections: no remote images or data fetches during composition."""

import discord


def safe(value, limit=350):
    return discord.utils.escape_mentions(
        discord.utils.escape_markdown(" ".join(str(value).split())[:limit])
    )


def meter(value):
    value = max(0, min(100, int(value)))
    filled = round(value / 20)
    return f'`{"▰"*filled}{"▱"*(5-filled)}` **{value}%**'


def sections(target, summary, visual, *, media=True):
    accent = int(visual.palette[0][1:], 16)
    state = summary.meyaya
    identity = []
    if media:
        identity.append(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    "attachment://meyaya-profile.png",
                    description=f"{target.display_name} · Meyaya profile",
                )
            )
        )
    identity.extend(
        (
            discord.ui.TextDisplay(
                f"<@{target.id}>"
                + (
                    "\n" + " · ".join(safe(title, 100) for title in summary.titles)
                    if summary.titles
                    else ""
                )
            ),
            discord.ui.TextDisplay(
                "### 🌸 Meyaya’s bond\n> "
                + safe(state.relationship)
                + (f"\nNickname: **{safe(state.nickname)}**" if state.nickname else "")
            ),
            discord.ui.TextDisplay(
                f"📖 Familiarity  {meter(state.familiarity)}\n"
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
    mood = discord.ui.Container(
        discord.ui.TextDisplay(
            f"### 🌸 Meyaya right now\n{mood_icon} **{safe(state.mood.title())}**"
        ),
        discord.ui.TextDisplay(
            f"⚡ Energy  {meter(state.energy)}\n💢 Irritation  {meter(state.global_annoyance)}"
        ),
        accent_color=accent,
    )
    closest = (
        f"<@{summary.most_interacted_member_id}>"
        if summary.most_interacted_member_id
        else "A shared story is still beginning."
    )
    social = discord.ui.Container(
        discord.ui.TextDisplay(
            "### 👥 Social activity\n"
            f"**{summary.total_interactions:,}** total interactions\n"
            f"Given **{summary.total_given:,}** · Received **{summary.total_received:,}**"
        ),
        discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(
            f'💗 Favorite interaction: **{safe((summary.favorite_interaction or "None yet").title())}**\n'
            f"Closest person: {closest}"
        ),
        accent_color=accent,
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
    details = discord.ui.Container(
        discord.ui.TextDisplay("### 💍 Marriage\n" + marriage_text),
        discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(
            "### Discord\n"
            f"Joined server: {joined}\nAccount created: <t:{int(target.created_at.timestamp())}:D>"
        ),
        accent_color=accent,
    )
    style = discord.ui.Container(
        discord.ui.TextDisplay(
            "### 🎨 Profile style\n"
            f"Aura **{visual.palette[0].upper()}** · "
            f'Decoration **{"Enabled" if visual.has_decoration else "None"}** · '
            f'Banner **{"Enabled" if visual.has_banner else "None"}**'
        ),
        accent_color=accent,
    )
    return [discord.ui.Container(*identity, accent_color=accent), mood, social, details, style]
