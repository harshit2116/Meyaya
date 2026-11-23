"""Self-only, explicit confirmation before replacing a global fantasy identity."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import discord

from bot.services.fantasy_profile import RebirthUnavailable
from bot.utils.embeds import meyaya_embed
from bot.views.fantasy import OwnedFantasyView


class RebirthView(OwnedFantasyView):
    command_name = "rebirth"

    def __init__(self, cog: Any, owner: int, profile: Any) -> None:
        super().__init__(cog, owner, timeout=90)
        self.profile: Any = profile
        self.expected_awakening: Any = profile.awakened_at
        self.token = uuid4().hex
        for index, button in enumerate(self.children):
            if isinstance(button, (discord.ui.Button, discord.ui.Select)):
                button.custom_id = f"meyaya:rebirth:{self.token}:{index}"

    @discord.ui.button(label="Rebirth · replace my build", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            if self.owner in self.cog.duel_users or self.cog.pending.get(self.owner) is not self:
                await interaction.followup.send(
                    "Finish your current fantasy activity before rebirth.", ephemeral=True
                )
                return
            try:
                profile = await self.cog.rebirth_user(self.owner, self.expected_awakening)
            except RebirthUnavailable as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            # Commit is complete. Never roll twice if rendering or delivery fails.
            self.finish()
            for view in tuple(self.cog.views):
                if getattr(getattr(view, "profile", None), "user_id", None) == self.owner:
                    view.finish()
            await self.cog.deliver(
                interaction, profile, interaction.user, self.owner, reveal=True, previous=self
            )

    @discord.ui.button(label="Keep my identity", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()
        async with self.lock:
            if self.closed:
                return
            self.finish()
            await interaction.edit_original_response(
                embed=meyaya_embed(
                    "Rebirth cancelled", "Your current build and guardian are unchanged.", icon="✦"
                ),
                view=self,
            )
