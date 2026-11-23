"""One-player sliding puzzle with serialized edits and a fixed lifetime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from io import BytesIO
from time import monotonic, time
from typing import Any, cast

import discord
from bot.utils.components_v2 import MeyayaView

from bot.services.scramble import GOAL, neighbours, render_board, shuffled_board
from bot.utils.image_work import image_work

logger = logging.getLogger(__name__)


class TileButton(discord.ui.Button["ScrambleView"]):
    def __init__(self, position: int, session_id: str) -> None:
        super().__init__(label="…", row=position // 3, custom_id=f"meyaya:scramble:{session_id}:{position}")
        self.position = position

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is not None:
            await self.view.move(interaction, self.position)


class ScrambleView(MeyayaView):
    def __init__(
        self,
        owner_id: int,
        name: str,
        avatar: bytes,
        release: Callable[[], object],
    ) -> None:
        # Own one absolute clock, rather than discord.py's interaction-reset idle
        # timeout racing our five-minute deadline and removing callbacks first.
        super().__init__(timeout=None)
        self.owner_id, self.name, self.avatar = owner_id, name, avatar
        self.release = release
        self.board: tuple[int, ...] = cast(Any, shuffled_board)()
        self.moves = 0
        self.started = monotonic()
        self.deadline = self.started + 300
        self.wall_deadline = int(time() + 300)
        self.duration: int | None = None
        self.lock = asyncio.Lock()
        self.message: discord.Message | None = None
        self.ended = False
        self.expiry_task: asyncio.Task[None] | None = None
        for pos in range(9):
            self.add_item(TileButton(pos, self.id))
        self.give_up.custom_id = f"meyaya:scramble:{self.id}:reveal"
        self.sync_buttons()

    def sync_buttons(self) -> None:
        legal: Any = cast(Any, neighbours)(self.board.index(0))
        for button in self.children:
            if isinstance(button, TileButton):
                tile = self.board[button.position]
                button.label = str(tile) if tile else "·"
                button.disabled = self.ended or button.position not in legal
                button.style = discord.ButtonStyle.primary if button.position in legal else discord.ButtonStyle.secondary
            elif isinstance(button, (discord.ui.Button, discord.ui.Select)):
                button.disabled = self.ended

    def embed(
        self,
        status: str = "Slide a numbered tile into the empty space.",
        *,
        completed: bool = False,
    ) -> discord.Embed:
        elapsed = self.duration if self.duration is not None else int(monotonic() - self.started)
        embed = discord.Embed(title="🧩 Avatar Scramble", description=status, color=0xAAB7F4)
        embed.add_field(name="Moves", value=str(self.moves))
        if self.ended or completed:
            embed.add_field(name="Run time", value=f"{elapsed // 60}:{elapsed % 60:02d}")
        else:
            # Discord refreshes relative timestamps without repeated API edits.
            embed.add_field(name="Time left", value=f"<t:{self.wall_deadline}:R>")
        embed.set_image(url="attachment://scramble.png")
        embed.set_footer(text="Only the player who started this puzzle can move tiles • 5 minute limit")
        return embed

    async def picture(self, finished: bool = False) -> discord.File:
        data: bytes = await image_work(
            render_board, self.avatar, self.board, self.name, finished=finished
        )
        return discord.File(BytesIO(data), filename="scramble.png")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This puzzle belongs to another player. Start yours with `/scramble`!", ephemeral=True)
            return False
        return True

    def finish(self) -> None:
        if self.ended:
            return
        self.ended = True
        self.duration = min(300, max(0, int(monotonic() - self.started)))
        self.release()
        self.sync_buttons()
        self.stop()
        if self.expiry_task and self.expiry_task is not asyncio.current_task():
            self.expiry_task.cancel()

    def start_clock(self) -> None:
        if self.ended or self.expiry_task is not None:
            return
        self.started = monotonic()
        self.deadline = self.started + 300
        self.wall_deadline = int(time() + 300)
        self.expiry_task = asyncio.create_task(self.expire(), name="scramble-expiry")

    async def expire(self) -> None:
        await asyncio.sleep(max(0, self.deadline - monotonic()))
        await self.on_timeout()

    async def move(self, interaction: discord.Interaction, position: int) -> None:
        await interaction.response.defer()
        if self.lock.locked():
            await interaction.followup.send("One tile at a time - your board is updating.", ephemeral=True)
            return
        async with self.lock:
            if self.ended:
                return
            if monotonic() >= self.deadline:
                await self._expire_locked()
                return
            if position not in cast(Any, neighbours)(self.board.index(0)):
                return
            old_board, old_moves = self.board, self.moves
            board = list(self.board)
            blank = board.index(0)
            board[blank], board[position] = board[position], board[blank]
            self.board, self.moves = tuple(board), self.moves + 1
            won = self.board == GOAL
            self.sync_buttons()
            try:
                file = await self.picture(finished=won)
                if won:
                    for button in self.children:
                        if isinstance(button, (discord.ui.Button, discord.ui.Select)):
                            button.disabled = True
                await interaction.edit_original_response(embed=self.embed("✨ Picture restored! Nicely done." if won else "Slide a numbered tile into the empty space.", completed=won), attachments=[file], view=self)
            except BaseException:
                self.board, self.moves = old_board, old_moves
                self.sync_buttons()
                raise
            if won:
                self.finish()

    @discord.ui.button(label="Give up / Reveal", style=discord.ButtonStyle.danger, row=3)
    async def give_up(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer()
        async with self.lock:
            if self.ended:
                return
            if monotonic() >= self.deadline:
                await self._expire_locked()
                return
            # A failed render must not stop a still-visible playable view.
            file = await self.picture(finished=True)
            for child in self.children:
                if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                    child.disabled = True
            try:
                await interaction.edit_original_response(embed=self.embed("Puzzle ended. Here’s the complete picture.", completed=True), attachments=[file], view=self)
            except BaseException:
                self.sync_buttons()
                raise
            self.finish()

    async def _expire_locked(self) -> None:
        self.finish()
        if self.message:
            try:
                await self.message.edit(embed=self.embed("Time’s up! Start a fresh puzzle with `/scramble`."), view=self)
            except discord.HTTPException:
                logger.warning("scramble_expiry_edit_failed message_id=%s", getattr(self.message, "id", None))

    async def on_timeout(self) -> None:
        async with self.lock:
            if not self.ended:
                await self._expire_locked()

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        logger.error("scramble_update_failed", exc_info=(type(error), error, error.__traceback__))
        if isinstance(error, discord.NotFound):
            self.finish()
        try:
            await interaction.followup.send("The board couldn't update. Please try the move again.", ephemeral=True)
        except discord.HTTPException:
            pass
