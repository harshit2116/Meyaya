"""Offline GIF, prefix/slash and graceful-avatar coverage for duck."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
from PIL import Image

from bot.cogs.fun import FunCog
from bot.services.duck_card import render_duck, MAX_OUTPUT_BYTES, duck_message


def member(name="Ayaya"):
    asset = NS(url="https://cdn.discordapp.com/avatars/42/test.png?size=128",
               read=AsyncMock(return_value=b"corrupt avatar"))
    asset.with_size = lambda _: asset
    asset.with_format = lambda _: asset
    return NS(id=42, display_name=name, display_avatar=asset)


def test_duck_full_ending_sentence():
    assert duck_message("Ayaya") == "Ayaya is looking for Davey Jones treasure."
    assert duck_message("Ruru") == "Ruru is looking for Davey Jones treasure."


def test_duck_preserves_animation_timeline_and_bounds_payload():
    avatar = BytesIO()
    Image.new("RGB", (128, 128), "#ff6600").save(avatar, format="PNG")
    data = render_duck("Ayaya", avatar.getvalue())
    assert data[:6] == b"GIF89a"
    assert len(data) < MAX_OUTPUT_BYTES
    with Image.open(BytesIO(data)) as gif:
        assert gif.size == (480, 400)
        assert gif.n_frames == 47
        assert gif.info["loop"] == 0
        duration = 0
        for index in range(gif.n_frames):
            gif.seek(index)
            duration += gif.info["duration"]
        assert duration == 6270
        gif.seek(20)
        pixel = gif.convert("RGB").getpixel((253, 140))
        assert pixel[0] > 200 and pixel[1] < 160


def test_corrupt_avatar_and_long_unicode_name_still_render():
    with Image.open(BytesIO(render_duck("🌸" * 100, b"bad"))) as gif:
        assert gif.n_frames == 47
        gif.seek(46)
        gif.load()


@pytest.mark.asyncio
@pytest.mark.parametrize("interaction,explicit", [(None, False), (object(), True)])
async def test_duck_defaults_to_requester_and_supports_target(interaction, explicit, monkeypatch):
    author, target = member(), member("Ruru")
    renderer = lambda name, avatar: b"GIF89a" + name.encode()
    monkeypatch.setattr("bot.services.duck_card.render_duck", renderer)
    ctx = NS(author=author, interaction=interaction, defer=AsyncMock(), send=AsyncMock())
    bot = NS(build_llm_provider=AsyncMock())
    cog = FunCog(bot)
    await FunCog.duck.callback(cog, ctx, member=target if explicit else None)
    ctx.defer.assert_awaited_once()
    sent = ctx.send.await_args.kwargs
    assert sent["file"].filename == "duck.gif"
    assert sent["embed"].title is None
    assert sent["embed"].colour is None
    assert sent["embed"].image.url == "attachment://duck.gif"
    assert sent["file"].fp.read() == b"GIF89a" + ("Ruru" if explicit else "Ayaya").encode()
    assert sent["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    assert cog.duck_slots.pending == 0
    bot.build_llm_provider.assert_not_called()


@pytest.mark.asyncio
async def test_failed_avatar_download_uses_initial_portrait(monkeypatch):
    author = member()
    author.display_avatar.read.side_effect = TimeoutError
    seen = []
    def renderer(name, avatar):
        seen.append(avatar)
        return b"GIF89a"
    monkeypatch.setattr("bot.services.duck_card.render_duck", renderer)
    ctx = NS(author=author, defer=AsyncMock(), send=AsyncMock())
    await FunCog.duck.callback(FunCog(NS()), ctx)
    assert seen == [b""]
    ctx.send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["reddit", "duck"])
async def test_new_commands_get_delayed_loading_and_cleanup(name):
    from discord.ext import commands
    from bot.utils.loading import install_command_loading, LOADING_DELAY
    assert LOADING_DELAY == 0.5
    loading_message = NS(delete=AsyncMock())
    sticker = NS(name="meyaya_loading")
    channel = NS(guild=NS(id=123, stickers=[sticker]), send=AsyncMock(return_value=loading_message))
    async def callback(ctx):
        await ctx._meyaya_loader.task
        return "done"
    command = commands.hybrid_command(name=name)(callback)
    bot = NS(walk_commands=lambda: [command], stickers=[])
    install_command_loading(bot)
    assert command.app_command._callback is command.callback
    ctx = NS(channel=channel, interaction=None)
    assert await command.callback(ctx) == "done"
    channel.send.assert_awaited_once_with(stickers=[sticker])
    loading_message.delete.assert_awaited_once()
    assert ctx._meyaya_loader is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_loader_remains_during_gif_upload_and_is_cleaned_after(fails):
    from unittest.mock import patch
    from discord.ext import commands
    from bot.utils.command_context import TimedContext
    ctx = TimedContext.__new__(TimedContext)
    order = []
    async def stop():
        order.append("cleanup")
    async def send(*args, **kwargs):
        assert order == []
        order.append("delivery")
        if fails:
            raise RuntimeError("upload failed")
        return "sent"
    ctx._meyaya_loader = NS(stop=stop)
    with patch.object(commands.Context, "send", side_effect=send):
        if fails:
            with pytest.raises(RuntimeError, match="upload failed"):
                await ctx.send("gif")
        else:
            assert await ctx.send("gif") == "sent"
    assert order == ["delivery", "cleanup"]
