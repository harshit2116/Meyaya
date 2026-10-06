"""Per-server configuration and lightweight administration diagnostics."""

from __future__ import annotations

import asyncio
import re
import time
import logging
from contextlib import AsyncExitStack

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
from bot.services.fantasy_profile import FantasyProfileService
from bot.views.server_setup import ServerSetupView

PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9!?.$%&*+_-]{1,10}$")


async def application_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == 715925710849572904


def private_owner(ctx):
    return ctx.author.id == 715925710849572904


def fantasy_reset_prefix(ctx):
    return getattr(ctx, "interaction", None) is None and (getattr(ctx, "prefix", "") or "").strip().casefold() == "uwu"


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

    @commands.command(name="fantasyreset", hidden=True)
    @commands.check(private_owner)
    @commands.check(fantasy_reset_prefix)
    async def fantasyreset(self, ctx: commands.Context, member: discord.User, confirmation: str = ""):
        # Defense in depth: no slash, mention-prefix or alternate-prefix route.
        if not private_owner(ctx) or not fantasy_reset_prefix(ctx):
            return
        if confirmation != "confirm":
            await ctx.send(f"This permanently deletes user `{member.id}`'s fantasy identity across all servers.\n"
                           f"To confirm: `uwu fantasyreset {member.id} confirm`",
                           allowed_mentions=discord.AllowedMentions.none())
            return
        cog = self.bot.get_cog("FantasyCog")
        def affected(view):
            if member.id in getattr(view, "participant_ids", ()):
                return True
            profile = getattr(view, "profile", None)
            return getattr(profile, "user_id", None) == member.id or (
                profile is None and view.owner == member.id)
        views = sorted((view for view in getattr(cog, "views", ()) if affected(view)), key=lambda view: view.id)
        try:
            # Wait for an in-flight local confirmation/reveal before deleting;
            # it must not silently recreate the identity after this reset.
            async with asyncio.timeout(30), AsyncExitStack() as locks:
                for view in views:
                    await locks.enter_async_context(view.lock)
                async with self.bot.db_session() as session:
                    deleted = await FantasyProfileService(session).reset(member.id)
                for view in tuple(getattr(cog, "views", ())):
                    if affected(view):
                        if view not in views:
                            views.append(view)
                        view.finish()
        except (SQLAlchemyError, TimeoutError):
            await ctx.send("I couldn't verify the reset. Check `/fantasyprofile` before trying again.")
            return
        for view in views:
            if view.message:
                try:
                    await view.message.edit(view=view)
                except discord.HTTPException:
                    pass
        logging.getLogger(__name__).info("fantasy_identity_reset actor_id=%s target_id=%s deleted=%s", ctx.author.id, member.id, deleted)
        await ctx.send(f"Fantasy identity reset for user `{member.id}`. They can use `/awaken` again." if deleted
                       else f"User `{member.id}` has no awakened fantasy identity.",
                       allowed_mentions=discord.AllowedMentions.none())

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

    @commands.command(name="errorlookup", hidden=True)
    @commands.check(private_owner)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def errorlookup(self, ctx: commands.Context, error_id: str = ""):
        """Privately retrieve an existing error ID, including retained logs."""
        if not private_owner(ctx):
            return
        from bot.logging.health import health, find_retained_error

        error_id = error_id.strip().upper()
        if not re.fullmatch(r"MY-[A-F0-9]{8}", error_id):
            await ctx.send("Usage: `uwu errorlookup MY-1234ABCD`")
            return
        items = health.search(error_id)
        record = items[0] if items else await asyncio.to_thread(find_retained_error, error_id)
        embed = discord.Embed(title=f"Error lookup · {error_id}", color=0xCF7195)
        if record is None:
            embed.description = "No matching error in this process or retained logs. It may have expired or belong to another bot instance."
        else:
            diagnosis = record["diagnosis"]
            embed.description = diagnosis["cause"]
            def field(name, value):
                embed.add_field(name=name, value=discord.utils.escape_markdown(str(value or "Not recorded"))[:1024], inline=False)
            field("Next check", diagnosis["next_step"])
            field("Command / stage", f"{record.get('command')} / {record.get('stage')}")
            field("Time (UTC)", record.get("timestamp"))
            field("Server / channel", f"{record.get('guild_id')} / {record.get('channel_id')}")
            field("Exception chain", " → ".join(item["exception"] for item in record.get("causes", [])) or record.get("exception"))
            frames = record.get("frames") or []
            location = diagnosis.get("location")
            if not location and frames:
                frame = frames[-1]
                location = f"{frame['file']}:{frame['line']} · {frame['function']}"
            field("Source location", location)
            if record.get("reason"):
                field("Recorded reason", record["reason"])
            if record.get("request_id"):
                field("AI request ID", record["request_id"])
        try:
            await ctx.author.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            await ctx.send("Enable DMs for the private error report, or look up the ID in the owner dashboard.")

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
