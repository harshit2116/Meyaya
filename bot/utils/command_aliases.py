"""Stable, explicit shortcuts for written commands; slash names stay canonical."""

SHORT_COMMANDS = {
    "feedback": "fb", "serversetup": "ss", "serverdashboard": "sd",
    "profilecheck": "pc", "aura": "au", "duostyle": "ds", "callingcard": "cc",
    "roast": "r", "compliment": "cm", "summon": "su", "impersonate": "im",
    "tarot": "tr", "fate": "ft", "guardian": "gd", "awaken": "aw",
    "fantasyprofile": "fp", "rebirth": "rb", "dungeon": "dg", "versus": "vs",
    "bossfight": "bf", "rank": "rk", "escape": "es", "detective": "dt",
    "personalitytest": "pt", "argumenttimeline": "at", "chatblacklist": "cbl",
    "moderation": "mod", "lockdown": "ld", "unlock": "ul",
    "raidlockdown": "rld", "raidunlock": "ru", "chatbind": "cb",
    "autoresponder": "ar", "help": "h", "profile": "p", "gif": "g",
    "nickname": "nk", "listen": "ls", "hug": "hu", "kiss": "k", "pat": "pa",
    "cuddle": "cu", "headpat": "hp", "boop": "bo", "poke": "pk", "bite": "bi",
    "slap": "sl", "bonk": "bk", "tickle": "tk", "highfive": "hf",
    "handhold": "hh", "wave": "w", "dance": "da", "laugh": "la", "cry": "cy",
    "smile": "sm", "blush": "bl", "cheer": "ch", "facepalm": "fpl",
    "iq": "i", "dumb": "dm", "smart": "st", "clown": "cl", "ship": "sh",
    "mostlikely": "ml", "fortune": "f", "rate": "rt", "reddit": "rd",
    "duck": "dk", "scramble": "sc", "bestiescore": "bs", "8ball": "8b",
    "marry": "my", "marriage": "mg", "renewvows": "rv", "divorce": "dv",
    "showdown": "sw", "excuse": "ex", "survive": "sv", "endgame": "eg",
    "court": "ct", "setcourt": "sct", "removecourt": "rc", "checkclaim": "ck",
    "memories": "mem", "nicknames": "nks", "roleplay": "rp", "join": "j",
    "leave": "l", "voice": "v", "voiceset": "vset", "voicecheck": "vck",
    "monitor_add": "ma", "monitor_remove": "mr", "monitor_list": "mli",
    "prefix": "px",
}

ALIAS_COMMANDS = {alias: name for name, alias in SHORT_COMMANDS.items()}


def install_command_aliases(bot):
    """Register aliases on the same command, sharing checks and cooldowns."""
    additions = []
    for name, alias in SHORT_COMMANDS.items():
        command = bot.get_command(name)
        if command is None:
            continue
        existing = bot.get_command(alias)
        if existing is command:
            continue
        if existing is not None:
            raise ValueError(f"Command shortcut {alias!r} for {name!r} is already in use")
        additions.append((command, alias))
    # Check every collision before touching the router.
    for command, alias in additions:
        bot.remove_command(command.name)
        command.aliases = [*command.aliases, alias]
        bot.add_command(command)


def command_aliases(name, bot=None):
    if bot is not None:
        registered = bot.get_command(name)
        return tuple(getattr(registered, "aliases", ()))
    alias = SHORT_COMMANDS.get(name)
    return (alias,) if alias else ()
