"""Versioned soul-bound guardians derived from saved awakenings, never daily draws."""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from random import Random
from datetime import UTC
from types import SimpleNamespace
from bot.data.fantasy import AFFINITIES
from bot.services.fantasy_duel import element_multiplier
from bot.data.fantasy_alignment import patron_for

GUARDIAN_VERSION = 3
COMMON_SPECIES = (
    ("Moonpetal Hare", "hare", "Moonlit messenger", "Petalstep",
     "Recover HP, sharpen a strike and prepare evasion.", "No extra armour.", 0, 0, 2),
    ("Cinder Kitten", "cat", "Hearth sentinel", "Emberglint",
     "Focused strikes find weak spots; brief evasion.", "Lower physical defence.", 0, -2, 2),
    ("Tideglass Axolotl", "axolotl", "Tidepool healer", "Dewdrop Wish",
     "A gentle blessing restores vitality.", "Lower attack power.", -2, 0, 2),
    ("Lantern Kirin", "kirin", "Little oathkeeper", "Lantern Ward",
     "Recover a little HP and raise a protective ward.", "Slower turn initiative.", 0, 2, -2),
    ("Rimefang Wolf", "wolf", "Winter pathfinder", "Froststep",
     "Recover HP, sharpen a strike and prepare evasion.", "No extra armour.", 0, 0, 2),
    ("Ribbon Serpent", "serpent", "Scarlet oathbinder", "Ribbon Ward",
     "Recover a little HP and raise a protective ward.", "Slower turn initiative.", 0, 2, -2),
    ("Shrine Tanuki", "tanuki", "Keeper of small wishes", "Leafbound Wish",
     "A gentle blessing restores vitality.", "Lower attack power.", -2, 0, 2),
    ("Duskfeather Crane", "crane", "Twilight wayfarer", "Stillwater Sight",
     "Focused strikes find weak spots; brief evasion.", "Lower physical defence.", 0, -2, 2),
    ("Starweft Ferret", "ferret", "Thread of good fortune", "Silkstep",
     "Recover HP, sharpen a strike and prepare evasion.", "No extra armour.", 0, 0, 2),
    ("Velvet Bat", "bat", "Midnight listener", "Echo Sight",
     "Focused strikes find weak spots; brief evasion.", "Lower physical defence.", 0, -2, 2),
)
RARE_SPECIES = (
    ("Eclipse Fenrir", "fenrir", "Hound of the black moon", "Eclipsestep",
     "Recover HP, sharpen a strike and prepare evasion.", "No extra armour.", 0, 0, 2),
    ("Obsidian Seraph", "seraph", "The six-winged oath", "Obsidian Ward",
     "Recover a little HP and raise a protective ward.", "Slower turn initiative.", 0, 2, -2),
    ("Astral Leviathan", "leviathan", "Sovereign of the starless deep", "Astral Sight",
     "Focused strikes find weak spots; brief evasion.", "Lower physical defence.", 0, -2, 2),
)
SPECIES = COMMON_SPECIES + RARE_SPECIES
NPC_SUMMONS = {
    "meyaya": ("origin_sovereign", "Aurelia, First Wish", "Origin's first promise", "Genesis Ward"),
    "veyra": ("erasure_sovereign", "Nihra, Last Silence", "Erasure's final witness", "Oblivion Ward"),
}
ART_SPECIES = frozenset(entry[1] for entry in SPECIES) | frozenset(
    entry[0] for entry in NPC_SUMMONS.values()
)
# Disjoint slots out of one million: per-species odds, never a daily reroll.
RARE_ROLL_SIZE = 1_000_000
RARE_THRESHOLDS = ((200, "leviathan"), (1200, "seraph"), (6200, "fenrir"))
SUMMON_RARITIES = {
    "fenrir": ("Legendary", "1 in 200"),
    "seraph": ("Mythic", "1 in 1,000"),
    "leviathan": ("Astral", "1 in 5,000"),
    "origin_sovereign": ("Sovereign", "Meyaya exclusive"),
    "erasure_sovereign": ("Sovereign", "Veyra exclusive"),
}


def rare_species_for_roll(roll):
    if not isinstance(roll, int) or not 0 <= roll < RARE_ROLL_SIZE:
        raise ValueError("Rare summon roll must be within the configured range")
    return next((species for limit, species in RARE_THRESHOLDS if roll < limit), None)


