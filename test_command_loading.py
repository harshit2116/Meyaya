"""All command dispatch paths share delayed loading, not AI conversations."""

import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
from discord import app_commands
from discord.ext import commands
import pytest

from bot.utils.loading import install_command_loading, LOADING_DELAY


@pytest.mark.asyncio
async def test_unlisted_prefix_and_standalone_slash_get_delayed_loading():
    bot = commands.Bot(command_prefix="uwu ", intents=discord.Intents.none())
    loaded = NS(delete=AsyncMock())
    channel = NS(guild=NS(id=1, stickers=[]), send=AsyncMock(return_value=loaded))
    @bot.command(name="unlisted")
    async def unlisted(ctx):
        await asyncio.sleep(LOADING_DELAY + .1)
    async def slash(interaction):
        await asyncio.sleep(LOADING_DELAY + .1)
    app = app_commands.Command(name="standalone", description="Test", callback=slash)
    bot.tree.add_command(app)
    install_command_loading(bot)
    callback = app.callback
    install_command_loading(bot)
    assert app.callback is callback
    try:
        await unlisted.callback(NS(channel=channel, interaction=None))
        channel.send.assert_awaited_once()
        loaded.delete.assert_awaited_once()
        channel.send.reset_mock()
        loaded.delete.reset_mock()
        await app._do_call(NS(channel=channel), {})
        channel.send.assert_awaited_once()
        loaded.delete.assert_awaited_once()
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_fast_command_stays_quiet_and_private_defer_is_preserved():
    bot = commands.Bot(command_prefix="uwu ", intents=discord.Intents.none())
    @bot.hybrid_command(name="private_test")
    async def private_test(ctx):
        await ctx.defer(ephemeral=True)
    channel = NS(send=AsyncMock())
    ctx = NS(channel=channel, interaction=NS(response=NS(is_done=Mock(return_value=False))), defer=AsyncMock())
    install_command_loading(bot)
    try:
        await private_test.app_command._do_call(ctx, {})
        ctx.defer.assert_awaited_once_with(ephemeral=True)
        channel.send.assert_not_awaited()
        assert ctx._meyaya_loader is None
    finally:
        await bot.close()
