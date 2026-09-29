"""Offline GIF, prefix/slash and graceful-avatar coverage for duck."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
from PIL import Image

from bot.cogs.fun import FunCog
from bot.services.duck_card import render_duck, MAX_OUTPUT_BYTES


def member(name="Ayaya"):
    asset = NS(read=AsyncMock(return_value=b"corrupt avatar"))
    asset.with_size = lambda _: asset
    asset.with_format = lambda _: asset
    return NS(id=42, display_name=name, display_avatar=asset)


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
