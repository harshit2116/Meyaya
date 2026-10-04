"""Interactive category browser for Meyaya's command help."""

from __future__ import annotations

import discord
import inspect
import re

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
SUPPORT_INVITE = "https://discord.gg/e9bK5ZbUZS"


def build_help_embed(
    *,
    bot_mention: str,
    command_prefix: str = "uwu",
    category: str | None = None,
    command_name: str | None = None,
    bot=None,
) -> discord.Embed:
    """Render the overview, one category, or one exact command."""

    if command_name is not None:
        if command_name.casefold() in {"voice chat", "voices", "vc"}:
            return build_help_embed(
                bot_mention=bot_mention,
                command_prefix=command_prefix,
                category="Voice Chat",
                bot=bot,
            )
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
            name="Category",
            value=f"{CATEGORY_EMOJIS[command.category]} {command.category}",
            inline=False,
        )
        examples = {
            "mostlikely": "mostlikely @Alex @Sam win a cooking contest",
            "room": "room @Alex",
            "warninglabel": "warninglabel @Alex",
            "fortune": "fortune",
            "rate": "rate pineapple pizza",
            "argumenttimeline": "argumenttimeline https://discord.com/channels/123/456/789",
            "checkclaim": "checkclaim https://discord.com/channels/123/456/789",
        }
        example = examples.get(command.name)
        if example is None:
            example = re.sub(r"\[[^\]]*\]", "", command.usage)
            example = re.sub(
                r"<([^>]*)>",
                lambda m: (
                    "@Alex"
                    if "member" in m[1]
                    else {
                        "question": "Will today be a good day?",
                        "text": "Hello there",
                        "message": "Hello there",
                        "reason": "Just for fun",
                        "amount": "1",
                        "number": "1",
                    }.get(m[1], m[1])
                ),
                example,
            )
            example = " ".join(example.split())
        embed.add_field(name="Example", value=f"`{command_prefix} {example}`", inline=False)
        registered = bot.get_command(command.name) if bot else None
        permissions, restrictions = set(), set()
        if registered:
            slash = bot.tree.get_command(command.name) if hasattr(bot, "tree") else None
            if slash is not None and hasattr(slash, "parameters"):
                slash_usage = " ".join(
                    (
                        f"{p.display_name}:<{p.display_name}>"
                        if p.required
                        else f"[{p.display_name}:value]"
                    )
                    for p in slash.parameters
                )
                embed.set_field_at(
                    0,
                    name="Ways to ask",
                    value=(
                        f"`{' '.join(filter(None, (f'/{command.name}', slash_usage)))}`\n"
                        f"`{' '.join(filter(None, (command_prefix, command.name, registered.signature)))}`"
                    )[:1024],
                    inline=False,
                )
                if slash.default_permissions:
                    permissions.update(
                        "Member: " + key.replace("_", " ").title()
                        for key, enabled in slash.default_permissions
                        if enabled
                    )
            for check in registered.checks:
                name = getattr(check, "__qualname__", "")
                if "owner" in name:
                    restrictions.add("Bot owner only")
                values = (
                    inspect.getclosurevars(check).nonlocals if inspect.isfunction(check) else {}
                )
                for key, enabled in values.get("perms", {}).items():
                    if enabled:
                        permissions.add(
                            ("Bot: " if "bot_has" in name else "Member: ")
                            + key.replace("_", " ").title()
                        )
            restrictions.update(permissions)
            if restrictions:
                embed.add_field(
                    name="Permissions", value="\n".join(sorted(restrictions)), inline=False
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
            "Every available command is listed below, grouped by category.\n\n"
            f"**Quick lookup** · `/help command:profile` or `{command_prefix} help profile`\n"
            f"**Command styles** · `/command` · `{command_prefix} command` · {bot_mention}"
        ),
        color=HELP_COLOR,
        icon="🌸",
    )
    for category in CATEGORY_ORDER:
        description = CATEGORY_DESCRIPTIONS[category]
        category_commands = commands_in_category(category)
        names = " · ".join(f"`/{command.name}`" for command in category_commands)
        embed.add_field(
            name=f"{CATEGORY_EMOJIS[category]} {category} · {len(category_commands)}",
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
                default=parent.category is None,
            )
        ]
        options.extend(
            discord.SelectOption(
                label=category,
                value=category,
                description=CATEGORY_DESCRIPTIONS[category][:100],
                emoji=CATEGORY_EMOJIS[category],
                default=category == parent.category,
            )
            for category in CATEGORY_ORDER
        )
        super().__init__(placeholder="Choose a command category", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        category = self.values[0]
        self.help_view.category = None if category == "__overview__" else category
        self.help_view.refresh_items()
        embed = build_help_embed(
            bot_mention=self.help_view.bot_mention,
            command_prefix=self.help_view.command_prefix,
            category=None if category == "__overview__" else category,
            bot=self.help_view.bot,
        )
        await interaction.response.edit_message(embed=embed, view=self.help_view)


class HelpView(discord.ui.View):
    def __init__(
        self, *, owner_id: int, bot_mention: str, command_prefix: str = "uwu", bot=None
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.bot_mention = bot_mention
        self.command_prefix = command_prefix
        self.bot = bot
        self.category = None
        self.message: discord.Message | None = None
        self.refresh_items()

    def refresh_items(self):
        self.clear_items()
        self.add_item(HelpCategorySelect(self))
        self.add_item(
            discord.ui.Button(
                label="Join Pondside Lounge",
                style=discord.ButtonStyle.link,
                url=SUPPORT_INVITE,
                row=1,
            )
        )

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
            if not isinstance(child, discord.ui.Button) or child.url is None:
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
