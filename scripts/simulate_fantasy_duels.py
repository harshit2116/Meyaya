"""Offline seeded balance report. No Discord, database or AI requests."""

import argparse
from collections import Counter
from random import Random
from types import SimpleNamespace
from bot.data.fantasy import CLASSES
from bot.services.fantasy_generation import generate_identity
from bot.services.fantasy_duel import DuelEngine, Fighter


def fight(left, right, seed):
    engine = DuelEngine(Fighter.snapshot(left, "Left"), Fighter.snapshot(right, "Right"), seed)
    while not engine.state.finished:
        engine.advance()
    return engine.state


def simulate(samples=5000, seed=20261005):
    rng = Random(seed)
    counts, wins, rounds, moves = Counter(), Counter(), Counter(), Counter()
    classes = tuple(CLASSES)
    draws = 0
    for index in range(samples):
        names = rng.sample(classes, 2)
        profiles = [
            SimpleNamespace(**generate_identity(user_id, rng=rng, class_id=name))
            for user_id, name in zip((1, 2), names)
        ]
        state = fight(*profiles, rng.randrange(2**63))
        rounds[state.round] += 1
        moves[state.moves] += 1
        for name in names:
            counts[name] += 1
        if state.winner_id is None:
            draws += 1
            for name in names:
                wins[name] += 0.5
        else:
            wins[names[state.winner_id - 1]] += 1
    rarity_wins, stronger_wins = 0, 0
    for index in range(1000):
        original = generate_identity(1, rng=rng)
        left = SimpleNamespace(**original)
        right = SimpleNamespace(**dict(original, user_id=2))
        left.weapon_rarity, right.weapon_rarity = "Mythic", "Common"
        result = fight(left, right, rng.randrange(2**63))
        rarity_wins += 1 if result.winner_id == 1 else 0.5 if result.winner_id is None else 0
        left.weapon_rarity = right.weapon_rarity
        # Same build, modest stat improvement; HP/MP scale with the actual generators.
        from bot.services.fantasy_generation import resource_totals

        for stat in ("strength", "dexterity", "intelligence", "vitality", "luck"):
            setattr(left, stat, getattr(left, stat) + 3)
        left.max_hp, left.max_mp = resource_totals(vars(left), CLASSES[left.class_id])
        result = fight(left, right, rng.randrange(2**63))
        stronger_wins += 1 if result.winner_id == 1 else 0.5 if result.winner_id is None else 0
    return dict(
        samples=samples,
        draws=draws,
        rounds=dict(sorted(rounds.items())),
        moves=dict(sorted(moves.items())),
        class_rates={name: round(100 * wins[name] / max(1, counts[name]), 1) for name in classes},
        mythic_vs_common_percent=rarity_wins / 10,
        stronger_stats_percent=stronger_wins / 10,
    )


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()
    if args.samples < 1000:
        parser.error("Use at least 1000 samples for balance checks.")
    print(json.dumps(simulate(args.samples, args.seed), indent=2))
