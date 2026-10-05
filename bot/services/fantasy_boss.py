"""Meyaya's dedicated Soul Interface archetype. Never persisted as a player."""

from datetime import UTC, datetime
from random import Random
from types import SimpleNamespace

from bot.services.fantasy_generation import generate_identity


def meyaya_boss_profile(user_id):
    values = generate_identity(
        user_id, rng=Random(7963), class_id="mage", now=datetime(2026, 1, 1, tzinfo=UTC)
    )
    stats = dict.fromkeys(("strength", "dexterity", "intelligence", "vitality", "luck"), 18)
    values.update(
        **stats,
        base_stats=stats,
        level=1,
        xp=0,
        hp=300,
        max_hp=300,
        mp=140,
        max_mp=140,
        affinity_id="arcane",
        affinity_name="Arcane · Bloom · Ego",
        weapon_rarity="Mythic",
        class_name="Soulweaver",
        subclass_name="[ REWRITING... ]",
        weapon_name="Everbloom - Crown of the Last Wish",
        weapon_type="Mythic Spellcrown",
        passive_name="Spell Memory",
        passive_id="boss:spell_memory",
        signature_name="Prism Cascade",
        signature_id="boss:prism_cascade",
        fantasy_title="The Unfair Final Boss",
        passive_description="Remembers repeated tactics; capped resistance and one prismatic reflection.",
        signature_description="Five flowering rays weave one bounded adaptive spell.",
        weapon_lore="An unwritten spell has chosen its author.",
        weapon_trait="Crystalline petals orbit the Soul Interface's author.",
        description="The Girl at the End of Every Story",
        is_meyaya_boss=True,
    )
    return SimpleNamespace(**values)
