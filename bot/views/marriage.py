"""UI components for marriage proposals."""

from __future__ import annotations

import discord

from bot.app import MeyayaBot
from bot.services.marriage import AlreadyMarriedError

CEREMONY_GIF_QUERY = "anime wedding kiss ring"


class MarriageProposalView(discord.ui.View):
    """Accept/Reject buttons for a marriage proposal."""

    def __init__(self, bot: MeyayaBot, proposer_id: int, target_id: int) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message(
                "💌 This proposal isn't addressed to you.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content=self.message.content + "\n\n*💤 This proposal has expired.*",
                    view=self,
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Accept", emoji="💍", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True

        async with self.bot.db_session() as session:
            service = self.bot.build_marriage_service(session)
            try:
                await service.marry(self.proposer_id, self.target_id)
            except (AlreadyMarriedError, ValueError):
                await interaction.response.edit_message(
                    content="💔 **This proposal fell through.** One of you is already taken.",
                    view=self,
                )
                return

        gif_url = ""
        giphy = self.bot.build_giphy_service()
        if giphy is not None:
            gif_result = await giphy.random_anime_gif(CEREMONY_GIF_QUERY)
            gif_url = gif_result.url if gif_result else ""

        content = (
            "# 💒 Wedding Ceremony 💒\n\n"
            f"<@{self.proposer_id}> **and** <@{self.target_id}> **are now married!** 🎉\n\n"
            "───────────────────────\n"
            "*Until anime cancels it...* 💞\n"
            "───────────────────────"
        )
        if gif_url:
            content += f"\n\n{gif_url}"

        await interaction.response.edit_message(content=content, view=self)

    @discord.ui.button(label="Reject", emoji="💔", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        content = (
            "# 💔 Proposal Declined\n\n"
            f"<@{self.target_id}> **turned down** <@{self.proposer_id}>**'s proposal.**\n\n"
            "*Better luck next time...* 😔"
        )
        await interaction.response.edit_message(content=content, view=self)