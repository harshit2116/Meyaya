"""Prefix lore aliases keep normal member and slash user lookup intact."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import discord
from discord.ext import commands
from discord.ext.commands.converter import run_converters
import pytest
from PIL import Image, ImageChops
from bot.cogs.fantasy import FantasyCog
from bot.utils.fantasy_profile_target import FantasyProfileTarget
from bot.services.meyaya_boss_renderer import render_patron_profile, template


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "argument,expected",
    [("Veyra", "veyra"), ("Veryra", "veyra"), ("vEyRa", "veyra"), ("Meyaya", "meyaya")],
)
async def test_real_prefix_converter_and_image_only_response(argument, expected):
    converter = FantasyCog.fantasyprofile.params["member"].converter
    ctx = NS(
        author=NS(id=123),
        defer=AsyncMock(),
        send=AsyncMock(),
        command=NS(qualified_name="fantasyprofile"),
    )
    value = await run_converters(
        ctx, converter, argument, FantasyCog.fantasyprofile.params["member"]
    )
    assert value == expected
    cog = FantasyCog(NS())
    cog.get_profile = AsyncMock(side_effect=AssertionError("Lore profile must not access DB"))
    await FantasyCog.fantasyprofile.callback(cog, ctx, value)
    payload = ctx.send.call_args.kwargs
    assert not payload["embed"].title and not payload["embed"].fields
    assert "view" not in payload
    art = Image.open(payload["file"].fp).convert("RGB")
    assert ImageChops.difference(art, template(f"{expected}-profile.png")).getbbox() is None


@pytest.mark.asyncio
async def test_normal_member_conversion_and_slash_user_type(monkeypatch):
    resolved = NS(id=123)
    original = AsyncMock(return_value=resolved)
    monkeypatch.setattr(commands.MemberConverter, "convert", original)
    target = FantasyProfileTarget()
    assert await target.convert(NS(), "@Haru") is resolved
    original.assert_awaited_once()
    assert target.type == discord.AppCommandOptionType.user
    assert (
        FantasyCog.fantasyprofile.app_command.parameters[0].type
        == discord.AppCommandOptionType.user
    )


@pytest.mark.parametrize("patron", ["meyaya", "veyra"])
def test_full_artwork_preserved_under_attachment_budget(patron):
    data = render_patron_profile(patron)
    assert len(data) <= 4 * 1024 * 1024
    image = Image.open(BytesIO(data)).convert("RGB")
    assert ImageChops.difference(image, template(f"{patron}-profile.png")).getbbox() is None
