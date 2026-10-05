"""Prefix lore names, while retaining a real member picker for slash commands."""

import discord
from discord import app_commands
from discord.ext import commands


class FantasyProfileTarget(commands.MemberConverter, app_commands.Transformer):
    @property
    def type(self):
        return discord.AppCommandOptionType.user

    async def convert(self, ctx, argument):
        name = argument.strip().casefold()
        if name in {"veyra", "veryra"}:
            return "veyra"
        if name == "meyaya":
            return "meyaya"
        return await super().convert(ctx, argument)

    async def transform(self, interaction, value):
        if not isinstance(value, discord.Member):
            raise app_commands.TransformerError(value, self.type, self)
        return value
