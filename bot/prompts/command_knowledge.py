"""Small, catalog-backed command context; no model calls or message-history scans."""

import re
from bot.data.help_catalog import COMMANDS

PROFILE_HELP = (
    "When someone asks to improve their profile, avatar, pfp, banner, colors or decorations, "
    "they may mean their Discord appearance, not their Meyaya relationship profile. "
    "Answer their actual design question helpfully; suggest /profilecheck for a visual review "
    "and /aura for a profile-inspired aura card. /profile is relationship/activity information, not an aesthetic review. "
    "Profilecheck reviews API-visible assets only: avatar, banner or available solid banner color, "
    "and avatar decoration. Its scores are subjective heuristics, not objective quality. "
    "Black/white/solid backgrounds can be intentional; do not demand paid decorations or Nitro. "
    "Full-profile effects and two-color panel themes aren't exposed by Discord's bot API. "
    "Animated assets have a short preview but scores use still frames. "
    "Never invent their colors, score, appearance, or claim you inspected an image. "
    "Use an explicitly supplied review if available, matching its target ID; otherwise offer "
    "general guidance and ask them to run /profilecheck or describe the look they want. "
    "A recent review is historical, not proof the profile hasn't changed."
)


def command_knowledge(bot, query):
    catalog = [item for item in COMMANDS if bot.get_command(item.name) or bot.tree.get_command(item.name)]
    words = set(re.findall(r"[a-z0-9]+", query.casefold()))
    profile_question = bool(words & {"profile", "profilecheck", "pfp", "avatar", "banner", "decoration", "decorations", "aesthetic", "palette"})
    relevant = [item for item in catalog if item.name in words or (
        profile_question and item.name in {"profilecheck", "aura", "duostyle", "profile"})]
    lines = [
        "Meyaya's available public command names (not permission to execute): " + ", ".join(item.name for item in catalog),
        "Recommend real commands only. Use /help command:<name> for exact options, permissions and cooldowns. "
        "Knowing a command does not execute it; never claim you ran it without a confirmed tool result. "
        "Do not expose hidden owner commands. Respect server access rules and limits.",
        "Slash commands use /name. Use the supplied server prefix for written commands, not an assumed prefix.",
    ]
    lines.extend(f"/{item.usage}: {item.description}" for item in relevant[:8])
    if profile_question:
        lines.append(PROFILE_HELP)
    return lines
