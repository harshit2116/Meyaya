"""Buttons and private submission modals for anonymous social games."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from bot.utils.components_v2 import MeyayaView

from bot.services.social_games import (
    COLLECTION_LIFETIME,
    LOBBY_LIFETIME,
    MIN_PLAYERS,
    GameSessionError,
    GameStatus,
    SocialGameService,
)
from bot.utils.embeds import meyaya_embed

JudgeCallback = Callable[[str, int | None, bool, discord.Message, bool], Awaitable[None]]

GAME_NAMES = {
    "showdown": "Showdown",
    "excuse": "Excuse Battle",
    "survive": "Survive",
}
GAME_ICONS = {"showdown": "⚔️", "excuse": "🎭", "survive": "🏕️"}


def _participant_list(service: SocialGameService, session_id: str) -> str:
    session = service.get(session_id)
    if session is None or not session.participants:
        return "No players yet."
    return "\n".join(
        f"{index}. <@{user_id}>{' - Host' if user_id == session.host_user_id else ''}"
        for index, user_id in enumerate(session.participants, start=1)
    )


def build_game_embed(service: SocialGameService, session_id: str) -> discord.Embed:
    session = service.get(session_id)
    if session is None:
        return meyaya_embed(
            "Social Game",
            "This game no longer exists.",
            tone="muted",
            icon="🎮",
        )
    snapshot = session.public_snapshot()
    embed = meyaya_embed(
        f"{GAME_NAMES[snapshot.game_type]} - {snapshot.theme}",
        snapshot.scenario,
        icon=GAME_ICONS[snapshot.game_type],
    )
    if snapshot.status is GameStatus.LOBBY:
        embed.add_field(
            name="Lobby",
            value=(
                f"**{snapshot.player_count}/{snapshot.max_players} players**\n"
                f"Minimum: {MIN_PLAYERS} players"
            ),
            inline=False,
        )
        embed.add_field(
            name="Players who joined",
            value=_participant_list(service, session_id),
            inline=False,
        )
        embed.add_field(
            name="How to play",
            value=(
                "Join the lobby, then submit one private answer when the host starts.\n"
                f"Lobby expires <t:{int(session.expires_at.timestamp())}:R>."
            ),
            inline=False,
        )
    elif snapshot.status is GameStatus.COLLECTING:
        embed.add_field(
            name="Anonymous submissions",
            value=f"**{snapshot.submission_count}/{snapshot.player_count} submitted**",
            inline=False,
        )
        embed.add_field(
            name="Privacy", value="Answers stay hidden until judging is complete.", inline=False
        )
        embed.add_field(
            name="Time limit",
            value=(
                f"Submissions close <t:{int(session.expires_at.timestamp())}:R>. "
                f"Meyaya will judge the submitted answers if at least {MIN_PLAYERS} are ready."
            ),
            inline=False,
        )
    elif snapshot.status is GameStatus.JUDGING:
        embed.add_field(
            name="Judging", value="Meyaya is comparing every answer together...", inline=False
        )
    elif snapshot.status is GameStatus.LOCKED:
        embed.add_field(
            name="Answers locked",
            value="Submissions are frozen. The host can retry judging or end the game.",
            inline=False,
        )
    return embed


def build_lobby_closed_embed(service: SocialGameService, session_id: str) -> discord.Embed:
    """Show the final visible roster while directing players to the next message."""

    session = service.get(session_id)
    if session is None:
        return meyaya_embed(
            "Lobby Closed",
            "This game no longer exists.",
            tone="muted",
            icon="🎮",
        )
    embed = meyaya_embed(
        f"{GAME_NAMES[session.game_type]} - Lobby Closed",
        "The game has started. Use the new submission message below.",
        tone="muted",
        icon=GAME_ICONS[session.game_type],
    )
    embed.add_field(
        name=f"Players - {len(session.participants)}",
        value=_participant_list(service, session_id),
        inline=False,
    )
    return embed


class GameSubmissionModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        service: SocialGameService,
        session_id: str,
        public_message: discord.Message,
        judge_callback: JudgeCallback,
    ) -> None:
        super().__init__(title="Anonymous submission", timeout=300)
        self.service = service
        self.session_id = session_id
        self.public_message = public_message
        self.judge_callback = judge_callback
        self.answer = discord.ui.TextInput(
            label="Your answer",
            placeholder="Only Meyaya will connect this answer to you.",
            style=discord.TextStyle.paragraph,
            min_length=1,
            max_length=500,
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            snapshot = await self.service.submit(
                self.session_id,
                interaction.user.id,
                str(self.answer),
            )
        except GameSessionError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            "Your anonymous answer is locked in.", ephemeral=True
        )
        try:
            await self.public_message.edit(embed=build_game_embed(self.service, self.session_id))
        except discord.HTTPException:
            pass

        if snapshot.submission_count == snapshot.player_count:
            await self.judge_callback(self.session_id, None, False, self.public_message, False)


class GameLobbyView(MeyayaView):
    def __init__(
        self,
        *,
        service: SocialGameService,
        session_id: str,
        judge_callback: JudgeCallback,
    ) -> None:
        super().__init__(timeout=LOBBY_LIFETIME.total_seconds())
        self.service = service
        self.session_id = session_id
        self.judge_callback = judge_callback
        self.message: discord.Message | None = None

    async def _error(self, interaction: discord.Interaction, exc: GameSessionError) -> None:
        await interaction.response.send_message(str(exc), ephemeral=True)

    @discord.ui.button(label="Join", emoji="➕", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await self.service.join(self.session_id, interaction.user.id)
        except GameSessionError as exc:
            await self._error(interaction, exc)
            return
        await interaction.response.edit_message(
            embed=build_game_embed(self.service, self.session_id), view=self
        )

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await self.service.leave(self.session_id, interaction.user.id)
        except GameSessionError as exc:
            await self._error(interaction, exc)
            return
        await interaction.response.edit_message(
            embed=build_game_embed(self.service, self.session_id), view=self
        )

    @discord.ui.button(label="Start", emoji="▶️", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await self.service.start(self.session_id, interaction.user.id)
        except GameSessionError as exc:
            await self._error(interaction, exc)
            return
        collection = GameCollectionView(
            service=self.service,
            session_id=self.session_id,
            judge_callback=self.judge_callback,
        )
        self.stop()
        await interaction.response.edit_message(
            embed=build_lobby_closed_embed(self.service, self.session_id),
            view=None,
        )
        if interaction.channel is None:
            return
        collection.message = await interaction.channel.send(
            embed=build_game_embed(self.service, self.session_id),
            view=collection,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await self.service.cancel(self.session_id, interaction.user.id)
        except GameSessionError as exc:
            await self._error(interaction, exc)
            return
        self.stop()
        await interaction.response.edit_message(
            embed=meyaya_embed(
                "Game Cancelled",
                "The host cancelled this game.",
                tone="muted",
                icon="🌙",
            ),
            view=None,
        )

    async def on_timeout(self) -> None:
        session = self.service.get(self.session_id)
        if session is None or session.status is not GameStatus.LOBBY:
            return
        try:
            await self.service.cancel(self.session_id, expected_status=GameStatus.LOBBY)
        except GameSessionError:
            return
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=meyaya_embed(
                        "Game Expired",
                        "The lobby was abandoned.",
                        tone="muted",
                        icon="⌛",
                    ),
                    view=None,
                )
            except discord.HTTPException:
                pass


class GameCollectionView(MeyayaView):
    def __init__(
        self,
        *,
        service: SocialGameService,
        session_id: str,
        judge_callback: JudgeCallback,
    ) -> None:
        super().__init__(timeout=COLLECTION_LIFETIME.total_seconds())
        self.service = service
        self.session_id = session_id
        self.judge_callback = judge_callback
        self.message: discord.Message | None = None
        session = self.service.get(session_id)
        if session is not None and session.status is GameStatus.LOCKED:
            self.submit.disabled = True

    @discord.ui.button(label="Submit privately", emoji="✍️", style=discord.ButtonStyle.primary)
    async def submit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message(
                "The game message is unavailable.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            GameSubmissionModal(
                service=self.service,
                session_id=self.session_id,
                public_message=interaction.message,
                judge_callback=self.judge_callback,
            )
        )

    @discord.ui.button(label="Judge submitted", style=discord.ButtonStyle.success)
    async def judge_submitted(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message(
                "The game message is unavailable.", ephemeral=True
            )
            return
        await interaction.response.defer()
        await self.judge_callback(
            self.session_id,
            interaction.user.id,
            True,
            interaction.message,
            False,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await self.service.cancel(self.session_id, interaction.user.id)
        except GameSessionError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            embed=meyaya_embed(
                "Game Cancelled",
                "The host cancelled this game.",
                tone="muted",
                icon="🌙",
            ),
            view=None,
        )

    async def on_timeout(self) -> None:
        session = self.service.get(self.session_id)
        if session is None or session.status not in {GameStatus.COLLECTING, GameStatus.LOCKED}:
            return
        if (
            session is not None
            and session.status is GameStatus.COLLECTING
            and len(session.submissions) >= MIN_PLAYERS
            and self.message is not None
        ):
            await self.judge_callback(
                self.session_id,
                None,
                False,
                self.message,
                True,
            )
            return

        try:
            await self.service.cancel(self.session_id, expected_status=session.status)
        except GameSessionError:
            return
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=meyaya_embed(
                        "Game Expired",
                        (
                            f"Fewer than {MIN_PLAYERS} players submitted in time, so the game "
                            "was ended."
                        ),
                        tone="muted",
                        icon="⌛",
                    ),
                    view=None,
                )
            except discord.HTTPException:
                pass
