"""Vote links and on-demand claims through Top.gg's read-only API."""

import asyncio
import logging

import discord
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot.services.topgg_api import TopggUnavailable
from bot.services.topgg_poll import TopggPoller
from bot.services.topgg_votes import VOTE_CREDITS, PollLeaseLost
from bot.utils.components_v2 import MeyayaView, send_native_embed
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)
# Exact media for https://klipy.com/gifs/elysia-honkai-impact-6, resolved via Klipy.
VOTE_THANKS_GIF = (
    "https://static.klipy.com/ii/4e7bea9f7a3371424e6c16ebc93252fe/22/29/Kj67SNmz02hGqrR.gif"
)


def vote_thanks_embed(vote):
    embed = meyaya_embed(
        "You voted for Meyaya!",
        "Thank you for voting for **Meyaya** on top.gg! ♡\n\n"
        f"You've received **{VOTE_CREDITS} personal bonus AI replies**. "
        "Mention me directly or use an AI text command after your server's shared "
        "chat allowance runs out to use them.",
        icon="🌸",
    )
    expiry = int(vote.expires_at.timestamp())
    embed.add_field(
        name="Your reward expires", value=f"<t:{expiry}:F> · <t:{expiry}:R>", inline=False
    )
    embed.set_image(url=VOTE_THANKS_GIF)
    embed.set_footer(text="Your support means a lot. ♡ • GIF via KLIPY")
    return embed


