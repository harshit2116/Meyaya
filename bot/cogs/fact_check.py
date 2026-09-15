"""Grounded fact checking for one message or a selected Discord argument range."""

from __future__ import annotations

from bot.logging.telemetry import discord_context, event

import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.fact_check import (
    MAX_ARGUMENT_CHARACTERS,
    MAX_ARGUMENT_MESSAGES,
    MAX_MESSAGE_CHARACTERS,
    FactCheckMessage,
    FactCheckService,
)
from bot.services.llm import GroundingError, GroundingRateLimitError
from bot.utils.embeds import meyaya_embed

MESSAGE_LINK = re.compile(
    r"^https?://(?:www\.)?(?:discord\.com|discordapp\.com)/channels/"
    r"(?P<guild>\d+)/(?P<channel>\d+)/(?P<message>\d+)/?$",
    re.IGNORECASE,
)
FACT_CHECK_COOLDOWN_SECONDS = 60
MAX_DISCORD_CHUNK = 1900


class FactCheckInputError(Exception):
    """A safe explanation for invalid Discord message selection."""


class FactCheckCog(commands.Cog):
    """Collect explicit message evidence and return neutral, sourced analysis."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._last_check: dict[tuple[int, int], float] = {}
        self._inflight: set[tuple[int, int]] = set()

    @commands.hybrid_command(
        name="argumenttimeline",
        description="Summarize an argument chronologically with links to the evidence.",
    )
    @app_commands.describe(
        start="Starting message link; written commands can reply instead",
        ending="Optional final message link; defaults to the command time",
    )
    @commands.has_guild_permissions(manage_messages=True)
    @app_commands.default_permissions(manage_messages=True)
    async def argumenttimeline(
        self,
        ctx: commands.Context,
        start: str | None = None,
        ending: str | None = None,
    ) -> None:
        """Analyze every selected message from the start through the optional end."""

        if not self._supported_channel(ctx):
            await ctx.send("Fact checking only works in a server text channel or thread.")
            return
        if ctx.interaction is not None:
            await ctx.defer()

        try:
            replied = await self._replied_message(ctx)
            if replied is not None:
                if start is not None and ending is None:
                    ending = start
                start_message = replied
            else:
                if start is None:
                    raise FactCheckInputError(
                        "Reply to the argument's first message with `uwu argumenttimeline`, or provide "
                        "the starting message link to `/argumenttimeline`."
                    )
                start_message = await self._message_from_link(ctx, start)

            end_message = await self._message_from_link(ctx, ending) if ending is not None else None
            messages = await self._argument_messages(ctx, start_message, end_message)
            await self._run_timeline(ctx, messages)
        except FactCheckInputError as exc:
            await ctx.send(str(exc), ephemeral=ctx.interaction is not None)

    @commands.hybrid_command(
        name="checkclaim",
        description="Fact-check only one Discord message.",
    )
    @app_commands.describe(message="Message link; written commands can reply instead")
    async def checkclaim(
        self,
        ctx: commands.Context,
        message: str | None = None,
    ) -> None:
        """Analyze one replied-to or linked Discord message without surrounding chat."""

        if not self._supported_channel(ctx):
            await ctx.send("Fact checking only works in a server text channel or thread.")
            return
        if ctx.interaction is not None:
            await ctx.defer()

        try:
            selected = await self._replied_message(ctx)
            if selected is None:
                if message is None:
                    raise FactCheckInputError(
                        "Reply to one message with `uwu checkclaim`, or provide its link to "
                        "`/checkclaim`."
                    )
                selected = await self._message_from_link(ctx, message)
            evidence = self._to_evidence(selected)
            if evidence is None:
                raise FactCheckInputError("That message has no text to fact-check.")
            await self._run_check(ctx, [evidence], single_message=True)
        except FactCheckInputError as exc:
            await ctx.send(str(exc), ephemeral=ctx.interaction is not None)

    @discord_context("argument_timeline")
    async def _run_timeline(self, ctx, messages):
        from bot.services.argument_timeline import build_timeline

        key = (ctx.guild.id, ctx.author.id)
        now = time.monotonic()
        if key in self._inflight or now - self._last_check.get(key, float("-inf")) < 60:
            await ctx.send("Please wait a minute before requesting another review.", ephemeral=True)
            return
        self._inflight.add(key)
        self._last_check[key] = now
        try:
            report = await build_timeline(self.bot.build_llm_provider(), messages)
            for chunk in split_discord_report(report):
                await ctx.send(
                    embed=meyaya_embed("Argument Timeline", chunk, icon="🧭"),
                    allowed_mentions=discord.AllowedMentions.none(),
                    ephemeral=ctx.interaction is not None,
                )
        finally:
            self._inflight.discard(key)

    @discord_context("fact_check")
    async def _run_check(
        self,
        ctx: commands.Context,
        messages: list[FactCheckMessage],
        *,
        single_message: bool,
    ) -> None:
        key = (ctx.guild.id, ctx.author.id)
        now = time.monotonic()
        if key in self._inflight:
            await ctx.send("You already have a fact check running.", ephemeral=True)
            return
        remaining = FACT_CHECK_COOLDOWN_SECONDS - (now - self._last_check.get(key, 0.0))
        if remaining > 0:
            await ctx.send(
                f"Please wait {int(remaining) + 1} seconds before another fact check.",
                ephemeral=True,
            )
            return

        self._inflight.add(key)
        try:
            service = FactCheckService(self.bot.build_llm_provider())
            result = await service.analyze(messages, single_message=single_message)
        except GroundingRateLimitError as exc:
            if exc.retry_after_seconds is not None:
                detail = f" Try again in about {exc.retry_after_seconds} seconds."
            else:
                detail = (
                    " The Google API project's Search grounding quota may be exhausted or "
                    "billing may need attention."
                )
            await ctx.send(
                "Google Search grounding is rate-limited, so Meyaya did not make a "
                f"fact-check conclusion.{detail}"
            )
            return
        except GroundingError:
            await ctx.send(
                "Google Search grounding is unavailable right now, so Meyaya did not make a "
                "fact-check conclusion. Try again shortly."
            )
            return
        finally:
            self._inflight.discard(key)

        if result is None:
            await ctx.send(
                "Meyaya could not produce a grounded fact check right now. No conclusion was made."
            )
            return

        self._last_check[key] = time.monotonic()

        heading = (
            f"Checked **{result.message_count}** message(s) with "
            f"{result.source_count} web source(s).\n\n"
        )
        chunks = split_discord_report(heading + result.report)
        for index, chunk in enumerate(chunks):
            title = "Meyaya Fact Check" if index == 0 else "Fact Check - Continued"
            await ctx.send(
                embed=meyaya_embed(title, chunk, tone="info", icon="🔎"),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def _argument_messages(
        self,
        ctx: commands.Context,
        start: discord.Message,
        ending: discord.Message | None,
    ) -> list[FactCheckMessage]:
        boundary_id = ctx.interaction.id if ctx.interaction is not None else ctx.message.id
        if start.id >= boundary_id:
            raise FactCheckInputError("The starting message must be older than this command.")
        if ending is not None:
            if ending.id < start.id:
                raise FactCheckInputError("The ending message cannot be older than the start.")
            if ending.id >= boundary_id:
                raise FactCheckInputError("The ending message must be older than this command.")

        raw_messages = [start]
        try:
            async for message in ctx.channel.history(
                limit=MAX_ARGUMENT_MESSAGES + 1,
                after=discord.Object(id=start.id),
                before=discord.Object(id=boundary_id),
                oldest_first=True,
            ):
                if ending is not None and message.id > ending.id:
                    break
                raw_messages.append(message)
        except (discord.Forbidden, discord.HTTPException) as exc:
            raise FactCheckInputError(
                "Meyaya could not read that message range. Check Read Message History permission."
            ) from exc

        if ending is not None and all(message.id != ending.id for message in raw_messages):
            raise FactCheckInputError(
                "The ending message was not found within the selected range. Use a smaller range."
            )
        if len(raw_messages) > MAX_ARGUMENT_MESSAGES:
            raise FactCheckInputError(
                f"That range exceeds {MAX_ARGUMENT_MESSAGES} messages. Provide an earlier ending "
                "message or start closer to the disagreement."
            )

        evidence = [item for message in raw_messages if (item := self._to_evidence(message))]
        if not evidence:
            raise FactCheckInputError("The selected range has no text to fact-check.")
        total_characters = sum(len(message.content) for message in evidence)
        if total_characters > MAX_ARGUMENT_CHARACTERS:
            raise FactCheckInputError(
                f"That range exceeds {MAX_ARGUMENT_CHARACTERS:,} text characters. Select a "
                "shorter ending point."
            )
        return evidence

    async def _message_from_link(
        self,
        ctx: commands.Context,
        raw_link: str,
    ) -> discord.Message:
        parsed = parse_message_link(raw_link)
        if parsed is None:
            raise FactCheckInputError("Use a complete Discord message link.")
        guild_id, channel_id, message_id = parsed
        if guild_id != ctx.guild.id or channel_id != ctx.channel.id:
            raise FactCheckInputError("The message must be from this channel and server.")
        try:
            return await ctx.channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            raise FactCheckInputError(
                "Meyaya could not read that message. Check the link and channel permissions."
            ) from exc

    @staticmethod
    async def _replied_message(ctx: commands.Context) -> discord.Message | None:
        reference = getattr(ctx.message, "reference", None)
        if reference is None or reference.message_id is None:
            return None
        if isinstance(reference.resolved, discord.Message):
            return reference.resolved
        try:
            return await ctx.channel.fetch_message(reference.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    @staticmethod
    def _to_evidence(message: discord.Message) -> FactCheckMessage | None:
        content = " ".join((message.content or "").split()).strip()
        if not content:
            return None
        handle = getattr(message.author, "name", None) or str(message.author)
        display_name = getattr(message.author, "display_name", handle)
        return FactCheckMessage(
            message_id=message.id,
            author_id=message.author.id,
            author_label=f"{display_name} (@{handle}, Discord ID {message.author.id})",
            content=content[:MAX_MESSAGE_CHARACTERS],
            jump_url=message.jump_url,
        )

    @staticmethod
    def _supported_channel(ctx: commands.Context) -> bool:
        return ctx.guild is not None and isinstance(
            ctx.channel, (discord.TextChannel, discord.Thread)
        )


def parse_message_link(raw_link: str) -> tuple[int, int, int] | None:
    """Parse a Discord message link into guild, channel, and message IDs."""

    match = MESSAGE_LINK.fullmatch(raw_link.strip().strip("<>"))
    if match is None:
        return None
    return tuple(int(match.group(name)) for name in ("guild", "channel", "message"))


def split_discord_report(text: str, limit: int = MAX_DISCORD_CHUNK) -> list[str]:
    """Split long reports on paragraph or line boundaries without losing text."""

    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(FactCheckCog(bot))
