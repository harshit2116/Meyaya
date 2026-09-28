"""Application-owned emojis, fetched once rather than on the reply hot path."""
import asyncio
import logging

import discord

logger = logging.getLogger(__name__)


async def load_application_emojis(bot):
    try:
        async with asyncio.timeout(5):
            emojis = await bot.fetch_application_emojis()
        bot.meyaya_application_emojis = tuple(emojis)
        logger.info('Loaded %s application emojis', len(emojis))
    except (discord.HTTPException, discord.MissingApplicationID, TimeoutError, OSError) as error:
        logger.warning('Application emojis unavailable: %s', type(error).__name__)


def application_emojis(bot):
    return tuple(item for item in getattr(bot, 'meyaya_application_emojis', ())
                 if item.name and item.available)


def loading_emoji(bot):
    return next((item for item in application_emojis(bot)
                 if item.name.casefold() == 'meyaya_loading'), None)
