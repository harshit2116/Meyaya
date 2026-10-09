"""Total soul XP and deterministic class-weighted growth, shared across rerolls."""

from bot.data.fantasy import CLASSES, STAT_NAMES
from bot.services.fantasy_generation import resource_totals

LEVEL_CAP = 100


def xp_for_level(level):
    steps = max(0, level - 1)
    return 100 * steps + 25 * steps * (steps - 1) // 2


def level_for_xp(xp):
    return next((level - 1 for level in range(2, LEVEL_CAP + 1) if xp < xp_for_level(level)), LEVEL_CAP)


def xp_progress(profile):
    level = profile.level
    if level >= LEVEL_CAP:
        return "MAX SOUL LEVEL · " + str(profile.xp) + " total XP"
    current = max(0, profile.xp - xp_for_level(level))
    needed = xp_for_level(level + 1) - xp_for_level(level)
    filled = min(14, current * 14 // needed)
    return f"{'█' * filled}{'░' * (14 - filled)} {current:,} / {needed:,} XP"


def growth_values(identity, level):
    """Rebuild from the original roll, never add growth to already-grown stats."""
    rule = CLASSES[identity.class_id] if hasattr(identity, "class_id") else CLASSES[identity["class_id"]]
    base = identity.base_stats if hasattr(identity, "base_stats") else identity["base_stats"]
    points = 4 * (max(1, min(level, LEVEL_CAP)) - 1)
    weights = rule.weights
    # Highest-averages allocation is monotonic: gaining a level can never
    # remove a stat point through rounding. At most 396 tiny iterations.
    increments = [0] * 5
    for _ in range(points):
        index = max(range(5), key=lambda i: weights[i] / (increments[i] + 1))
        increments[index] += 1
    stats = {name: int(base[name]) + increments[i] for i, name in enumerate(STAT_NAMES)}
    hp, mp = resource_totals(stats, rule)
    return dict(**stats, max_hp=hp, max_mp=mp)


def award_xp(profile, amount):
    if amount < 0:
        raise ValueError("XP rewards cannot be negative")
    old_level = profile.level
    before = {name: getattr(profile, name) for name in (*STAT_NAMES, "max_hp", "max_mp")}
    profile.xp += amount
    profile.level = max(old_level, level_for_xp(profile.xp))
    if profile.level > old_level:
        for name, value in growth_values(profile, profile.level).items():
            setattr(profile, name, value)
        # Saved vitals remain healthy; dungeon damage lives only in the run.
        profile.hp, profile.mp = profile.max_hp, profile.max_mp
    return dict(xp=amount, old_level=old_level, level=profile.level,
                gains={name: getattr(profile, name) - value for name, value in before.items()})
