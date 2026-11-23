"""All supported studio voices, split into Discord-sized selectable menus."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import discord

from bot.data.voices import GEMINI_LIVE_VOICES, VOICE_DESCRIPTIONS
from bot.utils.components_v2 import MeyayaView


class VoiceSelect(discord.ui.Select[Any]):
    def __init__(self, parent: VoicePicker, voices: Sequence[str], row: int) -> None:
        self.picker = parent
        super().__init__(
            placeholder=f"Choose a voice ({row * 15 + 1}-{row * 15 + len(voices)})",
            row=row,
            options=[
                discord.SelectOption(
                    label=voice,
                    value=voice,
                    description=VOICE_DESCRIPTIONS[voice],
                    default=voice == parent.current,
                )
                for voice in voices
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.picker.select_voice(interaction, self.values[0])


class VoicePicker(MeyayaView):
    def __init__(self, cog: Any, owner_id: int, guild_id: int) -> None:
        super().__init__(timeout=180)
        self.cog: Any = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.current: str = cog._voice_for_guild(guild_id)
        self.busy = False
        self.message: discord.Message | None = None
        for start in range(0, len(GEMINI_LIVE_VOICES), 15):
            self.add_item(VoiceSelect(self, GEMINI_LIVE_VOICES[start : start + 15], start // 15))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.cog.bot.chat_blacklist.is_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
            return False
        if (
            interaction.guild_id != self.guild_id
            or interaction.user.id != self.owner_id
            or not self.cog._is_manager(interaction.user)
        ):
            await interaction.response.send_message(
                "Only the server manager who opened this menu can change the voice.", ephemeral=True
            )
            return False
        return True

    async def select_voice(self, interaction: discord.Interaction, voice: str) -> None:
        if self.busy:
            await interaction.response.send_message(
                "A voice change is already in progress.", ephemeral=True
            )
            return
        self.busy = True
        await interaction.response.defer()
        try:
            result = await self.cog.change_voice(self.guild_id, voice)
            for child in self.children:
                if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                    child.disabled = True
            await interaction.edit_original_response(content=result, embed=None, view=self)
            self.stop()
        except Exception:
            await interaction.followup.send(
                "The voice change could not finish. Try `voiceset` again.", ephemeral=True
            )
        finally:
            self.busy = False

    @discord.ui.button(label="Use default voice", row=2, style=discord.ButtonStyle.secondary)
    async def reset(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.select_voice(interaction, "default")

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
