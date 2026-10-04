"""Acknowledge orphaned game buttons after timeout/restart, without replaying moves."""

import discord


async def reply_to_expired_game(bot, interaction):
    if interaction.type != discord.InteractionType.component:
        return
    message = getattr(interaction, "message", None)
    user = getattr(bot, "user", None)
    if not message or not user or message.author.id != user.id:
        return
    custom_id = (interaction.data or {}).get("custom_id", "")
    footer = " ".join(embed.footer.text or "" for embed in message.embeds)
    recognized = custom_id.startswith(("meyaya:scramble:", "meyaya:solo:", "meyaya:duel:")) or (
        "Only the player who started this puzzle" in footer
        or "Ends after 3 minutes without a choice" in footer
        or "Replay available for 3 minutes" in footer
    )
    if not recognized:
        return
    # Normal View dispatch owns the acknowledgement while a session is alive.
    # Never compete with its pending defer, including queued/stale turn clicks.
    for cog_name, attribute in (
        ("FunCog", "scramble_views"),
        ("SoloGamesCog", "views"),
        ("FantasyCog", "views"),
    ):
        cog = bot.get_cog(cog_name)
        for view in getattr(cog, attribute, ()):
            owns_message = getattr(getattr(view, "message", None), "id", None) == message.id
            owns_id = custom_id.startswith(
                (
                    f"meyaya:scramble:{view.id}:",
                    f"meyaya:solo:{view.id}:",
                    f"meyaya:duel:{getattr(view, 'token', '')}:",
                )
            )
            if (owns_message or owns_id) and not view.is_finished():
                return
    if interaction.response.is_done():
        return
    try:
        await interaction.response.send_message(
            "This game has expired or Meyaya restarted. Start a fresh run with `/versus`, `/scramble`, `/escape`, `/detective` or `/personalitytest`.",
            ephemeral=True,
        )
    except (discord.InteractionResponded, discord.HTTPException):
        # Another callback may already have acknowledged an in-flight click.
        pass
