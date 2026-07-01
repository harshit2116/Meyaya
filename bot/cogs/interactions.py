"""Slash commands for social interactions."""

from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.data.interactions import INTERACTION_DEFINITIONS
from bot.app import MeyayaBot
from bot.services.interactions import InteractionDefinition, InteractionResult, InteractionService
from bot.utils.embeds import build_interaction_embed
from bot.views.interactions import InteractionResponseView


class InteractionsCog(commands.Cog):
    """Dynamic slash and text commands for social interactions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._app_commands: list[app_commands.Command] = []
        self._text_commands: list[commands.Command] = []
        self._text_help_command: commands.Command | None = None
        self._text_gif_command: commands.Command | None = None

    async def cog_load(self) -> None:
        """Register the generated commands with both the tree and the text command router."""

        for definition in INTERACTION_DEFINITIONS:
            app_command = self._build_app_command(definition)
            self.bot.tree.add_command(app_command)
            self._app_commands.append(app_command)

            text_command = self._build_text_command(definition)
            self.bot.add_command(text_command)
            self._text_commands.append(text_command)

        self._text_gif_command = self._build_text_gif_command()
        self._text_help_command = self._build_text_help_command()
        self.bot.add_command(self._text_gif_command)
        self.bot.add_command(self._text_help_command)

    def cog_unload(self) -> None:
        """Remove generated commands during reload."""

        for command in self._app_commands:
            self.bot.tree.remove_command(command.name)
        for command in self._text_commands:
            self.bot.remove_command(command.name)
        if self._text_gif_command is not None:
            self.bot.remove_command(self._text_gif_command.name)
        if self._text_help_command is not None:
            self.bot.remove_command(self._text_help_command.name)

    def _build_app_command(self, definition: InteractionDefinition) -> app_commands.Command[commands.Cog, ..., None]:
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
                service = bot.build_interaction_service(session)
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

    def _build_text_command(self, definition: InteractionDefinition) -> commands.Command:
        async def callback(
            ctx: commands.Context[commands.Bot],
            target: discord.Member | None = None,
        ) -> None:
            if ctx.guild is None:
                await ctx.send("This command only works inside a server.")
                return

            chosen_target = target or ctx.author
            bot = cast(MeyayaBot, ctx.bot)
            async with bot.db_session() as session:
                service = bot.build_interaction_service(session)
                result = await service.perform(ctx.author.id, chosen_target.id, definition)
                embed, view = self._build_interaction_render(bot, definition, ctx.author, chosen_target, result)
                await ctx.send(embed=embed, view=view)

        return commands.Command(
            callback,
            name=definition.name,
            help=f"Send a {definition.name} interaction.",
        )

    def _build_text_gif_command(self) -> commands.Command:
        async def callback(
            ctx: commands.Context[commands.Bot],
            *,
            query: str,
        ) -> None:
            bot = cast(MeyayaBot, ctx.bot)
            gif_service = bot.build_giphy_service()
            if gif_service is None:
                await ctx.send("GIF support is not configured.")
                return

            result = await gif_service.random_gif(query)
            if result.url is None:
                await ctx.send(f"I could not find a GIF for `{query}`.")
                return

            embed = discord.Embed(title=f"GIF: {query}", color=0x8ECAE6)
            embed.set_image(url=result.url)
            await ctx.send(embed=embed)

        return commands.Command(
            callback,
            name="gif",
            help="Fetch a GIF from Giphy with uwu gif <query>.",
        )

    def _build_text_help_command(self) -> commands.Command:
        async def callback(ctx: commands.Context[commands.Bot]) -> None:
            embed = discord.Embed(title="Meyaya Commands", color=0x8ECAE6)
            lines = ["**Text commands**"]
            for command in self._text_commands:
                lines.append(f"`uwu {command.name} ...`")
            lines.append("`uwu gif <query>`")
            lines.append("`uwu help`")
            lines.append("`uwu dailyiq [member]`")
            lines.append("`uwu dailydumbest`")
            lines.append("`uwu dailysmartest`")
            lines.append("`uwu dailyclown`")
            lines.append("`uwu profile [member]`")
            lines.append("")
            lines.append("**Slash commands**")
            for command in INTERACTION_DEFINITIONS:
                lines.append(f"`/{command.name}`")
            lines.extend(["`/dailyiq`", "`/dailydumbest`", "`/dailysmartest`", "`/dailyclown`", "`/profile`"])
            embed.description = "\n".join(lines)
            await ctx.send(embed=embed)

        return commands.Command(
            callback,
            name="help",
            help="List all Meyaya commands.",
        )

    def _build_interaction_render(
        self,
        bot: MeyayaBot,
        definition: InteractionDefinition,
        actor: discord.Member,
        target: discord.Member,
        result: InteractionResult,
    ) -> tuple[discord.Embed, InteractionResponseView | None]:
        embed = build_interaction_embed(
            title=result.title,
            description=result.message.format(actor=actor.mention, target=target.mention),
            color=definition.color,
            actor_avatar=str(actor.display_avatar.url),
            target_avatar=str(target.display_avatar.url),
            gif_url=result.gif_url,
            count_label=f"{definition.name.title()}s between {actor.display_name} & {target.display_name}",
            count=result.count,
        )
        view = (
            InteractionResponseView(
                bot=bot,
                definition=definition,
                actor_id=actor.id,
                target_id=target.id,
            )
            if definition.button_label
            else None
        )
        return embed, view


async def setup(bot: commands.Bot) -> None:
    """Install the interactions cog."""

    await bot.add_cog(InteractionsCog(bot))
