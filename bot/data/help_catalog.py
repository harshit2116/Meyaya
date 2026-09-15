"""Complete user-facing command catalog for Meyaya's help menu."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class HelpCommand:
    name: str
    usage: str
    description: str
    category: str


CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "Social / AI": "Personalized social dialogue.",
    "Fortune / Tarot": "Daily celestial image cards. No AI.",
    "Fantasy / Profile": "Collectible-style fantasy image cards. No AI.",
    "Single Player Games": "Quick logic-based solo games. No AI.",
    "Essentials": "Profiles, GIF search, and command help.",
    "Social Reactions": "Send expressive interactions to another member.",
    "Daily Picks": "Results that stay consistent for the current day.",
    "Fun and Scores": "Quick predictions, ratings, and compatibility results.",
    "Relationships": "Meyaya's marriage and relationship features.",
    "Multiplayer Games": "Anonymous lobby games judged after everyone submits.",
    "Meyaya Court": "Entertainment-only courtroom cases and verdicts.",
    "Fact Checking": "Source-backed analysis of selected Discord claims and arguments.",
    "Memory": "Inspect or remove your permanent Meyaya memories.",
    "Roleplay": "Chat with an approved character through a separate RP identity.",
    "Voice Chat": "Control and diagnose Meyaya's live voice connection.",
    "Server Admin": "Manage server settings and inspect Meyaya's service health.",
}

CATEGORY_EMOJIS: dict[str, str] = {
    "Social / AI": "💬",
    "Fortune / Tarot": "🔮",
    "Fantasy / Profile": "🌙",
    "Single Player Games": "🎲",
    "Essentials": "🌸",
    "Social Reactions": "🫶",
    "Daily Picks": "📅",
    "Fun and Scores": "✨",
    "Relationships": "💞",
    "Multiplayer Games": "🎮",
    "Meyaya Court": "⚖️",
    "Fact Checking": "🔎",
    "Memory": "🧠",
    "Roleplay": "🎭",
    "Voice Chat": "🎙️",
    "Server Admin": "⚙️",
}

# User-facing navigation order. Keep everyday commands first and operational tools last.
CATEGORY_ORDER: tuple[str, ...] = (
    "Essentials",
    "Social / AI",
    "Social Reactions",
    "Fun and Scores",
    "Daily Picks",
    "Fortune / Tarot",
    "Fantasy / Profile",
    "Relationships",
    "Single Player Games",
    "Multiplayer Games",
    "Meyaya Court",
    "Roleplay",
    "Memory",
    "Fact Checking",
    "Voice Chat",
    "Server Admin",
)

COMMAND_ORDER: dict[str, tuple[str, ...]] = {
    "Essentials": ("help", "profile", "gif"),
    "Social / AI": ("roast", "compliment", "rank", "legacy", "impersonate"),
    "Social Reactions": (
        "hug",
        "pat",
        "headpat",
        "cuddle",
        "kiss",
        "handhold",
        "highfive",
        "wave",
        "cheer",
        "smile",
        "laugh",
        "dance",
        "blush",
        "poke",
        "boop",
        "tickle",
        "bite",
        "slap",
        "bonk",
        "facepalm",
        "cry",
    ),
    "Fun and Scores": ("ship", "bestiescore", "rate", "mostlikely", "8ball"),
    "Daily Picks": ("iq", "smart", "dumb", "clown"),
    "Fortune / Tarot": ("fortune", "tarot", "fate"),
    "Fantasy / Profile": ("summon", "guardian"),
    "Relationships": ("marry", "marriage", "renewvows", "divorce"),
    "Single Player Games": ("escape", "detective", "personalitytest"),
    "Multiplayer Games": ("showdown", "survive", "excuse", "endgame"),
    "Meyaya Court": ("court", "setcourt", "removecourt"),
    "Roleplay": ("roleplay",),
    "Memory": ("memories",),
    "Fact Checking": ("checkclaim",),
    "Voice Chat": ("join", "voice", "voicecheck", "leave"),
    "Server Admin": (
        "prefix",
        "autoresponder",
        "monitor_add",
        "monitor_list",
        "monitor_remove",
        "moderation",
        "argumenttimeline",
        "lockdown",
        "unlock",
        "raidlockdown",
        "raidunlock",
    ),
}


COMMANDS: tuple[HelpCommand, ...] = (
    HelpCommand("roast", "roast [member]", "A gentle context-aware roast.", "Social / AI"),
    HelpCommand("compliment", "compliment [member]", "A warm or funny compliment.", "Social / AI"),
    HelpCommand("legacy", "legacy [member]", "Your fictional server legacy.", "Social / AI"),
    HelpCommand(
        "summon",
        "summon [member]",
        "Fantasy class, rarity and passive ability.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "impersonate",
        "impersonate @member <message>",
        "Send your exact text with their name/avatar, then delete your command. No AI.",
        "Social / AI",
    ),
    HelpCommand(
        "tarot", "tarot [member]", "A three-card entertainment reading.", "Fortune / Tarot"
    ),
    HelpCommand("fate", "fate [member]", "Your fantasy fate archetype.", "Fortune / Tarot"),
    HelpCommand(
        "guardian", "guardian [member]", "Your spirit guardian and power.", "Fantasy / Profile"
    ),
    HelpCommand(
        "rank",
        "rank @first @second [third] [fourth] [fifth]",
        "Rank three members in a ridiculous category.",
        "Social / AI",
    ),
    HelpCommand("escape", "escape", "A local branching escape adventure.", "Single Player Games"),
    HelpCommand(
        "detective", "detective", "Clues, three suspects and one accusation.", "Single Player Games"
    ),
    HelpCommand(
        "personalitytest",
        "personalitytest",
        "Six funny questions with a local scored result.",
        "Single Player Games",
    ),
    HelpCommand(
        "argumenttimeline",
        "argumenttimeline [start] [ending]",
        "Moderator: review an argument in order with evidence links.",
        "Server Admin",
    ),
    HelpCommand(
        "moderation",
        "moderation [feature] [enabled]",
        "Configure 3-day probation, cross-channel spam and external invite rules.",
        "Server Admin",
    ),
    HelpCommand(
        "lockdown",
        "lockdown [channel]",
        "Lock one text channel and save its original permissions.",
        "Server Admin",
    ),
    HelpCommand("unlock", "unlock [channel]", "Restore a single-channel lockdown.", "Server Admin"),
    HelpCommand(
        "raidlockdown",
        "raidlockdown",
        "Lock all server text channels, including new ones during the raid.",
        "Server Admin",
    ),
    HelpCommand(
        "raidunlock",
        "raidunlock",
        "Restore raid lockdowns while keeping individual locks.",
        "Server Admin",
    ),
    HelpCommand(
        "autoresponder",
        "autoresponder [enable|disable|status]",
        "Manage occasional automatic replies that adapt to server activity.",
        "Server Admin",
    ),
    HelpCommand(
        "help", "help [command]", "Browse every command or inspect one command.", "Essentials"
    ),
    HelpCommand(
        "profile",
        "profile [member]",
        "Show Discord, social, marriage, mood, and Meyaya bond details.",
        "Essentials",
    ),
    HelpCommand("gif", "gif <query>", "Find a GIF matching a search query.", "Essentials"),
    HelpCommand("hug", "hug [member]", "Give someone a warm hug.", "Social Reactions"),
    HelpCommand("kiss", "kiss [member]", "Give someone a playful kiss.", "Social Reactions"),
    HelpCommand("pat", "pat [member]", "Give someone a comforting pat.", "Social Reactions"),
    HelpCommand("cuddle", "cuddle [member]", "Share a cozy cuddle.", "Social Reactions"),
    HelpCommand(
        "headpat", "headpat [member]", "Give someone a gentle headpat.", "Social Reactions"
    ),
    HelpCommand("boop", "boop [member]", "Boop someone on the nose.", "Social Reactions"),
    HelpCommand("poke", "poke [member]", "Poke someone for attention.", "Social Reactions"),
    HelpCommand("bite", "bite [member]", "Give someone a playful bite.", "Social Reactions"),
    HelpCommand("slap", "slap [member]", "Deliver a theatrical slap.", "Social Reactions"),
    HelpCommand(
        "bonk", "bonk [member]", "Bonk someone for excessive silliness.", "Social Reactions"
    ),
    HelpCommand("tickle", "tickle [member]", "Launch a tickle attack.", "Social Reactions"),
    HelpCommand("highfive", "highfive [member]", "Give someone a high five.", "Social Reactions"),
    HelpCommand("handhold", "handhold [member]", "Hold hands with someone.", "Social Reactions"),
    HelpCommand("wave", "wave [member]", "Send someone a cheerful wave.", "Social Reactions"),
    HelpCommand("dance", "dance [member]", "Start a tiny dance party.", "Social Reactions"),
    HelpCommand("laugh", "laugh [member]", "Share a laugh with someone.", "Social Reactions"),
    HelpCommand("cry", "cry [member]", "Have a dramatic cry near someone.", "Social Reactions"),
    HelpCommand("smile", "smile [member]", "Give someone a warm smile.", "Social Reactions"),
    HelpCommand("blush", "blush [member]", "Leave someone blushing.", "Social Reactions"),
    HelpCommand("cheer", "cheer [member]", "Hype someone up with a cheer.", "Social Reactions"),
    HelpCommand(
        "facepalm",
        "facepalm [member]",
        "React to someone's antics with a facepalm.",
        "Social Reactions",
    ),
    HelpCommand("iq", "iq [member]", "Show a member's stable daily IQ score.", "Daily Picks"),
    HelpCommand("dumb", "dumb", "Reveal today's dumbest eligible member.", "Daily Picks"),
    HelpCommand("smart", "smart", "Reveal today's smartest eligible member.", "Daily Picks"),
    HelpCommand("clown", "clown", "Reveal today's official server clown.", "Daily Picks"),
    HelpCommand(
        "ship",
        "ship <member> <member>",
        "Roll a fresh romantic compatibility score.",
        "Fun and Scores",
    ),
    HelpCommand(
        "mostlikely",
        "mostlikely <scenario>",
        "Choose who best matches a funny scenario.",
        "Fun and Scores",
    ),
    HelpCommand(
        "fortune",
        "fortune [member] [question]",
        "Reveal your stable daily fortune and lucky signs.",
        "Fortune / Tarot",
    ),
    HelpCommand(
        "rate", "rate <thing>", "Give anything a random score and verdict.", "Fun and Scores"
    ),
    HelpCommand(
        "bestiescore",
        "bestiescore <member> [other]",
        "Show today's friendship score for two members.",
        "Fun and Scores",
    ),
    HelpCommand(
        "8ball",
        "8ball <question>",
        "Ask Meyaya's magic 8-ball a yes-or-no question.",
        "Fun and Scores",
    ),
    HelpCommand(
        "marry",
        "marry <member>",
        "Send a marriage proposal that requires consent.",
        "Relationships",
    ),
    HelpCommand(
        "marriage",
        "marriage [member]",
        "Show a marriage, time together, and next anniversary.",
        "Relationships",
    ),
    HelpCommand(
        "renewvows",
        "renewvows <vow>",
        "Write a new public vow to your current spouse.",
        "Relationships",
    ),
    HelpCommand(
        "divorce",
        "divorce",
        "Open a confirmation before ending your marriage.",
        "Relationships",
    ),
    HelpCommand(
        "showdown",
        "showdown",
        "Start an anonymous comparison showdown for 2-8 players.",
        "Multiplayer Games",
    ),
    HelpCommand(
        "excuse", "excuse", "Start an anonymous excuse battle for 2-8 players.", "Multiplayer Games"
    ),
    HelpCommand(
        "survive",
        "survive",
        "Start an anonymous survival challenge for 2-8 players.",
        "Multiplayer Games",
    ),
    HelpCommand(
        "endgame",
        "endgame",
        "End the active social game in this channel as its host.",
        "Multiplayer Games",
    ),
    HelpCommand(
        "court",
        "court <member> <reason>",
        "File an entertainment-only case in the court channel.",
        "Meyaya Court",
    ),
    HelpCommand(
        "setcourt",
        "setcourt",
        "Set the current channel as this server's court channel.",
        "Meyaya Court",
    ),
    HelpCommand(
        "removecourt",
        "removecourt",
        "Disable the configured court channel for this server.",
        "Meyaya Court",
    ),
    HelpCommand(
        "checkclaim",
        "checkclaim [message]",
        "Fact-check only one replied-to or linked Discord message.",
        "Fact Checking",
    ),
    HelpCommand(
        "memories",
        "memories [member]",
        "Privately inspect categorized permanent memories.",
        "Memory",
    ),
    HelpCommand(
        "roleplay",
        "roleplay <jungkook|alya> <message>",
        "Get a one-message response from Jungkook RP or Alya RP.",
        "Roleplay",
    ),
    HelpCommand(
        "join", "join", "Join your voice channel and start live conversation.", "Voice Chat"
    ),
    HelpCommand("leave", "leave", "Stop live voice chat and disconnect Meyaya.", "Voice Chat"),
    HelpCommand(
        "voice", "voice [name]", "Show or change the voice used for new sessions.", "Voice Chat"
    ),
    HelpCommand(
        "voicecheck",
        "voicecheck",
        "Test Gemini audio playback in the active voice channel.",
        "Voice Chat",
    ),
    HelpCommand(
        "monitor_add",
        "monitor_add <channel>",
        "Enable three-strike English-only warnings in a channel.",
        "Server Admin",
    ),
    HelpCommand(
        "monitor_remove",
        "monitor_remove <channel>",
        "Disable English-only warnings in a channel.",
        "Server Admin",
    ),
    HelpCommand("monitor_list", "monitor_list", "List every monitored channel.", "Server Admin"),
    HelpCommand(
        "prefix",
        "prefix [new_prefix|reset]",
        "Show or change this server's written command prefix.",
        "Server Admin",
    ),
)

COMMANDS_BY_NAME: dict[str, HelpCommand] = {command.name: command for command in COMMANDS}


@lru_cache(maxsize=None)
def commands_in_category(category: str) -> tuple[HelpCommand, ...]:
    """Return one category in its intentional user-facing order."""

    preferred = {name: index for index, name in enumerate(COMMAND_ORDER.get(category, ()))}
    return tuple(
        sorted(
            (item for item in COMMANDS if item.category == category),
            key=lambda item: (preferred.get(item.name, len(preferred)), item.name),
        )
    )
