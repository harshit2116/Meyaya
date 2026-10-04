"""Meyaya's fixed, intentionally unfair NPC identity. Never persisted."""

from datetime import UTC, datetime
from random import Random
from types import SimpleNamespace

from bot.services.fantasy_generation import generate_identity


def meyaya_boss_profile(user_id):
    values = generate_identity(
        user_id, rng=Random(7963), class_id="mage", now=datetime(2026, 1, 1, tzinfo=UTC)
    )
    stats = dict.fromkeys(("strength", "dexterity", "intelligence", "vitality", "luck"), 250)
    values.update(
        **stats, base_stats=stats, level=999, xp=0,
        hp=10000, max_hp=10000, mp=10000, max_mp=10000,
        affinity_id="arcane", affinity_name="Arcane", weapon_rarity="Mythic",
        weapon_name="Meyaya's Crown of Absolute Chaos",
        fantasy_title="The Unfair Final Boss", subclass_name="Chaos Sovereign",
        is_meyaya_boss=True,
    )
    return SimpleNamespace(**values)
