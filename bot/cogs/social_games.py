"""Anonymous multiplayer Showdown, Excuse, and Survive commands."""

from __future__ import annotations

from bot.logging.telemetry import discord_context, event

import logging
import asyncio

import discord
from discord.ext import commands

from bot.app import MeyayaBot
from bot.data.social_games import choose_scenario
from bot.services.social_games import (
    GameJudgement,
    GameSessionError,
    GameStatus,
    SocialGameJudge,
    SocialGameService,
)
from bot.utils.embeds import meyaya_embed, score_bar
from bot.views.social_games import GameCollectionView, GameLobbyView, build_game_embed

logger = logging.getLogger(__name__)


class SocialGamesCog(commands.Cog):
    """Host anonymous games using one shared session engine."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.sessions = SocialGameService()
        self.judge = SocialGameJudge(bot.build_llm_provider())
        self._last_theme: dict[tuple[int, str], str] = {}

    @commands.hybrid_command(name="showdown", description="Start an anonymous comparison showdown.")
    @commands.guild_only()
    async def showdown(self, ctx: commands.Context) -> None:
        await self._create_game(ctx, "showdown")

    @commands.hybrid_command(name="excuse", description="Start an anonymous excuse battle.")
    @commands.guild_only()
    async def excuse(self, ctx: commands.Context) -> None:
        await self._create_game(ctx, "excuse")

    @commands.hybrid_command(name="survive", description="Start an anonymous survival challenge.")
    @commands.guild_only()
    async def survive(self, ctx: commands.Context) -> None:
        await self._create_game(ctx, "survive")

    @commands.hybrid_command(
        name="endgame",
        description="End the active social game in this channel.",
    )
    async def endgame(self, ctx: commands.Context) -> None:
        if ctx.guild is None or ctx.channel is None:
            await ctx.send("This command can only be used inside a server game channel.")
            return
        session = self.sessions.active_in_channel(ctx.guild.id, ctx.channel.id)
        if session is None:
            await ctx.send("There is no active social game in this channel.")
            return
        try:
            await self.sessions.cancel(session.session_id, ctx.author.id)
        except GameSessionError as exc:
            await ctx.send(str(exc), ephemeral=ctx.interaction is not None)
            return
        await ctx.send(
            embed=meyaya_embed(
                "Game Ended",
                f"<@{ctx.author.id}> ended the active social game.",
                tone="muted",
                icon="🌙",
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _create_game(self, ctx: commands.Context, game_type: str) -> None:
        if ctx.guild is None or ctx.channel is None:
            await ctx.send("This game can only be started inside a server.")
            return
        scenario_key = (ctx.guild.id, game_type)
        scenario = choose_scenario(
            game_type,
            exclude_theme=self._last_theme.get(scenario_key),
        )
        try:
            session = await self.sessions.create(
                guild_id=ctx.guild.id,
                channel_id=ctx.channel.id,
                host_user_id=ctx.author.id,
                game_type=game_type,
                scenario=scenario,
            )
        except GameSessionError as exc:
            await ctx.send(str(exc))
            return
        self._last_theme[scenario_key] = scenario.theme

        view = GameLobbyView(
            service=self.sessions,
            session_id=session.session_id,
            judge_callback=self._judge_session,
        )
        message = await ctx.send(
            embed=build_game_embed(self.sessions, session.session_id),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = message

    @discord_context("social_games")
    async def _judge_session(
        self,
        session_id: str,
        user_id: int | None,
        force: bool,
        message: discord.Message,
        timed_out: bool = False,
    ) -> None:
        try:
            submissions = await self.sessions.claim_judging(
                session_id,
                user_id,
                force=force,
                timed_out=timed_out,
            )
        except GameSessionError as exc:
            if force or timed_out:
                await message.channel.send(str(exc), delete_after=8)
            return

        session = self.sessions.get(session_id)
        if session is None:
            return
        judging_message = message
        try:
            await message.edit(view=None)
            judging_message = await message.channel.send(
                embed=build_game_embed(self.sessions, session_id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            result = await self.judge.judge(
                game_type=session.game_type,
                scenario=session.scenario,
                submissions=submissions,
            )
        except asyncio.CancelledError:
            await self.sessions.judging_failed(session_id)
            raise
        except Exception:
            logger.exception("Social game judging failed session=%s", session_id)
            result = None

        if session.status is GameStatus.CANCELLED:
            await judging_message.edit(
                embed=meyaya_embed(
                    "Game Ended",
                    "The host ended this game while Meyaya was judging.",
                    tone="muted",
                    icon="🌙",
                )
            )
            return

        if result is None:
            event("llm_fallback", reason="judgement_unavailable", session_id=session_id)
            await self.sessions.judging_failed(session_id)
            retry_view = GameCollectionView(
                service=self.sessions,
                session_id=session_id,
                judge_callback=self._judge_session,
            )
            await judging_message.edit(
                embed=meyaya_embed(
                    "Judging Interrupted",
                    "Meyaya could not judge the answers. A new retry message is below.",
                    tone="warning",
                    icon="💭",
                )
            )
            retry_view.message = await message.channel.send(
                embed=build_game_embed(self.sessions, session_id),
                view=retry_view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await message.channel.send(
                "Meyaya could not judge those answers yet. The host can try again.",
                delete_after=12,
            )
            return

        try:
            await self.sessions.complete(session_id, result)
        except GameSessionError:
            await judging_message.edit(
                embed=meyaya_embed(
                    "Game Ended",
                    "The game ended before its results could be posted.",
                    tone="muted",
                    icon="🌙",
                )
            )
            return
        try:
            await message.channel.send(
                embed=self._results_embed(session_id, result),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            await self.sessions.close(session_id)

    def _results_embed(self, session_id: str, result: GameJudgement) -> discord.Embed:
        session = self.sessions.get(session_id)
        if session is None:
            return meyaya_embed(
                "Results Unavailable",
                "This result is no longer available.",
                tone="muted",
                icon="💭",
            )
        labels = {
            "showdown": ("Showdown Results", "Success chance"),
            "excuse": ("Excuse Battle Results", "Excuse score"),
            "survive": ("Survival Results", "Survival chance"),
        }
        title, score_label = labels[session.game_type]
        embed = meyaya_embed(
            title,
            f"**{session.scenario.theme}**\n{session.scenario.prompt}",
            icon="🏆",
        )
        for best_index, entry in reversed(list(enumerate(result.ranking, start=1))):
            owner_id = self.sessions.owner_for_submission(session_id, entry.submission_id)
            answer = session.submissions[entry.submission_id]
            rank = best_index
            medal = "🏆 " if rank == 1 else ""
            embed.add_field(
                name=f"{medal}#{rank} - {answer[:120]}",
                value=(
                    f"**{score_label}: {entry.score}%**  {score_bar(entry.score, segments=5)}\n"
                    f"{entry.reason}\n"
                    f"Submitted by <@{owner_id}>"
                ),
                inline=False,
            )
        winner_id = self.sessions.owner_for_submission(session_id, result.winner_submission_id)
        embed.add_field(name="Winner", value=f"🏆 <@{winner_id}>", inline=False)
        return embed


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(SocialGamesCog(bot))
