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
                bot_mention=bot_mention, command_prefix=command_prefix, category="Voice Chat"
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
            name="Tucked inside",
            value=f"{CATEGORY_EMOJIS[command.category]} {command.category}",
            inline=False,
        )
        examples = {"mostlikely": "mostlikely @Alex @Sam win a cooking contest",
                    "room": "room @Alex", "warninglabel": "warninglabel @Alex",
                    "fortune": "fortune", "rate": "rate pineapple pizza",
                    "argumenttimeline": "argumenttimeline https://discord.com/channels/123/456/789",
                    "checkclaim": "checkclaim https://discord.com/channels/123/456/789"}
        example = examples.get(command.name)
        if example is None:
            example = re.sub(r"\[[^\]]*\]", "", command.usage)
            example = re.sub(r"<([^>]*)>", lambda m: "@Alex" if "member" in m[1] else {
                "question": "Will today be a good day?", "text": "Hello there", "message": "Hello there",
                "reason": "Just for fun", "amount": "1", "number": "1"}.get(m[1], m[1]), example)
            example = " ".join(example.split())
        embed.add_field(name="Example", value=f"`{command_prefix} {example}`", inline=False)
        registered = bot.get_command(command.name) if bot else None
        permissions, restrictions = set(), set()
        if registered:
            slash = bot.tree.get_command(command.name) if hasattr(bot, "tree") else None
            if slash is not None and hasattr(slash, "parameters"):
                slash_usage = " ".join(
                    f"{p.display_name}:<{p.description}>" if p.required else f"[{p.display_name}:value]"
                    for p in slash.parameters)
                embed.set_field_at(0, name="Ways to ask", value=(
                    f"`/{command.name} {slash_usage}`\n"
                    f"`{command_prefix} {command.name} {registered.signature}`\n"
                    "Angle brackets are required; square brackets are optional. Replace them with your values."
                )[:1024], inline=False)
                if slash.default_permissions:
                    permissions.update("Member: " + key.replace("_", " ").title()
                                       for key, enabled in slash.default_permissions if enabled)
            for check in registered.checks:
                name = getattr(check, "__qualname__", "")
                if "guild_only" in name:
                    restrictions.add("Server only")
                if "owner" in name:
                    restrictions.add("Bot owner only")
                values = inspect.getclosurevars(check).nonlocals if inspect.isfunction(check) else {}
                for key, enabled in values.get("perms", {}).items():
                    if enabled:
                        permissions.add(("Bot: " if "bot_has" in name else "Member: ") + key.replace("_", " ").title())
            cooldown = registered._buckets._cooldown
            cooldown_text = f"{cooldown.rate} use(s) per {cooldown.per:g} seconds ({registered._buckets.type.name})." if cooldown else "No fixed command cooldown."
            if command.name in {"argumenttimeline", "checkclaim"}:
                cooldown_text = "One completed review per member per server each 60 seconds; one review at a time."
            restrictions.update(permissions)
            embed.add_field(name="Permissions", value="\n".join(sorted(restrictions)) or "No additional Discord permission check.", inline=False)
            embed.add_field(name="Cooldown", value=cooldown_text + " Shared usage limits and feature checks may also apply.", inline=False)
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
            "Voice controls are under **Voice Chat**.\n"
            f"You can call me with `/`, `{command_prefix}`, or {bot_mention}.\n\n"
            f"[Join Pondside Lounge]({SUPPORT_INVITE}) to report an issue or try "
            "Meyaya without the daily server chat limit."
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
        self.add_item(discord.ui.Button(
            label="Join Pondside Lounge", style=discord.ButtonStyle.link,
            url=SUPPORT_INVITE, row=1,
        ))

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