# Internal combat archetypes retain their formulas; these are not roster choices.
SPECIES_ARCHETYPES = {
    "hare": "fox", "cat": "owl", "axolotl": "moth", "kirin": "dragon",
    "wolf": "fox", "serpent": "dragon", "tanuki": "moth", "crane": "owl",
    "ferret": "fox", "bat": "owl",
    "fenrir": "fox", "seraph": "dragon", "leviathan": "owl",
    "origin_sovereign": "dragon", "erasure_sovereign": "dragon",
}
GUARDIAN_PERSONALITIES = {
    "hare": ("Chases moonbeams, then naps inside its own ears.", "You take the brave step. I will take the bouncy one."),
    "cat": ("Guards your campfire and insists it was never worried.", "I was not waiting for you. The fire was."),
    "axolotl": ("Collects fallen tears and turns them into water pearls.", "We can be little and still keep going."),
    "kirin": ("Carries a lantern for promises too small for legends.", "A promise does not have to be loud to shine."),
    "wolf": ("Finds your footprints even when snow hides the road.", "Walk beside me. Winter is quieter with two."),
    "serpent": ("Ties a ribbon around every promise you keep.", "Some bonds hold gently. Mine will hold you."),
    "tanuki": ("Keeps your smallest wishes folded beneath a leaf.", "A little luck, a little tea, and we try again."),
    "crane": ("Waits at dusk until your wandering soul comes home.", "No need to hurry. I saved the last light."),
    "ferret": ("Untangles bad days and steals unattended ribbons.", "If fate knots the thread, we will tug together."),
    "bat": ("Hears the brave things you whisper in the dark.", "You need not shout. I heard you choose to stay."),
    "fenrir": ("Even the black moon lowers its gaze when he wakes.", "Let the night bare its teeth. I will bare mine."),
    "seraph": ("Six wings. One oath. No throne worth kneeling to.", "Stand behind me. The heavens can wait."),
    "leviathan": ("An ancient silence swims between the dying stars.", "Call once, little soul. The deep remembers."),
    "origin_sovereign": ("Born from Meyaya's very first wish; bound to her alone.", "For her, even an unwritten tomorrow will bloom."),
    "erasure_sovereign": ("The last witness to Veyra's silence; bound to her alone.", "When all names fade, her command remains."),
}


@dataclass(frozen=True)
class Guardian:
    owner_id: int
    name: str
    species: str
    role: str
    affinity: str
    affinity_name: str
    color: str
    owner_class: str
    bond: int
    max_hp: int
    max_mp: int
    attack: int
    defense: int
    speed: int
    blessing: str
    blessing_text: str
    weakness: str
    alignment: str = ""

    @property
    def battle_species(self):
        return SPECIES_ARCHETYPES.get(self.species, self.species)

    @property
    def rarity(self):
        return SUMMON_RARITIES.get(self.species, ("Bound", ""))[0]

    @property
    def summon_chance(self):
        return SUMMON_RARITIES.get(self.species, ("Bound", ""))[1]


