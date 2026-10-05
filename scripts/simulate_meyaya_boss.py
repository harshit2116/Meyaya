"""Deterministic boss balance across all authored classes; no network or DB."""

from collections import Counter
from random import Random
from types import SimpleNamespace
import json
from bot.data.fantasy import CLASSES
from bot.services.fantasy_generation import generate_identity
from bot.services.fantasy_boss import meyaya_boss_profile
from bot.services.fantasy_duel import Fighter
from bot.services.meyaya_boss_combat import BossDuelEngine


def simulate(samples=2100, seed=20261005):
    rng = Random(seed)
    totals, wins, moves, patterns = Counter(), Counter(), Counter(), Counter()
    player_wins, boss_wins, draws = 0, 0, 0
    for index in range(samples):
        class_id = tuple(CLASSES)[index % len(CLASSES)]
        player = SimpleNamespace(**generate_identity(1, rng=rng, class_id=class_id))
        engine = BossDuelEngine(
            Fighter.snapshot(player, "Player"),
            Fighter.snapshot(meyaya_boss_profile(2), "Meyaya"),
            rng.randrange(2**63),
        )
        while not engine.state.finished:
            engine.advance_move()
        state = engine.state
        totals[class_id] += 1
        wins[class_id] += int(state.winner_id == 2)
        player_wins += int(state.winner_id == 1)
        boss_wins += int(state.winner_id == 2)
        draws += int(state.winner_id is None)
        moves[state.moves] += 1
        patterns[engine.pattern] += 1
    return dict(
        samples=samples,
        boss_win_percent=round(boss_wins / samples * 100, 2),
        player_wins=player_wins,
        draws=draws,
        moves=dict(moves),
        patterns=dict(patterns),
        boss_win_by_class={key: round(wins[key] / value * 100, 1) for key, value in totals.items()},
    )


if __name__ == "__main__":
    print(json.dumps(simulate(), indent=2))
