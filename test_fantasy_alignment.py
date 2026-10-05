"""Saved faction oaths, reveal safety, resonance and guardian presentation."""

from copy import deepcopy
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from PIL import Image

from bot.cogs.fantasy import FantasyCog
from bot.data.fantasy_alignment import alignment_values, patron_for
from bot.models.fantasy_profile import FantasyProfile
from bot.services.fantasy_profile import FantasyProfileService, AlignmentUnavailable
from bot.services.fantasy_duel import Fighter, DuelEngine
from bot.services.fantasy_guardian import bound_guardian
from bot.services.fantasy_render import render_soul_card, theme_for
from bot.services.guardian_render import creature
from bot.views.fantasy import AwakeningRevealView, soul_embed
from test_fantasy_awaken import profile, interaction, SyncAsyncSession


@pytest.mark.asyncio
async def test_saved_alignment_lock_stale_choice_and_rebirth_clear():
    db = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(db)
    source = profile(123)
    stamp = source.awakened_at
    core = (source.class_id, source.weapon_id, deepcopy(source.base_stats))
    with Session(db, expire_on_commit=False) as session:
        session.add(source)
        session.commit()
        service = FantasyProfileService(SyncAsyncSession(session))
        with pytest.raises(AlignmentUnavailable):
            await service.choose_alignment(123, stamp, "random")
        with pytest.raises(AlignmentUnavailable, match="identity changed"):
            await service.choose_alignment(123, stamp - timedelta(seconds=1), "meyaya")
        saved = await service.choose_alignment(123, stamp, "veyra")
        assert saved.alignment == "veyra"
        assert (saved.class_id, saved.weapon_id, saved.base_stats) == core
        with pytest.raises(AlignmentUnavailable, match="already sealed"):
            await service.choose_alignment(123, stamp, "meyaya")
    with Session(db, expire_on_commit=False) as session:
        service = FantasyProfileService(SyncAsyncSession(session))
        assert patron_for(await service.get(123)).name == "Veyra"
        session.commit()
        fresh = await service.rebirth(123, stamp, now=stamp + timedelta(days=1))
        assert fresh.alignment == "unclaimed"
        with pytest.raises(AlignmentUnavailable, match="identity changed"):
            await service.choose_alignment(123, stamp, "meyaya")
    db.dispose()


@pytest.mark.asyncio
async def test_alignment_write_failure_rolls_back():
    db = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(db)
    with Session(db, expire_on_commit=False) as session:
        source = profile(123)
        session.add(source)
        session.commit()
        service = FantasyProfileService(SyncAsyncSession(session))
        service.profiles.replace_identity = AsyncMock(side_effect=RuntimeError("write failed"))
        with pytest.raises(RuntimeError):
            await service.choose_alignment(123, source.awakened_at, "meyaya")
    with Session(db) as session:
        assert session.get(FantasyProfile, 123).alignment == "unclaimed"
    db.dispose()


@pytest.mark.asyncio
async def test_choice_owner_stage_busy_double_click_and_media_fallback():
    cog = FantasyCog(NS())
    saved = profile(123)
    saved.alignment = "meyaya"
    cog.align_user = AsyncMock(return_value=saved)
    cog.deliver = AsyncMock()
    cog.weapon_bytes = AsyncMock(return_value=None)
    view = AwakeningRevealView(cog, 123, profile(123), interaction().user)
    own = interaction()
    await view.origin.callback(own)
    cog.align_user.assert_not_awaited()
    await view.origin.callback(interaction(456))
    cog.align_user.assert_not_awaited()
    view.step = 1
    view.refresh_buttons()
    own.edit_original_response.side_effect = [
        discord.HTTPException(NS(status=400, reason="upload"), "failed"),
        NS(),
    ]
    await view.advance.callback(own)
    assert view.step == 2 and own.edit_original_response.call_args.kwargs["attachments"] == []
    assert view.children == [view.origin, view.erasure, view.back]
    async with view.lock:
        await view.origin.callback(own)
    cog.align_user.assert_not_awaited()

    async def deliver(*args, **kwargs):
        view.finish()

    cog.deliver.side_effect = deliver
    await view.origin.callback(own)
    await view.erasure.callback(own)
    cog.align_user.assert_awaited_once()
    assert cog.align_user.call_args.args[-1] == "meyaya"


@pytest.mark.parametrize("choice", ["meyaya", "veyra"])
def test_patron_profile_theme_comment_and_balanced_guardian_forms(choice):
    soul = profile(123)
    neutral = bound_guardian(soul)
    for k, value in alignment_values(soul, choice).items():
        setattr(soul, k, value)
    patron = patron_for(soul)
    card = render_soul_card(soul, "Ayaya")
    assert Image.open(BytesIO(card)).size == (900, 1000) and len(card) < 4 * 1024 * 1024
    assert theme_for(soul).color == patron.color
    text = str(soul_embed(soul, "Ayaya").to_dict())
    assert patron.name in text and patron.oath in text and patron.resonance in text
    guardian = bound_guardian(soul)
    assert guardian.name != neutral.name and guardian.alignment == choice
    assert guardian.species == neutral.species
    assert (guardian.max_hp, guardian.attack, guardian.defense) == (
        neutral.max_hp,
        neutral.attack,
        neutral.defense,
    )
    assert creature(guardian).tobytes() != creature(neutral).tobytes()


def test_origin_and_erasure_have_real_bounded_combat_effects():
    a, b = profile(1), profile(2)
    a.alignment, b.alignment = "meyaya", "veyra"
    origin, erasure = Fighter.snapshot(a, "Origin"), Fighter.snapshot(b, "Erasure")
    e = DuelEngine(origin, erasure, 5)
    origin.passive = erasure.passive = ""
    e.activate_passive(origin)
    ward = origin.shield
    assert ward == round(origin.max_hp * 0.04)
    e.activate_passive(origin)
    assert origin.shield == ward
    origin.hp = 1
    assert e.heal(origin, 10) == 11
    origin.hp = origin.max_hp
    origin.shield = 100
    e.rng = NS(random=lambda: 0.99, uniform=lambda a, b: 1, choice=lambda options: options[0])
    e.attack(erasure, origin)
    assert erasure.erasure_hits == 1 and "erasure_trace" in origin.statuses
    origin.shield = 0
    before = origin.hp
    e.end_round()
    assert origin.hp < before
    e.attack(erasure, origin)
    e.attack(erasure, origin)
    assert erasure.erasure_hits == 2
