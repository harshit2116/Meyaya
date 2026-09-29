"""Offline coverage for Reddit cards and the local rating command."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
from PIL import Image

from bot.cogs.fun import FunCog
from bot.services.reddit_card import render_reddit
from bot.services.model_router import ModelRouter, ModelTier
from bot.logging.telemetry import current_model_context


def context(interaction=None):
    asset = NS(read=AsyncMock(return_value=b"not an image"))
    asset.with_size = lambda size: asset
    asset.with_format = lambda format: asset
    author = NS(id=42, name="Ayaya", display_name="Ayaya", display_avatar=asset)
    return NS(author=author, guild=NS(id=123, name="Pondside Lounge"),
              interaction=interaction, defer=AsyncMock(), send=AsyncMock())


def test_renderer_bounds_long_inputs_and_corrupt_avatars():
    for comment in ("", "long comment " * 100, "x" * 240):
        png = render_reddit("Server " * 100, "User" * 100, "x" * 300, comment,
                            b"corrupt", b"corrupt")
        with Image.open(BytesIO(png)) as card:
            assert card.width == 660
            assert 200 < card.height < 1000
            card.verify()


@pytest.mark.asyncio
async def test_rate_never_builds_or_calls_llm():
    provider = AsyncMock()
    builder = AsyncMock(return_value=provider)
    ctx = context()
    await FunCog.rate.callback(FunCog(NS(build_llm_provider=builder)), ctx, thing="snacks")
    builder.assert_not_called()
    assert "/100" in ctx.send.await_args.kwargs["embed"].description


@pytest.mark.asyncio
@pytest.mark.parametrize("interaction", [None, object()])
async def test_reddit_generates_meyaya_comment_with_feature_context(interaction):
    seen = []
    async def generate(*args, **kwargs):
        seen.append(current_model_context().get("feature"))
        assert kwargs["timeout_seconds"] == 8
        return NS(text="The snacks have spoken.")
    llm = NS(generate=AsyncMock(side_effect=generate))
    ctx = context(interaction)
    cog = FunCog(NS(build_llm_provider=lambda: llm, user=ctx.author))
    await FunCog.reddit.callback(cog, ctx, post="I ate the snacks")
    assert seen == ["reddit"]
    ctx.defer.assert_awaited_once()
    sent = ctx.send.await_args.kwargs
    assert sent["file"].filename == "reddit.png"
    assert sent["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    with Image.open(sent["file"].fp) as card:
        card.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("post,comment", [("Snacks | Mine now", None), ("Snacks", "Mine now"), ("Snacks |", None)])
async def test_custom_comment_skips_gemini(post, comment):
    builder = AsyncMock()
    ctx = context()
    cog = FunCog(NS(build_llm_provider=builder, user=ctx.author))
    await FunCog.reddit.callback(cog, ctx, post=post, comment=comment)
    builder.assert_not_called()
    ctx.send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, NS(text=""), NS(text="All out of energy for now")])
async def test_unavailable_gemini_still_renders_post(result):
    ctx = context()
    llm = NS(generate=AsyncMock(return_value=result))
    cog = FunCog(NS(build_llm_provider=lambda: llm, user=None))
    await FunCog.reddit.callback(cog, ctx, post="Hello server")
    ctx.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_post_never_calls_ai_or_fetches_avatar():
    builder = AsyncMock()
    ctx = context()
    await FunCog.reddit.callback(FunCog(NS(build_llm_provider=builder)), ctx, post="   ")
    builder.assert_not_called()
    ctx.author.display_avatar.read.assert_not_awaited()
    assert "Give me a post" in ctx.send.await_args.args[0]


def test_reddit_uses_fast_model_tier():
    providers = {tier: NS() for tier in ModelTier}
    assert ModelRouter(providers).tier_for_feature("reddit") == ModelTier.FAST


def test_avatar_is_rendered_and_comment_changes_card_height():
    avatar = BytesIO()
    Image.new("RGB", (128, 128), "#ff6600").save(avatar, format="PNG")
    no_reply = render_reddit("Server", "User", "Post", author_avatar=avatar.getvalue())
    with_reply = render_reddit("Server", "User", "Post", "Reply")
    with Image.open(BytesIO(no_reply)) as card, Image.open(BytesIO(with_reply)) as other:
        assert card.getpixel((52, 50)) == (255, 102, 0)
        assert card.height < other.height


@pytest.mark.asyncio
async def test_prefix_parser_preserves_pipe_comment():
    from discord.ext.commands.view import StringView
    ctx = context()
    ctx.message = NS(attachments=[])
    ctx.view = StringView("I stole the snacks | No regrets")
    cog = FunCog(NS(build_llm_provider=lambda: None, user=ctx.author))
    command = FunCog.reddit.copy()
    command.cog = cog
    await command._parse_arguments(ctx)
    assert ctx.kwargs["post"] == "I stole the snacks | No regrets"
    await command.callback(cog, ctx, **ctx.kwargs)
    ctx.send.assert_awaited_once()
