"""The Tenfold Descent: one authored campaign, two allegiance commentaries."""

from dataclasses import dataclass
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "fantasy" / "dungeon"
ROMAN = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
# Colours follow each world's environment rather than the selected patron.
WORLD_COLORS = (
    0xCF653E,  # Solenne: copper sunset
    0x268BA8,  # Nymora: deep ocean teal
    0xB8C4D9,  # Eidolon: mirror silver
    0xA63842,  # Kharos: battlefield crimson
    0x9383BE,  # Morrow: moonlit violet
    0xC5AF78,  # Astraeon: ancient celestial gold
    0xDEAA57,  # Velis: warm lamplight
    0xA8D3AA,  # Nhal: pale garden green
    0x586582,  # Nullis: fading starlight
    0xDFE3EA,  # The Seal: white light in the void
)


@dataclass(frozen=True)
class Enemy:
    name: str
    class_id: str
    affinity: str
    behavior: str
    abilities: tuple[str, ...]
    design: str


@dataclass(frozen=True)
class World:
    number: int
    key: str
    name: str
    title: str
    theme: str
    introduction: str
    story: str
    boss: Enemy
    enemies: tuple[Enemy, ...]
    boss_intro: str
    completion: str
    origin: str
    erasure: str
    clue: str
    art_direction: str

    def asset(self, name="world"):
        return ASSET_ROOT / self.key / f"{name}.jpg"

    @property
    def color(self):
        return WORLD_COLORS[self.number - 1]

    def commentary(self, alignment):
        return self.narrative("erasure" if alignment == "veyra" else "origin", alignment)

    def narrative(self, field, alignment):
        return getattr(self, field).format(patron="Meyaya")

    def xp(self, encounter):
        return 160 + 40 * self.number if encounter == 3 else 40 + 12 * self.number


def enemy(name, discipline, affinity, behavior, design):
    return Enemy(name, discipline, affinity, behavior,
                 ("Strike", "Affinity Pulse", "Ward"), design)


def boss(name, discipline, affinity, behavior, abilities, design):
    return Enemy(name, discipline, affinity, behavior, tuple(abilities), design)


