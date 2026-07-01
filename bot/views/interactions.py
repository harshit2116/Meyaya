"""Views for interaction responses."""

from __future__ import annotations

import discord

from bot.app import MeyayaBot
from bot.services.interactions import InteractionDefinition
from bot.utils.embeds import build_interaction_embed


class InteractionResponseView(discord.ui.View):
    """Button view attached to interaction embeds."""

    def __init__(
        self,
        *,
        bot: MeyayaBot,
        definition: InteractionDefinition,
        actor_id: int,
        target_id: int,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.definition = definition
        self.actor_id = actor_id
        self.target_id = target_id
        if definition.button_label:
            button = discord.ui.Button(label=definition.button_label, style=discord.ButtonStyle.primary)

            async def back_callback(interaction: discord.Interaction) -> None:
                await self._send_back(interaction)

            button.callback = back_callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Always allow the button press so the command stays playful."""

        return True

    async def _send_back(self, interaction: discord.Interaction) -> None:
        """Trigger the same interaction in reverse."""

        async with self.bot.db_session() as session:
            service = self.bot.build_interaction_service(session)
            result = await service.perform(interaction.user.id, self.actor_id, self.definition)
        target_member = interaction.guild.get_member(self.actor_id) if interaction.guild else None
        target_avatar = str(target_member.display_avatar.url) if target_member else str(interaction.user.display_avatar.url)
        await interaction.response.edit_message(
            embed=build_interaction_embed(
                title=result.title,
                description=result.message.format(
                    actor=interaction.user.mention,
                    target=target_member.mention if target_member else f"<@{self.actor_id}>",
                ),
                color=self.definition.color,
                actor_avatar=str(interaction.user.display_avatar.url),
                target_avatar=target_avatar,
                gif_url=result.gif_url,
                count_label=f"{self.definition.name.title()}s between {interaction.user.display_name} & {target_member.display_name if target_member else self.actor_id}",
                count=result.count,
            ),
            view=self,
        )