def bound_guardian(profile, *, preview_species=None):
    if getattr(profile, "is_meyaya_boss", False):
        if preview_species is not None:
            raise ValueError("Sovereign summons cannot be changed or previewed")
        boss_key = getattr(profile, "boss_key", "meyaya")
        species, name, role, blessing = NPC_SUMMONS[boss_key]
        # Reuse the ordinary binding only to supply its complete immutable schema.
        ordinary = SimpleNamespace(**(vars(profile) | {"is_meyaya_boss": False}))
        return replace(
            bound_guardian(ordinary),
            name=name,
            species=species,
            role=role,
            alignment=boss_key,
            color="#cd848d" if boss_key == "meyaya" else "#c52b59",
            bond=100,
            max_hp=30000,
            max_mp=10000,
            attack=500,
            defense=500,
            speed=500,
            blessing=blessing,
            blessing_text="Restores vitality and shields the sovereign.",
            weakness="Intentionally overpowered NPC - challenge at your own risk.",
        )
    # V3 retires the original four and rebinds all awakenings to this catalog. Preserve
    # this version and ordering for stable assignments across days and servers.
    when = profile.awakened_at
    when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
    seed = f"guardian-v{GUARDIAN_VERSION}:{profile.user_id}:{when.isoformat()}:{profile.class_id}"
    rng = Random(int.from_bytes(sha256(seed.encode()).digest(), "big"))
    # Keep the V3 common assignments unchanged except for the rare awakenings.
    entry = COMMON_SPECIES[rng.randrange(len(COMMON_SPECIES))]
    rare_roll = int.from_bytes(sha256(("guardian-rare-v1:" + seed).encode()).digest(), "big") % RARE_ROLL_SIZE
    rare_species = rare_species_for_roll(rare_roll)
    if rare_species is not None:
        entry = next(item for item in RARE_SPECIES if item[1] == rare_species)
    if preview_species is not None:
        entry = next((item for item in SPECIES if item[1] == preview_species), None)
        if entry is None:
            raise ValueError("Unknown guardian preview species")
    name, species, role, blessing, text, weakness, atk, defense, speed = entry
    archetype = SPECIES_ARCHETYPES.get(species, species)
    affinity = AFFINITIES.get(profile.affinity_id, AFFINITIES["arcane"])
    guardian = Guardian(
        profile.user_id,
        name,
        species,
        role,
        profile.affinity_id,
        profile.affinity_name,
        {"fenrir": "#cf5474", "seraph": "#a98be6", "leviathan": "#70cfef"}.get(species, affinity.color),
        profile.class_name,
        60 + (profile.luck % 21),
        95 + profile.vitality * 3 + (12 if archetype == "dragon" else 0),
        40 + profile.intelligence * 2,
        15 + (profile.strength + profile.intelligence) // 3 + atk,
        10 + profile.vitality // 2 + defense,
        10 + profile.dexterity + speed,
        blessing,
        text,
        weakness,
    )
    patron = patron_for(profile)
    if not patron:
        return guardian
    names = {
        "meyaya": {
            "hare": "Dawnpetal Hare",
            "cat": "Sunwick Kitten",
            "axolotl": "Wishspring Axolotl",
            "kirin": "Firstlight Kirin",
            "wolf": "Aurora Wolf",
            "serpent": "Dawnribbon Serpent",
            "tanuki": "Wishleaf Tanuki",
            "crane": "Sunveil Crane",
            "ferret": "Dawnweft Ferret",
            "bat": "Roseveil Bat",
            "fenrir": "Dawneclipse Fenrir",
            "seraph": "Everbloom Seraph",
            "leviathan": "Firststar Leviathan",
        },
        "veyra": {
            "hare": "Duskstep Hare",
            "cat": "Ashwhisper Kitten",
            "axolotl": "Stillwater Axolotl",
            "kirin": "Hollowlight Kirin",
            "wolf": "Hollowfrost Wolf",
            "serpent": "Ruinribbon Serpent",
            "tanuki": "Ashleaf Tanuki",
            "crane": "Graveveil Crane",
            "ferret": "Voidweft Ferret",
            "bat": "Bloodveil Bat",
            "fenrir": "Ashmoon Fenrir",
            "seraph": "Graveoath Seraph",
            "leviathan": "Voidtide Leviathan",
        },
    }
    return replace(
        guardian,
        name=names[profile.alignment][species],
        role=(
            "Origin guardian · Celestial protector"
            if profile.alignment == "meyaya"
            else "Erasure guardian · Ruin familiar"
        ),
        color=patron.color,
        alignment=profile.alignment,
        blessing=("Origin Blessing · " if profile.alignment == "meyaya" else "Ruin Pact · ")
        + blessing,
        blessing_text=patron.name + "'s oath empowers this companion. " + text,
    )


@dataclass
class GuardianFighter:
    guardian: Guardian
    owner_name: str
    hp: int = field(init=False)
    mp: int = field(init=False)
    guarded: bool = False
    blessing_uses: int = 0
    focus: int = 0
    evasive: int = 0
    dodges: int = 0

    def __post_init__(self):
        self.hp, self.mp = self.guardian.max_hp, self.guardian.max_mp

    def can_bless(self):
        return (
            self.mp >= 18
            and self.blessing_uses < 2
            and (self.guardian.battle_species != "moth" or self.hp < self.guardian.max_hp)
        )


