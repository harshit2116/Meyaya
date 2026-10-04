"""Versioned soul-bound guardians derived from saved awakenings, never daily draws."""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from random import Random
from datetime import UTC
from types import SimpleNamespace
from bot.data.fantasy import AFFINITIES
from bot.services.fantasy_duel import element_multiplier

GUARDIAN_VERSION = 1
SPECIES = (
    (
        "Velvet Owl",
        "owl",
        "Dream sentinel",
        "Clear Sight",
        "Focused strikes find weak spots.",
        "Lower physical defence.",
        0,
        -2,
        2,
    ),
    (
        "Comet Fox",
        "fox",
        "Astral familiar",
        "Starstep",
        "Recover a little HP and sharpen your next strike.",
        "No extra armour.",
        0,
        0,
        2,
    ),
    (
        "Moss Dragon",
        "dragon",
        "Ancient ward",
        "Root Ward",
        "Recover a little HP and raise a protective ward.",
        "Slower turn initiative.",
        0,
        2,
        -2,
    ),
    (
        "Pearl Moth",
        "moth",
        "Veil keeper",
        "Moonveil",
        "A gentle blessing restores vitality.",
        "Lower attack power.",
        -2,
        0,
        2,
    ),
)


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


def bound_guardian(profile):
    if getattr(profile, "is_meyaya_boss", False):
        # Reuse the ordinary binding only to supply its complete immutable schema.
        ordinary = SimpleNamespace(**(vars(profile) | {"is_meyaya_boss": False}))
        return replace(
            bound_guardian(ordinary), name="Meyaya's Astral Dragon", species="dragon",
            role="Final-boss guardian", bond=100, max_hp=30000, max_mp=10000,
            attack=500, defense=500, speed=500, blessing="Sovereign Ward",
            blessing_text="Restores vitality and shields the sovereign.",
            weakness="Intentionally overpowered NPC — challenge at your own risk.",
        )
    # No guild/day dependency. Preserve this version/catalog ordering for stability.
    when = profile.awakened_at
    when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
    seed = f"guardian-v1:{profile.user_id}:{when.isoformat()}:{profile.class_id}"
    rng = Random(int.from_bytes(sha256(seed.encode()).digest(), "big"))
    name, species, role, blessing, text, weakness, atk, defense, speed = SPECIES[
        rng.randrange(len(SPECIES))
    ]
    affinity = AFFINITIES.get(profile.affinity_id, AFFINITIES["arcane"])
    return Guardian(
        profile.user_id,
        name,
        species,
        role,
        profile.affinity_id,
        profile.affinity_name,
        affinity.color,
        profile.class_name,
        60 + (profile.luck % 21),
        95 + profile.vitality * 3 + (12 if species == "dragon" else 0),
        40 + profile.intelligence * 2,
        15 + (profile.strength + profile.intelligence) // 3 + atk,
        10 + profile.vitality // 2 + defense,
        10 + profile.dexterity + speed,
        blessing,
        text,
        weakness,
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

    def __post_init__(self):
        self.hp, self.mp = self.guardian.max_hp, self.guardian.max_mp

    def can_bless(self):
        return (
            self.mp >= 18
            and self.blessing_uses < 2
            and (self.guardian.species != "moth" or self.hp < self.guardian.max_hp)
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
            species = a.guardian.species
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
            if species == "dragon":
                a.guarded = True
            self.log = f"{a.guardian.name} invokes {a.guardian.blessing}: +{healed} HP{' · focused strikes ready' if a.focus else ''}{' · ward raised' if species == 'dragon' else ''}."
        else:
            if move == "affinity":
                a.mp -= 14
            raw = (20 + a.guardian.attack * 0.75 - b.guardian.defense * 0.35) * self.rng.uniform(
                0.9, 1.1
            )
            if a.guardian.species == "owl":
                raw *= 1.04
            if a.focus:
                raw *= 1.15
                a.focus -= 1
            if move == "affinity":
                raw *= 1.3 * element_multiplier(a.guardian.affinity, b.guardian.affinity)
            critical = self.rng.random() < (0.12 if a.guardian.species == "fox" else 0.08)
            if critical:
                raw *= 1.25
            if b.guarded:
                raw *= 0.5
                b.guarded = False
            damage = min(b.hp, max(5, min(round(b.guardian.max_hp * 0.32), round(raw))))
            b.hp -= damage
            self.log = f"{a.guardian.name} uses {a.guardian.affinity_name + ' Pulse' if move == 'affinity' else 'Strike'}! {damage} damage{' · Critical hit!' if critical else '.'}"
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
