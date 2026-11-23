"""Prefix lore names, while retaining a real member picker for slash commands."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


class FantasyProfileTarget(commands.MemberConverter, app_commands.Transformer):
    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.user

    async def convert(  # type: ignore[override]
        self, ctx: commands.Context[Any], argument: str
    ) -> discord.Member | str:
        name = argument.strip().casefold()
        if name in {"veyra", "veryra"}:
            return "veyra"
        if name == "meyaya":
            return "meyaya"
        return await super().convert(ctx, argument)

    async def transform(
        self, interaction: discord.Interaction[Any], value: Any
    ) -> discord.Member:
        if not isinstance(value, discord.Member):
            raise app_commands.TransformerError(value, self.type, self)
        return value
