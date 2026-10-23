"""Authored clash dialogue selected from combat state, without RNG or mutations."""

REACTIONS = {
    "Prism Cascade": (
        ("Meyaya", "Five little lights. Try not to blink.", "Veyra", "I only need the space between them."),
        ("Meyaya", "You missed a petal.", "Veyra", "Then I will erase the garden."),
    ),
    "World Sever": (
        ("Veyra", "Even your protection has an ending.", "Meyaya", "Good thing I brought a beginning."),
        ("Veyra", "Another seam. Another world undone.", "Meyaya", "And another thing for me to mend."),
    ),
    "Genesis Crown": (
        ("Meyaya", "A crown is a promise. Watch me keep it.", "Veyra", "Promises break more quietly than glass."),
        ("Meyaya", "Everbloom, remember what stood here.", "Veyra", "Memory is the next thing I take."),
    ),
    "Abyss Dominion": (
        ("Veyra", "There is nowhere left for your light to land.", "Meyaya", "Then I will teach the dark to bloom."),
        ("Veyra", "Your sky belongs to the abyss.", "Meyaya", "You can borrow it. I want it back."),
    ),
    "Origin Protocol · The First Dawn": (
        ("Meyaya", "You forgot who writes the first line.", "Veyra", "I remember. That is why I came."),
        ("Meyaya", "One more dawn. I am not done with you.", "Veyra", "Then let this be the last."),
    ),
    "Enemy of All · Absolute Erasure": (
        ("Veyra", "No author. No ending. Only absence.", "Meyaya", "You will have to erase me saying no."),
        ("Veyra", "Even your beginning will disappear.", "Meyaya", "Not while someone still needs it."),
    ),
}

# Later releases have their own exchanges, rather than repeating the opening taunt.
REACTIONS["Prism Cascade"] += (
    ("Meyaya", "Left, right, above. Oh, you thought I was done counting?", "Veyra", "I was counting the openings you left behind."),
    ("Meyaya", "That one was for the sky you broke.", "Veyra", "Send its replacement. I will break that too."),
)
REACTIONS["World Sever"] += (
    ("Veyra", "Your shield remembers being whole. How unfortunate.", "Meyaya", "My shield has a better recovery arc than you."),
    ("Veyra", "Stay still. This ending will be cleaner.", "Meyaya", "Terrible invitation. Zero stars."),
)
REACTIONS["Genesis Crown"] += (
    ("Meyaya", "You keep calling it rubble. I keep finding building material.", "Veyra", "Then let me give you more."),
    ("Meyaya", "Do you know how hard it is to accessorise during an apocalypse?", "Veyra", "I can remove the crown for you."),
)
REACTIONS["Abyss Dominion"] += (
    ("Veyra", "No sky. No ground. Tell me where you intend to stand.", "Meyaya", "In your way. Same as always."),
    ("Veyra", "Even your stars are learning to kneel.", "Meyaya", "They are getting a better angle."),
)
REACTIONS["Origin Protocol · The First Dawn"] += (
    ("Meyaya", "Every morning you stole. I want them back.", "Veyra", "Come take them from the edge of my blade."),
    ("Meyaya", "If this is my last line, I am making it a beginning.", "Veyra", "Then I will meet you on the next page."),
)
REACTIONS["Enemy of All · Absolute Erasure"] += (
    ("Veyra", "Listen carefully. That is the sound of no tomorrow.", "Meyaya", "Funny. I can still hear you being dramatic."),
    ("Veyra", "I did warn you what standing beside a world would cost.", "Meyaya", "And I told you I was staying."),
)


def dialogue_for(state, *, final=False, exchange=False):
    if exchange:
        if not state.finisher:
            return ("Meyaya", "Still here, Veyra.", "Veyra", "Then let the world choose.")
        actor = next((f for f in (state.left, state.right) if f.user_id == state.last_actor), None)
        if actor is state.left:
            return ("Meyaya", "Everbloom. One last beginning.", "Veyra", "Mournfang. Leave nothing unwritten.")
        return ("Veyra", "Mournfang. End this.", "Meyaya", "Everbloom. Stay with me.")
    if final:
        winner = next((f for f in (state.left, state.right) if f.user_id == state.winner_id), None)
        if winner is None:
            return ("Meyaya", "Neither of us gets the last word, then.", "Veyra", "Not today.")
        close = winner.hp / max(1, winner.max_hp) <= .25
        if winner is state.left:
            return (("Meyaya", "One heartbeat. That was all I had left.", "Veyra", "Remember how close silence came.")
                    if close else
                    ("Meyaya", "The world stays. So do you.", "Veyra", "Do not mistake this for surrender."))
        return (("Veyra", "You almost made me believe in another dawn.", "Meyaya", "Almost is a place to start.")
                if close else
                ("Veyra", "Your crown has fallen.", "Meyaya", "A flower does not need a crown to grow."))
    actor = next((f for f in (state.left, state.right) if f.user_id == state.last_actor), None)
    if actor is None or actor.last_move not in REACTIONS:
        return None
    # Read the attack's appearance in this phase; never advance the combat RNG.
    if actor.hp / max(1, actor.max_hp) <= .25:
        return (("Meyaya", "My hands are shaking. Everbloom isn't. That will do.",
                 "Veyra", "You could still lower the blade.") if actor is state.left else
                ("Veyra", "Even on my knees, I am the end of your world.",
                 "Meyaya", "Then get up. I want you to see it survive."))
    if actor.hp / max(1, actor.max_hp) > .5:
        defender = state.right if actor is state.left else state.left
        if defender.hp / max(1, defender.max_hp) <= .25:
            return (("Meyaya", "You are still here. Don't make me glad about that.",
                     "Veyra", "Save the kindness. Keep your blade up.") if actor is state.left else
                    ("Veyra", "One more dawn, you said. Show me.",
                     "Meyaya", "You should know better than to dare me."))
    variant = (max(1, actor.skills_used) - 1 + state.seed) % len(REACTIONS[actor.last_move])
    return REACTIONS[actor.last_move][variant]

