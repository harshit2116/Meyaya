"""Daily fun commands shared by slash, written prefix, and mention routing."""

from __future__ import annotations

from datetime import date
import asyncio
from collections import OrderedDict
from time import monotonic
from weakref import WeakValueDictionary

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.daily import DailyService


class DailyCog(commands.Cog):
    """Stable daily picks using one implementation for every command style."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._candidate_cache = OrderedDict()
        self._candidate_locks = WeakValueDictionary()
        self._candidate_downloads = asyncio.Semaphore(2)

    def _cached_candidates(self, guild_id):
        cached = self._candidate_cache.get(guild_id)
        if cached and cached[0] > monotonic():
            self._candidate_cache.move_to_end(guild_id)
            return cached[1]
        self._candidate_cache.pop(guild_id, None)
        return None

    async def _candidate_ids(self, guild) -> list[int]:
        # Startup chunking is deliberately disabled on small hosting plans.
        # REST iteration doesn't populate Discord's permanent member cache.
        if guild.chunked:
            return sorted(member.id for member in guild.members if not member.bot)
        cached = self._cached_candidates(guild.id)
        if cached is not None:
            return cached
        lock = self._candidate_locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            cached = self._cached_candidates(guild.id)
            if cached is not None:
                return cached
            async with asyncio.timeout(30):
                async with self._candidate_downloads:
                    candidates = sorted([member.id async for member in guild.fetch_members(limit=None)
                                         if not member.bot])
            # Bound retained memory; very large guilds are not cached.
            if len(candidates) <= 10_000:
                self._candidate_cache[guild.id] = (monotonic() + 600, candidates)
                while len(self._candidate_cache) > 8:
                    self._candidate_cache.popitem(last=False)
            return candidates

    @commands.hybrid_command(name="iq", description="Show a daily IQ score for a member.")
    @app_commands.describe(member="Member to score; defaults to you")
    async def iq(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.")
            return
        target = member or ctx.author
        if not isinstance(target, discord.Member):
            await ctx.send("I could not identify that member.")
            return
        day = date.today()
        score = DailyService.iq_score(ctx.guild.id, target.id, day)
        name = f"<@{target.id}>"
        await ctx.send(
            f"IQ of {name} is {score} today.",
            allowed_mentions=discord.AllowedMentions(users=[target], roles=False, everyone=False, replied_user=False),
        )

    @commands.hybrid_command(name="dumb", description="Choose the dumbest member of the day.")
    async def dumb(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "dumbest")

    @commands.hybrid_command(name="smart", description="Choose the smartest member of the day.")
    async def smart(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "smartest")

    @commands.hybrid_command(name="clown", description="Choose the clown of the day.")
    async def clown(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "clown")

    async def _daily_winner(
        self,
        ctx: commands.Context,
        kind: str,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.")
            return
        if ctx.interaction is not None:
            await ctx.defer()
        try:
            candidates = await self._candidate_ids(ctx.guild)
        except (discord.HTTPException, discord.ClientException, TimeoutError):
            await ctx.send("I couldn't load the server members right now. Please try again shortly.")
            return
        if not candidates:
            await ctx.send("No eligible members were found.")
            return
        day = date.today()
        async with self.bot.db_session() as session:
            winner_id = await DailyService(session).daily_winner(
                ctx.guild.id,
                day,
                kind,
                candidates,
            )
        name = f"<@{winner_id}>"
        label = {"dumbest": "dumbest member", "smartest": "smartest member", "clown": "clown"}[kind]
        await ctx.send(
            f"{name} is the {label} today.",
            allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=winner_id)], roles=False, everyone=False, replied_user=False),
        )


async def setup(bot: MeyayaBot) -> None:
    """Install the daily command family."""

    await bot.add_cog(DailyCog(bot))
