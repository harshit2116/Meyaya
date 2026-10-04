"""Owner-only, literal-prefix-only, explicit single-user fantasy reset."""

from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from bot.cogs.admin import AdminCog, fantasy_reset_prefix, private_owner
from bot.cogs.fantasy import FantasyCog
from bot.models.fantasy_profile import FantasyProfile
from bot.services.fantasy_generation import generate_identity
from bot.services.fantasy_profile import FantasyProfileService
from bot.views.fantasy import AwakeningView, FantasyProfileView
from test_fantasy_awaken import SyncAsyncSession


def context(owner=715925710849572904, prefix="uwu ", interaction=None):
    return NS(author=NS(id=owner), prefix=prefix, interaction=interaction, send=AsyncMock())


def test_owner_prefix_and_no_slash_registration():
    command = AdminCog.fantasyreset
    assert command.hidden and not hasattr(command, "app_command")
    assert private_owner(context()) and not private_owner(context(owner=123))
    assert fantasy_reset_prefix(context())
    assert not fantasy_reset_prefix(context(prefix="<@1521863347342016533> "))
    assert not fantasy_reset_prefix(context(prefix="!"))
    assert not fantasy_reset_prefix(context(interaction=object()))
    assert private_owner in command.checks and fantasy_reset_prefix in command.checks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,prefix", [(123, "uwu "), (715925710849572904, "!"), (715925710849572904, "<@1> ")]
)
async def test_denied_callback_never_touches_database(owner, prefix):
    bot = NS(db_session=Mock(), get_cog=Mock())
    await AdminCog.fantasyreset.callback(
        AdminCog(bot), context(owner, prefix), NS(id=123), "confirm"
    )
    bot.db_session.assert_not_called()
    bot.get_cog.assert_not_called()


@pytest.mark.asyncio
async def test_without_confirmation_only_warns():
    bot = NS(db_session=Mock())
    ctx = context()
    await AdminCog.fantasyreset.callback(AdminCog(bot), ctx, NS(id=123))
    assert "across all servers" in ctx.send.call_args.args[0]
    assert "uwu fantasyreset 123 confirm" in ctx.send.call_args.args[0]
    bot.db_session.assert_not_called()


@pytest.mark.asyncio
async def test_reset_commits_selected_user_only_then_can_awaken_again():
    engine = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [FantasyProfile(**generate_identity(123)), FantasyProfile(**generate_identity(456))]
        )
        session.commit()
        service = FantasyProfileService(SyncAsyncSession(session))
        assert await service.reset(123)
    with Session(engine, expire_on_commit=False) as session:
        assert session.get(FantasyProfile, 123) is None
        assert session.get(FantasyProfile, 456) is not None
        session.rollback()
        service = FantasyProfileService(SyncAsyncSession(session))
        assert not await service.reset(123)
        row, created = await service.awaken(123)
        assert created and row.user_id == 123
    engine.dispose()


@pytest.mark.asyncio
async def test_command_closes_target_views_not_another_user(monkeypatch):
    service = NS(reset=AsyncMock(return_value=True))
    monkeypatch.setattr("bot.cogs.admin.FantasyProfileService", lambda session: service)

    @asynccontextmanager
    async def session():
        yield object()

    bot = NS(db_session=session)
    fantasy = FantasyCog(bot)
    bot.get_cog = lambda name: fantasy
    pending = AwakeningView(fantasy, 123)
    other = AwakeningView(fantasy, 456)
    displayed = FantasyProfileView(fantasy, 789, FantasyProfile(**generate_identity(123)), "target")
    for view in (pending, other, displayed):
        fantasy.track_view(view)
        view.message = NS(edit=AsyncMock())
    fantasy.pending[123] = pending
    ctx = context()
    await AdminCog.fantasyreset.callback(AdminCog(bot), ctx, NS(id=123), "confirm")
    service.reset.assert_awaited_once_with(123)
    assert pending.closed and displayed.closed and not other.closed
    assert 123 not in fantasy.pending
    assert "identity reset" in ctx.send.call_args.args[0]
    fantasy.cog_unload()
