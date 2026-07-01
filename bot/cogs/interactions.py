"""Slash commands for social interactions."""

from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.data.interactions import INTERACTION_DEFINITIONS
from bot.app import MeyayaBot
from bot.services.interactions import InteractionDefinition, InteractionService
from bot.utils.embeds import build_interaction_embed
from bot.views.interactions import InteractionResponseView


class InteractionsCog(commands.Cog):
    """Dynamic slash commands for social interactions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._commands: list[app_commands.Command] = []

    async def cog_load(self) -> None:
        """Register the generated commands with the tree."""

        for definition in INTERACTION_DEFINITIONS:
            command = self._build_command(definition)
            self.bot.tree.add_command(command)
            self._commands.append(command)

    def cog_unload(self) -> None:
        """Remove generated commands during reload."""

        for command in self._commands:
            self.bot.tree.remove_command(command.name)

    def _build_command(self, definition: InteractionDefinition) -> app_commands.Command[commands.Cog, ..., None]:
        async def callback(
            interaction: discord.Interaction,
            target: discord.Member | None = None,
        ) -> None:
            chosen_target = target or interaction.user
            if interaction.guild is None:
                await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
                return

            bot = cast(MeyayaBot, interaction.client)
            async with bot.db_session() as session:
                service = InteractionService(session)
                result = await service.perform(interaction.user.id, chosen_target.id, definition)
                await interaction.response.send_message(
                    embed=build_interaction_embed(
                        title=result.title,
                        description=result.message.format(actor=interaction.user.mention, target=chosen_target.mention),
                        color=definition.color,
                        actor_avatar=str(interaction.user.display_avatar.url),
                        target_avatar=str(chosen_target.display_avatar.url),
                        gif_url=result.gif_url,
                        count_label=f"{definition.name.title()}s between {interaction.user.display_name} & {chosen_target.display_name}",
                        count=result.count,
                    ),
                    view=InteractionResponseView(
                        bot=bot,
                        service=service,
                        definition=definition,
                        actor_id=interaction.user.id,
                        target_id=chosen_target.id,
                    ) if definition.button_label else None,
                )

        return app_commands.Command(
            name=definition.name,
            description=f"Send a {definition.name} interaction.",
            callback=callback,
        )


async def setup(bot: commands.Bot) -> None:
    """Install the interactions cog."""

    await bot.add_cog(InteractionsCog(bot))
