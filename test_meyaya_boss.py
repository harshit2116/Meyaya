"""Boss-only mechanics, public masking, cinematic failure paths and balance."""

import asyncio
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from contextlib import asynccontextmanager
import discord
import pytest
from PIL import Image, ImageDraw
from test_fantasy_duel import profile, member, interaction
from bot.cogs.fantasy import FantasyCog, result_summary
from bot.services.fantasy_boss import meyaya_boss_profile
from bot.services.fantasy_duel import Fighter, element_multiplier
from bot.services.meyaya_boss_combat import BossDuelEngine, archetype, public_fighter
from bot.services.meyaya_boss_presentation import (
    BossPresentation,
    victory_dialogue,
    contextual_victory,
    INTRO_GIF,
)
from bot.services.fantasy_duel_renderer import render_duel
from bot.services.fantasy_render import render_soul_card
from bot.views.fantasy import soul_embed
from bot.views.fantasy import FantasyProfileView
from bot.views.fantasy_duel import DuelChallengeView, DuelResultView
from bot.services.klipy import KlipyService


def boss_engine(seed=5, class_id="mage"):
    return BossDuelEngine(
        Fighter.snapshot(profile(class_id=class_id), "Player"),
        Fighter.snapshot(meyaya_boss_profile(99), "Meyaya"),
        seed,
    )


def test_boss_resources_scale_to_challenger_without_mutating_saved_profile():
    source = profile()
    before = deepcopy(vars(source))
    e = BossDuelEngine(
        Fighter.snapshot(source, "Player"), Fighter.snapshot(meyaya_boss_profile(99), "Meyaya"), 5
    )
    assert e.boss.hp == e.boss.max_hp == e.player.max_hp * 10
    assert e.boss.mp == e.boss.max_mp == e.player.max_mp * 10
    for stat in ("strength", "dexterity", "intelligence", "vitality", "luck"):
        assert getattr(e.boss, stat) == max(30, getattr(e.player, stat) * 2)
    assert vars(source) == before


@pytest.mark.asyncio
async def test_boss_profile_is_image_only_and_preserves_complete_artwork():
    from PIL import ImageChops
    from bot.services.meyaya_boss_renderer import template, render_boss_profile

    boss = meyaya_boss_profile(99)
    payload = soul_embed(boss, "Meyaya", image=True).to_dict()
    assert not any(k in payload for k in ("title", "description", "fields", "footer", "color"))
    view = FantasyProfileView(NS(), 1, boss, "Meyaya", image=True)
    assert not view.children
    avatar = BytesIO()
    Image.new("RGB", (512, 512), "#11aa55").save(avatar, "PNG")
    base = template("meyaya-profile.png")
    result = Image.open(BytesIO(render_boss_profile(boss, avatar.getvalue()))).convert("RGB")
    assert result.size == base.size
    assert ImageChops.difference(base, result).getbbox() is None
    fallback = Image.open(BytesIO(render_boss_profile(boss))).convert("RGB")
    assert ImageChops.difference(base, fallback).getbbox() is None
    view.stop()


@pytest.mark.parametrize(
    "class_id,expected",
    [
        ("knight", "tank"),
        ("ranger", "agile"),
        ("assassin", "agile"),
        ("mage", "magic"),
        ("cleric", "support"),
        ("berserker", "physical"),
        ("paladin", "tank"),
        ("warlock", "magic"),
        ("spellblade", "hybrid"),
        ("runeblade", "hybrid"),
        ("voidblade", "hybrid"),
        ("starcaller", "magic"),
        ("dreamweaver", "magic"),
        ("gravekeeper", "tank"),
        ("spirit_tamer", "tank"),
        ("storm_herald", "hybrid"),
        ("fatebinder", "magic"),
        ("dragon_warden", "tank"),
        ("moon_priestess", "support"),
        ("chronomancer", "magic"),
        ("abyss_walker", "hybrid"),
    ],
)
def test_authored_archetypes_and_once_only_form(class_id, expected):
    e = boss_engine(class_id=class_id)
    assert e.pattern == expected and archetype(e.player) == expected
    form = e.state.boss_form
    while not e.state.finished:
        e.advance_move()
        assert e.state.boss_form == form
        assert 0 <= e.memory_resistance <= 0.12
        assert e.state.memory_count <= 3
    assert e.state.moves >= 4


