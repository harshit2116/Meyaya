"""Small, catalog-backed command context; no model calls or message-history scans."""

from __future__ import annotations

import re
from typing import Any

from bot.data.help_catalog import CATEGORY_ORDER, COMMANDS, HelpCommand

PROFILE_HELP = (
    "When someone asks to improve their profile, avatar, pfp, banner, colors or decorations, "
    "they may mean their Discord appearance, not their Meyaya relationship profile. "
    "Answer their actual design question helpfully; suggest uwu profilecheck (/profilecheck) for a "
    "visual review (with a 'Meyaya's Opinion' button for AI visual feedback) and uwu aura (/aura) "
    "for a profile-inspired aura card. /profile is relationship/activity information, not an aesthetic review. "
    "Profilecheck reviews API-visible assets only: avatar, banner or available solid banner color, "
    "and avatar decoration. Its scores are subjective heuristics, not objective quality. "
    "Black/white/solid backgrounds can be intentional; do not demand paid decorations or Nitro. "
    "Full-profile effects and two-color panel themes aren't exposed by Discord's bot API. "
    "Animated assets have a short preview but scores use still frames. "
    "Never invent their colors, score, appearance, or claim you inspected an image. "
    "Use an explicitly supplied review if available, matching its target ID; otherwise offer "
    "general guidance and ask them to run uwu profilecheck (/profilecheck) or describe the look they want. "
    "A recent review is historical, not proof the profile hasn't changed."
)

_TOPIC_COMMANDS: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (
        frozenset({"profile", "profilecheck", "pfp", "avatar", "banner", "decoration", "decorations", "aesthetic", "palette", "card"}),
        ("profilecheck", "aura", "duostyle", "callingcard", "profile"),
    ),
    (
        frozenset({"sing", "song", "lyrics", "music", "beats", "bgm", "lofi", "voice", "vc", "tts", "speak", "say", "voiceclip", "audio", "talk"}),
        ("sing", "voiceclip", "bgm", "join", "listen", "voice", "voiceset", "leave"),
    ),
    (
        frozenset({"fact", "facts", "factcheck", "check", "claim", "verify", "fake", "true", "false", "argument", "debate", "timeline", "screenshot"}),
        ("checkclaim", "argumenttimeline"),
    ),
    (
        frozenset({"game", "games", "play", "dungeon", "boss", "bossfight", "duel", "fight", "versus", "rpg", "fantasy", "summon", "awaken", "guardian", "escape", "detective", "scramble", "showdown", "survive", "elation"}),
        ("dungeon", "bossfight", "versus", "awaken", "summon", "elation", "showdown", "survive", "escape", "detective"),
    ),
    (
        frozenset({"marry", "marriage", "wedding", "divorce", "vows", "ship", "bestie", "couple", "love", "compatibility"}),
        ("marry", "marriage", "renewvows", "divorce", "ship", "bestiescore"),
    ),
    (
        frozenset({"court", "trial", "judge", "sue", "guilty", "lawsuit"}),
        ("court", "setcourt", "removecourt"),
    ),
    (
        frozenset({"hug", "kiss", "pat", "slap", "bonk", "boop", "poke", "cuddle", "headpat", "gif", "react", "reaction", "reactions", "act"}),
        ("act", "hug", "kiss", "pat", "slap", "cuddle", "poke", "gif"),
    ),
    (
        frozenset({"memory", "memories", "remember", "forget", "nickname", "nicknames", "roleplay", "rp"}),
        ("memories", "nicknames", "nickname", "roleplay"),
    ),
    (
        frozenset({"fortune", "tarot", "fate", "8ball", "iq", "smart", "dumb", "clown", "roast", "compliment", "rank", "impersonate", "reddit", "duck", "rate", "mostlikely", "disco", "solosamba", "solo", "ssm", "party", "samba", "dance"}),
        ("disco", "solosamba", "fortune", "tarot", "fate", "8ball", "roast", "compliment", "rate", "reddit", "iq"),
    ),
    (
        frozenset({"mod", "moderation", "lockdown", "unlock", "raid", "spam", "setup", "serversetup", "prefix", "autoresponder", "blacklist", "chatbind", "admin", "settings", "dashboard"}),
        ("serversetup", "serverdashboard", "moderation", "prefix", "chatbind", "autoresponder", "chatblacklist"),
    ),
    (
        frozenset({"help", "command", "commands", "feature", "features", "guide", "vote", "bonus", "allowance", "quota", "feedback"}),
        ("help", "guide", "vote", "feedback", "serverdashboard"),
    ),
)

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "your", "have", "what",
        "when", "where", "how", "can", "you", "does", "meyaya", "about", "into", "some",
    }
)