class GuardianBattle:
    """Alternating player choices; 24 actions and finite healing prevent stalling."""

    def __init__(self, left, right, seed):
        self.fighters = (left, right)
        self.rng = Random(seed)
        initiative = [f.guardian.speed + self.rng.uniform(-2, 2) for f in self.fighters]
        self.turn = 0 if initiative[0] > initiative[1] else 1
        self.moves = 0
        self.finished = False
        self.winner_id = None
        self.log = "The guardians enter the soul arena."

    @property
    def actor(self):
        return self.fighters[self.turn]

    @property
    def log(self):
        return self._log

    @log.setter
    def log(self, value):
        history = getattr(self, "history", [])
        if history and value.startswith(history[-1]):
            history[-1] = value
        else:
            history.append(value)
        self.history = history[-3:]
        self._log = value

    def choose(self, user_id, move):
        if self.finished:
            raise ValueError("This battle is already over.")
        if self.actor.guardian.owner_id != user_id:
            raise ValueError("It is the other trainer's turn.")
        if move not in {"strike", "affinity", "guard", "blessing", "forfeit"}:
            raise ValueError("Unknown guardian move.")
        a, b = self.actor, self.fighters[1 - self.turn]
        if move == "affinity" and a.mp < 14:
            raise ValueError("Not enough MP for an affinity move. Try Strike or Guard.")
        if move == "blessing" and not a.can_bless():
            raise ValueError(
                "Blessing needs 18 MP and an unused charge (two per match). Moonveil also needs missing HP."
            )
        self.moves += 1
        if move == "forfeit":
            self.finished, self.winner_id = True, b.guardian.owner_id
            self.log = f"{a.owner_name} recalled {a.guardian.name}. {b.guardian.name} wins."
            return
        if move == "guard":
            a.guarded = True
            a.mp = min(a.guardian.max_mp, a.mp + 8)
            self.log = f"{a.guardian.name} raises a ward and recovers 8 MP."
        elif move == "blessing":
            a.mp -= 18
            a.blessing_uses += 1
            species = a.guardian.battle_species
            healed = min(
                a.guardian.max_hp - a.hp,
                round(
                    a.guardian.max_hp
                    * (0.18 if species == "moth" else 0.08 if species in {"fox", "dragon"} else 0)
                ),
            )
            a.hp += healed
            if species in {"owl", "fox"}:
                a.focus = 2 if species == "owl" else 1
                a.evasive = 2 if species == "owl" else 1
            if species == "dragon":
                a.guarded = True
            self.log = f"{a.guardian.name} invokes {a.guardian.blessing}: +{healed} HP{' · focus and evasion ready' if a.focus else ''}{' · ward raised' if species == 'dragon' else ''}."
        else:
            if move == "affinity":
                a.mp -= 14
            raw = (20 + a.guardian.attack * 0.75 - b.guardian.defense * 0.35) * self.rng.uniform(
                0.9, 1.1
            )
            if a.guardian.battle_species == "owl":
                raw *= 1.04
            if a.focus:
                raw *= 1.15
                a.focus -= 1
            if move == "affinity":
                raw *= 1.3 * element_multiplier(a.guardian.affinity, b.guardian.affinity)
            critical = self.rng.random() < (0.12 if a.guardian.battle_species == "fox" else 0.08)
            if critical:
                raw *= 1.25
            evade = min(
                0.18,
                0.04
                + 0.10 * b.guardian.speed / max(1, a.guardian.speed + b.guardian.speed)
                + (0.025 if b.guardian.battle_species == "fox" else 0)
                + (0.08 if b.evasive else 0),
            )
            if b.evasive:
                b.evasive -= 1
            attack_name = a.guardian.affinity_name + " Pulse" if move == "affinity" else "Strike"
            if self.rng.random() < evade:
                b.dodges += 1
                self.log = f"DODGE · {b.guardian.name} avoids {a.guardian.name}'s {attack_name}! No damage; ward preserved."
            else:
                damage = max(5, min(round(b.guardian.max_hp * 0.32), round(raw)))
                blocked = 0
                if b.guarded:
                    blocked = damage // 2
                    damage -= blocked
                    b.guarded = False
                damage = min(b.hp, damage)
                b.hp -= damage
                self.log = f"{a.guardian.name} uses {attack_name}! {damage} damage{' · CRITICAL' if critical else ''}{' · shield absorbed ' + str(blocked) if blocked else ''}."
        if not b.hp:
            self.finished, self.winner_id = True, a.guardian.owner_id
        elif self.moves >= 24:
            self.finished = True
            delta = (
                self.fighters[0].hp / self.fighters[0].guardian.max_hp
                - self.fighters[1].hp / self.fighters[1].guardian.max_hp
            )
            self.winner_id = (
                None
                if abs(delta) <= 0.03
                else self.fighters[0 if delta > 0 else 1].guardian.owner_id
            )
            self.log += (
                " Arena limit reached: remaining HP percentage decides (within 3% is a draw)."
            )
        self.turn = 1 - self.turn
