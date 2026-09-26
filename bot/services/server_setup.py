"""Persist the guided setup using the existing server settings tables."""

from sqlalchemy.dialects.postgresql import insert

from bot.models.guild_settings import GuildSettings
from bot.models.moderation import ModerationSettings
from bot.repositories.guild_settings import GuildSettingsRepository

MODERATION_FEATURES = ("probation", "cross_spam", "anti_invite")


async def load_setup(bot, guild_id):
    async with bot.db_session() as session:
        settings = await session.get(GuildSettings, guild_id)
        moderation = await session.get(ModerationSettings, guild_id)
        return {
            "chat_channel_id": settings.chat_channel_id if settings else None,
            "autoresponder": settings.autoresponder_enabled if settings else False,
            **{name: getattr(moderation, name) if moderation else True for name in MODERATION_FEATURES},
        }


async def save_setup(bot, guild_id, actor_id, choices):
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