WORLDS = (
    World(1, "solenne", "Solenne", "The World Beneath the Last Dawn", "Hope",
          'Golden towers stand beneath a crimson sun that has not moved for centuries. Dead flowers line the road. A child asks whether morning has a sound.\n\nMeyaya: ‘Beyond these ten worlds waits the Origin Gate. Bring their fragments together, and we can free what has been held too long.’',
          "A gardener tends flowers that have never opened. Each evening he lays a fresh cup beside his sleeping daughter. ‘The queen promised a morning,’ he says. Above the palace, the sun answers with a heartbeat.",
          boss("Aurelia · Last Dawnbearer", "paladin", "solar", "pressure",
               ("Dawncleaver", "Crown of Cinders", "Sunward Aegis", "Last Light"),
               "tragic regal sun queen, golden fractured crown, luminous spear, flowing white mantle burning at its edges, life flowing from her chest into an exhausted sun"),
          (enemy("Dawnless Knight", "knight", "solar", "ward", "hollow gold-armored knight with a closed sun visor and a charred banner"),
           enemy("Cinder Hound", "berserker", "fire", "pressure", "lean black volcanic hound with ember ribs and a smoking mane"),
           enemy("Sun-Eaten Seraph", "mage", "solar", "drain", "winged celestial bird with eclipsed halo and burnt gold feathers")),
          "The queen lowers her spear. Her blood has kept the sun alight for centuries. ‘When you leave... will morning finally come?’ {patron} tells you the fragment is the only way to save her.",
          "Aurelia's light stops feeding the sky. You take the first fragment. For an instant the horizon shows an empty lattice beneath its sunset. Meyaya's outline becomes clearer. ‘One less boundary,’ she whispers, then tells you the Gate must be whole before it can help.",
          'Meyaya: ‘You chose Origin. Keep looking at what these people need, even when the road is difficult.’',
          'Meyaya: ‘You chose Erasure. You need not share my name or my path to help these worlds find release.’',
          "A fragment sustains its world rather than healing it.",
          "crimson eternal sunset kingdom, ruined gold architecture, dead flowers, burning horizon, melancholy luminous beauty"),
    World(2, "nymora", "Nymora", "The Sea That Remembers", "Loss",
          'A blue-black ocean covers the second world. Bells move without sound. Bioluminescent avenues remember footsteps nobody can identify. The Abyssal Choir sings a name twice; the second voice begins before the first has finished.',
          "A grieving mother shows you the face she keeps folded inside a shell. ‘If the sea stops remembering, who will know he lived?’ {patron} promises release, but will not meet her eyes.",
          boss("Nerissa · The Last Mourner", "moon_priestess", "water", "drain",
               ("Memory Siphon", "Undertow", "Mourner's Veil", "Abyssal Refrain"),
               "ocean mourning sovereign with translucent mourning veil, floating pearl reliquary, flowing spectral fins and submerged memories orbiting her"),
          (enemy("Drowned Oracle", "cleric", "water", "drain", "blind oracle suspended underwater inside a cracked diving-bell halo"),
           enemy("Memory Leech", "warlock", "water", "drain", "ribbonlike translucent deep-sea creature carrying tiny luminous memory pearls"),
           enemy("Tidal Revenant", "knight", "frost", "ward", "coral-encrusted revenant knight with an anchor blade and streaming drowned robes")),
          "Nerissa guards an altar of remembered faces. ‘You call it salvation because you will not stay to watch us forget.’ She closes both hands around the second fragment.",
          'The ocean grows quiet. The mother opens her shell and cannot remember the face inside it. A current of dark light leaves the fragment and vanishes along the path behind you. Meyaya reaches farther across the threshold than she could before. She says the road is recovering.',
          'Meyaya: ‘You chose Origin. Keep looking at what these people need, even when the road is difficult.’',
          'Meyaya: ‘You chose Erasure. You need not share my name or my path to help these worlds find release.’',
          "{patron} describes erasure as restoration.",
          "deep underwater civilization, colossal submerged temples, blue-black ocean, bioluminescent ruins, ghostly silhouettes, floating memories"),
    World(3, "eidolon", "Eidolon", "The City of Borrowed Faces", "Identity",
          "Mirrors cover a pale gothic city. Doorplates lose their names while you read them. A husband introduces himself to his wife as a stranger. Every faceless statue turns slightly toward {patron}.",
          "An injured citizen looks at Meyaya. ‘The face is right. The pause before she speaks isn't.’ She kneels beside him. ‘You have forgotten so much. Are you certain of that?’ You notice her hand passes through a locked archive door only after you open it.",
          boss("The Pale Archivist · Keeper of Forgotten Names", "dreamweaver", "arcane", "mirror",
               ("Borrowed Name", "Mirror Verdict", "Blank Index", "Glass Ward"),
               "nonhuman archivist composed of floating porcelain masks and silver book leaves, long ink-quill limbs, empty face under a gothic crown"),
          (enemy("Faceless Courtier", "assassin", "shadow", "mirror", "elegant masked courtier with blank porcelain face and folded glass daggers"),
           enemy("Name Eater", "warlock", "void", "drain", "ink-black moth creature with blank paper wings consuming empty nameplates"),
           enemy("Glass Mimic", "spellblade", "arcane", "mirror", "fractured mirrored humanoid reflecting incompatible identities through its crystalline body")),
          "The Archivist opens a ledger crowded with different travelers' handprints. One mark resembles yours, but its fingers do not fit your hand. ‘A familiar trace is not the same person,’ it says. Meyaya looks at the mismatched print as carefully as you do.",
          'The third fragment leaves the archive. Faces return to the mirrors, but several reflections repeat gestures their owners never made. You carry a torn page showing many incomplete signatures. Meyaya asks to see it. For once she has no explanation ready.',
          'Meyaya: ‘You chose Origin. Keep looking at what these people need, even when the road is difficult.’',
          'Meyaya: ‘You chose Erasure. You need not share my name or my path to help these worlds find release.’',
          "The companion's borrowed identity and the player's composite traces are separate mysteries.",
          "pale gothic metropolis, silver mirrors, glass cathedrals, faceless marble statues, identity horror, cool monochrome"),
    World(4, "kharos", "Kharos", "The War Without a Cause", "Purpose",
          "Fortresses rise from continents paved with weapons. Smoke is the only moving cloud. Two armies repeat the same battle beneath a red sky, each certain the other remembers why it began.",
          'A soldier carries an unsigned letter to a village that no longer exists on any map. He has marched past its supposed location every morning. ‘Someone keeps setting the road back,’ he says. Meyaya asks when it began. Neither of them can answer.',
          boss("Vhaldr · The Last Reason", "berserker", "earth", "execute",
               ("Siegebreaker", "Last Command", "Red Advance", "Iron Resolve"),
               "battle-scarred general fused into a colossal mobile siege bastion, broken command banners, iron greatblade, human eyes inside fortress armor"),
          (enemy("Crimson Legionnaire", "berserker", "fire", "execute", "red armored exhausted legionnaire carrying a chipped poleaxe and generations of broken medals"),
           enemy("Iron Penitent", "paladin", "earth", "ward", "chain-bound penitential soldier with an iron bell shield and sealed helm"),
           enemy("Warforged Beast", "knight", "storm", "pressure", "quadrupedal siege engine beast made from swords and battered cannons")),
          "Vhaldr plants his blade between you and the fourth fragment. ‘If there was never a reason... what did I spend my life protecting?’ Behind him, both armies stop to hear your answer.",
          "With the fragment gone, the fortresses expose identical foundations beneath opposing banners. A dark pulse travels toward the center of the road. Meyaya catches her breath. The soldier's letter repeats its first line where the ending should be.",
          'Meyaya: ‘You chose Origin. Keep looking at what these people need, even when the road is difficult.’',
          'Meyaya: ‘You chose Erasure. You need not share my name or my path to help these worlds find release.’',
          "The repeated justification conceals the cost of every fragment.",
          "war-torn continent, immense fortresses, weapons embedded in mountains, red skies, smoke seas, devastated epic battlefields"),
    World(5, "morrow", "Morrow", "The Kingdom That Refused Death", "Mortality",
          "Moonlight gilds an immaculate palace. Nobody has died here for thousands of years. Bodies remain when hope does not. The court applauds with hands too tired to stop.",
          "A mourning doll repairs a child's sleeve for the ten-thousandth night. ‘She has grown old inside the same small body.’ {patron} watches without speaking. Perhaps she knew what taking the fragments would do all along.",
          boss("Emperor Caelum · The Man Who Outlived Death", "gravekeeper", "blood", "recover",
               ("Undying Decree", "Thousand-Year Pulse", "Mourning Crown", "Stillborn Mercy"),
               "ancient emaciated immortal emperor enthroned inside an enormous living mourning clock, moon-pale crown, royal robes woven from endless funeral ribbons"),
          (enemy("Undying Knight", "knight", "blood", "recover", "beautiful tarnished silver knight with repaired porcelain joints and immortal exhausted eyes"),
           enemy("Rotless Giant", "berserker", "earth", "recover", "pale petrified giant with timeless skin and an overgrown miniature palace on its shoulders"),
           enemy("Eternal Apostle", "cleric", "lunar", "recover", "ageless masked apostle suspended in funeral silk with a broken moon censer")),
          "Caelum's heart beats against the fifth fragment. ‘Please don't save me.’ Meyaya starts to speak of release, then stops. He has spent so long unable to end that she recognizes something of her own confinement in his face.",
          '‘Thank you,’ the emperor whispers. His crown falls before his body does. The court stops applauding. The sound tries to begin again, catches on a missing beat, and fails. Meyaya watches the fragment dim in your hand. ‘Some things should be allowed to end,’ she says, almost to herself.',
          'Meyaya: ‘You chose Origin. Keep looking at what these people need, even when the road is difficult.’',
          'Meyaya: ‘You chose Erasure. You need not share my name or my path to help these worlds find release.’',
          'Preservation can deny the people preserved any say in their lives.',
          "eternal ornate kingdom turned disturbing, ancient moonlit palace, undying figures, frozen decay, beautiful melancholic mortality horror"),
    World(6, "astraeon", "Astraeon", "The Grave of Gods", "Sacrifice",
          "Mountains are the ribs of dead gods. Rivers of divine blood pass through cities built inside their remains. A cathedral hangs between two celestial fingers. Its choir has forgotten every god's name but one.",
          'A reliquary keeper recognizes the imprint that opens the shrine for Meyaya. Then he hears her speak and bars the inner door. ‘Permission is not proof,’ he says. ‘The keeper would know which name belongs on this candle.’ She cannot tell him.',
          boss("Aethra · The God Who Refused to Kneel", "dragon_warden", "celestial", "ward",
               ("Divine Remnant", "Bone Horizon", "Unbowed Ward", "Last Invocation"),
               "colossal nonhuman dead goddess consciousness inside a constellation of divine rib bones, shattered celestial halo, galaxies between bone fingers"),
          (enemy("God-Eater Spawn", "abyss_walker", "void", "drain", "star-black many-jawed sacred parasite gnawing a divine bone shard"),
           enemy("Reliquary Angel", "paladin", "celestial", "ward", "skeletal angel carrying a miniature cathedral inside its ribcage, stained-glass wings"),
           enemy("Divine Revenant", "mage", "light", "pressure", "fragmented divine humanoid with floating luminous bones and a broken astronomical staff")),
          "Aethra unfolds the sixth fragment from her ribs. ‘You carry the keeper's permission. That does not make the keeper your companion.’ Meyaya's expression closes. Behind Aethra, a diagram connects the divine remains to the same center as every fragment you carry.",
          "Aethra's last consciousness quiets. The shrine loses detail where its oldest inscriptions should be. Meyaya stares at a blank name she seems to have expected to recognize. Another restraint breaks somewhere you cannot see.",
          'Meyaya: ‘You chose Origin. Keep looking at what these people need, even when the road is difficult.’',
          'Meyaya: ‘You chose Erasure. You need not share my name or my path to help these worlds find release.’',
          "The seal accepts an imprint that does not prove the speaker's identity.",
          "celestial graveyard made of colossal divine skeletons, cathedral ruins inside god bones, crimson divine rivers, astral darkness"),
    World(7, "velis", "Velis", "The World That Remembers You", "Memory / Cycle",
          'Warm windows and quiet stalls welcome you. A shopkeeper prepares an order you almost recognize. A child says you promised to return, then describes a traveler with different eyes. Something about their disappointment feels familiar. You have never stood here before.',
          'An old woman begins, ‘Last time you-’ and stops. ‘No. Not you. Something about you.’ Your companion asks whether the woman remembers her. The woman gives two incompatible answers. Meyaya looks unsettled by both.',
          boss("The First Wanderer", "chronomancer", "arcane", "mirror",
               ("Previous Step", "Echo Parry", "Borrowed Tomorrow", "Broken Promise"),
               "weathered previous traveler in a patched star cloak, fractured compass sword, shadow showing many earlier versions of himself, tragic human silhouette"),
          (enemy("Echo Stalker", "assassin", "shadow", "mirror", "humanlike shadow repeating a traveler's pose with an impossible delay"),
           enemy("Mirrorbound Knight", "knight", "arcane", "ward", "knight trapped between two narrow mirror frames carrying a backwards shield"),
           enemy("Past-Sworn", "chronomancer", "lunar", "mirror", "faded soldier layered with translucent past selves and stopped clock talismans")),
          "The First Wanderer places a broken compass beside your archive page. Its scratches match several signatures, not one. ‘You carry what we left,’ he says. ‘That doesn't mean you owe every promise we made.’ He warns you that the road has ended here before. Meyaya asks how often. He cannot count.",
          'The seventh fragment comes free. Doorways repeat, each missing a different detail. You keep the compass. Your companion admits she has no memory of this town, though its residents have begun recognizing something in her too. Neither of you knows how to trust those recognitions.',
          'Meyaya: ‘Your oath is yours. It does not make either of us understand everything we have found.’',
          "Meyaya: ‘Even your chosen patron's name appears in things I cannot explain. Read the evidence for yourself.’",
          'Residual traces resemble prior travelers without making the player a reincarnation.',
          "peaceful impossible town, warm amber lamps, familiar welcoming faces, subtly repeated architecture, stopped clocks, surreal calm"),
    World(8, "nhal", "Nhal", "The World That Should Not Exist", "False Paradise",
          "No one is hungry here. No one is afraid. White gardens connect impossible palaces. Then you see Nymora's lost mother, Kharos's soldier, and Caelum walking beneath a sun stolen from Solenne.",
          "The mother remembers a son with a different face. The soldier's letter names a street from Solenne. Behind a garden, unfinished seams join pieces of places that should never touch. Meyaya runs a finger along one join. ‘This wasn't made whole,’ she says.",
          boss("The Curator · Mother of the Unforgotten", "spirit_tamer", "nature", "recover",
               ("Perfected Garden", "Borrowed Life", "Merciful Cage", "Seam Unraveled"),
               "elegant many-armed maternal curator woven from flowering marble and stitched dream fabric, living miniature worlds suspended in her hands"),
          (enemy("Perfected Husk", "spellblade", "light", "mirror", "beautiful hollow human statue with a hairline reality seam and a vacant golden heart"),
           enemy("Dreamborn Knight", "paladin", "nature", "ward", "white petal-armored knight with a living garden shield and seams in its silhouette"),
           enemy("Smiling Saint", "cleric", "light", "recover", "serene porcelain saint with unnatural fixed smile and floating borrowed halos")),
          "The Curator holds memories of places that once existed beyond her reach. ‘I was given what someone could remember,’ she says. ‘Not all of it agreed.’ Meyaya asks who supplied those memories. The Curator turns toward the keeper's imprint on the door.",
          'Nhal separates at its seams. The eighth fragment exposes support lines beneath its gardens. Your companion follows the lines toward the center. Her promised passage is beginning to look like part of a mechanism. She keeps the torn record you found instead of dismissing it.',
          'Meyaya: ‘Your oath is yours. It does not make either of us understand everything we have found.’',
          "Meyaya: ‘Even your chosen patron's name appears in things I cannot explain. Read the evidence for yourself.’",
          'The regions are reconstructions assembled from remembered places.',
          "perfect dream paradise, impossible white architecture, gardens from incompatible worlds, hidden reality seams, false warm perfection"),
    World(9, "nullis", "Nullis", "The Universe at the End", "Inevitability",
          'Almost no stars remain above Nullis. A street loses its windows, then its doors, then the fact that it was a street. A record vault hangs over the last solid ground. Its surface shows damage repaired so many times that the repairs have become its structure.',
          "You enter the vault together. The oldest doors do not open for a name or a patron's mark. They open when your hand touches the gaps between their inscriptions. Inside are records the reconstruction could not completely overwrite.",
          boss("The Last Observer · Witness of the End", "fatebinder", "void", "drain",
               ("Final Record", "Unwritten Star", "Event Horizon", "Witness Ward"),
               "abstract cosmic witness, vast dark eye encircled by nine shattered observatory rings, threads of disappearing stars, nonhuman cosmic scale"),
          (enemy("Void Surveyor", "ranger", "void", "mirror", "skeletal astronomer silhouette with a lens head and vanishing constellation bow"),
           enemy("Endborn Witness", "gravekeeper", "shadow", "ward", "silent robed witness carrying a tiny extinguished city in transparent hands"),
           enemy("Unwritten Herald", "mage", "void", "drain", "abstract winged messenger with negative-space body and disintegrating star feathers")),
          'The Last Observer closes its rings around the ninth fragment. ‘Every previous traveler failed before the containment could fully open. You are not registered as one of them.’ Meyaya asks whether anything outside this place has ended. The Observer answers: ‘The outside is beyond this record.’',
          "The ninth fragment comes free. Your companion doubles over as light runs through channels beneath the vault. She cannot explain what you saw. When she stands, she carries the cycle record openly. ‘I need to see the center,’ she says. You follow to learn what her borrowed certainty has concealed.",
          'Meyaya: ‘Your oath is yours. It does not make either of us understand everything we have found.’',
          "Meyaya: ‘Even your chosen patron's name appears in things I cannot explain. Read the evidence for yourself.’",
          'The automatic reconstruction and cycle 33,550,336 are proven; Veyra learns her forgotten imprisonment.',
          "dying cosmic universe, almost no stars, vanishing cities, black void, minimal silver color, immense existential scale"),
    World(10, "seal", "The Seal", "There Was Never an Origin Gate", "Truth / Allegiance",
          'The ten reconstructed regions meet at the Memory Core, the center of a sealed artificial reality.',
          "The fragments fit a prison's restraints. There is no Origin Gate.",
          boss("The Final Allegiance", "abyss_walker", "void", "pressure",
               ("Origin Bloom", "Erasure Trace", "Prismatic Ward", "Last Silence"),
               "Meyaya and Veyra facing each other across a broken cosmic seal, rose-prismatic creation against elegant black-crimson erasure, cinematic duel"),
          (enemy("Memory of Dawn", "paladin", "solar", "ward", "abstract golden afterimage of the lost sunrise trapped in a seal prism"),
           enemy("Memory of the Sea", "cleric", "water", "drain", "floating ocean memory sphere with mourning faces, inside a broken seal prism"),
           enemy("Memory of the Wanderer", "chronomancer", "arcane", "mirror", "ghostly past traveler silhouette inside an ancient fractured cosmic seal prism")),
          'Meyaya and Veyra face the Witness. Continuation or Finality is yours to choose.',
          'The chosen worldline is permanent. RPG progression remains a record of the soul that witnessed it.',
          "Meyaya: ‘Even broken things can begin again. Stand with me.’",
          "Veyra: ‘Some things are broken beyond repair. Stand with me, and end this cycle.’",
          'An Unbound Soul can choose a worldline without becoming a cosmic combatant.',
          "infinite abstract black-white void, enormous ancient geometric seal, ten floating components, cosmic prison, no dungeon architecture"),
)


# Compatibility exports for content consumers; the final decision is no longer alignment-locked.
from bot.data.fantasy_memory_world import CORE
SEAL_SCENES = tuple((s.title, s.dialogue, s.asset) for s in CORE)


def seal_scenes(alignment):
    return SEAL_SCENES



def world_for(number):
    return WORLDS[number - 1]


def campaign_asset(relative):
    return ASSET_ROOT / f"{relative}.jpg"
