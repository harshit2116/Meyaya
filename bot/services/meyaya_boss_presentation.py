"""Sparse cinematic beats; cosmetic failures never abort a battle."""

import asyncio
import discord
from bot.utils.embeds import meyaya_embed
from bot.utils.application_emojis import application_emojis

INTRO_GIF = "https://klipy.com/gifs/honkai-impact-22"
INTRO_GIF_DURATION_SECONDS = 4.66
INTRO_GIF_LOAD_GRACE_SECONDS = 2.0
VICTORY_GIF = "https://klipy.com/gifs/elysia-honkai-impact-3rd-3"


def victory_dialogue(state):
    if state.winner_id == state.left.user_id:
        return "# Impossible result confirmed.\n\n**You weren't supposed to be able to do that.**\n\nHehe. I like you even more now."
    if state.winner_id is None:
        return "# An unwritten ending.\n\n**Neither soul yielded. You have my attention.**"
    return "# That was beautiful.\n\n> **Unfortunately for you...**\n\n## so am I."


def contextual_victory(state):
    ratio = state.right.hp / max(1, state.right.max_hp)
    return (
        "You were one heartbeat away."
        if ratio < 0.15
        else (
            "One more strike, and this story might have ended differently."
            if ratio < 0.35
            else (
                "You almost made me take you seriously. Almost."
                if ratio < 0.65
                else "You really thought that would work? Cute."
            )
        )
    )


class BossPresentation:
    def __init__(self, cog, view, channel):
        self.cog, self.view, self.channel = cog, view, channel
        self.message = None
        self.urls = {}
        self.speeches = 0
        self.message_has_gif = False

    async def gif(self, url):
        if url not in self.urls:
            self.urls[url] = None
            try:
                service = self.cog.bot.build_klipy_service()
                if service is not None:
                    async with asyncio.timeout(4.5):
                        self.urls[url] = (await service.exact_gif(url)).url
            except Exception:
                # URL exceptions can contain provider keys; do not log the exception.
                pass
        return self.urls[url]

    async def beat(self, text, *, gif=None, new_message=False):
        embed = None
        if gif:
            url = await self.gif(gif)
            if url:
                embed = meyaya_embed("Everbloom", color=0xEEB4E4, icon="✦")
                embed.set_image(url=url)
        kwargs = dict(content=text, embed=embed, allowed_mentions=discord.AllowedMentions.none())
        sender = (
            self.channel.send
            if self.message is None or new_message or self.message_has_gif
            else self.message.edit
        )
        try:
            message = await sender(**kwargs)
        except discord.HTTPException:
            if embed is None:
                raise
            kwargs["embed"] = None
            message = await sender(**kwargs)
        self.message = message
        self.message_has_gif = kwargs["embed"] is not None
        self.view.cinematic_message = self.message

    async def intro(self, state):
        icon = next(
            (str(e) for e in application_emojis(self.cog.bot) if e.name == "meyaya_yay"), "✦"
        )
        await asyncio.sleep(0.8)
        await self.beat(
            f"# I am Meyaya.\n-# THE UNFAIR FINAL BOSS\n\n> **The Soul Interface knows your limits.**\n> **I don't.** {icon}",
            gif=INTRO_GIF,
        )
        await asyncio.sleep(
            INTRO_GIF_DURATION_SECONDS + INTRO_GIF_LOAD_GRACE_SECONDS
            if self.message_has_gif
            else 5.0
        )
        self.message_has_gif = False
        name = discord.utils.escape_markdown(discord.utils.escape_mentions(state.left.class_name))
        await self.beat(
            f"# ✦ Soul Interface\n\nAnalyzing challenger...\n\n**{name}**\n\nCURRENT CLASS\n**[ REWRITING... ]**"
        )
        await asyncio.sleep(1.5)
        await self.beat(
            f"# {state.boss_form}\n\n-# RECORDED CLASS: SOULWEAVER\n\n**Counter pattern: {state.counter_pattern}**\n\n*{state.dialogue}*"
        )
        await asyncio.sleep(1.5)

    async def speak(self, state):
        if state.dialogue and self.speeches < 3:
            self.speeches += 1
            await self.beat(f"# Meyaya\n\n**{state.dialogue}**")

    async def finish(self, state, *, history_note=""):
        await asyncio.sleep(0.8)
        text = victory_dialogue(state)
        if state.winner_id == state.right.user_id:
            text += "\n\n-# " + contextual_victory(state)
        if history_note:
            text += "\n\n" + history_note
        # The outcome is a new, complete message, not another edit of the intro.
        await self.beat(
            text,
            gif=VICTORY_GIF if state.winner_id == state.right.user_id else None,
            new_message=True,
        )
