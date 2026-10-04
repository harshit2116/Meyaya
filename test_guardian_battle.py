"""Offline soul binding, manual combat, consent, rendering and lifecycle checks."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, timezone
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import asyncio
import pytest
from PIL import Image
from bot.cogs.fantasy import FantasyCog
from bot.cogs.celestial import CelestialCommands
from bot.services.fantasy_guardian import bound_guardian, GuardianBattle, GuardianFighter
from bot.services.guardian_render import creature, guardian_card, battle_card, _illustration
from bot.views.guardian_battle import GuardianChallengeView, GuardianBattleView
from test_fantasy_duel import profile, member, interaction
from bot.services.fantasy_boss import meyaya_boss_profile
from bot.services.fantasy_duel import DuelEngine, Fighter


def battle(seed=1):
    return GuardianBattle(
        GuardianFighter(bound_guardian(profile(1)), "Ayaya"),
        GuardianFighter(bound_guardian(profile(2)), "Haru"),
        seed,
    )


def test_meyaya_boss_fixed_and_overpowered_in_both_modes():
    boss = meyaya_boss_profile(99)
    assert vars(boss) == vars(meyaya_boss_profile(99))
    assert boss.weapon_rarity == "Mythic" and boss.level == 999
    guardian = bound_guardian(boss)
    assert guardian.species == "dragon" and guardian.bond == 100
    assert guardian.max_hp == 30000 and guardian.attack == 500
    for seed in range(100):
        player = profile(1, seed)
        duel = DuelEngine(Fighter.snapshot(player, "Player"), Fighter.snapshot(boss, "Meyaya"), seed)
        while not duel.state.finished:
            duel.advance_move()
        assert duel.state.winner_id == 99
        arena = GuardianBattle(GuardianFighter(bound_guardian(player), "Player"), GuardianFighter(guardian, "Meyaya"), seed)
        while not arena.finished:
            arena.choose(arena.actor.guardian.owner_id, "affinity" if arena.actor.mp >= 14 else "strike")
        assert arena.winner_id == 99
    assert boss.hp == boss.max_hp and boss.mp == boss.max_mp


@pytest.mark.asyncio
async def test_meyaya_npc_turn_then_player_turn_and_recall():
    guild = NS(id=22)
    a, npc = member(1, guild), member(99, guild)
    npc.bot = True
    cog = FantasyCog(NS(user=NS(id=99)))
    boss = await cog.get_profile(99)  # Does not require a database.
    profiles = {1: profile(1), 99: boss}
    arena = GuardianBattle(GuardianFighter(bound_guardian(profiles[1]), "Player"), GuardianFighter(bound_guardian(boss), "Meyaya"), 1)
    view = GuardianBattleView(cog, a, npc, profiles, arena)
    cog.track_view(view)
    cog.duel_users[1] = view
    view.update = AsyncMock()
    assert arena.actor.guardian.owner_id == 99
    assert view.strike.disabled and not view.recall.disabled
    view.schedule_turn()
    view.timer.cancel()
    await view.npc_move()
    assert arena.moves == 1 and arena.actor.guardian.owner_id == 1
    await view.play(interaction(a, guild), "strike")
    assert arena.moves == 2 and arena.actor.guardian.owner_id == 99
    await view.play(interaction(a, guild), "forfeit")
    assert arena.winner_id == 99 and view.closed and not cog.duel_users
    assert view.timer.cancelled()


@pytest.mark.asyncio
async def test_only_meyaya_bot_admitted_and_not_globally_reserved():
    guild = NS(id=22)
    cog = FantasyCog(NS(user=NS(id=99)))
    cog.get_profile = AsyncMock(side_effect=lambda uid: meyaya_boss_profile(uid) if uid == 99 else profile(uid))
    npc = member(99, guild)
    npc.bot = True
    _, first = await cog.create_duel(member(1, guild), npc)
    _, second = await cog.create_duel(member(2, guild), npc)
    assert set(cog.duel_users) == {1, 2}
    other = member(88, guild)
    other.bot = True
    with pytest.raises(Exception, match="human member or Meyaya"):
        await cog.create_duel(member(3, guild), other)
    first.finish()
    assert set(cog.duel_users) == {2}
    second.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["versus", "guardianbattle"])
async def test_boss_commands_start_without_waiting_for_consent(monkeypatch, command):
    guild = NS(id=22)
    player, npc = member(1, guild), member(99, guild)
    npc.bot = True
    cog = FantasyCog(NS(user=NS(id=99)))
    cog.get_profile = AsyncMock(side_effect=lambda uid: meyaya_boss_profile(uid) if uid == 99 else profile(uid))
    message = NS(edit=AsyncMock())
    ctx = NS(author=player, channel=NS(send=AsyncMock()), send=AsyncMock(return_value=message), defer=AsyncMock())
    cog.run_duel = AsyncMock()
    monkeypatch.setattr(GuardianBattleView, "update", AsyncMock())
    await getattr(FantasyCog, command).callback(cog, ctx, npc)
    if command == "versus":
        assert cog.run_duel.await_count == 1 and not cog.duel_users
    else:
        view = cog.duel_users[1]
        assert isinstance(view, GuardianBattleView) and view.timer is not None
        view.finish()
    assert ctx.defer.await_count == 1 and not cog.duel_users


def test_guardian_stable_awakening_affinity_and_source_immutable():
    p = profile()
    before = deepcopy(vars(p))
    g = bound_guardian(p)
    assert g == bound_guardian(p)
    assert g.affinity == p.affinity_id and g.owner_class == p.class_name
    assert vars(p) == before
    p.awakened_at = p.awakened_at.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert g == bound_guardian(p)
    p.max_hp += 100
    p.weapon_id = "future_equipment"
    assert g == bound_guardian(p)


@pytest.mark.parametrize("species", ["owl", "fox", "dragon", "moth"])
def test_original_creatures_card_render_and_missing_names(species):
    master = _illustration(species)
    original = master.tobytes()
    assert master.mode == "RGBA" and max(master.size) <= 512
    assert master.getchannel("A").getextrema() == (0, 255)
    g = replace(bound_guardian(profile()), species=species)
    art = creature(g)
    assert art.mode == "RGBA" and art.getchannel("A").getextrema() == (0, 255)
    assert art.size == (280, 280)
    creature(g, 340, back=True)
    assert master.tobytes() == original
    data = guardian_card(g, "A very long trainer name " * 10)
    assert Image.open(BytesIO(data)).size == (1000, 660)
    b = battle()
    b.fighters[0].guardian = g
    assert Image.open(BytesIO(battle_card(b))).size == (1000, 660)
    b.finished, b.winner_id = True, 2
    assert len(battle_card(b)) < 4 * 1024 * 1024


def test_moves_and_alternating_ownership():
    b = battle()
    wrong = b.fighters[1 - b.turn].guardian.owner_id
    with pytest.raises(ValueError, match="other trainer"):
        b.choose(wrong, "strike")
    a, other = b.actor, b.fighters[1 - b.turn]
    a.mp = 0
    with pytest.raises(ValueError, match="MP"):
        b.choose(a.guardian.owner_id, "affinity")
    assert b.moves == 0
    a.mp = a.guardian.max_mp
    old_mp, old_hp = a.mp, other.hp
    b.choose(a.guardian.owner_id, "affinity")
    assert a.mp == old_mp - 14 and other.hp < old_hp and b.actor is other
    b.choose(other.guardian.owner_id, "guard")
    assert other.guarded
    b.choose(a.guardian.owner_id, "strike")
    assert not other.guarded


@pytest.mark.parametrize("species", ["owl", "fox", "dragon", "moth"])
def test_blessings_are_species_specific_and_finite(species):
    b = battle()
    a = b.actor
    a.guardian = replace(a.guardian, species=species)
    a.hp = max(1, a.hp - 50)
    before = a.hp
    b.choose(a.guardian.owner_id, "blessing")
    assert a.blessing_uses == 1
    if species == "owl":
        assert a.focus == 2 and a.hp == before
    elif species == "fox":
        assert a.focus == 1 and a.hp > before
    elif species == "dragon":
        assert a.guarded and a.hp > before
    else:
        assert a.hp > before
    a.blessing_uses = 2
    assert not a.can_bless()


def test_stalling_has_finite_limit_and_recall_is_real_loss():
    b = battle()
    while not b.finished:
        b.choose(b.actor.guardian.owner_id, "guard")
    assert b.moves == 24 and b.winner_id is None
    b = battle()
    winner = b.fighters[1 - b.turn].guardian.owner_id
    b.choose(b.actor.guardian.owner_id, "forfeit")
    assert b.finished and b.winner_id == winner


def test_1000_offline_battles_bound_resources_and_finish():
    for seed in range(1000):
        b = battle(seed)
        while not b.finished:
            a = b.actor
            b.choose(a.guardian.owner_id, "affinity" if a.mp >= 14 else "strike")
        assert b.moves <= 24 and b.winner_id in (None, 1, 2)
        for f in b.fighters:
            assert 0 <= f.hp <= f.guardian.max_hp and 0 <= f.mp <= f.guardian.max_mp


@pytest.mark.asyncio
async def test_command_registration_guardian_is_fantasy_not_daily():
    fantasy = FantasyCog(NS())
    assert "guardian" in {c.name for c in fantasy.get_commands()}
    assert "guardianbattle" in {c.name for c in fantasy.get_commands()}
    assert "guardian" not in {c.name for c in CelestialCommands(NS()).get_commands()}


@pytest.mark.asyncio
async def test_consent_then_one_battle_message_and_participant_turns(monkeypatch):
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    guild.get_member = lambda user_id: a if user_id == 1 else b
    cog = FantasyCog(NS())
    old = GuardianChallengeView(cog, a, b, {1: profile(1), 2: profile(2)})
    cog.track_view(old)
    cog.duel_users.update({1: old, 2: old})
    monkeypatch.setattr("bot.views.guardian_battle.image_work", AsyncMock(return_value=b"PNG"))
    bad = interaction(a, guild)
    await old.accept.callback(bad)
    assert not bad.channel.send.called
    inter = interaction(b, guild)
    msg = NS(id=66, channel=NS(id=55), edit=AsyncMock())
    msg.edit.return_value = msg
    inter.channel.send.return_value = msg
    await old.accept.callback(inter)
    view = next(iter(cog.views))
    assert isinstance(view, GuardianBattleView) and old.closed
    assert inter.channel.send.await_count == 1
    outsider = interaction(member(3, guild), guild)
    await view.strike.callback(outsider)
    assert not outsider.response.defer.called
    trainer = a if view.battle.actor.guardian.owner_id == 1 else b
    action = interaction(trainer, guild)
    await view.strike.callback(action)
    assert view.battle.moves == 1 and msg.edit.await_count == 1
    wrong = interaction(trainer, guild)
    await view.strike.callback(wrong)
    assert view.battle.moves == 1 and wrong.followup.send.called
    view.finish()
    assert not cog.views and not cog.duel_users and view.timer.cancelled()


@pytest.mark.asyncio
async def test_stale_click_and_fixed_turn_expiry(monkeypatch):
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    view = GuardianBattleView(cog, a, b, {}, battle())
    cog.track_view(view)
    cog.duel_users.update({1: view, 2: view})
    trainer = a if view.battle.actor.guardian.owner_id == 1 else b
    inter = interaction(trainer, guild)
    inter.data = dict(custom_id=f"meyaya:duel:{view.token}:0:99")
    await view.strike.callback(inter)
    assert view.battle.moves == 0
    view.update = AsyncMock()
    winner = view.battle.fighters[1 - view.battle.turn].guardian.owner_id
    await view.expire()
    assert view.battle.finished and view.battle.winner_id == winner
    assert not cog.duel_users and not cog.views


@pytest.mark.asyncio
async def test_delivery_failure_releases_reservation(monkeypatch):
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    old = GuardianChallengeView(cog, a, b, {1: profile(1), 2: profile(2)})
    cog.track_view(old)
    cog.duel_users.update({1: old, 2: old})
    inter = interaction(b, guild)
    inter.channel.send.side_effect = RuntimeError("delivery failed")
    monkeypatch.setattr("bot.views.guardian_battle.image_work", AsyncMock(return_value=b"PNG"))
    with pytest.raises(RuntimeError):
        await old.accept.callback(inter)
    assert not cog.views and not cog.duel_users
