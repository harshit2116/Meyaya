"""Transactional rerolls, self-only UI, persistent cooldown and native weapon variety."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace as NS

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql
from alembic.migration import MigrationContext
from alembic.operations import Operations

from bot.models.fantasy_profile import FantasyProfile
from bot.services.fantasy_profile import FantasyProfileService, RebirthUnavailable
from bot.services.fantasy_generation import generate_identity
from bot.services.fantasy_weapon_render import weapon_art, weapon_design
from bot.data.fantasy import WEAPONS
from bot.cogs.fantasy import FantasyCog
from bot.cogs.admin import AdminCog
from bot.views.fantasy_rebirth import RebirthView
from test_fantasy_awaken import SyncAsyncSession
from test_fantasy_duel import interaction, member, profile, engine
from test_guardian_battle import battle


@pytest.mark.asyncio
async def test_rebirth_persists_count_cooldown_and_rejects_stale_confirmations():
    db = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(db)
    now = datetime(2026, 10, 5, tzinfo=UTC)
    initial = generate_identity(123, now=now - timedelta(days=1))
    with Session(db, expire_on_commit=False) as s:
        s.add(FantasyProfile(**initial))
        s.commit()
        fresh = await FantasyProfileService(SyncAsyncSession(s)).rebirth(
            123, initial["awakened_at"], now=now
        )
        assert fresh.rebirth_count == 1 and fresh.level == 1 and fresh.xp == 0
        assert fresh.hp == fresh.max_hp and fresh.mp == fresh.max_mp
        expected = fresh.awakened_at
    with Session(db, expire_on_commit=False) as s:
        service = FantasyProfileService(SyncAsyncSession(s))
        with pytest.raises(RebirthUnavailable, match="identity changed"):
            await service.rebirth(123, initial["awakened_at"], now=now)
        with pytest.raises(RebirthUnavailable, match="24-hour cooldown"):
            await service.rebirth(123, expected, now=now + timedelta(hours=23))
        fresh = await service.rebirth(123, expected, now=now + timedelta(hours=24))
        assert fresh.rebirth_count == 2
        # Owner reset bypasses the player cooldown, including after a fresh roll.
        assert await service.reset(123)
        assert not AdminCog.fantasyreset._buckets.valid
    db.dispose()


@pytest.mark.asyncio
async def test_failed_rebirth_write_rolls_back(monkeypatch):
    db = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(db)
    original = generate_identity(1)
    with Session(db, expire_on_commit=False) as s:
        s.add(FantasyProfile(**original))
        s.commit()
        service = FantasyProfileService(SyncAsyncSession(s))
        service.profiles.replace_identity = AsyncMock(side_effect=RuntimeError("write failed"))
        with pytest.raises(RuntimeError):
            await service.rebirth(1, original["awakened_at"])
    with Session(db) as s:
        old = s.get(FantasyProfile, 1)
        assert old.rebirth_count == 0 and old.last_rebirth_at is None
        assert old.weapon_id == original["weapon_id"]
    db.dispose()


@pytest.mark.asyncio
async def test_confirmation_owner_cancel_and_double_click():
    cog = FantasyCog(NS())
    cog.rebirth_user = AsyncMock(return_value=profile(1, 9))
    cog.deliver = AsyncMock()
    view = RebirthView(cog, 1, profile(1))
    cog.track_view(view)
    cog.pending[1] = view
    guild = NS(id=22)
    outsider = interaction(member(2, guild), guild)
    await view.confirm.callback(outsider)
    cog.rebirth_user.assert_not_called()
    own = interaction(member(1, guild), guild)
    await view.confirm.callback(own)
    await view.confirm.callback(own)
    assert cog.rebirth_user.await_count == 1 and view.closed
    assert not cog.pending and cog.deliver.await_count == 1
    cancel = RebirthView(cog, 1, profile(1))
    cog.track_view(cancel)
    cog.pending[1] = cancel
    await cancel.cancel.callback(own)
    assert cancel.closed and cog.rebirth_user.await_count == 1


@pytest.mark.asyncio
async def test_no_rebirth_during_battle_or_awaken_and_no_target_argument():
    cog = FantasyCog(NS())
    cog.get_profile = AsyncMock()
    ctx = NS(author=NS(id=1), defer=AsyncMock(), send=AsyncMock())
    cog.duel_users[1] = object()
    await FantasyCog.rebirth.callback(cog, ctx)
    cog.get_profile.assert_not_called()
    assert len(FantasyCog.rebirth.app_command.parameters) == 0


def test_migration_and_locked_select():
    path = Path("alembic/versions/0031_fantasy_rebirth.py")
    spec = spec_from_file_location("rebirth_migration", path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0030_fantasy_duels"
    output = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(ctx):
        mod.upgrade()
        mod.downgrade()
    sql = output.getvalue()
    assert "ADD COLUMN rebirth_count INTEGER DEFAULT '0' NOT NULL" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql and "DROP COLUMN last_rebirth_at" in sql
    query = sa.select(FantasyProfile).where(FantasyProfile.user_id == 1).with_for_update()
    assert "FOR UPDATE" in str(query.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("family", tuple(WEAPONS))
def test_three_distinct_weapon_geometries_and_deterministic_choice(family):
    arts = [weapon_art(family, "#b994ff", "#f4cd7b", i, 44) for i in range(3)]
    assert len({a.tobytes() for a in arts}) == 3
    assert all(a.getchannel("A").getextrema() == (0, 255) for a in arts)
    for i, name in enumerate(WEAPONS[family][1]):
        p = NS(
            weapon_family=family,
            weapon_name="Arcane " + name,
            weapon_id="arcane:" + family + ":" + name,
        )
        assert weapon_design(p)[0] == i and weapon_design(p) == weapon_design(p)


def test_three_event_window_keeps_latest_in_both_engines():
    e = engine()
    previous = []
    for _ in range(4):
        e.advance_move()
        assert e.state.history == (previous + e.state.log)[-3:]
        previous = e.state.history.copy()
    b = battle()
    for i in range(5):
        b.log = f"Event {i}"
    assert b.history == ["Event 2", "Event 3", "Event 4"]


def test_guardian_dodge_preserves_ward_and_attack_consumes_mp():
    b = battle()
    attacker, defender = b.actor, b.fighters[1 - b.turn]
    defender.guarded = True
    hp, mp = defender.hp, attacker.mp
    b.rng = NS(uniform=lambda a, z: 1, random=lambda: 0)
    b.choose(attacker.guardian.owner_id, "affinity")
    assert defender.hp == hp and defender.guarded and defender.dodges == 1
    assert attacker.mp == mp - 14 and "DODGE" in b.log