def test_memory_caps_reflection_normalization_and_real_cascade():
    e = boss_engine()
    e.rng = NS(random=lambda: 0.99, uniform=lambda a, b: 1, choice=lambda values: values[0])
    e.boss.hp = e.boss.max_hp = 100000
    e.player.signature_name = "CUSTOM_EXECUTABLE_NAME"
    for _ in range(10):
        e.player.mp = e.player.max_mp
        e.attack(e.player, e.boss, e.player.skills_used < 2)
    assert e.memory_resistance <= 0.12 and e.state.memory_count <= 3
    assert e.learned_signature == "CUSTOM_EXECUTABLE_NAME"
    memory = e.memory_resistance
    e.attack(e.player, e.boss)
    assert e.memory_resistance == memory
    e.player.hp = e.player.max_hp = 10000
    e.attack(e.boss, e.player)
    e.attack(e.boss, e.player)
    assert len(e.cascade_hits) == 5 and sum(e.cascade_hits) <= e.player.max_hp * 0.32
    e.attack(e.boss, e.player)
    assert e.reflected and e.boss.last_move.startswith("Prism Reflection")
    e.attack(e.boss, e.player)
    assert e.boss.last_move == "Prism Cascade"
    assert e.boss.skills_used <= 2
    assert element_multiplier(e.ray_affinity, e.player.affinity) >= 1


def test_anti_heal_piercing_and_reactive_ward_are_bounded():
    support = boss_engine(class_id="cleric")
    support.player.hp = 10
    assert support.heal(support.player, 40) == 30
    tank = boss_engine(class_id="paladin")
    tank.rng.random = lambda: 0.99
    tank.player.shield = 100
    tank.attack(tank.boss, tank.player)
    assert tank.player.shield < 100 * 0.65
    physical = boss_engine(class_id="berserker")
    physical.rng.random = lambda: 0.99
    physical.attack(physical.player, physical.boss)
    ward = physical.boss.shield
    assert ward == round(physical.boss.max_hp * 0.06)
    physical.attack(physical.player, physical.boss)
    assert physical.boss.shield <= ward


