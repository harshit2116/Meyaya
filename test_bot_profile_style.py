"""All-guild fixed style, serialized requests and best-effort failures."""

import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest

from bot.app import MeyayaBot
from bot.services.bot_profile_style import (
    STYLE_PAYLOAD,
    apply_all_guild_name_styles,
    apply_guild_name_style,
)


def client():
    return NS(
        settings=NS(guild_id=None, discord_token="SECRET_TEST_TOKEN"),
        guilds=[NS(id=123, unavailable=False), NS(id=456, unavailable=False)],
        http=NS(request=AsyncMock(return_value=dict(STYLE_PAYLOAD))),
    )


@pytest.mark.asyncio
async def test_every_guild_exact_payload_and_no_repeat():
    bot = client()
    await apply_all_guild_name_styles(bot)
    await apply_all_guild_name_styles(bot)
    calls = bot.http.request.call_args_list
    assert len(calls) == 2
    assert [call.args[0].guild_id for call in calls] == [123, 456]
    for call in calls:
        route = call.args[0]
        assert route.method == "PATCH" and route.url.endswith(
            f"/guilds/{route.guild_id}/members/@me"
        )
        assert call.kwargs["json"] == {
            "display_name_font_id": 16,
            "display_name_effect_id": 2,
            "display_name_colors": [int("EEB2AA", 16), int("E36DE0", 16)],
        }


@pytest.mark.asyncio
async def test_unavailable_then_available_and_no_guilds():
    bot = client()
    bot.guilds = []
    await apply_all_guild_name_styles(bot)
    bot.http.request.assert_not_awaited()
    guild = NS(id=777, unavailable=True)
    await apply_guild_name_style(bot, guild)
    assert 777 not in bot._guild_name_style_attempted
    guild.unavailable = False
    await apply_guild_name_style(bot, guild)
    bot.http.request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(400, 50035), (403, 50013), (404, 10004), (503, 0)])
async def test_rejection_does_not_block_next_guild_or_change_payload(status, code, caplog):
    bot = client()
    error = discord.HTTPException(
        NS(status=status, reason="error"),
        {"code": code, "message": "unsupported field SECRET_TEST_TOKEN"},
    )
    bot.http.request.side_effect = [error, dict(STYLE_PAYLOAD)]
    await apply_all_guild_name_styles(bot)
    assert bot.http.request.await_count == 2
    assert f"status={status}" in caplog.text and f"code={code}" in caplog.text
    assert "unsupported field" in caplog.text and "SECRET_TEST_TOKEN" not in caplog.text
    assert all(call.kwargs["json"] == STYLE_PAYLOAD for call in bot.http.request.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), OSError("network down")])
async def test_other_failure_nonfatal(error):
    bot = client()
    bot.http.request.side_effect = error
    await apply_all_guild_name_styles(bot)
    assert bot.http.request.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_events_serialized_and_duplicate_suppressed(caplog):
    bot = client()
    running = 0
    maximum = 0

    async def request(*args, **kwargs):
        nonlocal running, maximum
        running += 1
        maximum = max(running, maximum)
        await asyncio.sleep(0.01)
        running -= 1
        return {}

    bot.http.request.side_effect = request
    await asyncio.gather(
        apply_all_guild_name_styles(bot),
        apply_guild_name_style(bot, bot.guilds[0]),
        apply_guild_name_style(bot, bot.guilds[1]),
    )
    assert maximum == 1 and bot.http.request.await_count == 2
    assert "style_fields_not_echoed" in caplog.text


@pytest.mark.asyncio
async def test_ready_join_availability_and_rejoin(monkeypatch):
    all_style, one_style = AsyncMock(), AsyncMock()
    monkeypatch.setattr("bot.services.bot_profile_style.apply_all_guild_name_styles", all_style)
    monkeypatch.setattr("bot.services.bot_profile_style.apply_guild_name_style", one_style)
    bot = client()
    bot.user = NS(id=999)
    bot.is_ready = lambda: True
    await MeyayaBot.on_ready(bot)
    all_style.assert_awaited_once_with(bot)
    for guild in bot.guilds:
        await MeyayaBot.on_guild_available(bot, guild)
    await MeyayaBot.on_guild_join(bot, NS(id=777))
    assert one_style.await_count == 3
    bot.is_ready = lambda: False
    await MeyayaBot.on_guild_available(bot, bot.guilds[0])
    await MeyayaBot.on_guild_join(bot, NS(id=777))
    assert one_style.await_count == 3
    bot._guild_name_style_attempted = {123, 456}
    await MeyayaBot.on_guild_remove(bot, NS(id=123))
    assert bot._guild_name_style_attempted == {456}
