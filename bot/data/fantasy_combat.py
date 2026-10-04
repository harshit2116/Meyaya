"""Explicit combat interpretations of Meyaya's existing authored identities."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CombatRule:
    mode: str
    passive: str
    signature: str
    initiative: float = 0
    mitigation: float = 0
    damage_scale: float = 1.0


CLASS_COMBAT = {
    "knight": CombatRule("physical", "shield", "weaken", mitigation=0.06),
    "ranger": CombatRule("agile", "evasion", "precise", initiative=1),
    "assassin": CombatRule("agile", "crit", "evasion", initiative=2),
    "mage": CombatRule("magic", "discount", "burst", damage_scale=1.1),
    "cleric": CombatRule("magic", "shield", "heal", damage_scale=0.95),
    "berserker": CombatRule("physical", "empower", "break"),
    "paladin": CombatRule("hybrid", "shield", "guard", mitigation=0.04),
    "warlock": CombatRule("magic", "refund", "weaken"),
    "spellblade": CombatRule("hybrid", "empower", "burst"),
    "runeblade": CombatRule("hybrid", "discount", "weaken", damage_scale=1.1),
    "voidblade": CombatRule("hybrid", "evasion", "break", initiative=1),
    "starcaller": CombatRule("magic", "precision", "burst", initiative=2, damage_scale=1.18),
    "dreamweaver": CombatRule("magic", "resist", "weaken", damage_scale=1.1),
    "gravekeeper": CombatRule("hybrid", "shield", "guard", mitigation=0.04),
    "spirit_tamer": CombatRule("magic", "evasion", "guard"),
    "storm_herald": CombatRule("hybrid", "empower", "burst"),
    "fatebinder": CombatRule("magic", "precision", "precise", initiative=1, damage_scale=1.18),
    "dragon_warden": CombatRule("physical", "shield", "weaken", mitigation=0.04, damage_scale=1.05),
    "moon_priestess": CombatRule("magic", "renew", "heal", damage_scale=0.98),
    "chronomancer": CombatRule("magic", "discount", "weaken", initiative=1),
    "abyss_walker": CombatRule("hybrid", "resist", "evasion", initiative=1, damage_scale=1.08),
}

# Weapon family affects attack scaling/crit/evasion; rarity adds at most 5%.
WEAPON_COMBAT = {
    "sword": (1.00, 0.01, 0),
    "greatsword": (1.04, 0, 0),
    "spear": (1.01, 0.01, 0),
    "bow": (0.98, 0.02, 0.01),
    "daggers": (0.97, 0.03, 0.02),
    "katana": (1.00, 0.02, 0.01),
    "staff": (1.02, 0, 0),
    "spellbook": (1.00, 0.01, 0),
    "mace": (1.02, 0, 0),
    "axe": (1.03, 0.01, 0),
}

# Reverse edges resist by 10%; other pairings are neutral.
ELEMENT_ADVANTAGES = frozenset(
    {
        ("fire", "nature"),
        ("nature", "water"),
        ("water", "fire"),
        ("storm", "water"),
        ("earth", "storm"),
        ("frost", "blood"),
        ("blood", "earth"),
        ("solar", "frost"),
        ("light", "shadow"),
        ("shadow", "lunar"),
        ("lunar", "solar"),
        ("celestial", "void"),
        ("void", "arcane"),
        ("arcane", "celestial"),
    }
)

ARENAS = (
    ("Moonlit Ruins", "#171b34", "#a89cfa", "moon"),
    ("Sakura Shrine", "#291827", "#f0a6c9", "petals"),
    ("Astral Gate", "#171c32", "#88cbea", "gate"),
    ("Crimson Garden", "#28191e", "#dc8297", "petals"),
    ("Hollow Court", "#1c1929", "#b4a0c8", "gate"),
    ("Drowned Cathedral", "#122630", "#86cdc7", "gate"),
    ("Celestial Observatory", "#20213a", "#d8c48b", "moon"),
    ("Shattered Throne", "#251f2d", "#c6ac91", "gate"),
)
