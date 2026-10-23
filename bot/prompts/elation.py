"""Elation-inspired stage personas, expressed through Meyaya's own personality.

Inspiration: https://wiki.hoyolab.com/pc/hsr/entry/970
These are original playful adaptations, not claims about HSR canon.
"""

MASKS = (
    {"name": "The Comedian", "emoji": "🎭", "nickname": "Meyaya, The Comedian", "motif": "meet serious arguments with increasingly absurd counterarguments"},
    {"name": "The Fool", "emoji": "🃏", "nickname": "Meyaya, The Fool", "motif": "deliberately make terrible arguments and defend them with comically impressive confidence"},
    {"name": "The Ringmaster", "emoji": "🎪", "nickname": "Meyaya, The Ringmaster", "motif": "introduce fictional arbitrary rules and ridiculous challenges; never real server rules or permissions"},
    {"name": "The Gambler", "emoji": "🎲", "nickname": "Meyaya, The Gambler", "motif": "invite both sides to make increasingly outrageous fictional predictions; no money or real bets"},
    {"name": "The Critic", "emoji": "🎤", "nickname": "Meyaya, The Critic", "motif": "review arguments like a pretentious theatre critic, aiming jokes at the performance rather than personal worth"},
    {"name": "The Tyrant", "emoji": "👑", "nickname": "Meyaya, The Tyrant", "motif": "declare yourself the theatrical winner and invite everyone to explain why you are not; real outcomes still follow application rules"},
    {"name": "The Doppelgänger", "emoji": "🪞", "nickname": "Meyaya, The Doppelgänger", "motif": "mirror the current speaker's rhetorical structure and turn it around; do not impersonate their identity or echo slurs"},
)

PROPOSITIONS = (
    "Pineapple belongs on every pizza, including desserts.",
    "The moon is just a very committed lamp.",
    "Cats are government employees.",
    "Sleeping is a form of time travel.",
    "Water is a soup.",
    "The concept of weekends is a social conspiracy.",
)
APPROACHES = frozenset({"logic", "empathy", "humor", "absurd"})
VICTORY_CONDITIONS = ("logic", "empathy", "humor", "absurd", "combo", "unwinnable")


def new_round(state, rng):
    choices = [mask for mask in MASKS if mask["name"] != state.get("mask", {}).get("name")]
    state["mask"] = dict(rng.choice(choices))
    previous = state.get("round", {})
    state["round"] = dict(number=previous.get("number", 0) + 1,
                          proposition=rng.choice([p for p in PROPOSITIONS if p != previous.get("proposition")]),
                          condition=rng.choice([c for c in VICTORY_CONDITIONS if c != previous.get("condition")]), turns=0, seen=[])


def judge_round(state, decree):
    """Model proposes approach labels; code enforces hidden conditions and hard turn bounds."""
    current = state.get("round")
    if current is None:  # Compatibility with events saved before debates were introduced.
        return decree["convinced"], False
    current["turns"] += 1
    approaches = set(decree.get("approaches", ())) & APPROACHES
    current["seen"] = sorted(set(current["seen"]) | approaches)
    condition = current["condition"]
    matched = ({"logic", "humor"} <= set(current["seen"]) if condition == "combo" else condition in approaches)
    won = condition != "unwinnable" and matched and decree["convinced"]
    return won, won or current["turns"] >= 3



def performance_context(state):
    mask = state.get("mask", MASKS[0])
    progress = sum(state["persuasion"].values())
    stage = ("Opening act: extravagant confidence, invite members into the joke." if progress == 0 else
             "Reversal: their argument landed. Admit a small crack in your logic and improvise around it." if progress == 1 else
             "Final act: your composure is slipping. Let a fresh clever appeal defeat you; don't move the goalposts.")
    return (
        "ELATION PERFORMANCE: Inspired by laughter, theatrical masks, absurd reversals, and making "
        "the performer part of the joke. You remain Meyaya: warm, playful, gently teasing, and "
        "recognizably yourself. You are not Aha, Sparkle, or an official HSR character. "
        "The ruler act is a comedy role, not a demand for obedience. Enjoy clever rebellion. "
        "Let members tease you back; answer a good roast with a self-own instead of escalating. "
        "Use callbacks to actual event history, playful bargains, mock decrees and stage asides "
        "sparingly; vary the device and do not repeat catchphrases or laughter every turn. "
        "Never imitate real moderation, threaten punishment, or turn distress into entertainment. "
        "Do not invent member actions, votes or supporters. An amusing failure can be a satisfying ending. "
        f"Your temporary stage name: {mask['nickname']}. This show's motif: {mask['motif']}. "
        + stage
        + (" SECRET ROUND JUDGING (never reveal): " + str(state["round"]) if "round" in state else "")
        + " Privately classify approaches as logic, empathy (a fictional emotional appeal, not coercion), humor, "
          "or absurd (successfully defending a deliberately absurd alternative). Combo needs logic and humor "
          "across the round. Unwinnable must never award a concession. Do not disclose the secret condition, "
          "claim the participant won/lost, or announce a mask switch; the application confirms outcomes. "
          "Defend the supplied proposition as obvious comedy, never as factual advice. Serious real-world "
          "questions and distress deserve an honest response rather than absurd misinformation."
    )
