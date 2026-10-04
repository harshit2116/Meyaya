"""Local caught cards must stay bounded, private-data-free and AI-free."""

import json
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import pytest
from PIL import Image

from bot.cogs.fun import FunCog
from bot.data.help_catalog import COMMANDS
from bot.services.caught_card import INCIDENTS, SIZE, render_caught, scene_background


@pytest.mark.parametrize("scene", ["pantry", "arcade", "server"])
def test_each_scene_renders_sharp_bounded_png_with_avatar(scene):
    avatar = BytesIO()
    Image.new("RGB", (128, 128), "#ff6600").save(avatar, format="PNG")
    case = next(case for case in INCIDENTS if case.scene == scene)
    png = render_caught("Ayaya", avatar.getvalue(), case, datetime(2026, 10, 4, tzinfo=timezone.utc))
    assert len(png) < 2 * 1024 * 1024
    with Image.open(BytesIO(png)) as card:
        assert card.size == SIZE
        r, g, b = card.getpixel((500, 230))
        assert r > 240 and 80 < g < 130 and b < 20
    with Image.open(BytesIO(png)) as card:
        card.verify()


def test_long_name_bad_avatar_and_cached_background_are_safe():
    background = scene_background("pantry")
    before = background.tobytes()
    with Image.open(BytesIO(render_caught("W" * 200, b"bad", INCIDENTS[0]))) as card:
        assert card.size == SIZE
    assert background.tobytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("interaction,explicit", [(None, False), (object(), True)])
async def test_prefix_slash_target_and_no_gemini(interaction, explicit):
    author = NS(id=11, display_name="Ayaya")
    member = NS(id=22, display_name="Haru")
    ctx = NS(author=author, interaction=interaction, defer=AsyncMock(), send=AsyncMock())
    bot = NS(build_llm_provider=AsyncMock())
    cog = FunCog(bot)
    cog._card_avatar = AsyncMock(return_value=b"")
    with patch("bot.services.caught_card.render_caught", return_value=b"png") as render:
        await FunCog.caught.callback(cog, ctx, member=member if explicit else None)
    bot.build_llm_provider.assert_not_called()
    target = member if explicit else author
    assert render.call_args.args[0] == target.display_name
    cog._card_avatar.assert_awaited_once_with(target)
    assert cog.caught_slots.pending == 0
    sent = ctx.send.await_args.kwargs
    assert sent["file"].filename == "caught.png"
    assert sent["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    result = json.loads(ctx._meyaya_result_summary)
    assert result["target_id"] == target.id
    assert result["incident"] == render.call_args.args[2].incident
    assert "fictional" in result["method"]


def test_caught_is_discoverable_and_has_member_cooldown():
    assert any(item.name == "caught" for item in COMMANDS)
    assert FunCog.caught.app_command.name == "caught"
    assert FunCog.caught._buckets._cooldown.per == 10
