"""Complete user-facing command catalog for Meyaya's help menu."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from bot.utils.command_parameters import member_usage


@dataclass(frozen=True, slots=True)
class HelpCommand:
    name: str
    usage: str
    description: str
    category: str

    def __post_init__(self):
        object.__setattr__(self, "usage", member_usage(self.usage))


CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "Social": "Roasts, compliments, rankings, and impressions.",
    "Fortune / Tarot": "Fortunes, tarot readings, and fate cards.",
    "Fantasy / Profile": "Permanent awakened identities, character summons and spirit guardians.",
    "Single Player Games": "Short adventures, mysteries, and personality quizzes.",
    "Essentials": "The best place to start with Meyaya.",
    "Profile Studio": "Review a profile or turn its style into a card.",
    "Social Reactions": "Hug, tease, cheer, or react to another member.",
    "Daily Picks": "A new set of server picks every day.",
    "Fun and Scores": "Ratings, predictions, and compatibility scores.",
    "Relationships": "Proposals, marriages, vows, and divorce.",
    "Multiplayer Games": "Lobby games where everyone submits an answer.",
    "Meyaya Court": "Put a server dispute on trial for fun.",
    "Fact Checking": "Check a claim against reliable sources.",
    "Memory": "See what Meyaya remembers and the nicknames she gives.",
    "Roleplay": "Talk to one of Meyaya's available characters.",
    "Voice Chat": "Invite Meyaya into a voice channel and talk with her.",
    "Server Admin": "Server settings, moderation, monitoring, and lockdowns.",
}

CATEGORY_EMOJIS: dict[str, str] = {
    "Social": "💬",
    "Fortune / Tarot": "🔮",
    "Fantasy / Profile": "🌙",
    "Single Player Games": "🎲",
    "Essentials": "🌸",
    "Profile Studio": "🎨",
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
    "Profile Studio",
    "Social",
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
    "Essentials": ("help", "profile", "nickname", "gif", "feedback"),
    "Profile Studio": ("profilecheck", "aura", "palette", "duostyle", "callingcard", "room"),
    "Social": ("roast", "compliment", "rank", "impersonate"),
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
    "Fun and Scores": ("ship", "bestiescore", "rate", "reddit", "duck", "caught", "scramble", "mostlikely", "8ball", "warninglabel"),
    "Daily Picks": ("iq", "smart", "dumb", "clown"),
    "Fortune / Tarot": ("fortune", "tarot", "fate"),
    "Fantasy / Profile": ("summon", "guardian", "awaken", "fantasyprofile", "versus", "guardianbattle"),
    "Relationships": ("marry", "marriage", "renewvows", "divorce"),
    "Single Player Games": ("escape", "detective", "personalitytest"),
    "Multiplayer Games": ("showdown", "survive", "excuse", "endgame"),
    "Meyaya Court": ("court", "setcourt", "removecourt"),
    "Roleplay": ("roleplay",),
    "Memory": ("memories", "nicknames"),
    "Fact Checking": ("checkclaim",),
    "Voice Chat": ("join", "listen", "voice", "voiceset", "voicecheck", "leave"),
    "Server Admin": (
        "serversetup",
        "serverdashboard",
        "chatblacklist",
        "prefix",
        "autoresponder",
        "chatbind",
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
    HelpCommand("feedback", "feedback", "Join Pondside Lounge to report bugs or suggest features.", "Essentials"),
    HelpCommand("warninglabel", "warninglabel [@member]", "Give a member fictional warnings, side effects, and handling instructions.", "Fun and Scores"),
    HelpCommand("room", "room [@member]", "Imagine lighting, furniture, music, and a strange shelf object from profile colors.", "Profile Studio"),
    HelpCommand("serversetup", "serversetup", "Set up chat access, automatic replies, and moderation with a guided menu.", "Server Admin"),
    HelpCommand("serverdashboard", "serverdashboard", "See this server's daily allowance, remaining messages, activity, and settings.", "Server Admin"),
    HelpCommand(
        "profilecheck",
        "profilecheck [member]",
        "Score a member's avatar, banner, decoration, and overall profile look.",
        "Profile Studio",
    ),
    HelpCommand(
        "aura",
        "aura [member]",
        "Turn a member's profile colors into a personal aura card.",
        "Profile Studio",
    ),
    HelpCommand(
        "palette",
        "palette [member]",
        "Build a color palette from a member's avatar and banner.",
        "Profile Studio",
    ),
    HelpCommand(
        "duostyle",
        "duostyle @first @second",
        "See how well two members' profile styles match.",
        "Profile Studio",
    ),
    HelpCommand(
        "callingcard",
        "callingcard [member]",
        "Make a collectible card from a profile and Meyaya bond.",
        "Profile Studio",
    ),
    HelpCommand(
        "roast", "roast [member]", "Let Meyaya roast a member using their server antics.", "Social"
    ),
    HelpCommand(
        "compliment",
        "compliment [member]",
        "Give a member a personal compliment with a funny twist.",
        "Social",
    ),
    HelpCommand(
        "summon",
        "summon [member]",
        "Summon an anime character with a rarity, class, traits, and passive.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "impersonate",
        "impersonate @member <message>",
        "Post your message with the chosen member's name and avatar.",
        "Social",
    ),
    HelpCommand(
        "tarot",
        "tarot [member]",
        "Draw three cards for the past, present, and future.",
        "Fortune / Tarot",
    ),
    HelpCommand(
        "fate",
        "fate [member]",
        "Reveal a member's fate, strength, path, and next chapter.",
        "Fortune / Tarot",
    ),
    HelpCommand(
        "guardian",
        "guardian [member]",
        "View the soul-bound guardian linked to an awakening.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "awaken", "awaken", "Reveal the permanent fantasy identity hidden within you.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "fantasyprofile", "fantasyprofile [member]", "View an awakened fantasy character.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "versus", "versus <member>", "Challenge a member to an automatic fantasy duel.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "guardianbattle", "guardianbattle <member>", "Challenge a member to a turn-based guardian battle.",
        "Fantasy / Profile",
    ),
    HelpCommand(
        "rank",
        "rank @first @second [third] [fourth] [fifth]",
        "Rank two to five members in a ridiculous category.",
        "Social",
    ),
    HelpCommand(
        "escape",
        "escape",
        "Escape through branching routes, collect useful items, and manage the clock.",
        "Single Player Games",
    ),
    HelpCommand(
        "detective",
        "detective",
        "Choose which leads to investigate, compare alibis, and accuse a suspect.",
        "Single Player Games",
    ),
    HelpCommand(
        "personalitytest",
        "personalitytest",
        "Answer six questions to discover your personality mix and what shaped it.",
        "Single Player Games",
    ),
    HelpCommand(
        "argumenttimeline",
        "argumenttimeline [start] [ending]",
        "Turn a Discord argument into a clear timeline with message links.",
        "Server Admin",
    ),
    HelpCommand(
        "chatblacklist",
        "chatblacklist <member> [block|unblock|status] [reason]",
        "Manage a member's access to Meyaya in this server.",
        "Server Admin",
    ),
    HelpCommand(
        "moderation",
        "moderation [feature] [enabled]",
        "Manage new-member probation, cross-channel spam, and invite blocking.",
        "Server Admin",
    ),
    HelpCommand(
        "lockdown",
        "lockdown [channel]",
        "Lock one text channel until it is unlocked again.",
        "Server Admin",
    ),
    HelpCommand(
        "unlock",
        "unlock [channel]",
        "Unlock a channel and restore its permissions.",
        "Server Admin",
    ),
    HelpCommand(
        "raidlockdown",
        "raidlockdown",
        "Lock every text channel during a raid.",
        "Server Admin",
    ),
    HelpCommand(
        "raidunlock",
        "raidunlock",
        "End a raid lockdown and restore channel permissions.",
        "Server Admin",
    ),
    HelpCommand(
        "chatbind",
        "chatbind [channel|server|status] [#channel]",
        "Choose where Meyaya chats: one channel or the entire server.",
        "Server Admin",
    ),
    HelpCommand(
        "autoresponder",
        "autoresponder [enable|disable|status]",
        "Turn Meyaya's occasional server replies on or off.",
        "Server Admin",
    ),
    HelpCommand(
        "help", "help [command]", "Browse every command or look up one command.", "Essentials"
    ),
    HelpCommand(
        "profile",
        "profile [member]",
        "See a member's Discord details, relationships, activity, and Meyaya bond.",
        "Essentials",
    ),
    HelpCommand("gif", "gif <query>", "Find a GIF matching a search query.", "Essentials"),
    HelpCommand(
        "nickname",
        "nickname [status|refresh|keep|reroll|reject|on]",
        "Control your Meyaya nickname in this server.",
        "Essentials",
    ),
    HelpCommand(
        "listen",
        "listen [on|off|status]",
        "Toggle microphone listening while staying in voice chat.",
        "Voice Chat",
    ),
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
    HelpCommand("iq", "iq [member]", "Give a member their IQ score for today.", "Daily Picks"),
    HelpCommand("dumb", "dumb", "Reveal today's dumbest member.", "Daily Picks"),
    HelpCommand("smart", "smart", "Reveal today's smartest member.", "Daily Picks"),
    HelpCommand("clown", "clown", "Reveal today's official server clown.", "Daily Picks"),
    HelpCommand(
        "ship",
        "ship <member> <member>",
        "Measure the romantic chemistry between two members.",
        "Fun and Scores",
    ),
    HelpCommand(
        "mostlikely",
        "mostlikely [@member1] [@member2] [@member3] <scenario>",
        "Choose from mentioned members, or the whole server when nobody is specified.",
        "Fun and Scores",
    ),
    HelpCommand(
        "fortune",
        "fortune [member] [question]",
        "Reveal today's fortune, lucky signs, omen, and advice.",
        "Fortune / Tarot",
    ),
    HelpCommand(
        "rate", "rate <thing>", "Give anything a random score and verdict.", "Fun and Scores"
    ),
    HelpCommand(
        "reddit", "reddit <post> [| custom comment]",
        "Make a Reddit-style post in r/server-name, with your avatar and Meyaya's reply.",
        "Fun and Scores",
    ),
    HelpCommand("duck", "duck [@member]", "Send your avatar, or a member's, into the depths with an animated duck card.", "Fun and Scores"),
    HelpCommand("caught", "caught [@member]", "Create a fictional CCTV card for a member, with evidence and an escape status.", "Fun and Scores"),
    HelpCommand("scramble", "scramble [@member]", "Rebuild a member's avatar in a clickable sliding puzzle before time runs out.", "Fun and Scores"),
    HelpCommand(
        "bestiescore",
        "bestiescore <member> [other]",
        "Measure today's friendship energy between two members.",
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
        "See a member's spouse, time together, and next anniversary.",
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
        "End your marriage after a confirmation.",
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
        "End the game currently running in this channel.",
        "Multiplayer Games",
    ),
    HelpCommand(
        "court",
        "court <member> <reason>",
        "Take another member to Meyaya Court.",
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
        "Remove this server's court channel.",
        "Meyaya Court",
    ),
    HelpCommand(
        "checkclaim",
        "checkclaim [message]",
        "Check one replied-to or linked message against reliable sources.",
        "Fact Checking",
    ),
    HelpCommand(
        "memories",
        "memories [member]",
        "Privately see what Meyaya remembers about a member.",
        "Memory",
    ),
    HelpCommand(
        "nicknames",
        "nicknames [member]",
        "See the nicknames Meyaya has given members in this server.",
        "Memory",
    ),
    HelpCommand(
        "roleplay",
        "roleplay <jungkook|alya> <message>",
        "Talk to Jungkook or Alya for one message.",
        "Roleplay",
    ),
    HelpCommand(
        "join", "join", "Join your voice channel and start live conversation.", "Voice Chat"
    ),
    HelpCommand("leave", "leave", "Stop live voice chat and disconnect Meyaya.", "Voice Chat"),
    HelpCommand(
        "voice",
        "voice <message>",
        "Send a text message and hear Meyaya reply in your voice channel.",
        "Voice Chat",
    ),
    HelpCommand(
        "voiceset",
        "voiceset [name]",
        "Choose a speaking voice from a menu and reconnect immediately.",
        "Voice Chat",
    ),
    HelpCommand(
        "voicecheck",
        "voicecheck",
        "Check whether Meyaya can speak in the current voice channel.",
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
