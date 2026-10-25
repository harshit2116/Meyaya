"""Interactive category browser for Meyaya's command help."""

from __future__ import annotations

import discord
import asyncio
import math
from bot.services.help_art import gallery, help_files
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
from bot.utils.command_aliases import ALIAS_COMMANDS, command_aliases

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
        lookup = command_name.casefold()
        registered_alias = bot.get_command(lookup) if bot else None
        canonical = ALIAS_COMMANDS.get(lookup, lookup)
        resolved_name = getattr(registered_alias, "name", None)
        if lookup not in COMMANDS_BY_NAME and resolved_name in COMMANDS_BY_NAME:
            canonical = resolved_name
        command = COMMANDS_BY_NAME.get(canonical)
        if command is None:
            return meyaya_embed(
                "Command not found",
                f"I could not find `{command_name}`. Use `/help` to browse every command.",
                tone="danger",
                icon="💭",
            )
        usage = command.usage.split(" | ship random")[0]
        embed = meyaya_embed(
            f"/{command.name}",
            command.description,
            color=HELP_COLOR,
            icon=CATEGORY_EMOJIS[command.category],
        )
        embed.add_field(
            name="Ways to ask",
            value=(
                f"`/{usage}`\n"
                f"`{command_prefix} {usage}`\n"
                f"`{bot_mention} {usage}`"
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
            "ship": "ship @Alex @Sam",
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
        aliases = command_aliases(command.name, bot)
        if aliases:
            embed.add_field(name="Short forms", value=" · ".join(
                f"`{command_prefix} {alias}`" for alias in aliases
            )[:1024], inline=False)
        return embed

    if category is not None and category in CATEGORY_DESCRIPTIONS:
        embed = meyaya_embed(
            category,
            CATEGORY_DESCRIPTIONS[category],
            color=HELP_COLOR,
            icon=CATEGORY_EMOJIS[category],
        )
        lines = [
            f"**/{command.usage}**"
            + (" · " + " / ".join(f"`{alias}`" for alias in command_aliases(command.name, bot))
               if command_aliases(command.name, bot) else "")
            + f"\n> {command.description}"
            for command in commands_in_category(category)
        ]
        embed.description += "\n\n" + "\n\n".join(lines)
        return embed

    embed = meyaya_embed(
        "Meyaya's Command Directory",
        description=(
            "Every available command is listed below, grouped by category.\n\n"
            f"**Quick lookup** · `/help command:profile` or `{command_prefix} h p`\n"
            f"**Short forms** · `{command_prefix} pc` (profilecheck) · `{command_prefix} dg` (dungeon)\n"
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


# Every command is visible directly across these four directory tabs.
DIRECTORY_PAGES = (
    ("Discover", ("Essentials", "Profile Studio", "Fantasy / Profile", "Fortune / Tarot")),
    ("Together", ("Social", "Social Reactions", "Fun and Scores", "Relationships")),
    ("Play & stories", ("Multiplayer Games", "Single Player Games", "Meyaya Court", "Roleplay", "Daily Picks")),
    ("Voice & server", ("Voice Chat", "Memory", "Fact Checking", "Server Admin")),
)
PAGE_SIZE=6

# Directory copy stays brief; command pages retain the complete catalog text.
DIRECTORY_SUMMARIES = {
    "profile": "Your profile, relationships, activity, and bond with Meyaya.",
    "profilecheck": "Review your avatar, banner, decoration, and profile style.",
    "aura": "Turn your profile colors into a personal aura card.",
    "duostyle": "Compare two profiles in a shared style card.",
    "callingcard": "A collectible card shaped by your style and Meyaya bond.",
    "summon": "Summon a character with rarity, traits, and a signature passive.",
    "guardian": "Meet your soul-bound guardian or preview rare summons.",
    "awaken": "Discover your permanent fantasy identity.",
    "fantasyprofile": "View your awakened character and build.",
    "rebirth": "Start a new fantasy build after confirmation.",
    "dungeon": "A saved story adventure through ten worlds with Meyaya.",
    "versus": "Challenge another member or face Meyaya herself.",
    "bossfight": "Fight Meyaya or Veyra, or watch their cinematic clash.",
    "elation": "Meyaya takes over the channel. Try to outwit your new queen.",
    "serversetup": "Configure chat access, automatic replies, and moderation.",
    "serverdashboard": "View this server's allowance, activity, and settings.",
    "tarot": "Three illustrated cards for your past, present, and future.",
    "fate": "Discover your archetype, strength, path, and next chapter.",
}


def _resolve(name, bot):
    lookup=(name or "").strip().casefold().removeprefix("/")
    registered=bot.get_command(lookup) if bot else None
    canonical=ALIAS_COMMANDS.get(lookup,lookup)
    if lookup not in COMMANDS_BY_NAME and getattr(registered,"name",None) in COMMANDS_BY_NAME:
        canonical=registered.name
    return canonical if canonical in COMMANDS_BY_NAME else None


def can_attach_help_art(channel, guild):
    if guild is None or channel is None or getattr(guild,"me",None) is None:
        return True
    return channel.permissions_for(guild.me).attach_files


class HelpCategorySelect(discord.ui.Select):
    def __init__(self,parent):
        self.help_view=parent
        options=[discord.SelectOption(label="Command directory",value="__overview__",emoji="🌸",
                    description="Browse every command across four compact pages.",default=parent.category is None)]
        options.extend(discord.SelectOption(label=f"{category} · {len(commands_in_category(category))}",
            value=category,description=CATEGORY_DESCRIPTIONS[category][:100],
            emoji=CATEGORY_EMOJIS[category],default=parent.category==category) for category in CATEGORY_ORDER)
        super().__init__(placeholder="Explore a command category",options=options)

    async def callback(self,interaction):
        await self.help_view.navigate(interaction,category=self.values[0])


class HelpCommandSelect(discord.ui.Select):
    def __init__(self,parent):
        self.help_view=parent
        options=[discord.SelectOption(label=f"/{command.name}",value=command.name,
                    description=command.description[:100],default=parent.command_name==command.name)
                 for command in commands_in_category(parent.category)]
        super().__init__(placeholder="Open a command's usage, example and permissions",options=options)

    async def callback(self,interaction):
        await self.help_view.navigate(interaction,command=self.values[0])


class HelpButton(discord.ui.Button):
    def __init__(self,parent,label,action,*,disabled=False,style=discord.ButtonStyle.secondary):
        self.help_view=parent
        self.action=action
        super().__init__(label=label,style=style,disabled=disabled)

    async def callback(self,interaction):
        await self.help_view.navigate(interaction,action=self.action)


class HelpView(discord.ui.LayoutView):
    """Compact native command directory. One banner upload; text-only navigation."""
    def __init__(self,*,owner_id,bot_mention,command_prefix="uwu",bot=None,command_name=None,illustrated=True):
        super().__init__(timeout=300)
        self.owner_id=owner_id
        self.illustrated=illustrated
        self.bot_mention=bot_mention
        self.command_prefix=command_prefix
        self.bot=bot
        self.category=None
        self.command_name=None
        self.page=0
        self.directory_page=0
        self.message=None
        self.unknown=None
        self._navigation=asyncio.Lock()
        if command_name:
            category=next((c for c in CATEGORY_ORDER if c.casefold()==command_name.casefold()),None)
            if command_name.casefold() in {"voice chat","voices","vc"}:category="Voice Chat"
            self.command_name=_resolve(command_name,bot)
            if self.command_name:self.category=COMMANDS_BY_NAME[self.command_name].category
            elif category:self.category=category
            else:self.unknown=command_name[:80]
        self.refresh_items()

    def files(self):
        return help_files() if self.illustrated else []

    def _image(self,name):
        return gallery(name) if self.illustrated else None

    @property
    def page_count(self):
        return max(1,math.ceil(len(commands_in_category(self.category))/PAGE_SIZE)) if self.category else 1

    def _container(self,*items,color=0xDE91B4):
        self.add_item(discord.ui.Container(*(item for item in items if item is not None),accent_color=color))

    def _overview(self):
        title, categories = DIRECTORY_PAGES[self.directory_page]
        parts = [self._image("directory"), discord.ui.TextDisplay(
            f"## 🌸 Meyaya's command directory\n"
            f"**{len(COMMANDS)} commands · {len(CATEGORY_ORDER)} categories** · "
            "Choose a tab below, or jump straight to a category.")]
        if self.unknown:
            safe = discord.utils.escape_mentions(discord.utils.escape_markdown(self.unknown))
            parts.append(discord.ui.TextDisplay(f"I couldn't find **{safe}**. Try a command or category below."))
        parts.append(discord.ui.TextDisplay(
            f"**Chat naturally** · Mention {self.bot_mention}. She follows conversations and remembers shared moments.\n"
            f"**Commands** · `/profile` or `{self.command_prefix} profile` · **Details** · `/help command:profilecheck`"))
        self._container(*parts)
        tabs = [HelpButton(self, label, f"directory:{index}",
                 style=discord.ButtonStyle.primary if index == self.directory_page else discord.ButtonStyle.secondary)
                for index, (label, _) in enumerate(DIRECTORY_PAGES)]
        self.add_item(discord.ui.ActionRow(*tabs))
        self.add_item(discord.ui.ActionRow(HelpCategorySelect(self)))
        for category in categories:
            entries = commands_in_category(category)
            if category == "Social Reactions":
                lines = [" · ".join(f"`/{entry.name}`" for entry in entries)]
            else:
                lines = [f"`/{entry.name}` · {DIRECTORY_SUMMARIES.get(entry.name, entry.description)}" for entry in entries]
            self._container(discord.ui.TextDisplay(
                f"### {CATEGORY_EMOJIS[category]} {category} · {len(entries)}\n"
                + (CATEGORY_DESCRIPTIONS[category] + "\n" if category == "Social Reactions" else "")
                + "\n".join(lines)))
        self.add_item(discord.ui.TextDisplay(
            f"-# {title} · {self.directory_page+1}/{len(DIRECTORY_PAGES)} · "
            "Choose a category above for usage, examples, and permissions."))

    def _category_page(self):
        commands=commands_in_category(self.category)
        self.page=max(0,min(self.page,self.page_count-1))
        start=self.page*PAGE_SIZE
        entries=commands[start:start+PAGE_SIZE]
        parts=[discord.ui.TextDisplay(
            f"## {CATEGORY_EMOJIS[self.category]} {self.category}\n{CATEGORY_DESCRIPTIONS[self.category]}")]
        for command in entries:
            aliases=command_aliases(command.name,self.bot)
            shortcut=(" · Short form: "+" / ".join(f"`{self.command_prefix} {alias}`" for alias in aliases)) if aliases else ""
            # Ship's random shortcut is prefix-only. Keep slash member usage precise.
            usage=command.usage.split(" | ship random")[0]
            parts.append(discord.ui.TextDisplay(
                f"### /{command.name}\n{command.description}\n"
                f"-# `{self.command_prefix} {usage}`{shortcut}"))
        parts.append(discord.ui.TextDisplay(
            f"-# Page {self.page+1}/{self.page_count} · {start+1}–{start+len(entries)} of {len(commands)} commands. "
            "Choose a command above for examples and permissions."))
        self._container(*parts)

    def _command_page(self):
        embed=build_help_embed(bot_mention=self.bot_mention,command_prefix=self.command_prefix,
                              command_name=self.command_name,bot=self.bot)
        parts=[discord.ui.TextDisplay(
            f"## {CATEGORY_EMOJIS[self.category]} /{self.command_name}\n{embed.description}")]
        for field in embed.fields:
            if field.name=="Category":continue
            parts.append(discord.ui.TextDisplay(f"### {field.name}\n{field.value}"))
        if self.command_name=="ship":
            parts.append(discord.ui.TextDisplay(
                f"### A surprise pairing\n`{self.command_prefix} ship random` chooses two different human members in this server."))
        parts.append(discord.ui.TextDisplay(f"-# {self.category} · Choose another command, or return to the category."))
        self._container(*parts)

    def refresh_items(self):
        self.clear_items()
        if self.category:
            self.add_item(discord.ui.ActionRow(HelpCategorySelect(self)))
            self.add_item(discord.ui.ActionRow(HelpCommandSelect(self)))
            if self.command_name:self._command_page()
            else:self._category_page()
        else:self._overview()
        if self.command_name:
            buttons=[HelpButton(self,"← Back to category","back"),HelpButton(self,"All commands","home")]
        elif self.category:
            buttons=[]
            if self.page_count>1:
                buttons.extend([HelpButton(self,"← Previous","previous",disabled=self.page==0),
                                HelpButton(self,"Next →","next",disabled=self.page>=self.page_count-1)])
            buttons.append(HelpButton(self,"All commands","home"))
        else:
            buttons=[]
        buttons.append(discord.ui.Button(label="Support server",style=discord.ButtonStyle.link,url=SUPPORT_INVITE))
        self.add_item(discord.ui.ActionRow(*buttons))

    async def navigate(self,interaction,*,category=None,command=None,action=None):
        async with self._navigation:
            if self.is_finished():
                await interaction.response.send_message("This guide has closed. Open a fresh one with `/help`.",ephemeral=True)
                return
            if category is not None:
                if category!="__overview__" and category not in CATEGORY_ORDER:
                    await interaction.response.send_message("That category isn't available. Open `/help` to browse.",ephemeral=True)
                    return
                self.category=None if category=="__overview__" else category
                self.command_name=None;self.page=0;self.unknown=None
            elif command:
                self.command_name=_resolve(command,self.bot)
                if self.command_name:self.category=COMMANDS_BY_NAME[self.command_name].category
            elif action and action.startswith("directory:"):
                try:
                    index=int(action.split(":",1)[1])
                except ValueError:
                    index=0
                self.directory_page=max(0,min(len(DIRECTORY_PAGES)-1,index))
                self.category=None;self.command_name=None;self.page=0;self.unknown=None
            elif action=="home":
                self.category=None;self.command_name=None;self.page=0;self.unknown=None
            elif action=="back":self.command_name=None
            elif action=="previous":self.page=max(0,self.page-1)
            elif action=="next":self.page=min(self.page_count-1,self.page+1)
            elif action in CATEGORY_ORDER:
                self.category=action;self.command_name=None;self.page=0;self.unknown=None
            self.refresh_items()
            # The compact banner was attached at initial send.
            # Keep those attachments; only component JSON changes on navigation.
            await interaction.response.edit_message(view=self,allowed_mentions=discord.AllowedMentions.none())

    async def interaction_check(self,interaction):
        if interaction.user.id==self.owner_id:return True
        await interaction.response.send_message("Open your own help guide with `/help`.",ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item,discord.ui.Select) or isinstance(item,discord.ui.Button) and item.url is None:
                item.disabled=True
        if self.message is not None:
            try:await self.message.edit(view=self)
            except discord.HTTPException:pass
