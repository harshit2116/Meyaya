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
    phase = max(0, min(2, state.memory_count - 1))
    variant = max(0, actor.skills_used - phase * 2 - 1) % 2
    return REACTIONS[actor.last_move][variant]

