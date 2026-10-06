"""Veyra and patron-clash combat, routing, visuals and media regressions."""

import asyncio
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from discord.ext import commands
from bot.cogs.fantasy import FantasyCog
from bot.services.fantasy_boss import meyaya_boss_profile, veyra_boss_profile
from bot.services.fantasy_duel import Fighter
from bot.services.fantasy_duel_renderer import render_duel
from bot.services.meyaya_boss_combat import public_fighter
from bot.services.patron_boss_combat import VeyraDuelEngine, PatronClashEngine
from bot.services.patron_boss_presentation import (
    VeyraPresentation,
    PatronClashPresentation,
    VEYRA_INTRO_GIF,
    VEYRA_VICTORY_GIF,
)
from bot.services.meyaya_boss_presentation import VICTORY_GIF
from test_fantasy_duel import profile, member


def encounter(clash=False, seed=1):
    left = Fighter.snapshot(
        meyaya_boss_profile(99) if clash else profile(), "Meyaya" if clash else "Challenger"
    )
    right = Fighter.snapshot(veyra_boss_profile(), "Veyra")
    return (PatronClashEngine if clash else VeyraDuelEngine)(left, right, seed)


@pytest.mark.parametrize("clash", [False, True])
def test_encounters_are_seeded_bounded_and_mask_bosses(clash):
    winners = set()
    for seed in range(100):
        first, second = encounter(clash, seed), encounter(clash, seed)
        for engine in (first, second):
            for _ in range(40):
                engine.advance_move()
                if engine.state.finished:
                    break
            assert engine.state.finished
            assert 4 <= engine.state.moves <= (16 if clash else 40)
            for fighter in (engine.state.left, engine.state.right):
                assert 0 <= fighter.hp <= fighter.max_hp
                if fighter.is_boss:
                    public = public_fighter(fighter)
                    assert public["hp"] == public["mp"] == "UNKNOWN"
                    assert "strength" not in public and "damage_taken" not in public
        assert first.state == second.state
        winners.add(first.state.winner_id)
    if clash:
        assert {99, -1} <= winners


def test_veyra_does_not_mutate_saved_identity_and_severs_wards():
    source = profile()
    before = deepcopy(vars(source))
    engine = VeyraDuelEngine(
        Fighter.snapshot(source, "Player"), Fighter.snapshot(veyra_boss_profile(), "Veyra"), 1
    )
    engine.player.shield = 100
    engine.boss_actions = 2
    engine.attack(engine.boss, engine.player)
    assert engine.boss.last_move == "World Sever"
    assert engine.player.shield <= 35
    assert vars(source) == before


@pytest.mark.parametrize("clash", [False, True])
def test_veyra_and_clash_cards_have_distinct_openings(clash):
    engine = encounter(clash)
    opening = render_duel(engine.state, intro=True)
    engine.advance_move()
    live = render_duel(engine.state)
    assert opening != live
    for data in (opening, live):
        assert len(data) < 4 * 1024 * 1024
        assert Image.open(BytesIO(data)).size == (1100, 640)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "clash,winner,expected",
    [(False, -1, VEYRA_VICTORY_GIF), (True, -1, VEYRA_VICTORY_GIF), (True, 99, VICTORY_GIF)],
)
async def test_patron_media_and_ending(monkeypatch, clash, winner, expected):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    message = NS(edit=AsyncMock())
    message.edit.return_value = message
    channel = NS(send=AsyncMock(return_value=message))
    lookup = AsyncMock(return_value=NS(url="https://cdn.klipy.com/test.gif"))
    cog = NS(bot=NS(build_klipy_service=lambda: NS(exact_gif=lookup)))
    presentation = (PatronClashPresentation if clash else VeyraPresentation)(cog, NS(), channel)
    state = encounter(clash).state
    await presentation.intro(state)
    if not clash:
        assert lookup.call_args_list[0].args == (VEYRA_INTRO_GIF,)
        assert asyncio.sleep.call_args_list[0].args == (11.2,)
        assert message.edit.await_count == 2
    state.winner_id = winner
    await presentation.finish(state)
    assert lookup.call_args.args == (expected,)
    assert channel.send.await_count == 2
    assert "files" not in channel.send.call_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("clash", [False, True])
@pytest.mark.parametrize("fails", [False, True])
async def test_patron_command_reservations_and_cleanup(clash, fails):
    guild = NS(id=8)
    message = NS(edit=AsyncMock())
    ctx = NS(
        author=member(1, guild), guild=guild, channel=NS(), send=AsyncMock(return_value=message)
    )
    cog = FantasyCog(NS(user=NS(id=99)))
    cog.get_profile = AsyncMock(return_value=profile())

    async def run(view, interaction):
        assert cog.duel_users[1] is view
        assert view.owner == 1 and view.participant_ids == (1,)
        assert view.right.id == -1
        assert view.patron_clash == clash
        if fails:
            raise RuntimeError("transport failed")

    cog.run_duel = run
    if fails:
        with pytest.raises(RuntimeError):
            await cog.start_patron_encounter(ctx, "veyra", clash=clash)
    else:
        await cog.start_patron_encounter(ctx, "veyra", clash=clash)
    assert not cog.views and not cog.duel_users
    if clash:
        cog.get_profile.assert_not_awaited()
    with pytest.raises(commands.CommandError, match="15 seconds"):
        await cog.start_patron_encounter(ctx, "veyra", clash=clash)


@pytest.mark.asyncio
async def test_prefix_veyra_routes_to_boss_and_slash_offers_choices():
    cog = FantasyCog(NS())
    cog.start_patron_encounter = AsyncMock()
    ctx = NS(defer=AsyncMock())
    await FantasyCog.versus.callback(cog, ctx, "veyra")
    cog.start_patron_encounter.assert_awaited_once_with(ctx, "veyra")
    assert {choice.value for choice in FantasyCog.bossfight.app_command.parameters[0].choices} == {
        "meyaya",
        "veyra",
        "clash",
    }


@pytest.mark.asyncio
async def test_clash_cooldown_is_shared_between_users_and_routes():
    guild = NS(id=8)
    message = NS(edit=AsyncMock())
    ctx = NS(
        author=member(1, guild), guild=guild, channel=NS(), send=AsyncMock(return_value=message)
    )
    cog = FantasyCog(NS(user=NS(id=99)))
    cog.run_duel = AsyncMock()
    await cog.start_patron_encounter(ctx, "veyra", clash=True)
    ctx.author = member(2, guild)
    with pytest.raises(commands.CommandError, match="60 seconds"):
        await cog.start_patron_encounter(ctx, "veyra", clash=True)
    assert cog.run_duel.await_count == 1
    assert not cog.duel_users and not cog.views


@pytest.mark.asyncio
async def test_unawakened_player_cannot_start_veyra_encounter():
    guild = NS(id=8)
    cog = FantasyCog(NS(user=NS(id=99)))
    cog.get_profile = AsyncMock(return_value=None)
    ctx = NS(author=member(1, guild), guild=guild)
    with pytest.raises(commands.CommandError, match="Awaken"):
        await cog.start_patron_encounter(ctx, "veyra")
    assert not cog.views and not cog.duel_users and not cog.duel_cooldowns
