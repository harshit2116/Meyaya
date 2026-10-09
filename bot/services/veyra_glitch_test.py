"""Temporary Veyra visual prototype. No production fantasy integration."""

import asyncio
from contextlib import closing
import logging
from pathlib import Path

import discord

from bot.data.private_identity import AYAYA_USER_ID

logger = logging.getLogger(__name__)


def is_veyra_glitch_test(message: discord.Message) -> bool:
    """Exact text trigger, using the same identity as admin.private_owner."""
    return (
        not message.author.bot
        and message.author.id == AYAYA_USER_ID
        and message.content == "uwu veyra"
    )


_EMPTY = "\u200b"
_ERROR = "E̸R̸R̸O̸R̸:̸ S̸O̸U̸L̸"
_FRIED = "~V̷̛Ë̴́Y̶̿R̸̈́A̷͝~"
_REJECTED = "~E̷x̷i̷s̷t̷e̷n̷c̷e̷ R̷e̷j̷e̷c̷t̷e̷d̷~"
_BANNER = (
    "█   █  █████  █   █  ████   ███",
    "█   █  █      █   █  █   █  █   █",
    "█   █  ████    ███   ████   █████",
    " █ █   █        █    █  █   █   █",
    "  █    █████    █    █   █  █   █",
)


def _frame(title: str, pattern: str = "", intensity: int = 0, *, ghost=False,
           failure: str = "") -> str:
    """Build a plain-text, 20-row canvas with the title always on row five.

    Empty rows contain a zero-width character so Discord retains the canvas.
    No markdown headings or code fences: the larger scale comes from the
    five-row block-letter banner and wide static walls, not font formatting.
    All occupied slots stay fixed; corruption overwrites them instead of moving.
    """
    rows = [_EMPTY] * 20
    rows[4] = title
    if intensity:
        band = (pattern * 48)[:48]
        rows[1] = band
        rows[11] = _ERROR
        rows[17] = band
    if intensity >= 2:
        rows[5:10] = _BANNER
        rows[12] = f"{_ERROR}  {_ERROR}"
        rows[15] = failure or "SIGNAL LOST // SIGNAL LOST // SIGNAL LOST"
    if ghost:
        rows[10] = f"{_FRIED}   {_FRIED}   {_FRIED}"
        rows[14] = f"{_ERROR}  {_ERROR}"
    if intensity >= 3:
        for index in (0, 2, 3, 13, 16, 18, 19):
            # Phase shifts change the noise in place without shifting the title.
            offset = index % len(pattern)
            rows[index] = ((pattern[offset:] + pattern[:offset]) * 48)[:48]
        rows[6] = f"{band[:12]}  V̷E̴Y̶R̸A̷  {band[:12]}"
        rows[8] = band
    if intensity >= 4:
        rows[5] = band
        rows[7] = f"{_ERROR}  {_ERROR}"
        rows[9] = band
    return "\n".join(rows)


# Four short glitch bursts punctuated by clean, unobstructed image reveals.
# 12 edits / 4.1 seconds of holds; HTTP/upload/backoff adds wall time.
# Each delay holds the current frame BEFORE the next edit; final frame stays.
VEYRA_GLITCH_FRAMES = (
    (_frame(_FRIED, "░▒▓█", 3, ghost=True), 0.25),
    (_frame(_FRIED, "██▓░", 4, ghost=True,
            failure="SIGNAL FOUND // SIGNAL FOUND"), 0.25),
    ("~Veyra~", 0.65),
    (_frame(_FRIED, "█░▒▓", 3, ghost=True), 0.25),
    (_frame(_FRIED, "▓██▒", 4, ghost=True,
            failure="SOUL BUFFER OVERFLOW"), 0.25),
    ("~Veyra~", 0.65),
    (_frame(_FRIED, "▒█░▓", 4, ghost=True), 0.25),
    (_frame("~Veyra~"), 0.15),
    (_frame(_FRIED, "███░", 4, ghost=True,
            failure="RESTORE FAILED // RESTORE FAILED"), 0.25),
    ("~Enemy of All~", 0.65),
    (_frame(_REJECTED, "█▓▒░", 4, ghost=True,
            failure="EXISTENCE DENIED // EXISTENCE DENIED"), 0.25),
    (_frame(_REJECTED, "▓█▓█", 4, ghost=True,
            failure="REALITY DESYNC // REALITY DESYNC"), 0.25),
    ("~Existence Rejected~", 0.0),
)


# Prepared, lossless panel crops; no image rendering at runtime.
# A reveal uploads one panel; every intervening glitch frame clears attachments.
_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "veyra-glitch-test"
VEYRA_GLITCH_IMAGES = {
    2: _ASSET_DIR / "01-eye.png",
    5: _ASSET_DIR / "02-portrait.png",
    9: _ASSET_DIR / "03-standing.png",
    12: _ASSET_DIR / "04-throne.png",
}

async def run_veyra_glitch(channel: discord.abc.Messageable) -> None:
    """Alternate image-free glitch bursts and clean reveals in one message."""
    try:
        content, delay = VEYRA_GLITCH_FRAMES[0]
        message = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
        for index, (content, next_delay) in enumerate(VEYRA_GLITCH_FRAMES[1:], start=1):
            await asyncio.sleep(delay)
            if index in VEYRA_GLITCH_IMAGES:
                with closing(discord.File(str(VEYRA_GLITCH_IMAGES[index]))) as image:
                    # Replace rather than append, keeping exactly one panel.
                    await message.edit(
                        content=content, attachments=[image],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            else:
                # Cut away the previous image so each burst leads into a reveal.
                await message.edit(
                    content=content, attachments=[], allowed_mentions=discord.AllowedMentions.none()
                )
            delay = next_delay
    except (discord.HTTPException, OSError):
        # Includes deleted messages and lost permissions. Stop without retries
        # or extra error messages; cancellation still propagates normally.
        logger.warning("Veyra visual test stopped: image load or Discord send/edit failed", exc_info=True)
