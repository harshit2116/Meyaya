"""Public command copy and navigation stay consistent across Discord entry points."""

import discord
import pytest

from bot.app import MeyayaBot
from bot.config.settings import Settings
from bot.data.help_catalog import COMMANDS, CATEGORY_ORDER, commands_in_category
from bot.utils.command_parameters import (
    normalize_member_parameters,
    member_annotation,
    member_label,
)
from bot.views.help import HelpView, build_help_embed


@pytest.mark.asyncio
async def test_all_public_commands_share_descriptions_and_member_labels():
    bot = MeyayaBot(
        Settings(
            DISCORD_TOKEN="test-token",
            DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
            REDIS_URL="redis://localhost:6379/15",
        )
    )
    await bot._async_setup_hook()
    extensions = "interactions daily profile profile_studio ship fun extras member_fun celestial fantasy character_catalog solo_games social_games marriage court fact_check memory roleplay monitor voice_live admin moderation"
    try:
        for name in extensions.split():
            await bot.load_extension(f"bot.cogs.{name}")
        normalize_member_parameters(bot)
        normalize_member_parameters(bot)
        for entry in COMMANDS:
            slash, prefix = bot.tree.get_command(entry.name), bot.get_command(entry.name)
            assert slash.description == prefix.help == prefix.description == entry.description
            assert len(entry.description) <= 100
            slash_members = [
                p for p in slash.parameters if p.type == discord.AppCommandOptionType.user
            ]
            prefix_members = [p for p in prefix.params.values() if member_annotation(p.annotation)]
            expected = [
                member_label(i, len(slash_members)) for i in range(1, len(slash_members) + 1)
            ]
            assert [p.display_name for p in slash_members] == expected
            assert [p.displayed_name for p in prefix_members] == expected
            embed = build_help_embed(bot_mention="@Meyaya", command_name=entry.name, bot=bot)
            assert embed.description == slash.description
            assert len(embed) <= 6000
        ship = bot.tree.get_command("ship")
        assert [(p.name, p.display_name) for p in ship.parameters] == [
            ("user_one", "member1"),
            ("user_two", "member2"),
        ]
        assert bot.tree.get_command("profile").parameters[0].display_name == "member"
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_overview_lists_every_command_without_extra_navigation():
    view = HelpView(owner_id=1, bot_mention="@Meyaya")
    try:
        overview = build_help_embed(bot_mention="@Meyaya")
        assert len(overview) <= 6000
        assert all(len(field.value) <= 1024 for field in overview.fields)
        text = "\n".join(field.value for field in overview.fields)
        assert all(f"`/{entry.name}`" in text for entry in COMMANDS)
        for category in CATEGORY_ORDER:
            view.category = category
            view.refresh_items()
            assert len(view.children) == 2
            embed = build_help_embed(bot_mention="@Meyaya", category=category)
            assert all(f"/{entry.usage}" in embed.description for entry in commands_in_category(category))
    finally:
        view.stop()