class VoteView(MeyayaView):
    def __init__(self, cog, owner_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.add_item(
            discord.ui.Button(
                label="Vote on top.gg",
                url=f"https://top.gg/bot/{cog.bot.user.id}/vote",
            )
        )
        if cog.bot.settings.topgg_enabled:
            button = discord.ui.Button(label="Check vote", style=discord.ButtonStyle.primary)
            button.callback = self.check_vote
            self.add_item(button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Run /vote to check your own reward.", ephemeral=True
            )
            return False
        blacklist = getattr(self.cog.bot, "chat_blacklist", None)
        if blacklist and blacklist.is_command_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "Meyaya commands are restricted for you here.", ephemeral=True
            )
            return False
        return True

    async def check_vote(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self.cog.reward_embed(interaction.user.id, recipient=interaction.user)
        await interaction.followup.send(
            embed=embed,
            view=VoteView(self.cog, interaction.user.id),
            ephemeral=True,
        )


class VotingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._poll_task = None
        self._notification_task = None
        self._notification_wakeup = asyncio.Event()

    async def cog_load(self):
        if not self.bot.settings.topgg_enabled:
            return
        self._notification_task = asyncio.create_task(
            self._notification_loop(), name="topgg-vote-dms"
        )
        if self.bot.settings.topgg_auto_detect_enabled:
            self._poll_task = asyncio.create_task(self._poll_loop(), name="topgg-vote-poll")

    async def cog_unload(self):
        tasks = [task for task in (self._poll_task, self._notification_task) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._poll_task = self._notification_task = None

    async def _poll_loop(self):
        await self.bot.wait_until_ready()
        poller = TopggPoller(
            self.bot.topgg_api, self.bot.votes, self.bot.user.id, self.bot.settings.topgg_project_id
        )
        interval = self.bot.settings.topgg_poll_interval_seconds
        failures = 0
        while True:
            try:
                count = await poller.poll_once()
                failures = 0
                if count:
                    self._notification_wakeup.set()
                    logger.info("Top.gg automatic vote rewards added count=%s", count)
            except (
                TopggUnavailable,
                SQLAlchemyError,
                TimeoutError,
                OSError,
                PollLeaseLost,
            ) as error:
                # No tokens, provider bodies, cursors or database parameters.
                failures = min(failures + 1, 4)
                logger.warning(
                    "Top.gg automatic vote check unavailable error=%s", type(error).__name__
                )
            delay = min(interval * 2**failures, max(interval, 900))
            await asyncio.sleep(max(delay, self.bot.topgg_api.retry_after_seconds))

    async def _notification_loop(self):
        await self.bot.wait_until_ready()
        while True:
            self._notification_wakeup.clear()
            delay = 60
            try:
                if await self._deliver_pending_notifications_once() == 10:
                    delay = 1
            except (SQLAlchemyError, TimeoutError, OSError) as error:
                logger.warning(
                    "Top.gg pending DM delivery unavailable error=%s", type(error).__name__
                )
            try:
                await asyncio.wait_for(self._notification_wakeup.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def _deliver_pending_notifications_once(self):
        async with asyncio.timeout(5):
            pending = await self.bot.votes.pending_notifications(limit=10)
        for vote in pending:
            await self.send_vote_thanks(None, vote)
        return len(pending)

    async def send_vote_thanks(self, recipient, vote):
        if recipient is not None and recipient.id != vote.user_id:
            logger.warning("Vote thank-you recipient mismatch")
            return False
        try:
            async with asyncio.timeout(5):
                if not await self.bot.votes.claim_notification(vote.vote_id):
                    return None
            async with asyncio.timeout(8):
                if recipient is None:
                    recipient = self.bot.get_user(vote.user_id) or await self.bot.fetch_user(
                        vote.user_id
                    )
                await send_native_embed(recipient, vote_thanks_embed(vote))
            return True
        except (discord.HTTPException, OSError, TimeoutError, SQLAlchemyError) as error:
            # DM permissions and delivery are optional; never log exception bodies.
            logger.info("Vote thank-you DM unavailable error=%s", type(error).__name__)
            return False

    async def reward_embed(self, user_id, *, recipient=None):
        enabled = self.bot.settings.topgg_enabled
        claim_instruction = (
            "New votes are detected automatically, usually within a minute. "
            "Press **Check vote** or run `/vote` to check sooner. "
            if getattr(self.bot.settings, "topgg_auto_detect_enabled", True)
            else "After voting, press **Check vote** or run `/vote` again to claim your reward. "
        )
        description = (
            f"Vote for Meyaya to receive **{VOTE_CREDITS} personal AI replies** for **12 hours**.\n"
            "They work across servers after the server's shared chat allowance runs out. "
            "Mention me directly or use an AI text command to spend them. "
            "Automatic and combined group replies use the server allowance.\n\n"
            f"{claim_instruction}"
            "Unused replies expire 12 hours after the original vote. "
            "Disabled chat, server restrictions, and AI limits still apply."
            if enabled
            else "Support Meyaya by voting on top.gg. Chat rewards are not active yet."
        )
        embed = meyaya_embed("Vote for Meyaya", description, icon="🌸")
        if not enabled:
            return embed
        new_vote = None
        try:
            async with asyncio.timeout(10):
                vote = await self.bot.topgg_api.check_vote(self.bot.user.id, user_id)
                if vote is not None:
                    inserted = await self.bot.votes.record(vote)
                    if inserted:
                        new_vote = vote
                    note = "Your vote is confirmed. " + (
                        "20 bonus replies added."
                        if inserted
                        else "This vote's reward was already claimed."
                    )
                else:
                    note = "No active vote found. If you just voted, wait a few seconds and check again."
        except TopggUnavailable as error:
            note = str(error)
        except (SQLAlchemyError, TimeoutError):
            logger.warning("Top.gg reward verification could not finish")
            note = "I couldn't finish verifying your reward. Please check again shortly."
        # Only the request that committed the new receipt may send a DM. The
        # database's unique constraints prevent duplicate sends across rechecks,
        # concurrent commands, cog reloads and process restarts.
        if new_vote is not None and recipient is not None:
            sent = await self.send_vote_thanks(recipient, new_vote)
            if sent is False:
                note += "\nYour reward is saved, but I couldn't send your thank-you DM."
        embed.add_field(name="Vote verification", value=note, inline=False)
        try:
            async with asyncio.timeout(5):
                status = await self.bot.votes.status(user_id)
            detail = f"**{status['remaining']}** bonus replies remaining"
            expiry = status["expires_at"]
            if expiry is not None and expiry > discord.utils.utcnow():
                detail += f"\nExpires <t:{int(expiry.timestamp())}:R>"
            elif expiry is not None:
                detail += "\nYour previous reward has expired. You can vote again on top.gg."
            embed.add_field(name="Your reward", value=detail, inline=False)
        except (SQLAlchemyError, TimeoutError):
            logger.warning("Top.gg reward status unavailable")
            embed.add_field(
                name="Your reward",
                value="Your balance is temporarily unavailable. Please check again shortly.",
                inline=False,
            )
        return embed

    @commands.hybrid_command(
        name="vote", description="Vote on top.gg and check your personal bonus AI replies."
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def vote(self, ctx):
        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)
        await ctx.send(
            embed=await self.reward_embed(ctx.author.id, recipient=ctx.author),
            view=VoteView(self, ctx.author.id),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(VotingCog(bot))
