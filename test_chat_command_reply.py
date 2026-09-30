"""A reply to a command card keeps the result and speaker identities separate."""

import time
from collections import OrderedDict
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import pytest
from discord.ext import commands
from discord.ext.commands.view import StringView

from bot.cogs.chat import ChatCog
from bot.utils.command_context import CommandOutput, TimedContext, command_output_for


def _author(user_id, name):
    return NS(id=user_id, name=name, display_name=name)


@pytest.mark.asyncio
async def test_image_only_command_reply_includes_command_and_invoker():
    bot = NS(user=_author(99, "Meyaya"))
    bot._meyaya_command_outputs = OrderedDict({
        (7, 8): (time.monotonic(), CommandOutput("duck", 11, "Original user")),
    })
    embed = discord.Embed(title="Duck")
    embed.set_image(url="attachment://duck.gif")
    original = NS(id=8, author=bot.user, content="", embeds=[embed],
                  attachments=[NS(filename="duck.gif")], interaction_metadata=None)
    message = NS(channel=NS(id=7, fetch_message=AsyncMock(return_value=original)),
                 reference=NS(message_id=8, resolved=None))

    context = await ChatCog(bot)._resolve_reply_context(message)
    prompt = ChatCog._reply_aware_prompt(
        ChatCog._speaker_label(_author(22, "Original user")),
        "what happened to me?", context,
    )

    assert 'Original Meyaya command: "duck"' in prompt
    assert "Discord ID 11" in prompt
    assert "Discord user ID 22" in prompt
    assert "image: present" in prompt
    assert "duck.gif" in prompt
    assert "not necessarily the current speaker" in prompt


@pytest.mark.asyncio
async def test_embed_only_result_survives_restart_without_local_command_cache():
    bot = NS(user=_author(99, "Meyaya"))
    embed = discord.Embed(title="Most Likely", description="The scenario: be late")
    embed.add_field(name="Meyaya's pick", value="<@22>")
    original = NS(id=8, author=bot.user, content="", embeds=[embed], attachments=[],
                  interaction_metadata=NS(user=_author(11, "Invoker")))
    message = NS(channel=NS(id=7, fetch_message=AsyncMock(return_value=original)),
                 reference=NS(message_id=8, resolved=None))

    context = await ChatCog(bot)._resolve_reply_context(message)
    prompt = ChatCog._reply_aware_prompt(ChatCog._speaker_label(_author(22, "Responder")),
                                         "why me?", context)
    assert "Most Likely" in prompt
    assert "The scenario: be late" in prompt
    assert "Discord ID 11" in prompt
    assert "Discord user ID 22" in prompt


def test_non_reply_still_labels_verified_current_speaker():
    prompt = ChatCog._reply_aware_prompt(
        ChatCog._speaker_label(_author(22, "Ayaya")), "I am papa", None,
    )
    assert "Discord user ID 22" in prompt
    assert "verified from the incoming Discord message" in prompt
    assert '"I am papa"' in prompt


@pytest.mark.asyncio
async def test_command_send_registers_visible_result_only():
    bot = NS()
    author = _author(11, "Invoker")
    message = NS(_state=NS(), author=author, channel=NS(id=7))
    ctx = TimedContext(message=message, bot=bot, view=StringView(""),
                       command=NS(qualified_name="duck"))
    with patch.object(commands.Context, "send", new=AsyncMock(return_value=NS(id=8))):
        await ctx.send("result")
        assert command_output_for(bot, 7, 8) == CommandOutput("duck", 11, "Invoker")
        await ctx.send("secret", ephemeral=True)
        assert len(bot._meyaya_command_outputs) == 1
