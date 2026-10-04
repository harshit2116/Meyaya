"""One best-effort cosmetic style per joined guild, without recurring sync."""

import asyncio
import logging

import discord
from discord.http import Route

logger = logging.getLogger(__name__)
STYLE_PAYLOAD = {
    "display_name_font_id": 16,  # Observed Journal ID, not a documented stable enum.
    "display_name_effect_id": 2,  # Observed Gradient ID.
    "display_name_colors": [0xEEB2AA, 0xE36DE0],  # Screenshot peach-to-pink endpoints.
}


async def apply_guild_name_style(bot, guild) -> None:
    if not hasattr(bot, "_guild_name_style_lock"):
        bot._guild_name_style_lock = asyncio.Lock()
        bot._guild_name_style_attempted = set()
    async with bot._guild_name_style_lock:
        if guild.unavailable or guild.id in bot._guild_name_style_attempted:
            return
        bot._guild_name_style_attempted.add(guild.id)
        await _request_style(bot, guild.id)


async def apply_all_guild_name_styles(bot) -> None:
    for guild in tuple(bot.guilds):
        await apply_guild_name_style(bot, guild)


async def _request_style(bot, guild_id) -> None:
    try:
        async with asyncio.timeout(15):
            result = await bot.http.request(
                Route("PATCH", "/guilds/{guild_id}/members/@me", guild_id=guild_id),
                json={
                    **STYLE_PAYLOAD,
                    "display_name_colors": list(STYLE_PAYLOAD["display_name_colors"]),
                },
            )
        # A 2xx can still silently ignore experimental fields. Don't claim the
        # member's visual styling was verified if the returned member omits them.
        echoed = isinstance(result, dict) and all(
            result.get(key) == value for key, value in STYLE_PAYLOAD.items()
        )
        logger.info(
            "guild_name_style request_succeeded guild_id=%s style_echoed=%s", guild_id, echoed
        )
        if not echoed:
            logger.warning(
                "guild_name_style guild_id=%s reason=style_fields_not_echoed_verify_in_Discord",
                guild_id,
            )
    except discord.HTTPException as error:
        # Discord's API text explains unsupported fields/permissions. Redact
        # credentials defensively and never log the full response/configuration.
        reason = " ".join(str(error.text).split())
        token = getattr(bot.settings, "discord_token", None)
        if token:
            reason = reason.replace(token, "[redacted]")
        logger.warning(
            "guild_name_style failed guild_id=%s status=%s code=%s reason=%s",
            guild_id,
            error.status,
            error.code,
            reason[:300],
        )
    except Exception as error:
        # Cosmetic errors (including connection failures) must not break ready.
        logger.warning(
            "guild_name_style failed guild_id=%s status=unknown code=unknown reason=%s",
            guild_id,
            type(error).__name__,
        )
