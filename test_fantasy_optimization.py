"""Fantasy command concurrency, bounded media work and graceful fallbacks."""

import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from bot.cogs import fantasy
from bot.cogs.fantasy import FantasyCog
from test_fantasy_awaken import context


@pytest.mark.asyncio
async def test_simultaneous_awakenings_keep_one_confirmation():
    cog = FantasyCog(NS())
    arrived = 0
    ready = asyncio.Event()

    async def lookup(user_id):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await ready.wait()
        return None

    cog.get_profile = lookup
    first, second = context(), context()
    await asyncio.gather(
        FantasyCog.awaken.callback(cog, first),
        FantasyCog.awaken.callback(cog, second),
    )
    assert len(cog.views) == len(cog.pending) == 1
    assert sum("view" in ctx.send.call_args.kwargs for ctx in (first, second)) == 1
    cog.cog_unload()


@pytest.mark.asyncio
async def test_awakening_during_battle_skips_database():
    cog = FantasyCog(NS())
    ctx = context()
    cog.duel_users[ctx.author.id] = object()
    cog.get_profile = AsyncMock()
    await FantasyCog.awaken.callback(cog, ctx)
    cog.get_profile.assert_not_awaited()
    assert not cog.views


@pytest.mark.asyncio
async def test_duel_profile_lookups_overlap_without_losing_order():
    from test_fantasy_duel import member, profile

    cog = FantasyCog(NS())
    guild = NS(id=22)
    arrived = set()
    ready = asyncio.Event()

    async def lookup(user_id):
        arrived.add(user_id)
        if len(arrived) == 2:
            ready.set()
        await ready.wait()
        return profile(user_id)

    cog.get_profile = lookup
    async with asyncio.timeout(1):
        _, view = await cog.create_duel(member(1, guild), member(2, guild))
    assert view.profiles[1].user_id == 1
    assert view.profiles[2].user_id == 2
    view.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize("patron", ["meyaya", "veyra"])
@pytest.mark.parametrize("failure", ["render", "upload"])
async def test_patron_failures_preserve_readable_lore(monkeypatch, patron, failure):
    cog = FantasyCog(NS())
    cog.report = Mock()
    ctx = context()
    render = AsyncMock(return_value=b"PNG")
    monkeypatch.setattr(fantasy, "image_work", render)
    if failure == "render":
        render.side_effect = RuntimeError("renderer unavailable")
    else:
        ctx.send.side_effect = [
            discord.HTTPException(NS(status=500, reason="upload failed"), "failed"),
            NS(),
        ]
    await FantasyCog.fantasyprofile.callback(cog, ctx, patron)
    payload = ctx.send.call_args.kwargs
    assert "file" not in payload
    assert payload["embed"].fields
    assert not payload["embed"].image.url
    assert cog.render_slots.pending == 0


def test_static_patron_art_is_encoded_once(monkeypatch):
    from bot.services import meyaya_boss_renderer as renderer

    renderer.render_patron_profile.cache_clear()
    encode = Mock(return_value=b"PNG")
    monkeypatch.setattr(renderer, "encode", encode)
    try:
        assert renderer.render_patron_profile("meyaya") == b"PNG"
        assert renderer.render_patron_profile("meyaya") == b"PNG"
        encode.assert_called_once()
        renderer.render_patron_profile("veyra")
        assert encode.call_count == 2
    finally:
        renderer.render_patron_profile.cache_clear()


@pytest.mark.asyncio
async def test_avatar_timeout_keeps_profile_render_and_releases_slot(monkeypatch):
    from test_fantasy_awaken import member, profile

    cancelled = asyncio.Event()

    async def download(url):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    cog = FantasyCog(NS(build_profile_aesthetic_service=lambda: NS(_download=download)))
    cog.report = Mock()
    original_timeout = asyncio.timeout
    monkeypatch.setattr(fantasy.asyncio, "timeout", lambda duration: original_timeout(0.01))
    render = AsyncMock(return_value=b"PNG")
    monkeypatch.setattr(fantasy, "image_work", render)
    assert await cog.card_bytes(profile(123), member(123)) == b"PNG"
    assert cancelled.is_set()
    assert render.call_args.args[-1] == b""
    assert cog.render_slots.pending == 0
