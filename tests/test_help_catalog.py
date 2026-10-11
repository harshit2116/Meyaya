"""The help directory must match every slash and written command."""

from __future__ import annotations

import pytest

from bot.app import MeyayaBot
from bot.config.settings import Settings
from bot.data.help_catalog import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_ORDER,
    COMMAND_ORDER,
    COMMANDS,
    commands_in_category,
)
from bot.views.help import build_help_embed
from bot.views.help import HelpView
from bot.utils.command_parameters import normalize_member_parameters, member_annotation
from bot.utils.command_aliases import SHORT_COMMANDS, install_command_aliases
import discord

EXTENSIONS = (
    "bot.cogs.interactions",
    "bot.cogs.daily",
    "bot.cogs.profile",
    "bot.cogs.profile_studio",
    "bot.cogs.ship",
    "bot.cogs.fun",
    "bot.cogs.extras",
    "bot.cogs.member_fun",
    "bot.cogs.celestial",
    "bot.cogs.fantasy",
    "bot.cogs.character_catalog",
    "bot.cogs.solo_games",
    "bot.cogs.social_games",
    "bot.cogs.marriage",
    "bot.cogs.court",
    "bot.cogs.fact_check",
    "bot.cogs.memory",
    "bot.cogs.roleplay",
    "bot.cogs.monitor",
    "bot.cogs.voice_live",
    "bot.cogs.admin",
    "bot.cogs.moderation",
)


def test_help_embeds_fit_discord_limits() -> None:
    assert len(build_help_embed(bot_mention="@Meyaya")) <= 6000
    for category in CATEGORY_DESCRIPTIONS:
        embed = build_help_embed(bot_mention="@Meyaya", category=category)
        assert len(embed) <= 6000
        assert len(embed.description or "") <= 4096
        assert all(len(field.value) <= 1024 for field in embed.fields)


@pytest.mark.asyncio
async def test_help_overview_covers_every_command_directly():
    view = HelpView(owner_id=1, bot_mention="@Meyaya")
    try:
        for category in CATEGORY_ORDER:
            view.category = category
            view.refresh_items()
            assert len(view.children) == 2
        overview = build_help_embed(bot_mention="@Meyaya")
        text = "\n".join(field.value for field in overview.fields)
        assert all(f"`/{entry.name}`" in text for entry in COMMANDS)
    finally:
        view.stop()


@pytest.mark.asyncio
async def test_help_category_respects_access_and_timeout():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    view = HelpView(owner_id=1, bot_mention="@Meyaya", command_prefix="u")
    response = SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock())
    interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=response)
    try:
        view.category = "Essentials"
        view.refresh_items()
        picker = view.children[0]
        picker._values = ["Essentials"]
        assert await view.interaction_check(interaction)
        await picker.callback(interaction)
        embed = response.edit_message.call_args.kwargs["embed"]
        assert "/profile [member]" in embed.description
        interaction.user.id = 2
        assert not await view.interaction_check(interaction)
        response.send_message.assert_awaited_once()
        await view.on_timeout()
        assert all(child.disabled for child in view.children if not isinstance(child, discord.ui.Button) or not child.url)
    finally:
        view.stop()


def test_help_uses_the_server_prefix() -> None:
    embed = build_help_embed(
        bot_mention="@Meyaya",
        command_prefix="u",
        command_name="profile",
    )
    ways_to_ask = embed.fields[0].value
    assert "`u profile [member]`" in ways_to_ask
    assert "`uwu profile [member]`" not in ways_to_ask


def test_detailed_help_omits_generic_notes() -> None:
    from types import SimpleNamespace

    registered = SimpleNamespace(
        signature="[member]", checks=[],
        _buckets=SimpleNamespace(_cooldown=None),
    )
    slash = SimpleNamespace(
        parameters=[SimpleNamespace(display_name="member", required=False)],
        default_permissions=None,
    )
    bot = SimpleNamespace(
        get_command=lambda _: registered,
        tree=SimpleNamespace(get_command=lambda _: slash),
    )
    embed = build_help_embed(bot_mention="@Meyaya", command_name="profile", bot=bot)
    fields = {field.name: field.value for field in embed.fields}
    assert "Permissions" not in fields
    assert "Cooldown" not in fields
    assert "Angle brackets" not in fields["Ways to ask"]
    assert "`/profile [member:value]`" in fields["Ways to ask"]
    assert "Example" in fields


