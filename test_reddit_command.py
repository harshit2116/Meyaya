"""Offline coverage for Reddit cards and the local rating command."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import pytest
from PIL import Image

from bot.cogs.fun import FunCog
from bot.services.reddit_card import render_reddit
from bot.services.model_router import ModelRouter, ModelTier
from bot.logging.telemetry import current_model_context
from bot.utils.display_mentions import display_mentions


def test_rendered_mentions_use_names_without_api_fetches():
    ctx = context()
    target = NS(id=7, display_name="Haru")
    ctx.guild.get_member = lambda user_id: target if user_id == 7 else None
    ctx.guild.get_channel_or_thread = lambda channel_id: NS(name="general") if channel_id == 8 else None
    ctx.guild.get_role = lambda role_id: NS(name="Friends") if role_id == 9 else None
    assert display_mentions(ctx, "<@7> <@!7> <#8> <@&9>") == "@Haru @Haru #general @Friends"
    assert display_mentions(ctx, "<@42>") == "@Ayaya"
    assert display_mentions(ctx, "<@999> <#999>") == "@unknown-user #unknown-channel"


@pytest.mark.asyncio
@pytest.mark.parametrize("interaction", [None, object()])
async def test_reddit_resolves_mentions_in_post_and_custom_comment(interaction):
    ctx = context(interaction)
    ctx.guild.get_channel_or_thread = lambda _: NS(name="general")
    cog = FunCog(NS(user=ctx.author))
    cog._card_avatar = AsyncMock(return_value=b"")
    with patch("bot.services.reddit_card.render_reddit", return_value=b"png") as render:
        await FunCog.reddit.callback(cog, ctx, post="<@42> is the best", comment="Meet in <#9>")
    args = render.call_args.args
    assert args[2] == "@Ayaya is the best"
    assert args[3] == "Meet in #general"
    assert "<@42>" not in ctx._meyaya_result_summary


def context(interaction=None):
    asset = NS(url="https://cdn.discordapp.com/avatars/42/test.png?size=128",
               read=AsyncMock(return_value=b"not an image"))
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
async def test_party_avatar_uses_shared_cdn_loader_not_discord_read():
    image = BytesIO()
    Image.new("RGB", (128, 128), "#ff6600").save(image, format="PNG")
    ship = NS(_get_avatar_bytes=AsyncMock(return_value=image.getvalue()))
    ctx = context()
    bot = NS(get_cog=lambda name: ship if name == "ShipCog" else None)
    cog = FunCog(bot)
    assert await cog._card_avatar(ctx.author) == image.getvalue()
    ship._get_avatar_bytes.assert_awaited_once_with(ctx.author.display_avatar)
    ctx.author.display_avatar.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_party_avatar_failure_is_logged_and_not_cached(caplog):
    ship = NS(_get_avatar_bytes=AsyncMock(side_effect=[b"", b"valid bytes"]))
    cog = FunCog(NS(get_cog=lambda _: ship))
    ctx = context()
    assert await cog._card_avatar(ctx.author) == b""
    assert "party_avatar_unavailable" in caplog.text
    assert await cog._card_avatar(ctx.author) == b"valid bytes"
    assert ship._get_avatar_bytes.await_count == 2


@pytest.mark.asyncio
async def test_avatar_download_uses_app_http_pool_and_caches_real_portrait():
    from unittest.mock import Mock
    image = BytesIO()
    Image.new("RGB", (128, 128), "#ff6600").save(image, format="PNG")
    data = image.getvalue()
    async def chunks(size):
        yield data
    response = NS(raise_for_status=Mock(), content=NS(iter_chunked=chunks))
    request = AsyncMock()
    request.__aenter__.return_value = response
    session = NS(closed=False, get=Mock(return_value=request))
    cog = FunCog(NS(http_session=session))
    ctx = context()
    assert await cog._card_avatar(ctx.author) == data
    assert await cog._card_avatar(ctx.author) == data
    session.get.assert_called_once_with(ctx.author.display_avatar.url)
    ctx.author.display_avatar.read.assert_not_awaited()


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