def _format_written(prefix: str, usage: str) -> str:
    clean = (prefix or "uwu").strip() or "uwu"
    return f"{clean} {usage}" if clean[-1].isalnum() else f"{clean}{usage}"


def _group_catalog(catalog: list[HelpCommand], prefix: str) -> str:
    by_category: dict[str, list[str]] = {}
    for item in catalog:
        by_category.setdefault(item.category, []).append(_format_written(prefix, item.name))
    parts: list[str] = []
    for category in CATEGORY_ORDER:
        names = by_category.pop(category, None)
        if names:
            parts.append(f"{category}: {', '.join(names)}")
    for category, names in by_category.items():
        parts.append(f"{category}: {', '.join(names)}")
    return " | ".join(parts)


def command_knowledge(bot: Any, query: str, *, prefix: str = "uwu") -> list[str]:
    catalog = [item for item in COMMANDS if bot.get_command(item.name) or bot.tree.get_command(item.name)]
    by_name = {item.name: item for item in catalog}
    words = set(re.findall(r"[a-z0-9]+", (query or "").casefold()))
    profile_question = bool(
        words & {"profile", "profilecheck", "pfp", "avatar", "banner", "decoration", "decorations", "aesthetic", "palette"}
    )

    matched_names: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        if name in by_name and name not in seen:
            seen.add(name)
            matched_names.append(name)

    for item in catalog:
        if item.name in words:
            _add(item.name)
    for triggers, names in _TOPIC_COMMANDS:
        if words & triggers:
            for name in names:
                _add(name)
    significant = {w for w in words if len(w) >= 4 and w not in _STOPWORDS}
    if significant and len(matched_names) < 8:
        for item in catalog:
            desc_words = set(re.findall(r"[a-z0-9]+", item.description.casefold()))
            if significant & desc_words:
                _add(item.name)

    clean_prefix = (prefix or "uwu").strip() or "uwu"
    lines = [
        f"Meyaya's complete public command catalog (written prefix '{clean_prefix}', not permission to execute): "
        + _group_catalog(catalog, clean_prefix),
        f"When a member asks what you can do or asks for a feature/command, suggest the exact real "
        f"command(s) in written prefix format (for example: '{_format_written(clean_prefix, 'sing <topic>')}', "
        f"'{_format_written(clean_prefix, 'profilecheck')}', '{_format_written(clean_prefix, 'checkclaim')}'). "
        f"Recommend real commands from this catalog only. Use {_format_written(clean_prefix, 'help <name>')} "
        "(or /help command:<name>) for exact options, permissions, and cooldowns. "
        "Knowing a command does not execute it; never claim you ran it without a confirmed tool result. "
        "Do not expose hidden owner commands. Respect server access rules and limits.",
    ]
    for name in matched_names[:10]:
        item = by_name[name]
        written = _format_written(clean_prefix, item.usage)
        has_slash = bot.tree.get_command(item.name) is not None
        slash_note = f" (or /{item.name})" if has_slash else ""
        lines.append(f"{written}{slash_note}: {item.description}")
    if profile_question:
        lines.append(PROFILE_HELP)
    return lines
