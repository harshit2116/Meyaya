"""Remembered regions and gradually earned evidence of the artificial world."""

from dataclasses import dataclass
from bot.data.fantasy_memory_world import NULLIS_REVELATION


@dataclass(frozen=True)
class WorldLore:
    history: tuple[str, str]
    witness: tuple[str, str]
    discovery: tuple[str, str]
    guardian: tuple[str, str]


LORE = {
    1: WorldLore(
        ("THE LAST CALENDAR", "Solenne's calendar ends on the day Aurelia crowned herself. The sun began to fall that evening; she bound its heart to her own before it reached the horizon. People still mark birthdays by turning a page, though every page bears the same date."),
        ("THE LAMPLIGHTER", "A lamplighter cleans lamps that have never been lit. His grandmother taught him the route in case night returned. He presses a wick into your hand. ‘If you find morning, tell it we kept everything ready.’ {patron} waits while you wrap it carefully."),
        ("BENEATH THE ROOTS", "Below the gardener's house, gold roots run toward the palace. Every unopened flower is connected to them. When the fragment pulses, the roots brighten and the child's breathing steadies. Removing it will touch more than the queen; you trace one root until it disappears beneath the nursery."),
        ("THE QUEEN'S VIGIL", "The palace has no throne. Aurelia stands in a shallow basin worn smooth by centuries of blood. Beside it are petitions she has answered in her own hand: a repaired roof, a missing dog, a request for rain. The figure keeping this world alive still knows its people by name.")),
    2: WorldLore(
        ("THE FIRST DROWNING", "Nymora's seawall carries a list of evacuation boats. The final boat never launched. Nerissa gathered the voices of those left behind into the tide so their families could hear them again. Houses were rebuilt beneath the sea, close enough to listen."),
        ("THE BELL DIVER", "A diver replaces a cracked bell with one cast from his wedding ring. Each bell keeps a single voice distinct from the choir. ‘Without it, my wife sounds like everyone else.’ He asks you to listen until you can tell her song apart. {patron} stands silent beside you."),
        ("A DEBT OF MEMORY", "Pearls in the archive hold ordinary moments: burnt bread, a quarrel, someone returning home late. New memories have been scraped away to preserve older ones. A clerk forgets your name while writing it. The sea can keep the dead only by taking room from the living."),
        ("THE EMPTY RELIQUARY", "Nerissa's own reliquary is empty. She gave away the memory of her daughter to make space for the city. At the altar she repeats the child's name from a note tied to her wrist, but the name no longer brings a face. She still refuses to let anyone else's song go quiet.")),
    3: WorldLore(
        ("THE REGISTRY", "Eidolon's mirrors once preserved a reflection against illness, age, and grief. Citizens could borrow a former self until they recovered. The registry still lists return dates, all overdue. People kept the versions they preferred until the city forgot who had borrowed whom."),
        ("A NAME ON PAPER", "A courtier carries her name in a sealed envelope. Opening it costs a memory; leaving it shut means strangers choose what to call her. She asks you to read it aloud. {patron} holds the paper steady while the woman repeats the sound until she can say it without help."),
        ("THE MISSING ENTRY", "Several incomplete handprints overlap in an archive ledger. Together they almost resemble yours. The accompanying note changes handwriting mid-sentence: ‘Ask what happens to the places we leave.’ A corner lists a date earlier than the library's foundation. Your companion cannot read the damaged authority mark."),
        ("THE ARCHIVIST'S FACE", "Behind the masks is a small portrait with the face cut out. The Archivist surrendered its own identity to remember everyone else's. Its shelves contain names the city has already lost. To reach the fragment, you must pass the only witness who still knows who those people were.")),
    4: WorldLore(
        ("TWO COPIES OF A TREATY", "Both armies carry the same peace treaty, each calling the other's copy a forgery. Even the ink stains match. The village in its first clause is absent from both maps. Vhaldr's orders keep soldiers moving while nobody can remember the first day of the war."),
        ("THE FIELD KITCHEN", "An army cook sets out bowls for soldiers who will never return. Soldiers from both sides eat here without speaking. She mends their uniforms with the same thread. {patron} watches you leave your bowl unfilled for a messenger the cook still expects at sunset."),
        ("ORDERS UNDER ORDERS", "Under the latest battle map is another, identical down to a bloodstain. Older maps repeat beneath it. The fragment restores the armies after each defeat but never restores what they remember of the war's beginning. Every victory starts the next morning's conscription."),
        ("THE GENERAL'S SIGNATURE", "Vhaldr signed the first order and every renewal after it. In private he writes letters releasing soldiers from service, then burns them before dawn. He fears that ending the war would make him responsible for all the deaths he called necessary. The fourth fragment glows beneath his medals.")),
    5: WorldLore(
        ("THE ABOLITION OF DEATH", "Caelum's decree is carved above the hospital: ‘No parent shall bury a child again.’ The first wards celebrated for a century. Later records stop listing recoveries and begin listing rooms added. The fragment preserves each body at the moment death would have claimed it."),
        ("THE REPAIR ROOM", "A seamstress maintains mourning clothes nobody has been allowed to wear. She shows you a coat altered for the same man across eight hundred years. ‘He wants to look like himself at the end.’ {patron} lets her finish explaining each repair before you leave."),
        ("THE UNUSED CEMETERY", "The cemetery is a garden of empty graves. Families visit to speak words they cannot say in the palace. The emperor's grave is smallest, bought before his decree. Fresh flowers stand beside it. Someone has been changing them every day for thousands of years."),
        ("A DECREE UNSIGNED", "On Caelum's desk lies an order revoking immortality. His hand has hovered over it so long that the ink dried in the pen. Ending his bargain would end everyone else's as well. He asks you to understand that his first promise was made out of love, before you decide what to do with it.")),
    6: WorldLore(
        ("CITIES OF BONE", "Astraeon's gods gave their bodies to shelter people from a collapsing sky. Settlements grew inside their ribs. Prayers became building permits; sacred rivers became irrigation channels. The inhabitants still thank a god before repairing a wall, although most no longer know which god it was."),
        ("THE BONE MASON", "A mason refuses to cut a supporting rib even as his house collapses. His daughter wants to build elsewhere. ‘If we leave, what was the sacrifice for?’ he asks. {patron} looks toward the open plain, where the daughter has already laid the first stones of a smaller home."),
        ("THE NINTH SOCKET", "Inside a divine hand, nine channels meet around an empty socket. Their shapes match the fragments you carry. The carving shows worlds feeding something beyond the sky. Aethra's name appears among the witnesses; your patron's mark is there too. This arrangement predates every kingdom you have crossed."),
        ("AETHRA'S REFUSAL", "Aethra remained conscious when the other gods went quiet. She watched cities grow inside her friends and refused to surrender the fragment in her ribs. ‘A sacrifice is a choice,’ she says. ‘What did these people choose?’ Her question follows you across the bridge of her outstretched hand.")),
    7: WorldLore(
        ("THE TOWN'S ROUTINE", "Velis resets at the evening bell. Bread returns to the oven, rain climbs into the clouds, and broken cups stand whole on their shelves. Small habits survive. The baker always makes one extra loaf. The town has learned to prepare for someone it cannot quite remember."),
        ("THE PROMISE BOOK", "The child keeps promises in a box beneath the floor. Each page belongs to a different traveler. You recognize a feeling in one sentence and the shape of a letter on another, but no complete hand matches yours. {patron} asks the child whether she remembers the woman who came with them. The child cannot settle on a face."),
        ("A MARK THAT STAYS", "You scratch a line beneath the clock. Beneath the paint are hundreds of matching lines. Nearby, a warning survives in the First Wanderer's script: ‘The road remembers the oath. We forget the price.’ The compass drawn on your archive page matches a symbol carved beside his warning."),
        ("THE FIRST ARRIVAL", "The Wanderer holds fragments of arrivals that cannot all belong to one lifetime. Some travelers carry familiar marks; none is entirely you. He stayed to keep a promise to the child at the window. He guards the fragment because the town's repeating days are the only days he can still offer her.")),
    8: WorldLore(
        ("THE GARDEN'S FOUNDATIONS", "Nhal's foundations contain stones from nine different worlds. A public plaque credits the Curator with rescuing places that would otherwise disappear. The dates have been chiseled out and rewritten many times. Paradise has been rebuilt from the remnants of earlier journeys."),
        ("THE WRONG SEASON", "The gardener from Solenne tends flowers that finally opened, but he cannot find his daughter's house. A street ends where her door should be. {patron} walks its length with you. The Curator saved the garden; the map has no place for the person it was planted for."),
        ("THE REPAIR LEDGER", "The Curator's ledger counts shelter, food, and faces restored. In a narrower column it lists what could not be carried over: a child's laugh, the smell of a kitchen, the reason two people loved each other. The paradise is incomplete in ways its residents cannot name."),
        ("THE CURATOR'S HANDS", "Each of the Curator's hands holds a different failing place together. She will have to release one to defend herself. She asks which place you think she should drop. Behind you, your patron says your name, but for a moment you cannot turn away from the worlds in those hands.")),
    9: WorldLore(
        ("THE OBSERVATORY'S WORK", "Nullis tried to measure what lay beyond its sky. Its observers found repeating coordinates where distance should have grown. When the stars began disappearing, they started recording who had lived beneath them. A bench survives beside a telescope whose constellation is gone. Its notebook remains open to unfinished names."),
        ("THE LAST ADDRESS", "A courier carries a letter to a street erased minutes ago. He reads its address aloud to keep it from vanishing too. {patron} helps you copy it onto the archive page. The courier can no longer remember the letter's recipient, but thanks you for giving him somewhere to go."),
        ("THE COMPLETE DIAGRAM", "The vault's diagram joins nine regions to a central mechanism. Its measurements describe a constructed interior rather than distances between stars. A tenth restraint lies at the center. Beside it, an intact archive offers a reconstruction history far older than any world you have crossed."),
        ("THE OBSERVER'S QUESTION", "The Last Observer has recorded every departure and no return. It offers you the final volume instead of an answer. The newest page contains your arrival, still drying. ‘When you reach the center,’ it asks, ‘will you remember us as people, or as steps along the way?’")),
}


def patron_name(alignment):
    return "Meyaya"  # Display identity only; Veyra's mask is revealed at the Core.


def lore_scenes(world, phase, alignment, beat=1):
    """Scene positions live in the existing run JSON, including old-run defaults."""
    patron = patron_name(alignment)
    lore = LORE.get(world.number)
    if phase == "intro":
        scenes = [("ARRIVAL", world.narrative("introduction", alignment) + "\n\n" + world.commentary(alignment))]
        if lore:
            scenes.append(lore.history)
    elif phase == "story":
        if lore and beat == 0:
            scenes = [lore.witness]
        elif lore and beat == 2:
            scenes = [lore.guardian]
        else:
            scenes = [("THE PEOPLE WHO REMAIN", world.narrative("story", alignment))]
            if lore:
                scenes.append(lore.discovery)
            if world.number == 9:
                scenes.extend((s.title, s.dialogue) for s in NULLIS_REVELATION)
    else:
        scenes = []
    return tuple((title, text.format(patron=patron)) for title, text in scenes)


def lore_asset(world, phase, beat, index):
    if world.number == 9 and phase == "story" and beat == 1 and index >= 2:
        return NULLIS_REVELATION[index - 2].asset
    return None
