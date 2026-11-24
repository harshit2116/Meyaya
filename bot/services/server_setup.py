"""Persist the guided setup using the existing server settings tables."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from bot.models.guild_settings import GuildSettings
from bot.models.moderation import ModerationSettings
from bot.repositories.guild_settings import GuildSettingsRepository

MODERATION_FEATURES = ("probation", "cross_spam", "anti_invite")
CORE_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("view_channel", "View Channel"),
    ("send_messages", "Send Messages"),
    ("send_messages_in_threads", "Send Messages in Threads"),
    ("embed_links", "Embed Links"),
    ("attach_files", "Attach Files"),
    ("read_message_history", "Read Message History"),
    ("use_external_emojis", "Use External Emojis"),
)


def permission_checklist(
    guild: Any,
    *,
    channel_id: int | None = None,
    moderation_enabled: bool = True,
) -> str | None:
    """Return a concise summary of Meyaya's Discord permissions in this server."""
    me = getattr(guild, "me", None)
    if me is None:
        return None
    channel = guild.get_channel(channel_id) if channel_id and hasattr(guild, "get_channel") else None
    permissions_for = getattr(channel, "permissions_for", None)
    perms = permissions_for(me) if callable(permissions_for) else getattr(me, "guild_permissions", None)
    if perms is None:
        return None
    missing_core = [label for attr, label in CORE_PERMISSIONS if not getattr(perms, attr, False)]
    lines: list[str] = []
    if missing_core:
        lines.append(
            "Missing core: "
            + ", ".join(missing_core)
            + " (cards, embeds, voice clips, or threads may not work until granted)."
        )
    else:
        lines.append("Core permissions look good (chat, cards, files, threads, emojis).")
    if moderation_enabled and not getattr(perms, "manage_messages", False):
        lines.append("Missing moderation: Manage Messages (required for probation/spam/invite deletion).")
    return "\n".join(lines)


async def load_setup(bot: Any, guild_id: int) -> dict[str, Any]:
    async with bot.db_session() as session:
        settings = await session.get(GuildSettings, guild_id)
        moderation = await session.get(ModerationSettings, guild_id)
        return {
            "chat_channel_id": settings.chat_channel_id if settings else None,
            "autoresponder": settings.autoresponder_enabled if settings else False,
            **{name: getattr(moderation, name) if moderation else True for name in MODERATION_FEATURES},
        }


async def save_setup(
    bot: Any, guild_id: int, actor_id: int, choices: Mapping[str, Any]
) -> None:
    """Commit all choices together; leave quota, prefix and raid state untouched."""
    async with bot.db_session() as session:
        repository = GuildSettingsRepository(session)
        await repository.set_chat_channel(guild_id, choices["chat_channel_id"], actor_id)
        await repository.set_autoresponder(guild_id, choices["autoresponder"], actor_id)
        values = {name: bool(choices[name]) for name in MODERATION_FEATURES}
        await session.execute(
            insert(ModerationSettings).values(guild_id=guild_id, **values)
            .on_conflict_do_update(index_elements=[ModerationSettings.guild_id], set_=values)
        )
        # Recover the cache safely if startup could not load it.
        channels = await repository.list_chat_channels() if bot._guild_chat_channels is None else None
        await session.commit()
    if channels is not None:
        bot._guild_chat_channels = channels
    else:
        bot._guild_chat_channels[guild_id] = choices["chat_channel_id"]
    bot.cache_autoresponder(guild_id, choices["autoresponder"])
    moderation = bot.get_cog("ModerationCog")
    if moderation is not None:
        moderation._settings.pop(guild_id, None)