def test_detailed_help_omits_review_cooldown() -> None:
    from types import SimpleNamespace

    registered = SimpleNamespace(checks=[], _buckets=SimpleNamespace(_cooldown=None))
    bot = SimpleNamespace(get_command=lambda _: registered)
    embed = build_help_embed(bot_mention="@Meyaya", command_name="checkclaim", bot=bot)
    fields = {field.name: field.value for field in embed.fields}
    assert "Cooldown" not in fields


def test_detailed_help_keeps_required_permissions() -> None:
    from types import SimpleNamespace
    from discord.ext import commands

    async def callback(ctx):
        pass

    registered = commands.Command(commands.has_permissions(manage_guild=True)(callback))
    bot = SimpleNamespace(get_command=lambda _: registered)
    embed = build_help_embed(bot_mention="@Meyaya", command_name="serversetup", bot=bot)
    fields = {field.name: field.value for field in embed.fields}
    assert fields["Permissions"] == "Member: Manage Guild"
    assert "Cooldown" not in fields


def test_help_categories_and_commands_have_explicit_order() -> None:
    assert set(CATEGORY_ORDER) == set(CATEGORY_DESCRIPTIONS)
    assert len(CATEGORY_ORDER) == len(set(CATEGORY_ORDER))
    for category in CATEGORY_ORDER:
        actual = tuple(command.name for command in commands_in_category(category))
        assert actual == COMMAND_ORDER[category]


@pytest.mark.asyncio
async def test_catalog_matches_written_and_slash_commands() -> None:
    settings = Settings(
        DISCORD_TOKEN="test-token",
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        REDIS_URL="redis://localhost:6379/15",
    )
    bot = MeyayaBot(settings)
    # Initialize Discord's local readiness event without logging into Discord.
    await bot._async_setup_hook()
    try:
        for extension in EXTENSIONS:
            await bot.load_extension(extension)
        assert len(bot.tree.get_commands()) <= 100
        for removed in ("palette", "room", "warninglabel", "badapple", "badapplestop"):
            assert bot.get_command(removed) is None
            assert bot.tree.get_command(removed) is None
        assert bot.tree.get_command("dungeon") is not None
        normalize_member_parameters(bot)
        normalize_member_parameters(bot)  # Owner sync is safe to repeat.
        for command in bot.tree.walk_commands():
            members = [p for p in command.parameters if p.type == discord.AppCommandOptionType.user]
            assert [p.display_name for p in members] == (["member"] if len(members) == 1 else [f"member{i}" for i in range(1, len(members) + 1)])
        for command in bot.walk_commands():
            members = [p for p in command.params.values() if member_annotation(p.annotation)]
            assert [p.displayed_name for p in members] == (["member"] if len(members) == 1 else [f"member{i}" for i in range(1, len(members) + 1)])
        for entry in COMMANDS:
            assert len(entry.description) <= 100
            slash = bot.tree.get_command(entry.name)
            assert slash.description == entry.description
            assert bot.get_command(entry.name).help == entry.description
            assert bot.get_command(entry.name).description == entry.description
        # Renaming a slash option must still bind to the original Python parameter.
        ship = bot.tree.get_command("ship")
        assert [(p.name, p.display_name) for p in ship.parameters] == [("user_one", "member1"), ("user_two", "member2")]

        catalog_names = {item.name for item in COMMANDS}
        install_command_aliases(bot)
        install_command_aliases(bot)
        assert set(SHORT_COMMANDS) == catalog_names
        for name, alias in SHORT_COMMANDS.items():
            assert bot.get_command(alias) is bot.get_command(name)
        written_names = {command.name for command in bot.walk_commands() if not command.hidden}
        slash_names = {
            command.name for command in bot.tree.walk_commands()
        }
        assert bot.tree.get_command("synccommands") is None
        sync_command = bot.get_command("synccommands")
        assert sync_command is not None and sync_command.hidden
        from bot.cogs.admin import private_owner
        assert private_owner in sync_command.checks

        assert len(catalog_names) == len(COMMANDS)
        assert catalog_names == written_names
        assert catalog_names == slash_names

        banned_terms = ("gemini", "no ai", "logic-based", "deterministic", "llm")
        visible_copy = [
            *(item.description for item in COMMANDS),
            *CATEGORY_DESCRIPTIONS.values(),
            *(command.description for command in bot.tree.walk_commands()),
        ]
        assert not [
            text for text in visible_copy if any(term in text.casefold() for term in banned_terms)
        ]
    finally:
        await bot.close()