def test_masked_profile_and_renderer_never_draw_internal_numbers(monkeypatch):
    e = boss_engine()
    e.boss.hp, e.boss.max_hp, e.boss.mp, e.boss.max_mp = 1289, 99999, 7788, 88888
    e.boss.intelligence = 71717
    text = []
    original = ImageDraw.ImageDraw.text

    def capture(self, xy, value, *args, **kwargs):
        text.append(str(value))
        return original(self, xy, value, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", capture)
    for intro in (True, False):
        assert Image.open(BytesIO(render_duel(e.state, intro=intro))).size == (1100, 640)
    boss = meyaya_boss_profile(99)
    boss.hp, boss.max_hp, boss.intelligence = 1289, 99999, 71717
    render_soul_card(boss, "Meyaya")
    for tab in ("character", "weapon", "abilities", "details"):
        text.append(json.dumps(soul_embed(boss, "Meyaya", tab=tab).to_dict()))
    text.append(json.dumps(public_fighter(e.boss)))
    text.append(json.dumps(result_summary(boss, NS(display_name="Meyaya"))))
    assert "??? / ???" in " ".join(text)
    assert not any(
        secret in " ".join(text) for secret in ("1289", "99999", "7788", "88888", "71717")
    )


def test_hidden_bars_change_without_changing_text():
    from bot.services.meyaya_boss_renderer import masked_bar

    images = []
    for hp in (300, 100):
        image = Image.new("RGB", (500, 100))
        masked_bar(ImageDraw.Draw(image), 10, 40, hp, 300)
        images.append(image)
    assert images[0].getpixel((200, 48)) != images[1].getpixel((200, 48))


def test_seeded_balance_player_can_win_and_data_not_mutated():
    from scripts.simulate_meyaya_boss import simulate

    result = simulate()
    assert result["boss_win_percent"] >= 95
    assert min(result["moves"]) >= 4 and max(result["moves"]) <= 40
    a, b = boss_engine(7), boss_engine(7)
    while not a.state.finished:
        a.advance_move()
    while not b.state.finished:
        b.advance_move()
    assert asdict(a.state) == asdict(b.state)
    # Large real player offence is not defeated by an immortal/survival-floor cheat.
    strong = boss_engine()
    strong.player.intelligence = 10000
    strong.player.hp = strong.player.max_hp = 500
    while not strong.state.finished:
        strong.advance_move()
    assert strong.state.winner_id == strong.player.user_id


def test_dialogue_outcomes_context_and_sparse_triggers():
    e = boss_engine()
    e.state.winner_id = 99
    assert "# That was beautiful." in victory_dialogue(e.state)
    e.boss.hp = 1
    assert contextual_victory(e.state) == "You were one heartbeat away."
    e.state.winner_id = 1
    assert "Impossible result confirmed" in victory_dialogue(e.state)
    e.state.winner_id = None
    assert "unwritten ending" in victory_dialogue(e.state)
    for _ in range(10):
        e.speak("memory", "Once")
    assert len(e.dialogue_seen) == 1


@pytest.mark.asyncio
async def test_exact_gif_matching_cache_no_scrape_and_failure():
    response = NS(
        status=200,
        json=AsyncMock(
            return_value={
                "data": {
                    "data": [
                        {
                            "slug": "honkai-impact-22",
                            "file": {"md": {"gif": {"url": "https://cdn.klipy.com/boss.gif"}}},
                        }
                    ]
                }
            }
        ),
    )

    @asynccontextmanager
    async def get(*args, **kwargs):
        yield response

    session = NS(get=Mock(side_effect=get))
    service = KlipyService("secret", "pg", session, None)
    assert (await service.exact_gif(INTRO_GIF)).url.endswith("boss.gif")
    assert (await service.exact_gif(INTRO_GIF)).url.endswith("boss.gif")
    assert session.get.call_count == 1
    assert session.get.call_args.args[0].endswith("/gifs/items")
    assert (await service.exact_gif("https://evil.test/bad")).url is None
    response.status = 503
    assert (await service.exact_gif("https://klipy.com/gifs/other")).url is None


@pytest.mark.asyncio
async def test_cinematic_gif_failure_and_single_message_reuse(monkeypatch):
    from bot.services import meyaya_boss_presentation as presentation

    monkeypatch.setattr(presentation.asyncio, "sleep", AsyncMock())
    message = NS(edit=AsyncMock())
    message.edit.return_value = message
    channel = NS(send=AsyncMock(return_value=message))
    service = NS(exact_gif=AsyncMock(side_effect=RuntimeError("provider failed")))
    cog = NS(bot=NS(build_klipy_service=lambda: service))
    view = NS()
    cinema = BossPresentation(cog, view, channel)
    e = boss_engine()
    await cinema.intro(e.state)
    assert presentation.asyncio.sleep.await_args_list[1].args == (5.0,)
    assert channel.send.await_count == 1 and message.edit.await_count == 2
    assert "# I am Meyaya." in channel.send.call_args.kwargs["content"]
    assert channel.send.call_args.kwargs["embed"] is None
    assert await cinema.gif(INTRO_GIF) is None
    assert service.exact_gif.await_count == 1
    e.state.winner_id = 1
    await cinema.finish(e.state)
    assert channel.send.await_count == 2
    assert message.edit.await_count == 2
    assert "Impossible result confirmed" in channel.send.call_args.kwargs["content"]


@pytest.mark.asyncio
async def test_rejected_gif_embed_retries_as_dialogue(monkeypatch):
    from bot.services import meyaya_boss_presentation as presentation

    monkeypatch.setattr(presentation.asyncio, "sleep", AsyncMock())
    message = NS(edit=AsyncMock())
    channel = NS(
        send=AsyncMock(
            side_effect=[
                discord.HTTPException(NS(status=400, reason="media"), "media rejected"),
                message,
            ]
        )
    )
    service = NS(exact_gif=AsyncMock(return_value=NS(url="https://cdn.klipy.com/boss.gif")))
    cinema = BossPresentation(NS(bot=NS(build_klipy_service=lambda: service)), NS(), channel)
    await cinema.beat("# I am Meyaya.", gif=INTRO_GIF)
    assert channel.send.await_count == 2
    assert channel.send.call_args.kwargs["embed"] is None


@pytest.mark.asyncio
async def test_boss_cinematic_deletion_departure_and_cancel_clear_locks():
    guild = NS(id=5)
    left, right = member(1, guild), member(99, guild)
    cog = FantasyCog(NS(user=NS(id=99)))
    for trigger in ("deletion", "departure", "cancel"):
        view = DuelChallengeView(cog, left, right, {1: profile(), 99: meyaya_boss_profile(99)})
        cog.track_view(view)
        cog.duel_users[1] = view
        view.cinematic_message = NS(id=42)
        if trigger == "deletion":
            await cog.on_raw_message_delete(NS(message_id=42))
        elif trigger == "departure":
            await cog.on_member_remove(left)
        else:
            inter = interaction(left, guild)
            await view.cancel.callback(inter)
        assert view.closed and not cog.duel_users and not cog.views


@pytest.mark.asyncio
async def test_boss_bypasses_db_canonical_id_and_details_masking():
    cog = FantasyCog(NS(user=NS(id=99), db_session=Mock(side_effect=AssertionError("boss DB"))))
    boss = await cog.get_profile(99)
    assert boss.is_meyaya_boss
    guild = NS(id=5)
    left, right = member(1, guild), member(99, guild)
    e = boss_engine()
    while not e.state.finished:
        e.advance_move()
    view = DuelResultView(cog, left, right, {1: profile(), 99: boss}, e.state)
    inter = interaction(left, guild)
    await view.details.callback(inter)
    text = inter.response.send_message.call_args.kwargs["embed"].description
    assert "HP/MP: UNKNOWN" in text and "Damage dealt/taken" not in text
    assert view.rematch.disabled


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "gif", "render", "db", "message", "cache"])
async def test_boss_full_flow_serialization_and_cleanup(monkeypatch, failure):
    from bot.cogs import fantasy

    monkeypatch.setattr(fantasy.asyncio, "sleep", AsyncMock())
    render = AsyncMock(return_value=b"PNG")
    if failure == "render":
        render.side_effect = ValueError("bad PNG")
    monkeypatch.setattr(fantasy, "image_work", render)
    session = NS(execute=AsyncMock())

    @asynccontextmanager
    async def begin():
        yield

    session.begin = begin

    @asynccontextmanager
    async def db():
        yield session

    gif = AsyncMock(return_value=NS(url=None))
    if failure == "gif":
        gif.side_effect = RuntimeError("provider down")
    bot = NS(
        user=NS(id=99),
        db_session=db,
        build_klipy_service=lambda: NS(exact_gif=gif),
        build_profile_aesthetic_service=lambda: NS(
            inspect=AsyncMock(return_value=NS(avatar=b"", palette=()))
        ),
    )
    cog = FantasyCog(bot)
    cog.report = Mock(return_value="MY-TEST")
    guild = NS(id=5, get_member=lambda uid: NS(id=uid))
    if failure == "cache":
        guild.get_member = lambda uid: None
    left, right = member(1, guild), member(99, guild)
    right.bot = True
    view = DuelChallengeView(cog, left, right, {1: profile(), 99: meyaya_boss_profile(99)})
    cog.track_view(view)
    cog.duel_users[1] = view
    message = NS(id=9, channel=NS(id=5), edit=AsyncMock())
    message.edit.return_value = message
    view.message = message
    inter = interaction(right, guild)
    inter.channel.send.return_value = message
    inter.edit_original_response.return_value = message
    if failure == "message":
        inter.channel.send.side_effect = discord.HTTPException(
            NS(status=404, reason="gone"), "gone"
        )
    elif failure == "db":
        session.execute.side_effect = RuntimeError("DB down")
    try:
        if failure == "message":
            with pytest.raises(discord.HTTPException):
                await cog.run_duel(view, inter)
        else:
            await cog.run_duel(view, inter)
            result = next(v for v in cog.views if isinstance(v, DuelResultView))
            output = bot._meyaya_command_outputs[(5, 9)][1].result_summary
            assert '"hp": "UNKNOWN"' in output
            for call in inter.channel.send.call_args_list + message.edit.call_args_list:
                embed = call.kwargs.get("embed")
                if embed:
                    assert "HP 300/300" not in (embed.description or "")
            recorded = (
                session.execute.call_args.args[0].compile().params["summary"]
                if failure != "db"
                else None
            )
            if recorded:
                boss = recorded["fighters"][1]
                assert boss["hp"] == "UNKNOWN" and "strength" not in boss
            result.finish()
    finally:
        view.finish()
    assert not cog.duel_users and not cog.views
