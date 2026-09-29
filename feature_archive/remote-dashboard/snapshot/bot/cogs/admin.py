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
from bot.utils.command_parameters import normalize_member_parameters
from bot.services.server_setup import load_setup
from bot.services.server_dashboard import server_overview, dashboard_embed
from bot.views.server_setup import ServerSetupView

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

    @commands.hybrid_command(name="serversetup", description="Set up Meyaya's chat access and moderation for this server.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def serversetup(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            choices = await load_setup(self.bot, ctx.guild.id)
        except SQLAlchemyError:
            await ctx.send("I couldn't load the server settings. Please try again shortly.", ephemeral=True)
            return
        view = ServerSetupView(self.bot, ctx.guild.id, ctx.author.id, choices)
        view.message = await ctx.send(embed=view.embed(), view=view, ephemeral=True,
                                      allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="serverdashboard", description="See this server's allowance, remaining messages, activity, and settings.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def serverdashboard(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            data = await server_overview(self.bot, ctx.guild.id)
        except SQLAlchemyError:
            await ctx.send("I couldn't load server usage. Please try again shortly.", ephemeral=True)
            return
        await ctx.send(embed=dashboard_embed(ctx.guild, data), ephemeral=True,
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="owner", hidden=True)
    @commands.check(private_owner)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def owner(self, ctx: commands.Context):
        if self.bot.dashboard is None:
            await ctx.author.send(
                "Dashboard is disabled. Set DASHBOARD_ENABLED=true on the bot host and restart."
            )
            return
        try:
            if getattr(self.bot.settings, 'dashboard_mode', 'hosted') == 'api':
                await ctx.author.send(
                    "The hosted management API is enabled. On your laptop, run "
                    "`python dashboard_remote.py` using your private `.dashboard.env`, "
                    "then open `http://127.0.0.1:8080` (or your chosen local port). "
                    "There is no public owner login page in this mode.",
                    suppress_embeds=True,
                )
                return
            link = self.bot.dashboard.login_link()
            await ctx.author.send(
                f"[Open Meyaya dashboard]({link})\nThis private link expires in 60 seconds and works once. Do not share it.\n"
                "A localhost link opens only on the bot's computer. For remote hosting, configure DASHBOARD_PUBLIC_URL with your HTTPS address.",
                suppress_embeds=True,
            )
        except discord.Forbidden:
            await ctx.send("Enable DMs so I can send your private dashboard link.")
        except ValueError:
            await ctx.author.send(
                "Check DASHBOARD_PUBLIC_URL and DASHBOARD_TRUSTED_PROXIES: remote access needs HTTPS through an explicitly trusted proxy; local access must use localhost."
            )

    @commands.hybrid_command(
        name="chatblacklist",
        description="Block or restore a member's access to Meyaya in this server.",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chatblacklist(
        self,
        ctx: commands.Context,
        member: discord.Member,
        action: str = "status",
        *,
        reason: str = "Server manager decision",
    ):
        action = action.lower()
        if action not in {"block", "unblock", "status"}:
            await ctx.send(
                "Use `chatblacklist @member block|unblock|status [reason]`.", ephemeral=True
            )
            return
        if action != "status":
            await self.bot.chat_blacklist.set(
                ctx.guild.id,
                member.id,
                active=action == "block",
                reason=reason,
                actor_id=ctx.author.id,
            )
        blocked = self.bot.chat_blacklist.is_blocked(ctx.guild.id, member.id)
        await ctx.send(
            f"Member `{member.id}` is **{'blocked' if blocked else 'allowed'}** in this server.",
            ephemeral=True,
        )

    @commands.command(
        name="synccommands",
        description="Owner-only repair of slash-command registration.",
        hidden=True,
    )
    @commands.check(private_owner)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def synccommands(self, ctx: commands.Context) -> None:
        normalize_member_parameters(self.bot)
        synced = await self.bot.tree.sync()
        if self.bot.settings.guild_id:
            guild = discord.Object(id=self.bot.settings.guild_id)
            self.bot.tree.copy_global_to(guild=guild)
            await self.bot.tree.sync(guild=guild)
        await ctx.send(
            f"Synced {len(synced)} global commands. Refresh Discord if the menu still shows older options.",
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

    @commands.hybrid_command(
        name="chatbind", description="Choose one channel or the whole server for Meyaya chat."
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="One channel", value="channel"),
            app_commands.Choice(name="Entire server", value="server"),
            app_commands.Choice(name="Current setting", value="status"),
        ]
    )
    @app_commands.describe(
        channel="Text or voice channel for chat; defaults to the current channel"
    )
    async def chatbind(
        self,
        ctx: commands.Context,
        mode: str = "status",
        channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | None = None,
    ):
        mode = mode.lower().strip()
        if mode not in {"channel", "server", "status"}:
            await ctx.send(
                "Use `chatbind channel #channel`, `chatbind server`, or `chatbind status`.",
                ephemeral=True,
            )
            return
        if channel is not None and mode != "channel":
            await ctx.send("Only supply a channel when using `chatbind channel`.", ephemeral=True)
            return
        selected = channel or ctx.channel
        if mode == "channel":
            if (
                not isinstance(
                    selected, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)
                )
                or selected.guild.id != ctx.guild.id
            ):
                await ctx.send("Choose a text or voice channel in this server.", ephemeral=True)
                return
            permissions = selected.permissions_for(ctx.guild.me)
            if not permissions.view_channel or not permissions.send_messages:
                await ctx.send(
                    "I need permission to view and send messages in that channel first.",
                    ephemeral=True,
                )
                return
        await ctx.defer(ephemeral=True)
        try:
            async with self.bot.db_session() as session:
                repository = GuildSettingsRepository(session)
                if mode != "status":
                    await repository.set_chat_channel(
                        ctx.guild.id, selected.id if mode == "channel" else None, ctx.author.id
                    )
                    await session.commit()
                channels = await repository.list_chat_channels()
            self.bot._guild_chat_channels = channels
        except SQLAlchemyError:
            await ctx.send(
                "I couldn't load or save the chat setting. Please try again shortly.",
                ephemeral=True,
            )
            return
        bound = channels.get(ctx.guild.id)
        location = f"<#{bound}> only (threads excluded)" if bound else "the entire server"
        await ctx.send(
            f"Meyaya chat is available in {location}. This includes mentions, replies to Meyaya and automatic replies. Commands keep their usual access.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
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
