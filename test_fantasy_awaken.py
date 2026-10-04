"""Offline regression tests; optional concurrency integration uses an isolated DB only."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO, StringIO
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
from sqlalchemy.orm import Session

from bot.cogs.fantasy import FantasyCog, MAX_VIEWS, result_summary
from bot.data.fantasy import AFFINITIES, CLASSES, RARITIES, RARITY_WEIGHTS, STAT_NAMES
from bot.data.help_catalog import COMMANDS, COMMAND_ORDER
from bot.models.fantasy_profile import FantasyProfile
from bot.repositories.fantasy_profiles import FantasyProfileRepository
from bot.services.fantasy_generation import generate_identity, resource_totals
from bot.services.fantasy_profile import FantasyProfileService
from bot.services.fantasy_render import CARD_SIZE, render_ritual, render_soul_card
from bot.services.fantasy_weapon_render import (
    weapon_art,
    render_weapon_acquisition,
    WEAPON_CARD_SIZE,
    MAX_WEAPON_BYTES,
)
from bot.views.fantasy import (
    AlreadyAwakenedView,
    AwakeningView,
    AwakeningRevealView,
    FantasyProfileView,
    soul_embed,
)


def profile(user_id=715925710849572904, seed=3, **kwargs):
    return FantasyProfile(
        **generate_identity(
            user_id, rng=Random(seed), now=datetime(2026, 10, 4, tzinfo=UTC), **kwargs
        )
    )


def test_weapon_families_are_distinct_and_animation_is_bounded():
    from bot.data.fantasy import WEAPONS

    arts = [weapon_art(family, "#c6aaff", "#d8b87d") for family in WEAPONS]
    assert len({art.tobytes() for art in arts}) == len(WEAPONS)
    assert all(art.size == (260, 260) and art.getbbox() for art in arts)
    soul = profile(123)
    original = result_summary(soul, NS(display_name="Ayaya"))
    data = render_weapon_acquisition(soul)
    assert len(data) <= MAX_WEAPON_BYTES
    with Image.open(BytesIO(data)) as image:
        assert image.size == WEAPON_CARD_SIZE and image.n_frames == 48
        assert image.info["loop"] == 0 and image.info["duration"] == 40
        first = image.convert("RGB").tobytes()
        image.seek(12)
        assert image.convert("RGB").tobytes() != first
    assert result_summary(soul, NS(display_name="Ayaya")) == original


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "render", "upload"])
async def test_weapon_discovery_animation_cache_and_fallback(failure):
    cog = FantasyCog(NS())
    cog.weapon_bytes = AsyncMock(return_value=None if failure == "render" else b"GIF")
    view = AwakeningRevealView(cog, 123, profile(123), interaction().user)
    cog.track_view(view)
    inter = interaction()
    if failure == "upload":
        inter.edit_original_response.side_effect = [
            discord.HTTPException(NS(status=500, reason="failed"), "upload failed"),
            NS(),
        ]
    await view.advance.callback(inter)
    kwargs = inter.edit_original_response.call_args.kwargs
    assert view.step == 1 and not view.closed
    assert "received this weapon" in kwargs["embed"].title
    assert bool(kwargs["attachments"]) == (failure == "none")
    inter.edit_original_response.side_effect = None
    await view.back.callback(inter)
    await view.advance.callback(inter)
    assert cog.weapon_bytes.await_count == (2 if failure == "render" else 1)
    view.finish()
    assert view.weapon_gif is None


@pytest.mark.asyncio
async def test_weapon_renderer_failure_returns_text_fallback(monkeypatch):
    cog = FantasyCog(NS())
    monkeypatch.setattr(
        "bot.cogs.fantasy.image_work", AsyncMock(side_effect=ValueError("bad render"))
    )
    assert await cog.weapon_bytes(profile(123)) is None


@pytest.mark.parametrize("class_id", tuple(CLASSES))
def test_generation_compatible_balanced_and_stored(class_id):
    rule = CLASSES[class_id]
    for seed in range(30):
        values = generate_identity(seed + 1, rng=Random(seed), class_id=class_id)
        assert values["class_name"] == rule.name
        assert values["subclass_name"] in rule.subclasses
        assert values["affinity_id"] in rule.affinities
        assert values["weapon_family"] in rule.weapons
        stats = {key: values[key] for key in STAT_NAMES}
        assert values["base_stats"] == stats
        assert sum(stats.values()) == 75
        assert all(6 <= value <= 24 for value in stats.values())
        assert resource_totals(stats, rule) == (values["hp"], values["mp"])
        assert values["hp"] == values["max_hp"] and values["mp"] == values["max_mp"]
        assert values["level"] == 1 and values["xp"] == 0
        assert values["weapon_rarity"] in RARITIES
        assert values["passive_name"] == rule.passive and values["signature_name"] == rule.signature
        assert set(values) == set(FantasyProfile.__table__.columns.keys())
        for key in (
            "weapon_id",
            "passive_id",
            "signature_id",
            "fantasy_title",
            "description",
            "meyaya_reaction",
        ):
            assert values[key]
        for column in FantasyProfile.__table__.columns:
            if isinstance(column.type, sa.String) and column.type.length:
                assert len(values[column.name]) <= column.type.length


def test_rarity_distribution_and_no_stat_advantage():
    assert sum(RARITY_WEIGHTS) == 100
    assert len(RARITIES) == 6
    count = dict.fromkeys(RARITIES, 0)
    for seed in range(2000):
        values = generate_identity(seed + 1, rng=Random(seed))
        count[values["weapon_rarity"]] += 1
        assert sum(values[stat] for stat in STAT_NAMES) == 75
    assert all(count.values())
    assert 650 < count["Common"] < 950
    assert count["Mythic"] < 25


@pytest.mark.parametrize("user_id", [0, -1, "123", None])
def test_invalid_id_rejected(user_id):
    with pytest.raises(ValueError):
        generate_identity(user_id)


class SyncAsyncSession:
    """Exercise actual ORM SQL against SQLite without adding a runtime driver."""

    def __init__(self, session):
        self.session = session

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield

    async def get(self, *args):
        return self.session.get(*args)

    async def execute(self, *args):
        return self.session.execute(*args)


@pytest.mark.asyncio
async def test_first_persist_second_never_regenerates_and_conflict_returns_winner(monkeypatch):
    engine = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        first, created = await FantasyProfileService(SyncAsyncSession(session)).awaken(123)
        assert created
        original = {
            column.name: getattr(first, column.name) for column in FantasyProfile.__table__.columns
        }
    monkeypatch.setattr(
        "bot.services.fantasy_profile.generate_identity",
        Mock(side_effect=AssertionError("Rerolled!")),
    )
    with Session(engine, expire_on_commit=False) as session:
        second, created = await FantasyProfileService(SyncAsyncSession(session)).awaken(123)
        assert not created
        # SQLite omits timezone data; compare all other actual stored values.
        assert all(
            getattr(second, key) == value for key, value in original.items() if key != "awakened_at"
        )
    with Session(engine, expire_on_commit=False) as session:
        async with SyncAsyncSession(session).begin():
            winner, created = await FantasyProfileRepository(
                SyncAsyncSession(session)
            ).create_if_absent(generate_identity(123, rng=Random(99)))
            assert not created and winner.weapon_name == first.weapon_name
        assert session.scalar(sa.select(sa.func.count()).select_from(FantasyProfile)) == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_atomic_postgres_insert_sql_and_rollback():
    statement = None

    async def execute(value):
        nonlocal statement
        statement = value
        return NS(scalar_one_or_none=lambda: None)

    winner = profile(123)
    session = NS(execute=execute, get=AsyncMock(return_value=winner))
    result, created = await FantasyProfileRepository(session).create_if_absent(
        generate_identity(123)
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (user_id) DO NOTHING RETURNING" in sql
    assert "DO UPDATE" not in sql and "guild_id" not in sql
    assert result is winner and not created
    session.get.assert_awaited_once_with(FantasyProfile, 123)
    engine = sa.create_engine("sqlite://")
    FantasyProfile.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        service = FantasyProfileService(SyncAsyncSession(session))
        service.profiles.create_if_absent = AsyncMock(side_effect=RuntimeError("DB rejected write"))
        with pytest.raises(RuntimeError):
            await service.awaken(123)
        assert session.scalar(sa.select(sa.func.count()).select_from(FantasyProfile)) == 0
    engine.dispose()


def migration_module():
    path = Path(__file__).parent / "alembic/versions/0029_fantasy_profiles.py"
    spec = spec_from_file_location("fantasy_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_matches_model_and_offline_upgrade_downgrade():
    module = migration_module()
    assert module.down_revision == "0028_dashboard_usage"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        module.upgrade()
        module.downgrade()
    sql = output.getvalue()
    assert "PRIMARY KEY (user_id)" in sql and "DROP TABLE fantasy_profiles" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql and "base_stats JSON NOT NULL" in sql
    for column in FantasyProfile.__table__.columns:
        assert column.name in sql and column.nullable is False
    for constraint in FantasyProfile.__table__.constraints:
        if isinstance(constraint, sa.CheckConstraint):
            assert constraint.name in sql


@pytest.mark.parametrize("affinity", tuple(AFFINITIES))
def test_renderer_theme_size_avatar_and_embed_limits(affinity):
    soul = profile()
    soul.affinity_id, soul.affinity_name = affinity, AFFINITIES[affinity].name
    avatar = BytesIO()
    Image.new("RGB", (512, 512), "#ed728e").save(avatar, "PNG")
    data = render_soul_card(soul, "W" * 200, avatar.getvalue())
    assert len(data) < 4 * 1024 * 1024
    with Image.open(BytesIO(data)) as card:
        assert card.size == CARD_SIZE and card.getpixel((450, 350)) == (237, 114, 142)
    for tab in ("character", "weapon", "abilities", "details"):
        embed = soul_embed(soul, "@everyone", tab=tab, image=True)
        assert len(embed) < 6000 and len(embed.description) < 4096
        assert all(len(field.value) <= 1024 for field in embed.fields)
        assert embed.image.url == "attachment://meyaya-soul.png"


def test_bad_avatar_fallback_and_small_smooth_ritual():
    soul = profile()
    assert render_soul_card(soul, "Ayaya", b"corrupt")
    gif = render_ritual(soul)
    assert len(gif) < 1024 * 1024
    with Image.open(BytesIO(gif)) as image:
        assert image.size == (560, 280) and image.n_frames >= 20
        assert image.info["loop"] == 0


def member(user_id=123):
    return NS(
        id=user_id,
        display_name="Ayaya",
        display_avatar=NS(
            with_size=lambda size: NS(with_format=lambda fmt: "https://cdn.discordapp.com/test.png")
        ),
    )


def context(user_id=123):
    return NS(author=member(user_id), defer=AsyncMock(), send=AsyncMock(), guild=NS(id=1))


def interaction(user_id=123):
    msg = NS(id=9, channel=NS(id=5), edit=AsyncMock())
    return NS(
        user=member(user_id),
        channel=NS(id=5),
        guild_id=1,
        channel_id=5,
        response=NS(defer=AsyncMock(), send_message=AsyncMock()),
        edit_original_response=AsyncMock(return_value=msg),
        followup=NS(send=AsyncMock(return_value=msg)),
    )


@pytest.mark.asyncio
async def test_commands_first_existing_missing_and_database_error():
    cog = FantasyCog(NS())
    ctx = context()
    cog.get_profile = AsyncMock(return_value=None)
    await FantasyCog.awaken.callback(cog, ctx)
    assert isinstance(ctx.send.call_args.kwargs["view"], AwakeningView)
    assert ctx.send.call_args.kwargs["embed"].title.endswith("stirring…")
    assert cog.pending[123].owner == 123
    # Another confirmation isn't created while the first is pending.
    await FantasyCog.awaken.callback(cog, ctx)
    assert len(cog.views) == 1
    cog.cog_unload()
    cog.get_profile.return_value = profile(123)
    await FantasyCog.awaken.callback(cog, ctx)
    assert isinstance(ctx.send.call_args.kwargs["view"], AlreadyAwakenedView)
    cog.cog_unload()
    cog.get_profile.return_value = None
    await FantasyCog.fantasyprofile.callback(cog, ctx, member(456))
    assert ctx.send.call_args.args == ("Their soul hasn't awakened yet.",)
    cog.get_profile.side_effect = RuntimeError("DB unavailable")
    await FantasyCog.awaken.callback(cog, ctx)
    assert "Error ID:" in ctx.send.call_args.args[0]
    assert not cog.views


@pytest.mark.asyncio
async def test_ownership_cancel_timeout_and_view_bounds():
    cog = FantasyCog(NS())
    view = AwakeningView(cog, 123)
    cog.track_view(view)
    cog.pending[123] = view
    outsider = interaction(456)
    assert not await view.interaction_check(outsider)
    assert outsider.response.send_message.call_args.kwargs["ephemeral"]
    await view.decline.callback(interaction())
    assert view.closed and all(button.disabled for button in view.children)
    assert not cog.pending and not cog.views
    for index in range(MAX_VIEWS):
        view = AwakeningView(cog, index)
        cog.track_view(view)
    with pytest.raises(Exception, match="busy"):
        cog.track_view(AwakeningView(cog, 1000))
    view.message = NS(edit=AsyncMock())
    await view.on_timeout()
    view.message.edit.assert_awaited_once()
    cog.cog_unload()


@pytest.mark.asyncio
async def test_confirmation_commits_before_delivery_and_loading_cleanup(monkeypatch):
    events = []

    @asynccontextmanager
    async def loading(channel, bot):
        events.append("loading_start")
        try:
            yield
        finally:
            events.append("loading_stop")

    monkeypatch.setattr("bot.views.fantasy.loading_indicator", loading)
    cog = FantasyCog(NS())
    soul = profile(123)

    async def save(user_id):
        events.append("committed")
        return soul, True

    async def deliver(*args, **kwargs):
        assert events[-1] == "committed"
        events.append("delivered")

    cog.awaken_user, cog.deliver = save, AsyncMock(side_effect=deliver)
    view = AwakeningView(cog, 123)
    await view.awaken.callback(interaction())
    await view.awaken.callback(interaction())
    assert events == ["loading_start", "committed", "delivered", "loading_stop"]
    assert cog.deliver.await_count == 1
    view = AwakeningView(cog, 123)
    cog.awaken_user = AsyncMock(side_effect=RuntimeError("db failure"))
    with pytest.raises(RuntimeError):
        await view.awaken.callback(interaction())
    assert events[-1] == "loading_stop" and view.closed


@pytest.mark.asyncio
async def test_tabs_use_stored_profile_and_keep_image():
    cog = FantasyCog(NS())
    view = FantasyProfileView(cog, 123, profile(123), "Ayaya", image=True)
    inter = interaction()
    for button in view.children:
        await button.callback(inter)
        kwargs = inter.edit_original_response.call_args.kwargs
        assert "attachments" not in kwargs and kwargs["embed"].image.url.endswith("meyaya-soul.png")
        assert sum(b.style == discord.ButtonStyle.primary for b in view.children) == 1
    view.finish()


@pytest.mark.asyncio
async def test_render_failure_falls_back_and_stores_actual_summary():
    cog = FantasyCog(NS())
    cog.card_bytes = AsyncMock(side_effect=ValueError("bad renderer"))
    soul = profile(123)
    inter = interaction()
    await cog.deliver(inter, soul, inter.user, 123)
    kwargs = inter.edit_original_response.call_args.kwargs
    assert kwargs["attachments"] == [] and not kwargs["embed"].image.url
    assert any(field.name == "Awakened identity" for field in kwargs["embed"].fields)
    entry = cog.bot._meyaya_command_outputs[(5, 9)][1]
    assert soul.weapon_name in entry.result_summary and soul.class_name in entry.result_summary
    cog.cog_unload()


@pytest.mark.asyncio
async def test_reveal_and_upload_failure_keep_saved_profile(monkeypatch):
    cog = FantasyCog(NS())
    cog.card_bytes = AsyncMock(return_value=b"PNG")
    inter = interaction()
    error = discord.HTTPException(NS(status=500, reason="failure"), "upload failed")
    inter.edit_original_response.side_effect = [error, NS(id=9, channel=NS(id=5))]
    await cog.deliver(inter, profile(123), inter.user, 123)
    assert inter.edit_original_response.await_count == 2
    assert not inter.edit_original_response.call_args.kwargs["view"].image
    cog.cog_unload()
    monkeypatch.setattr(
        "bot.cogs.fantasy.image_work", AsyncMock(side_effect=ValueError("ritual failed"))
    )
    inter = interaction()
    await cog.deliver(inter, profile(123), inter.user, 123, reveal=True)
    assert inter.edit_original_response.call_args.kwargs["embed"].title.endswith("Your awakening")
    assert isinstance(inter.edit_original_response.call_args.kwargs["view"], AwakeningRevealView)
    cog.cog_unload()


@pytest.mark.asyncio
async def test_reveal_waits_for_buttons_and_final_profile_is_explicit(monkeypatch):
    monkeypatch.setattr("bot.cogs.fantasy.image_work", AsyncMock(return_value=b"GIF"))
    cog = FantasyCog(NS())
    cog.card_bytes = AsyncMock(return_value=b"PNG")
    cog.weapon_bytes = AsyncMock(return_value=b"GIF")
    inter = interaction()
    previous = AwakeningView(cog, 123)
    cog.track_view(previous)
    cog.pending[123] = previous
    soul = profile(123)
    await cog.deliver(inter, soul, inter.user, 123, reveal=True, previous=previous)
    view = inter.edit_original_response.call_args.kwargs["view"]
    assert previous.closed and isinstance(view, AwakeningRevealView)
    assert cog.pending[123] is view and view.step == 0
    assert view.embed().fields[0].value.endswith(f"**{soul.affinity_name}**")
    assert len(view.embed().fields) == 1
    cog.card_bytes.assert_not_awaited()
    await asyncio.sleep(0)
    assert view.step == 0
    for step in range(1, 5):
        await view.advance.callback(inter)
        assert view.step == step and not view.closed
        assert view.embed().fields[0].name == "Affinity"
        assert len(view.embed()) < 6000
        cog.card_bytes.assert_not_awaited()
    assert view.advance.label == "Open full profile"
    await view.back.callback(inter)
    assert view.step == 3 and view.advance.label == "Reveal abilities"
    await view.advance.callback(inter)
    await view.advance.callback(inter)
    cog.card_bytes.assert_awaited_once()
    assert view.closed and 123 not in cog.pending
    assert isinstance(inter.edit_original_response.call_args.kwargs["view"], FantasyProfileView)
    assert soul.weapon_name in cog.bot._meyaya_command_outputs[(5, 9)][1].result_summary
    await view.advance.callback(inter)
    cog.card_bytes.assert_awaited_once()
    cog.cog_unload()


@pytest.mark.asyncio
async def test_reveal_author_timeout_and_failed_step_preserve_identity():
    cog = FantasyCog(NS())
    cog.weapon_bytes = AsyncMock(return_value=None)
    soul = profile(123)
    view = AwakeningRevealView(cog, 123, soul, interaction().user)
    cog.track_view(view)
    cog.pending[123] = view
    assert not await view.interaction_check(interaction(456))
    assert await view.interaction_check(interaction(123))
    failed = interaction()
    failed.edit_original_response.side_effect = RuntimeError("edit failed")
    with pytest.raises(RuntimeError):
        await view.advance.callback(failed)
    assert view.step == 0 and view.profile is soul and not view.closed
    assert view.advance.label == "Reveal weapon"
    view.message = NS(edit=AsyncMock())
    await view.on_timeout()
    assert view.closed and not cog.pending and not cog.views
    assert all(button.disabled for button in view.children)
    assert view.profile is soul


@pytest.mark.asyncio
async def test_reveal_busy_click_acknowledged_without_skipping_discovery():
    cog = FantasyCog(NS())
    view = AwakeningRevealView(cog, 123, profile(123), interaction().user)
    inter = interaction()
    async with view.lock:
        await view.advance.callback(inter)
    inter.response.defer.assert_awaited_once()
    inter.edit_original_response.assert_not_awaited()
    assert view.step == 0
    view.finish()


def test_help_cog_registration_and_shared_loading():
    names = {command.name for command in COMMANDS if command.category == "Fantasy / Profile"}
    assert {"awaken", "fantasyprofile", "summon", "guardian"} <= names
    assert {"awaken", "fantasyprofile"} <= set(COMMAND_ORDER["Fantasy / Profile"])
    assert (
        'load_extension("bot.cogs.fantasy")' in (Path(__file__).parent / "bot/app.py").read_text()
    )
    assert FantasyCog.awaken.app_command and FantasyCog.fantasyprofile.app_command
    assert FantasyCog.awaken._buckets._cooldown.per == 15
    assert FantasyCog.fantasyprofile._buckets._cooldown.per == 8


@pytest.mark.asyncio
async def test_simultaneous_confirmation_uses_one_save_and_cancellation_releases_loader(
    monkeypatch,
):
    entered, release = asyncio.Event(), asyncio.Event()
    stopped = []

    @asynccontextmanager
    async def loading(channel, bot):
        try:
            yield
        finally:
            stopped.append(True)

    monkeypatch.setattr("bot.views.fantasy.loading_indicator", loading)
    cog = FantasyCog(NS())

    async def save(user_id):
        entered.set()
        await release.wait()
        return profile(user_id), True

    cog.awaken_user = AsyncMock(side_effect=save)
    cog.deliver = AsyncMock()
    view = AwakeningView(cog, 123)
    cog.track_view(view)
    first = asyncio.create_task(view.awaken.callback(interaction()))
    await entered.wait()
    await view.awaken.callback(interaction())
    assert cog.awaken_user.await_count == 1
    release.set()
    await first
    assert cog.deliver.await_count == 1 and stopped == [True]
    entered.clear()
    release.clear()
    view = AwakeningView(cog, 123)
    cog.track_view(view)
    task = asyncio.create_task(view.awaken.callback(interaction()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert view.closed and not cog.views and stopped == [True, True]


@pytest.mark.asyncio
async def test_postgres_concurrent_awakenings_on_explicit_isolated_database():
    """Set only a disposable DB URL: table is created and dropped by this test."""
    import os
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = os.getenv("MEYAYA_FANTASY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("No explicitly isolated PostgreSQL test database configured")
    engine = create_async_engine(url)
    # Refuse to touch an existing fantasy table, including production.
    async with engine.begin() as connection:
        exists = await connection.scalar(sa.text("SELECT to_regclass('fantasy_profiles')"))
        if exists:
            await engine.dispose()
            pytest.fail("Refusing integration test: fantasy_profiles already exists")
        await connection.run_sync(lambda sync: FantasyProfile.__table__.create(sync))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def awaken():
        async with sessions() as session:
            return await FantasyProfileService(session).awaken(123)

    try:
        results = await asyncio.gather(*(awaken() for _ in range(12)))
        assert sum(created for _, created in results) == 1
        assert len({row.weapon_name + row.fantasy_title for row, _ in results}) == 1
        async with sessions() as session:
            assert await session.scalar(sa.select(sa.func.count()).select_from(FantasyProfile)) == 1
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: FantasyProfile.__table__.drop(sync))
        await engine.dispose()
