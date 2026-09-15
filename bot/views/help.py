"""Interactive category browser for Meyaya's command help."""

from __future__ import annotations

import discord

from bot.data.help_catalog import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_EMOJIS,
    CATEGORY_ORDER,
    COMMANDS,
    COMMANDS_BY_NAME,
    commands_in_category,
)
from bot.utils.embeds import MeyayaColors, meyaya_embed

HELP_COLOR = MeyayaColors.PINK


def build_help_embed(
    *,
    bot_mention: str,
    command_prefix: str = "uwu",
    category: str | None = None,
    command_name: str | None = None,
) -> discord.Embed:
    """Render the overview, one category, or one exact command."""

    if command_name is not None:
        command = COMMANDS_BY_NAME.get(command_name.casefold())
        if command is None:
            return meyaya_embed(
                "Command not found",
                f"I could not find `{command_name}`. Use `/help` to browse every command.",
                tone="danger",
                icon="💭",
            )
        embed = meyaya_embed(
            f"/{command.name}",
            command.description,
            color=HELP_COLOR,
            icon=CATEGORY_EMOJIS[command.category],
        )
        embed.add_field(
            name="Ways to ask",
            value=(
                f"`/{command.usage}`\n"
                f"`{command_prefix} {command.usage}`\n"
                f"`{bot_mention} {command.usage}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Tucked inside",
            value=f"{CATEGORY_EMOJIS[command.category]} {command.category}",
            inline=False,
        )
        return embed

    if category is not None and category in CATEGORY_DESCRIPTIONS:
        embed = meyaya_embed(
            category,
            CATEGORY_DESCRIPTIONS[category],
            color=HELP_COLOR,
            icon=CATEGORY_EMOJIS[category],
        )
        lines = [
            f"**/{command.usage}**\n> {command.description}"
            for command in commands_in_category(category)
        ]
        embed.description += "\n\n" + "\n\n".join(lines)
        return embed

    embed = meyaya_embed(
        "Meyaya's Command Garden",
        description=(
            "Pick a category below or use `/help command:<name>`.\n\n"
            f"You can call me with `/`, `{command_prefix}`, or {bot_mention}."
        ),
        color=HELP_COLOR,
        icon="🌸",
    )
    for category in CATEGORY_ORDER:
        description = CATEGORY_DESCRIPTIONS[category]
        category_commands = commands_in_category(category)
        names = "  •  ".join(f"`{item.name}`" for item in category_commands)
        embed.add_field(
            name=f"{CATEGORY_EMOJIS[category]} {category} - {len(category_commands)}",
            value=f"{description}\n{names}",
            inline=False,
        )
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, parent: "HelpView") -> None:
        self.help_view = parent
        options = [
            discord.SelectOption(
                label="Overview",
                value="__overview__",
                description="Show every category and invocation style.",
                emoji="🌸",
            )
        ]
        options.extend(
            discord.SelectOption(
                label=category,
                value=category,
                description=CATEGORY_DESCRIPTIONS[category][:100],
                emoji=CATEGORY_EMOJIS[category],
            )
            for category in CATEGORY_ORDER
        )
        super().__init__(placeholder="Choose a command category", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        category = self.values[0]
        embed = build_help_embed(
            bot_mention=self.help_view.bot_mention,
            command_prefix=self.help_view.command_prefix,
            category=None if category == "__overview__" else category,
        )
        await interaction.response.edit_message(embed=embed, view=self.help_view)


class HelpView(discord.ui.View):
    def __init__(self, *, owner_id: int, bot_mention: str, command_prefix: str = "uwu") -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.bot_mention = bot_mention
        self.command_prefix = command_prefix
        self.message: discord.Message | None = None
        self.add_item(HelpCategorySelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Open your own help menu with `/help`.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
