"""Deterministic moderation with durable, reversible channel lockdowns."""

import asyncio
import hashlib
import logging
import time
from typing import Literal
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from bot.models.moderation import ModerationSettings, ChannelLock
from bot.services.moderation import (
    INVITE,
    LINK,
    SpamWindow,
    LockdownService,
    on_probation,
    text_fingerprint,
)

logger = logging.getLogger(__name__)


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lockdown_service = LockdownService(bot)
        self.spam = SpamWindow()
        self._settings = {}
        self._settings_locks = [asyncio.Lock() for _ in range(16)]
        self._checks = {}
        self._next_check_cleanup = 0.0
        self._invites = {}
        self._notices = {}
        self._downloads = asyncio.Semaphore(3)

    async def settings(self, guild_id):
        # Coalesce expired settings reads from simultaneous message listeners.
        async with self._settings_locks[guild_id % len(self._settings_locks)]:
            return await self._load_settings(guild_id)

    async def _load_settings(self, guild_id):
        cached = self._settings.get(guild_id)
        if cached and time.monotonic() - cached[0] < 60:
            return cached[1]
        async with self.bot.db_session() as session:
            row = await session.get(ModerationSettings, guild_id)
            value = {
                name: getattr(row, name) if row else name != "raid_active"
                for name in ("probation", "cross_spam", "anti_invite", "raid_active")
            }
        self._settings[guild_id] = (time.monotonic(), value)
        return value

    async def set_setting(self, guild_id, name, value):
        async with self.bot.db_session() as session:
            await session.execute(
                insert(ModerationSettings)
                .values(guild_id=guild_id, **{name: value})
                .on_conflict_do_update(
                    index_elements=[ModerationSettings.guild_id], set_={name: value}
                )
            )
            await session.commit()
        self._settings.pop(guild_id, None)

    async def should_block(self, message):
        if (
            message.guild is None
            or message.author.bot
            or not isinstance(message.author, discord.Member)
        ):
            return False
        if message.author.guild_permissions.manage_guild:
            return False
        now = time.monotonic()
        if now >= self._next_check_cleanup or len(self._checks) >= 2000:
            self._next_check_cleanup = now + 5
            for key, (when, task) in list(self._checks.items()):
                if task.done() and now - when > 60:
                    self._checks.pop(key, None)
        key = (message.id, str(message.edited_at))
        if key not in self._checks:
            if len(self._checks) >= 2000:
                return False
            self._checks[key] = (now, asyncio.create_task(self._check(message)))
        return await asyncio.shield(self._checks[key][1])

    async def _check(self, message):
        try:
            settings = await self.settings(message.guild.id)
            reason = None
            if (
                settings["probation"]
                and on_probation(message.author.joined_at)
                and (
                    message.attachments
                    or LINK.search(message.content)
                    or INVITE.search(message.content)
                )
            ):
                reason = "For your first 3 days in this server, please use text without links or attachments."
            elif settings["anti_invite"]:
                for code in INVITE.findall(message.content)[:5]:
                    cached = self._invites.get(code)
                    if not cached or time.monotonic() - cached[0] > 300:
                        try:
                            invite = await self.bot.fetch_invite(code)
                            destination = getattr(invite.guild, "id", None)
                        except discord.HTTPException:
                            destination = None
                        if len(self._invites) >= 500:
                            self._invites.pop(next(iter(self._invites)))
                        self._invites[code] = (time.monotonic(), destination)
                    else:
                        destination = cached[1]
                    if destination is not None and destination != message.guild.id:
                        reason = "Invites to other servers aren't allowed here."
                        break
            if reason is None and settings["cross_spam"]:
                fingerprints = set()
                fingerprint = text_fingerprint(message.content)
                if fingerprint:
                    fingerprints.add("text:" + fingerprint)
                for attachment in message.attachments[:3]:
                    if attachment.size > 8 * 1024 * 1024 or not (
                        attachment.content_type or ""
                    ).startswith("image/"):
                        continue
                    try:
                        async with self._downloads:
                            async with asyncio.timeout(8):
                                content = await attachment.read()
                        fingerprints.add("image:" + hashlib.sha256(content).hexdigest())
                    except (discord.HTTPException, TimeoutError):
                        continue
                if self.spam.record(
                    message.guild.id, message.author.id, message.channel.id, fingerprints
                ):
                    reason = "Please don't repeat the same text or image across 3 or more channels within a minute."
            if reason:
                try:
                    await message.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    logger.warning(
                        "Moderation needs Manage Messages in channel=%s", message.channel.id
                    )
                key = (message.guild.id, message.author.id)
                if time.monotonic() - self._notices.get(key, float("-inf")) > 30:
                    self._notices[key] = time.monotonic()
                    if len(self._notices) > 5000:
                        self._notices.pop(next(iter(self._notices)))
                    try:
                        await message.channel.send(
                            f"{message.author.mention} {reason}",
                            allowed_mentions=discord.AllowedMentions.none(),
                            delete_after=20,
                        )
                    except discord.HTTPException:
                        pass
                return True
            return False
        except (SQLAlchemyError, discord.HTTPException):
            logger.warning("Moderation check unavailable guild=%s", message.guild.id)
            return False

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content != after.content or before.attachments != after.attachments:
            await self.should_block(after)

    @commands.hybrid_command(
        name="moderation", description="Show or change Meyaya's moderation settings."
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def moderation(
        self,
        ctx,
        feature: Literal["probation", "cross_spam", "anti_invite"] = "probation",
        enabled: bool | None = None,
    ):
        await ctx.defer(ephemeral=True)
        if enabled is not None:
            await self.set_setting(ctx.guild.id, feature, enabled)
        values = await self.settings(ctx.guild.id)
        await ctx.send(
            "Moderation rules:\n"
            + "\n".join(f"{name}: {'On' if value else 'Off'}" for name, value in values.items())
            + "\nProbation: first 3 days. Spam: same text/image in 3 channels in 60 seconds. Manage Server members are exempt.",
            ephemeral=True,
        )

    async def _lock_command(self, ctx, channel, *, raid=False, unlock=False):
        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if guild is None:
            return
        if channel is not None and channel.guild.id != guild.id:
            await ctx.send("Choose a text channel in this server.", ephemeral=True)
            return
        results = []
        async with self.lockdown_service.guild_lock(guild.id):
            if raid:
                await self.set_setting(guild.id, "raid_active", not unlock)
                channels = list(guild.text_channels)
                if unlock:
                    async with self.bot.db_session() as session:
                        ids = (
                            await session.scalars(
                                select(ChannelLock.channel_id).where(
                                    ChannelLock.guild_id == guild.id
                                )
                            )
                        ).all()
                    channels = [
                        guild.get_channel(cid) for cid in ids if guild.get_channel(cid) is not None
                    ]
            else:
                channels = [channel or ctx.channel]
            for target in channels:
                if not isinstance(target, discord.TextChannel):
                    results.append("Not a server text channel")
                    continue
                try:
                    outcome = await self.lockdown_service.apply(target, raid=raid, unlock=unlock)
                    results.append(f"<#{target.id}>: {outcome}")
                except (discord.HTTPException, SQLAlchemyError):
                    logger.exception("Lockdown operation failed channel=%s", target.id)
                    results.append(
                        f"<#{target.id}>: Failed - saved state retained; check permissions and retry"
                    )
        text = "\n".join(results) or "No text channels to process."
        for offset in range(0, len(text), 1800):
            await ctx.send(
                text[offset : offset + 1800],
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @commands.hybrid_command(
        name="lockdown", description="Lock one text channel until it is unlocked again."
    )
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_channels=True)
    async def lockdown(self, ctx, channel: discord.TextChannel | None = None):
        await self._lock_command(ctx, channel)

    @commands.hybrid_command(
        name="unlock", description="Unlock a channel and restore its permissions."
    )
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel | None = None):
        await self._lock_command(ctx, channel, unlock=True)

    @commands.hybrid_command(
        name="raidlockdown", description="Lock every text channel in this server."
    )
    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_guild=True)
    async def raidlockdown(self, ctx):
        await self._lock_command(ctx, None, raid=True)

    @commands.hybrid_command(
        name="raidunlock", description="End a raid lockdown and restore channel permissions."
    )
    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_guild=True)
    async def raidunlock(self, ctx):
        await self._lock_command(ctx, None, raid=True, unlock=True)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            async with self.lockdown_service.guild_lock(channel.guild.id):
                if (await self.settings(channel.guild.id))["raid_active"]:
                    await self.lockdown_service.apply(channel, raid=True)
        except (discord.HTTPException, SQLAlchemyError):
            logger.exception("Could not raid-lock new channel=%s", channel.id)

    async def cog_unload(self):
        tasks = [task for _, task in self._checks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
