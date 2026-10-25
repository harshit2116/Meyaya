"""Per-server feature controls shared by commands and the owner dashboard."""
from bot.data.help_catalog import CATEGORY_ORDER, COMMANDS_BY_NAME
from bot.utils.command_aliases import ALIAS_COMMANDS
from discord.ext import commands

FEATURES = {
    "AI Chat": "Natural conversations and replies to mentions. Automatic replies have a separate switch.",
    **{name: f"Commands in {name}." for name in CATEGORY_ORDER if name not in {"Essentials", "Server Admin"}},
}


class FeatureDisabled(commands.CheckFailure):
    def __init__(self, feature):
        super().__init__(f"{feature} is disabled in this server's Meyaya settings.")


def command_feature(name):
    root = (name or "").split(" ", 1)[0].casefold()
    entry = COMMANDS_BY_NAME.get(ALIAS_COMMANDS.get(root, root))
    return entry.category if entry is not None and entry.category in FEATURES else None


def feature_states(disabled=()):
    return {name: name not in disabled for name in FEATURES}
