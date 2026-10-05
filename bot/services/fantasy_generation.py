"""Controlled local generation. Only the first insert persists this snapshot."""

from datetime import UTC, datetime
from random import SystemRandom

from bot.data.fantasy import (
    AFFINITIES,
    CLASSES,
    GENERATION_VERSION,
    HP_BASE,
    HP_VIT_SCALE,
    MP_BASE,
    MP_INT_SCALE,
    RARITIES,
    RARITY_WEIGHTS,
    STAT_BUDGET,
    STAT_MAX,
    STAT_MIN,
    STAT_NAMES,
    TITLE_PATTERNS,
    WEAPONS,
)


def resource_totals(stats, rule):
    return (
        HP_BASE + stats["vitality"] * HP_VIT_SCALE + rule.hp_modifier,
        MP_BASE + stats["intelligence"] * MP_INT_SCALE + rule.mp_modifier,
    )


def generate_identity(user_id, *, rng=None, now=None, class_id=None):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("A positive Discord user ID is required")
    rng = rng or SystemRandom()
    class_id = class_id or rng.choice(tuple(CLASSES))
    rule = CLASSES[class_id]
    subclass_index = rng.randrange(len(rule.subclasses))
    subclass = rule.subclasses[subclass_index]
    affinity_id = rng.choices(rule.affinities, weights=(6, 3, 1), k=1)[0]
    affinity = AFFINITIES[affinity_id]
    stats = {name: STAT_MIN for name in STAT_NAMES}
    for _ in range(STAT_BUDGET - STAT_MIN * len(STAT_NAMES)):
        eligible = [name for name in STAT_NAMES if stats[name] < STAT_MAX]
        selected = rng.choices(
            eligible, weights=[rule.weights[STAT_NAMES.index(n)] for n in eligible], k=1
        )[0]
        stats[selected] += 1
    hp, mp = resource_totals(stats, rule)
    family = rng.choice(rule.weapons)
    weapon_type, names = WEAPONS[family]
    prefix = rng.choice(affinity.vocabulary)
    suffix = rng.choice(names)
    rarity = rng.choices(RARITIES, weights=RARITY_WEIGHTS, k=1)[0]
    reactions = (
        f"A {rule.name}? I knew you were hiding main-character problems.",
        "Your soul came with its own dramatic entrance. Naturally.",
        f"{affinity.name} chose you. Please remember who helped with the introduction.",
    )
    return {
        "user_id": user_id,
        "generation_version": GENERATION_VERSION,
        "class_id": class_id,
        "class_name": rule.name,
        "subclass_id": f"{class_id}:{subclass_index}",
        "subclass_name": subclass,
        "affinity_id": affinity_id,
        "affinity_name": affinity.name,
        "level": 1,
        "xp": 0,
        "rebirth_count": 0,
        "last_rebirth_at": None,
        "hp": hp,
        "max_hp": hp,
        "mp": mp,
        "max_mp": mp,
        **stats,
        "base_stats": dict(stats),
        "weapon_id": f"{affinity_id}:{family}:{prefix.lower()}:{suffix.lower()}",
        "weapon_name": f"{prefix} {suffix}",
        "weapon_family": family,
        "weapon_type": weapon_type,
        "weapon_rarity": rarity,
        "weapon_lore": f"A {weapon_type.lower()} that answered a {subclass}'s first call. {affinity.lore}",
        "weapon_trait": f"Resonance: {affinity.effect}.",
        "passive_id": f"{class_id}:passive:{subclass_index}",
        "passive_name": rule.passive,
        "passive_description": f"{rule.passive_text} Your {subclass} training attunes it to {affinity.name.lower()}.",
        "signature_id": f"{class_id}:signature:{affinity_id}",
        "signature_name": rule.signature,
        "signature_description": f"{rule.signature_text} It {affinity.effect}.",
        "fantasy_title": rng.choice(TITLE_PATTERNS).format(word=prefix),
        "alignment": "unclaimed",
        "description": f"A {subclass} whose {affinity.name.lower()} resonance first surfaced as a {rule.name}. {affinity.lore}",
        "meyaya_reaction": rng.choice(reactions),
        "awakened_at": now or datetime.now(UTC),
    }
