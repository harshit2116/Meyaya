"""Offline combat, consent, persistence and palette-card regression tests."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO, StringIO
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from random import Random
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from PIL import Image
from sqlalchemy.dialects import postgresql

from bot.cogs.fantasy import FantasyCog
from bot.data.fantasy import CLASSES, WEAPONS, AFFINITIES
from bot.data.fantasy_combat import CLASS_COMBAT, ELEMENT_ADVANTAGES, WEAPON_COMBAT
from bot.models.fantasy_duel import FantasyDuelResult
from bot.repositories.fantasy_duels import FantasyDuelRepository
from bot.services.fantasy_generation import generate_identity
from bot.services.fantasy_duel import DuelEngine, Fighter, element_multiplier
from bot.services.fantasy_duel_renderer import render_duel, DUEL_SIZE
from bot.views.fantasy_duel import DuelChallengeView, DuelResultView


def profile(user_id=1, seed=3, class_id="knight"):
    return NS(**generate_identity(user_id, rng=Random(seed), class_id=class_id))


def engine(seed=5):
    return DuelEngine(
        Fighter.snapshot(profile(1), "Ayaya"), Fighter.snapshot(profile(2, 4, "mage"), "Haru"), seed
    )


def complete(e):
    while not e.state.finished:
        e.advance()
    return e.state


def member(user_id, guild):
    return NS(id=user_id, guild=guild, bot=False, display_name=f"Member {user_id}")


def interaction(user, guild):
    return NS(
        user=user,
        guild=guild,
        response=NS(defer=AsyncMock(), send_message=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
        edit_original_response=AsyncMock(return_value=NS(id=44, channel=NS(id=55))),
        channel=NS(send=AsyncMock()),
        message=NS(edit=AsyncMock()),
    )


def test_catalog_coverage_and_immutable_snapshot():
    assert set(CLASS_COMBAT) == set(CLASSES)
    assert set(WEAPON_COMBAT) == set(WEAPONS)
    assert all(a in AFFINITIES and b in AFFINITIES for a, b in ELEMENT_ADVANTAGES)
    p = profile()
    before = deepcopy(vars(p))
    f = Fighter.snapshot(p, "A")
    complete(DuelEngine(f, Fighter.snapshot(profile(2), "B"), 3))
    assert vars(p) == before
    assert f.rule.mode == "physical" and f.passive and f.signature


@pytest.mark.parametrize("class_id", tuple(CLASSES))
def test_each_actual_class_has_mapped_passive_signature(class_id):
    f = Fighter.snapshot(profile(class_id=class_id), "A")
    assert f.passive == CLASS_COMBAT[class_id].passive
    assert f.signature == CLASS_COMBAT[class_id].signature


def test_unknown_fields_fall_back_honestly():
    p = profile()
    p.class_id, p.passive_name, p.signature_name = "future_class", "Unknown", "Unknown"
    p.weapon_family = "future_weapon"
    f = Fighter.snapshot(p, "A")
    assert not f.passive and not f.signature
    assert complete(DuelEngine(f, Fighter.snapshot(profile(2), "B"), 5)).finished


def test_elements_and_determinism():
    assert element_multiplier("fire", "nature") == 1.1
    assert element_multiplier("nature", "fire") == 0.9
    assert element_multiplier("fire", "arcane") == 1
    assert asdict(complete(engine(5))) == asdict(complete(engine(5)))


def test_single_move_steps_preserve_round_order_and_rng():
    e = engine(5)
    while not e.state.finished:
        previous_moves = e.state.moves
        state = e.advance_move()
        assert state.moves == previous_moves + 1
        assert state.last_actor in (1, 2) and state.log
        assert state.round == (state.moves + 1) // 2
    assert 4 <= state.moves <= 40
    assert asdict(state) == asdict(complete(engine(5)))
    before = asdict(state)
    e.advance_move()
    assert asdict(state) == before


def test_crit_dodge_skill_mp_healing_and_shield():
    e = engine()
    a, b = e.state.left, e.state.right
    e.rng = NS(random=lambda: 0, uniform=lambda a, b: 1, choice=lambda values: values[0])
    e.attack(a, b)
    assert b.dodges == 1 and b.hp == b.max_hp
    values = iter((0.99, 0))
    e.rng.random = lambda: next(values)
    e.attack(a, b, True)
    assert a.critical_hits == 1 and a.skills_used == 1 and a.mp < a.max_mp
    a.mp = 0
    e.rng.random = lambda: 0.99
    skills = a.skills_used
    e.attack(a, b, True)
    assert a.skills_used == skills and a.mp == 0
    assert e.heal(b, 10000) <= b.max_hp and b.hp == b.max_hp
    b.shield = 20
    assert e.absorb(b, 15) == (0, 15)
    assert e.absorb(b, 10) == (5, 5)


def test_status_expiry_passives_and_bounded_stacks():
    e = engine()
    a, b = e.state.left, e.state.right
    e.activate_passive(a)
    shield = a.shield
    e.activate_passive(a)
    assert a.passive_used and a.shield == shield
    for name in ("burn", "bleed", "weaken", "evasion"):
        e.status(b, name, 2)
    assert len(b.statuses) == 3
    e.end_round()
    assert all(turn == 1 for turn in b.statuses.values())
    e.end_round()
    assert not b.statuses
    assert a.damage_dealt == b.damage_taken


@pytest.mark.parametrize("left_hp,right_hp,winner", [(0, 0, None), (1, 0, 1), (0, 1, 2)])
def test_knockouts(left_hp, right_hp, winner):
    e = engine()
    e.state.left.hp, e.state.right.hp = left_hp, right_hp
    e.end_round()
    assert e.state.finished and e.state.winner_id == winner


def test_maximum_round_fallback_and_draw():
    e = engine()
    e.state.round = 20
    e.end_round()
    assert e.state.finished and e.state.winner_id is None
    e = engine()
    e.state.round = 20
    e.state.right.hp = 1
    e.end_round()
    assert e.state.winner_id == 1


def test_chance_caps_and_damage_cap():
    e = engine()
    a, b = e.state.left, e.state.right
    a.luck = a.strength = b.dexterity = 100000
    values = iter((0.21, 0.23))
    e.rng = NS(
        random=lambda: next(values), uniform=lambda low, high: 1, choice=lambda values: values[0]
    )
    e.attack(a, b)
    assert not b.dodges and not a.critical_hits
    assert a.damage_dealt <= int(b.max_hp * 0.45)
    # After the opening, a vastly stronger fighter may deliver a real knockout.
    e.state.moves = 3
    b.hp = b.max_hp
    e.rng.random = lambda: 0.99
    e.attack(a, b)
    assert b.hp == 0


@pytest.mark.parametrize("class_id", ["cleric", "paladin", "mage", "warlock", "moon_priestess"])
def test_support_and_resource_effects(class_id):
    f = Fighter.snapshot(profile(class_id=class_id), "A")
    e = DuelEngine(f, Fighter.snapshot(profile(2), "B"), 10)
    e.rng = NS(random=lambda: 0.99, uniform=lambda low, high: 1, choice=lambda values: values[0])
    f.hp = 10
    old_hp, old_mp = f.hp, f.mp
    e.activate_passive(f)
    if class_id == "moon_priestess":
        assert f.hp > old_hp
    e.attack(f, e.state.right, True)
    if class_id == "cleric":
        assert f.hp > old_hp
    if class_id == "paladin":
        assert f.shield > 0
    expected = 16 if class_id == "mage" else 17 if class_id == "warlock" else 22
    assert old_mp - f.mp == expected
    assert f.skills_used == 1


def test_balance_simulator_actual_class_and_rarity_distribution():
    from scripts.simulate_fantasy_duels import simulate

    result = simulate(5000)
    assert sum(result["rounds"].values()) == 5000
    assert min(result["rounds"]) >= 2 and max(result["rounds"]) <= 20
    assert min(result["moves"]) >= 4 and max(result["moves"]) <= 40
    assert all(35 <= rate <= 65 for rate in result["class_rates"].values())
    assert 50 < result["mythic_vs_common_percent"] < 70
    assert 65 < result["stronger_stats_percent"] < 95


def test_1000_battles_are_bounded_and_not_one_shots():
    for seed in range(1000):
        e = engine(seed)
        state = complete(e)
        assert 2 <= state.round <= 20
        assert 4 <= state.moves <= 40
        for f in (state.left, state.right):
            assert 0 <= f.hp <= f.max_hp and 0 <= f.mp <= f.max_mp
            assert f.skills_used <= 2 and len(f.statuses) <= 3


def test_renderer_missing_avatar_and_palette_quality():
    e = engine()
    e.state.left.subclass = e.state.left.title = ""
    image = Image.open(
        BytesIO(render_duel(e.state, palettes=(("#ef8070",), ("#56bbef",)), intro=True))
    )
    assert image.size == DUEL_SIZE and image.format == "PNG"
    assert image.getpixel((30, 300))[0] > image.getpixel((30, 300))[2]
    assert image.getpixel((1060, 300))[2] > image.getpixel((1060, 300))[0]
    final = Image.open(BytesIO(render_duel(complete(e))))
    assert final.tobytes() != image.tobytes()


def test_three_stages_use_distinct_art_and_missing_asset_falls_back(monkeypatch):
    import bot.services.fantasy_duel_renderer as renderer

    e = engine()
    opening = render_duel(e.state, intro=True)
    e.advance_move()
    battle = render_duel(e.state)
    victory = render_duel(complete(e))
    assert len({opening, battle, victory}) == 3
    for data in (opening, battle, victory):
        assert len(data) < 4 * 1024 * 1024
        assert Image.open(BytesIO(data)).size == DUEL_SIZE

    def unavailable(kind):
        raise FileNotFoundError(kind)

    monkeypatch.setattr(renderer, "cinematic_background", unavailable)
    assert Image.open(BytesIO(render_duel(engine().state, intro=True))).size == DUEL_SIZE


@pytest.mark.asyncio
async def test_challenge_validation_and_reservation():
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    cog.get_profile = AsyncMock(side_effect=lambda user_id: profile(user_id))
    with pytest.raises(Exception, match="another human"):
        await cog.create_duel(a, a)
    b.bot = True
    with pytest.raises(Exception, match="another human"):
        await cog.create_duel(a, b)
    b.bot = False
    cog.get_profile.return_value = None
    cog.get_profile.side_effect = None
    with pytest.raises(Exception, match="saved identity"):
        await cog.create_duel(a, b)
    cog.get_profile.side_effect = lambda user_id: profile(user_id)
    _, view = await cog.create_duel(a, b)
    assert cog.duel_users == {1: view, 2: view}
    with pytest.raises(Exception, match="open duel"):
        await cog.create_duel(b, a)
    view.finish()
    assert not cog.duel_users and not cog.views
    with pytest.raises(Exception, match="15 seconds"):
        await cog.create_duel(a, b)


@pytest.mark.asyncio
async def test_only_opponent_accepts_and_single_execution():
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    view = DuelChallengeView(cog, a, b, {1: profile(1), 2: profile(2)})
    cog.track_view(view)
    cog.duel_users.update({1: view, 2: view})
    cog.run_duel = AsyncMock()
    await view.accept.callback(interaction(a, guild))
    assert not cog.run_duel.called
    inter = interaction(b, guild)
    await view.accept.callback(inter)
    await view.accept.callback(inter)
    assert cog.run_duel.await_count == 1
    assert view.closed and not cog.duel_users


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["decline", "cancel", "on_timeout"])
async def test_close_paths_release_every_lock(action):
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    view = DuelChallengeView(cog, a, b, {})
    cog.track_view(view)
    cog.duel_users.update({1: view, 2: view})
    if action == "on_timeout":
        await view.on_timeout()
    else:
        button = getattr(view, action)
        wrong = a if action == "decline" else b
        await button.callback(interaction(wrong, guild))
        assert not view.closed
        await button.callback(interaction(b if action == "decline" else a, guild))
    assert view.closed and not cog.views and not cog.duel_users


@pytest.mark.asyncio
async def test_result_security_and_timeout_preserves_result():
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    view = DuelResultView(cog, a, b, {}, complete(engine()))
    outsider = interaction(member(3, guild), guild)
    for button in view.children:
        await button.callback(outsider)
    assert outsider.response.send_message.await_count == 3
    view.message = NS(edit=AsyncMock())
    await view.on_timeout()
    assert "embed" not in view.message.edit.call_args.kwargs


@pytest.mark.asyncio
async def test_overlapping_challenges_have_one_reservation():
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())

    async def lookup(user_id):
        await asyncio.sleep(0)
        return profile(user_id)

    cog.get_profile = lookup
    results = await asyncio.gather(
        cog.create_duel(a, b), cog.create_duel(b, a), return_exceptions=True
    )
    assert sum(isinstance(result, Exception) for result in results) == 1
    assert len(cog.views) == 1 and len(cog.duel_users) == 2
    cog.cog_unload()
    assert not cog.views and not cog.duel_users


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["member", "raw_member", "guild", "message", "unload"])
async def test_lifecycle_cancels_active_callback_and_releases_admission(event):
    guild = NS(id=22)
    a, b = member(1, guild), member(2, guild)
    cog = FantasyCog(NS())
    view = DuelChallengeView(cog, a, b, {})
    view.message = NS(id=44)
    cog.track_view(view)
    cog.duel_users.update({1: view, 2: view})
    started, wait = asyncio.Event(), asyncio.Event()

    async def run(*args):
        started.set()
        await wait.wait()

    cog.run_duel = run
    task = asyncio.create_task(view.accept.callback(interaction(b, guild)))
    await started.wait()
    if event == "member":
        await cog.on_member_remove(b)
    elif event == "raw_member":
        await cog.on_raw_member_remove(NS(guild_id=guild.id, user=NS(id=b.id)))
    elif event == "guild":
        await cog.on_guild_remove(guild)
    elif event == "message":
        await cog.on_raw_message_delete(NS(message_id=44))
    else:
        cog.cog_unload()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert view.closed and not cog.views and not cog.duel_users


@pytest.mark.asyncio
async def test_unknown_duel_buttons_after_restart_do_not_execute():
    from bot.utils.game_interactions import reply_to_expired_game

    guild = NS(id=22)
    inter = interaction(member(1, guild), guild)
    inter.type = discord.InteractionType.component
    inter.data = dict(custom_id="meyaya:duel:old:0")
    inter.message = NS(id=44, author=NS(id=99), embeds=[])
    inter.response.is_done = lambda: False
    bot = NS(user=NS(id=99), get_cog=lambda name: None)
    await reply_to_expired_game(bot, inter)
    assert "expired" in inter.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_live_duel_buttons_are_left_for_view_dispatch():
    from bot.utils.game_interactions import reply_to_expired_game

    guild = NS(id=22)
    cog = FantasyCog(NS())
    view = DuelChallengeView(cog, member(1, guild), member(2, guild), {})
    cog.track_view(view)
    inter = interaction(view.right, guild)
    inter.type = discord.InteractionType.component
    inter.data = dict(custom_id=view.children[0].custom_id)
    inter.message = NS(id=44, author=NS(id=99), embeds=[])
    inter.response.is_done = lambda: False
    bot = NS(user=NS(id=99), get_cog=lambda name: cog if name == "FantasyCog" else None)
    await reply_to_expired_game(bot, inter)
    assert not inter.response.send_message.called
    view.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "render", "upload", "database", "message", "cache", "parallel"])
async def test_full_flow_every_move_image_fallbacks_and_cleanup(monkeypatch, failure):
    guild = NS(id=22, get_member=lambda user_id: NS(id=user_id))
    if failure == "cache":
        guild.get_member = lambda user_id: None
    a, b = member(1, guild), member(2, guild)
    session = NS(execute=AsyncMock())

    @asynccontextmanager
    async def begin():
        yield

    session.begin = begin

    @asynccontextmanager
    async def db():
        yield session

    bot = NS(
        db_session=db,
        build_profile_aesthetic_service=lambda: NS(
            inspect=AsyncMock(return_value=NS(avatar=b"", palette=("#ffaaaa",)))
        ),
    )
    cog = FantasyCog(bot)
    cog.report = Mock(return_value="MY-TEST")
    if failure == "parallel":
        started = set()
        both_started = asyncio.Event()

        async def inspect_fighter(fighter):
            started.add(fighter.id)
            if len(started) == 2:
                both_started.set()
            await both_started.wait()
            return NS(avatar=b"", palette=("#ffaaaa",))

        bot.build_profile_aesthetic_service = lambda: NS(inspect=inspect_fighter)
    view = DuelChallengeView(cog, a, b, {1: profile(1), 2: profile(2)})
    cog.track_view(view)
    cog.duel_users.update({1: view, 2: view})
    from bot.cogs import fantasy

    rendered_moves = []

    async def capture_render(function, state, *args, **kwargs):
        rendered_moves.append(state.moves)
        return b"PNG"

    render = AsyncMock(side_effect=capture_render)
    if failure == "render":
        render.side_effect = ValueError("render failure")
    monkeypatch.setattr(fantasy, "image_work", render)
    monkeypatch.setattr(fantasy.asyncio, "sleep", AsyncMock())
    inter = interaction(b, guild)
    battle_message = NS(id=44, channel=NS(id=55), edit=AsyncMock())
    battle_message.edit.return_value = battle_message
    intro_message = NS(id=43, channel=NS(id=55))
    result_message = NS(id=45, channel=NS(id=55))
    inter.channel.send.side_effect = [intro_message, battle_message, result_message]
    if failure in ("upload", "message"):
        error = discord.HTTPException(NS(status=500, reason="failure"), "failed")
        if failure == "message":
            inter.edit_original_response.side_effect = error
        else:

            async def edit(**kwargs):
                if kwargs.get("attachments"):
                    raise error
                return battle_message

            async def send(**kwargs):
                if kwargs.get("files"):
                    raise error
                return battle_message

            inter.channel.send.side_effect = send
            battle_message.edit.side_effect = edit
    if failure == "database":
        session.execute.side_effect = RuntimeError("DB unavailable")
    if failure == "message":
        with pytest.raises(discord.HTTPException):
            await view.accept.callback(inter)
    else:
        await view.accept.callback(inter)
        assert session.execute.await_count == 1
        if failure == "parallel":
            assert started == {1, 2}
            cog.report.assert_not_called()
        result = next(iter(cog.views))
        assert isinstance(result, DuelResultView)
        assert 4 <= result.battle.moves <= 40
        assert render.await_count == result.battle.moves + 2
        if failure != "render":
            assert rendered_moves == list(range(result.battle.moves + 1)) + [result.battle.moves]
        if failure == "none":
            sends = inter.channel.send.call_args_list
            assert len(sends) == 3
            assert sends[0].kwargs["embed"] is None and sends[0].kwargs["files"]
            assert sends[1].kwargs["embed"].title.endswith("Move 1 · Round 1")
            assert sends[2].kwargs["embed"] is None and sends[2].kwargs["files"]
            assert sends[2].kwargs["view"] is result
            assert battle_message.edit.await_count == result.battle.moves - 1
            assert inter.edit_original_response.await_count == 1
        assert "identities unchanged" in battle_message.edit.call_args.kwargs["embed"].footer.text
        if failure == "database":
            assert "could not be saved" in inter.channel.send.call_args.kwargs["content"]
        assert bot._meyaya_command_outputs[(55, result.message.id)][1].command == "versus"
        result.finish()
    assert not cog.duel_users and not cog.views


def test_migration_postgres_and_isolated_sqlite_upgrade_downgrade():
    path = Path(__file__).parent / "alembic/versions/0030_fantasy_duels.py"
    spec = spec_from_file_location("duel_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    out = StringIO()
    context = MigrationContext.configure(
        dialect=postgresql.dialect(), opts={"as_sql": True, "output_buffer": out}
    )
    with Operations.context(context):
        module.upgrade()
    assert "CREATE TABLE fantasy_duel_results" in out.getvalue()
    assert "ck_duel_winner" in out.getvalue()
    db = sa.create_engine("sqlite://")
    with db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            assert "fantasy_duel_results" in sa.inspect(conn).get_table_names()
            module.downgrade()
            assert "fantasy_duel_results" not in sa.inspect(conn).get_table_names()


@pytest.mark.asyncio
async def test_repository_is_idempotent_insert_only():
    session = NS(execute=AsyncMock())
    await FantasyDuelRepository(session).record(
        dict(
            id="a" * 32,
            guild_id=22,
            challenger_id=1,
            opponent_id=2,
            winner_id=1,
            seed=42,
            rules_version=1,
            rounds=3,
            arena="Moonlit Ruins",
            summary={},
        )
    )
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (id) DO NOTHING" in sql and "fantasy_profiles" not in sql
