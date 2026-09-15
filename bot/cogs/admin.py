"""Per-server configuration and lightweight administration diagnostics."""

from __future__ import annotations

import asyncio
import re
import time

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from bot.app import DEFAULT_COMMAND_PREFIX, MeyayaBot
from bot.models.court import CourtConfiguration
from bot.repositories.guild_settings import GuildSettingsRepository
from bot.services.model_router import ModelRouter, ModelTier
from bot.utils.embeds import meyaya_embed

PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9!?.$%&*+_-]{1,10}$")


async def application_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == 715925710849572904


def private_owner(ctx):
    return ctx.author.id == 715925710849572904


def normalize_prefix(value: str) -> str | None:
    """Validate a compact written-command prefix without Discord syntax collisions."""

    candidate = value.strip()
    if not PREFIX_PATTERN.fullmatch(candidate):
        return None
    if candidate.startswith(("/", "@")):
        return None
    return candidate


class AdminCog(commands.Cog):
    """Manager-only server settings and operational status."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="synccommands",
        description="Owner-only repair of slash-command registration.",
        hidden=True,
    )
    @commands.check(private_owner)
    @app_commands.check(application_owner)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def synccommands(self, ctx: commands.Context) -> None:
        await ctx.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        if self.bot.settings.guild_id:
            guild = discord.Object(id=self.bot.settings.guild_id)
            self.bot.tree.copy_global_to(guild=guild)
            await self.bot.tree.sync(guild=guild)
        await ctx.send(
            f"Synced {len(synced)} global commands. Refresh Discord if the menu still shows older options.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="prefix",
        description="Show or change this server's written command prefix.",
    )
    @app_commands.describe(value="New prefix, or reset to restore uwu")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix(self, ctx: commands.Context, value: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send("Server prefixes can only be configured inside a server.")
            return

        current = self.bot.prefix_for_guild(ctx.guild.id)
        if value is None:
            await ctx.send(
                embed=meyaya_embed(
                    "Server Prefix",
                    f"The written prefix here is `{current}`.\n" f"Example: `{current} help`",
                    tone="info",
                    icon="⌨️",
                ),
                ephemeral=ctx.interaction is not None,
            )
            return

        requested = DEFAULT_COMMAND_PREFIX if value.strip().casefold() == "reset" else value
        selected = normalize_prefix(requested)
        if selected is None:
            await ctx.send(
                "Choose 1-10 letters, numbers, or simple symbols without spaces, `/`, or `@`.",
                ephemeral=ctx.interaction is not None,
            )
            return

        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)
        try:
            async with self.bot.db_session() as session:
                saved = await GuildSettingsRepository(session).set_prefix(
                    ctx.guild.id,
                    selected,
                    ctx.author.id,
                )
                await session.commit()
        except SQLAlchemyError:
            await ctx.send(
                "I could not save that prefix because PostgreSQL is unavailable.",
                ephemeral=ctx.interaction is not None,
            )
            return

        self.bot.cache_guild_prefix(ctx.guild.id, saved)
        await ctx.send(
            embed=meyaya_embed(
                "Prefix Updated",
                f"This server now uses `{saved}`.\nTry `{saved} help`.",
                tone="success",
                icon="⌨️",
            ),
            ephemeral=ctx.interaction is not None,
        )

    @commands.hybrid_command(
        name="autoresponder",
        description="Enable or disable occasional automatic replies in this server.",
    )
    @app_commands.describe(mode="enable, disable, or status")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Enable", value="enable"),
            app_commands.Choice(name="Disable", value="disable"),
            app_commands.Choice(name="Status", value="status"),
        ]
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def autoresponder(self, ctx: commands.Context, mode: str = "status") -> None:
        if ctx.guild is None:
            await ctx.send("Use this command inside a server.")
            return
        mode = mode.strip().casefold()
        if mode not in {"enable", "disable", "status", "on", "off"}:
            await ctx.send("Choose `enable`, `disable`, or `status`.", ephemeral=True)
            return
        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)
        if mode != "status":
            enabled = mode in {"enable", "on"}
            try:
                async with self.bot.db_session() as session:
                    await GuildSettingsRepository(session).set_autoresponder(
                        ctx.guild.id, enabled, ctx.author.id
                    )
                    await session.commit()
            except SQLAlchemyError:
                await ctx.send(
                    "I couldn't save that setting. Please try again when the database is available.",
                    ephemeral=True,
                )
                return
            self.bot.cache_autoresponder(ctx.guild.id, enabled)
        enabled = self.bot.autoresponder_enabled(ctx.guild.id)
        await ctx.send(
            embed=meyaya_embed(
                "Automatic Replies",
                f"Automatic replies are **{'enabled' if enabled else 'disabled'}** in this server.\n"
                "When enabled, Meyaya occasionally replies to new messages she can read - more often when the server is quiet and less often when it is busy. She waits between replies and can choose to stay silent.",
                tone="success" if enabled else "muted",
                icon="💬",
            ),
            ephemeral=True,
        )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(0, int(seconds))
        days, remainder = divmod(total, 86_400)
        hours, remainder = divmod(remainder, 3_600)
        minutes, _ = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(AdminCog(bot))
