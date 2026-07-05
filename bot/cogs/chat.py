"""Mention-triggered Gemini chat responses."""

from __future__ import annotations

import logging
import re
import time

import discord
from discord.ext import commands

from bot.app import MeyayaBot
from bot.data.gemini_persona import build_system_instruction
from bot.services.profiles import ProfileService

logger = logging.getLogger(__name__)

MAX_DISCORD_MESSAGE_LENGTH = 2000
MENTION_PATTERN = re.compile(r"<@!?(\d+)>")


class ChatCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._last_reply_at: dict[int, float] = {}
        self._cooldown_seconds = 15.0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if self.bot.user is None or self.bot.user not in message.mentions:
            return
        if message.mention_everyone:
            return
        now = time.monotonic()
        last = self._last_reply_at.get(message.channel.id, 0.0)
        if now - last < self._cooldown_seconds:
            return
        self._last_reply_at[message.channel.id] = now

        user_text = MENTION_PATTERN.sub("", message.content).strip()
        if not user_text:
            return
        gemini = self.bot.build_gemini_service()
        if gemini is None:
            await message.reply("💤 *rubs eyes* ...my brain isn't plugged in right now. Try again later!")
            return

        context_lines = await self._build_context_lines(message)
        system_instruction = build_system_instruction(context_lines=context_lines)

        async with message.channel.typing():
            reply = await gemini.generate(system_instruction, user_text)

        if reply is None:
            await message.reply("😵 *short-circuits* ...I couldn't think of anything, sorry!")
            return

        for chunk in self._chunk_text(reply.text):
            await message.reply(chunk)

    async def _build_context_lines(self, message: discord.Message) -> list[str]:
        lines = [
            f"The person talking to you is named {message.author.display_name}.",
            f"This is happening in the server \"{message.guild.name}\"." if message.guild else "This is a DM.",
        ]

        if message.guild is not None:
            async with self.bot.db_session() as session:
                profile_service = ProfileService(session)
                try:
                    summary = await profile_service.build(message.author.id)
                except Exception:  # noqa: BLE001
                    summary = None
                marriage_service = self.bot.build_marriage_service(session)
                marriage = await marriage_service.get_active_marriage(message.author.id)

            if summary is not None:
                lines.append(
                    f"{message.author.display_name} has given {summary.total_given} and "
                    f"received {summary.total_received} affectionate interactions on this bot."
                )
                if summary.favorite_interaction:
                    lines.append(
                        f"{message.author.display_name}'s favorite interaction to send is "
                        f"\"{summary.favorite_interaction}\"."
                    )

            if marriage is not None:
                other_id = (
                    marriage.user_b_id if marriage.user_a_id == message.author.id else marriage.user_a_id
                )
                lines.append(f"{message.author.display_name} is currently married to <@{other_id}>.")
            else:
                lines.append(f"{message.author.display_name} is currently single.")

        return lines

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        if len(text) <= MAX_DISCORD_MESSAGE_LENGTH:
            return [text]
        return [text[i : i + MAX_DISCORD_MESSAGE_LENGTH] for i in range(0, len(text), MAX_DISCORD_MESSAGE_LENGTH)]


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ChatCog(bot))