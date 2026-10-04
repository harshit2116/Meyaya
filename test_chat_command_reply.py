"""A reply to a command card keeps the result and speaker identities separate."""

import time
import json
from collections import OrderedDict
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import pytest
from discord.ext import commands
from discord.ext.commands.view import StringView

from bot.cogs.chat import ChatCog
from bot.utils.command_context import (
    CommandOutput, TimedContext, command_output_for, remember_command_result, MAX_RESULT_SUMMARY,
)


def _author(user_id, name):
    return NS(id=user_id, name=name, display_name=name)


@pytest.mark.asyncio
async def test_image_only_command_reply_includes_command_and_invoker():
    bot = NS(user=_author(99, "Meyaya"))
    bot._meyaya_command_outputs = OrderedDict({
        (7, 8): (time.monotonic(), CommandOutput("duck", 11, "Original user",
                                               '{"target_id":33,"ending":"Ruru is looking for treasure."}')),
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
    assert context.command_result_summary.startswith('{"target_id":33')
    assert "Ruru is looking for treasure." in prompt
    assert "not visual inspection" in prompt


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
    with patch.object(commands.Context, "send", new=AsyncMock(side_effect=[NS(id=8), NS(id=9), NS(id=10)])):
        remember_command_result(ctx, target_id=22, score=73)
        await ctx.send("result")
        assert json.loads(command_output_for(bot, 7, 8).result_summary) == {"target_id": 22, "score": 73}
        remember_command_result(ctx, private_fact="private")
        await ctx.send("secret", ephemeral=True)
        assert len(bot._meyaya_command_outputs) == 1
        await ctx.send("later")
        assert command_output_for(bot, 7, 10).result_summary == ""
        assert command_output_for(bot, 7, 9) is None


def test_result_summaries_are_bounded_and_channel_scoped():
    ctx = NS()
    remember_command_result(ctx, post="x" * 10000)
    assert len(ctx._meyaya_result_summary) <= MAX_RESULT_SUMMARY
    bot = NS(_meyaya_command_outputs=OrderedDict({
        (7, 8): (time.monotonic(), CommandOutput("reddit", 11, "Invoker", ctx._meyaya_result_summary)),
    }))
    assert command_output_for(bot, 9, 8) is None
    bot._meyaya_command_outputs[(7, 8)] = (
        time.monotonic() - 86401, CommandOutput("reddit", 11, "Invoker", "old"),
    )
    assert command_output_for(bot, 7, 8) is None


@pytest.mark.asyncio
async def test_reddit_summary_matches_text_and_counts_passed_to_renderer():
    from bot.cogs.fun import FunCog
    ctx = NS(author=_author(11, "Invoker"), guild=NS(id=2, name="My Server"),
             defer=AsyncMock(), send=AsyncMock())
    cog = FunCog(NS(user=_author(99, "Meyaya")))
    cog._card_avatar = AsyncMock(return_value=b"")
    cog._gemini_flavor = AsyncMock(return_value="That is quite a claim.")
    with patch("bot.cogs.fun.image_work", new=AsyncMock(return_value=b"png")) as render:
        await FunCog.reddit.callback(cog, ctx, post="My post")
    result = json.loads(ctx._meyaya_result_summary)
    args = render.await_args.args
    assert result["post"] == args[3] == "My post"
    assert result["comment"] == args[4] == "That is quite a claim."
    assert result["votes"] == args[7]
    assert result["replies"] == args[8]
    assert result["subreddit"] == "r/My-Server"
    assert result["author_id"] == 11


@pytest.mark.asyncio
async def test_mostlikely_summary_explains_actual_random_pick():
    from bot.cogs.fun import FunCog
    winner = _author(22, "Selected member")
    winner.bot = False
    winner.display_avatar = NS(url="https://example.test/avatar")
    ctx = NS(author=_author(11, "Invoker"), guild=NS(id=2, get_member=lambda _: winner),
             interaction=None, send=AsyncMock(), message=NS(mentions=[]))
    bot = NS(get_cog=lambda _: NS(_candidate_ids=AsyncMock(return_value=[22])))
    with patch("bot.cogs.fun.image_work", new=AsyncMock(return_value=b"png")):
        await FunCog.mostlikely.callback(FunCog(bot), ctx, scenario="lose the keys")
    result = json.loads(ctx._meyaya_result_summary)
    assert result["selected_member_id"] == 22
    assert result["scenario"] == "lose the keys"
    assert result["eligible_members"] == 1
    assert "Random choice" in result["method"]


@pytest.mark.asyncio
async def test_ship_summary_uses_rendered_roll_without_rerolling():
    from bot.cogs.ship import ShipCog
    cog = ShipCog(NS())
    cog.service = NS(ship=lambda *_: NS(percentage=73, label="Promising!"))
    cog._get_ship_card = AsyncMock(return_value=b"png")
    ctx = NS()
    await cog._build_ship_response(_author(11, "First"), _author(22, "Second"), ctx=ctx)
    result = json.loads(ctx._meyaya_result_summary)
    assert result["score"] == cog._get_ship_card.await_args.args[2] == 73
    assert result["verdict"] == "Promising!"
    assert (result["first_id"], result["second_id"]) == (11, 22)


def test_profile_summary_keeps_unavailable_categories_empty():
    from bot.cogs.profile_studio import profile_review_result
    from bot.services.profile_aesthetic import ProfileVisual
    visual = ProfileVisual(
        user_id=22, name="Target", avatar=b"avatar", banner=None, decoration=None,
        palette=("#111111",) * 5, avatar_score=80, styling_score=0,
        harmony_score=0, originality_score=70, overall_score=49,
        has_banner=False, has_decoration=False, has_nameplate=False,
        has_server_tag=False, has_server_avatar=False, badge_count=0,
        animated_avatar=False, accent_color=None, asset_fingerprint="abc",
        comparison_available=False,
    )
    result = profile_review_result(visual)
    assert result["target_id"] == 22
    assert result["overall"] == 49
    assert result["scores_out_of_100"] == {
        "readability": 80, "cohesion": None, "color_harmony": None, "detail_balance": 70,
    }
    assert sum(result["internal_weights"].values()) == 100
