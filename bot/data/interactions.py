"""Definitions for social interaction commands."""

from __future__ import annotations

from bot.services.interactions import InteractionDefinition


INTERACTION_DEFINITIONS: tuple[InteractionDefinition, ...] = (
    InteractionDefinition(
        name="hug",
        emoji="🫂",
        color=0xFFB3C7,
        responses=(
            "{actor} gave {target} the biggest hug imaginable.",
            "{actor} wrapped {target} in a warm hug.",
            "{actor} couldn't resist giving {target} a hug.",
        ),
        gif_urls=(),
        gif_query="anime hug",
        button_label="Hug Back",
        back_command="hug",
    ),
    InteractionDefinition("kiss", "💋", 0xFF6B9A, (
        "{actor} stole a sweet kiss from {target}.",
        "{actor} kissed {target} with a dramatic flourish.",
        "{actor} leaned in and kissed {target}.",
    ), (), "anime kiss", "Kiss Back", "kiss"),
    InteractionDefinition("pat", "🤍", 0xD0E8FF, (
        "{actor} gently patted {target} on the head.",
        "{actor} gave {target} a comforting pat.",
        "{actor} offered {target} a soft pat.",
    ), (), "head pat", "Pat Back", "pat"),
    InteractionDefinition("cuddle", "🧸", 0xF9C74F, (
        "{actor} cuddled up with {target}.",
        "{actor} pulled {target} into a cozy cuddle.",
        "{actor} made {target} feel extra safe with a cuddle.",
    ), (), "anime cuddle", "Cuddle Back", "cuddle"),
    InteractionDefinition("headpat", "✨", 0x9DDE8F, (
        "{actor} gave {target} a delightful headpat.",
        "{actor} softly head-patted {target}.",
        "{actor} couldn't resist a gentle headpat for {target}.",
    ), (), "cute headpat", None, None),
    InteractionDefinition("boop", "🐾", 0xA8DADC, (
        "{actor} booped {target} right on the nose.",
        "{actor} delivered a tiny boop to {target}.",
        "{actor} gave {target} a playful boop.",
    ), (), "boop anime", None, None),
    InteractionDefinition("poke", "👉", 0xFFD166, (
        "{actor} poked {target} to get their attention.",
        "{actor} gave {target} a cheeky poke.",
        "{actor} lightly poked {target}.",
    ), (), "poke anime", None, None),
    InteractionDefinition("bite", "🦈", 0xE76F51, (
        "{actor} playfully bit {target}.",
        "{actor} gave {target} a tiny nibble.",
        "{actor} went full goblin mode on {target}.",
    ), (), "anime bite", None, None),
    InteractionDefinition("slap", "👋", 0xEF476F, (
        "{actor} slapped {target} with theatrical energy.",
        "{actor} delivered a dramatic slap to {target}.",
        "{actor} gave {target} a chaotic slap.",
    ), (), "anime slap", None, None),
    InteractionDefinition("bonk", "🔨", 0xB08968, (
        "{actor} bonked {target} for being too silly.",
        "{actor} gave {target} a bonk of correction.",
        "{actor} bonked {target} into the vibe check zone.",
    ), (), "bonk meme", None, None),
    InteractionDefinition("tickle", "🪶", 0xF4D35E, (
        "{actor} tickled {target} until they laughed.",
        "{actor} launched a sneaky tickle attack on {target}.",
        "{actor} gave {target} a chaotic tickle.",
    ), (), "tickle anime", None, None),
    InteractionDefinition("highfive", "🙌", 0x2A9D8F, (
        "{actor} high-fived {target} with perfect timing.",
        "{actor} and {target} landed a crisp high five.",
        "{actor} slapped palms with {target}.",
    ), (), "high five anime", "High Five Back", "highfive"),
    InteractionDefinition("handhold", "🤝", 0x5E60CE, (
        "{actor} took {target}'s hand.",
        "{actor} held hands with {target}.",
        "{actor} shared a quiet handhold with {target}.",
    ), (), "hand hold anime", "Handhold Back", "handhold"),
    InteractionDefinition("wave", "👋", 0x8ECAE6, (
        "{actor} waved at {target}.",
        "{actor} sent {target} a cheerful wave.",
        "{actor} gave {target} a friendly wave.",
    ), (), "wave anime", None, None),
    InteractionDefinition("dance", "💃", 0xFFAFCC, (
        "{actor} started dancing with {target}.",
        "{actor} spun into a dance with {target}.",
        "{actor} and {target} began a tiny dance party.",
    ), (), "dance anime", None, None),
    InteractionDefinition("laugh", "😂", 0xF8961E, (
        "{actor} laughed with {target}.",
        "{actor} burst into laughter around {target}.",
        "{actor} couldn't stop laughing with {target}.",
    ), (), "laugh anime", None, None),
    InteractionDefinition("cry", "😭", 0x4D96FF, (
        "{actor} cried into {target}'s shoulder.",
        "{actor} had a tiny dramatic cry with {target} nearby.",
        "{actor} shed some emotional tears around {target}.",
    ), (), "cry anime", None, None),
    InteractionDefinition("smile", "😊", 0xFFD6A5, (
        "{actor} smiled warmly at {target}.",
        "{actor} gave {target} a bright smile.",
        "{actor} made {target} smile back.",
    ), (), "smile anime", None, None),
    InteractionDefinition("blush", "🌸", 0xF4A261, (
        "{actor} made {target} blush.",
        "{actor} caused a shy blush from {target}.",
        "{actor} left {target} blushing softly.",
    ), (), "blush anime", None, None),
    InteractionDefinition("cheer", "🎉", 0x00B4D8, (
        "{actor} cheered loudly for {target}.",
        "{actor} hyped up {target} with a big cheer.",
        "{actor} gave {target} a celebration-worthy cheer.",
    ), (), "cheer anime", None, None),
    InteractionDefinition("facepalm", "🤦", 0x577590, (
        "{actor} facepalmed at {target}'s antics.",
        "{actor} let out a dramatic facepalm near {target}.",
        "{actor} had a very expressive facepalm moment with {target}.",
    ), (), "facepalm meme", None, None),
)
