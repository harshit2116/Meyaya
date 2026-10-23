"""Restart-safe finale combat. Story routing is isolated from ordinary bossfights."""

from dataclasses import asdict
from random import Random

from bot.services.fantasy_duel import DuelEngine, Fighter
from bot.services.fantasy_boss import veyra_boss_profile, meyaya_boss_profile
from bot.services.fantasy_dungeon_combat import restore_fighter
from bot.services.patron_boss_combat import PatronClashEngine

MEYAYA_STORY_ID = -10001
ALLY_TURNS = 6
CLASH_MAX_MOVES = 16


def origin_fighter():
    profile = meyaya_boss_profile(1)
    profile.user_id = MEYAYA_STORY_ID
    return Fighter.snapshot(profile, "Meyaya")


class MemoryCoreBattle(DuelEngine):
    """The player buys time with Meyaya; defeating Erasure is not the objective."""

    def __init__(self, player, enemy, ally, seed, turn=0):
        super().__init__(player, enemy, seed)
        self.ally = ally
        self.state.round = turn

    @classmethod
    def begin(cls, profile, seed):
        player = Fighter.snapshot(profile, "You")
        ally = origin_fighter()
        enemy = Fighter.snapshot(veyra_boss_profile(), "Veyra")
        ally.hp = ally.max_hp = enemy.hp = enemy.max_hp = 2400
        ally.mp = ally.max_mp = enemy.mp = enemy.max_mp = 800
        return cls(player, enemy, ally, seed)

    @classmethod
    def restore(cls, saved, seed):
        battle = cls(restore_fighter(saved["player"]), restore_fighter(saved["enemy"]),
                     restore_fighter(saved["ally"]), seed, saved["turn"])
        battle.state.log = list(saved.get("log", ()))
        return battle

    def export(self):
        return dict(player=asdict(self.state.left), enemy=asdict(self.state.right),
                    ally=asdict(self.ally), turn=self.state.round, log=self.state.log[-6:])

    def absorb(self, fighter, amount):
        if fighter is self.state.right:
            amount = min(amount, max(0, fighter.hp + fighter.shield - 1))
        return super().absorb(fighter, amount)

    def player_turn(self, action):
        if action not in {"attack", "ability", "guard"} or self.state.round >= ALLY_TURNS:
            raise ValueError("Choose an available Memory Core action")
        player, enemy = self.state.left, self.state.right
        cost = 16 if player.passive == "discount" and player.skills_used == 0 else 22
        if action == "ability" and (not player.signature or player.mp < cost or player.skills_used >= 2):
            raise ValueError("Your signature is exhausted or needs more MP")
        state = self.state
        state.round += 1
        state.moves = state.round * 3
        state.log = []
        self.rng = Random(state.seed + state.round * 7919)
        if state.round == 1:
            self.activate_passive(player)
        if action == "guard":
            player.mp = min(player.max_mp, player.mp + 8)
            player.shield = min(round(player.max_hp * .30), player.shield + max(1, round(player.max_hp * .18)))
            state.log.append("You brace the escape boundary. Meyaya has room to raise Everbloom.")
        else:
            # Existing awakened class, weapon, affinity and signature rules.
            self.attack(player, enemy, action == "ability")
        move = ("Prism Cascade", "Genesis Crown", "Origin Protocol · The First Dawn")[(state.round - 1) // 2]
        self.ally.last_move = move
        self.ally.skills_used += 1
        self.ally.mp = max(0, self.ally.mp - 40)
        damage = min(enemy.hp - 1, 170 + state.round * 18)
        self.absorb(enemy, max(0, damage))
        state.log.append(f"Meyaya · {move}. Your opening lets her force Veyra away from the boundary.")
        enemy.last_move = "World Sever" if state.round % 3 == 0 else "Mournfang · Memory Rend"
        incoming = max(1, round(player.max_hp * (.16 if state.round % 3 == 0 else .10)))
        # Meyaya visibly intercepts a fatal hit; the player remains a mortal.
        if incoming >= player.hp + player.shield:
            self.absorb(self.ally, incoming)
            state.log.append("Meyaya catches Mournfang on Everbloom. 'Behind me. You are not dying here.'")
        else:
            taken, _ = self.absorb(player, incoming)
            state.log.append(f"Veyra · {enemy.last_move} · {taken} damage. The remembered sky tears behind her.")
        if state.round == ALLY_TURNS:
            state.finished = True
            state.finisher = "Memory World Erasure"
            state.log.append("Veyra turns her blade away from you. The Memory World itself is her target.")
        return state


class WorldlineClashEngine(PatronClashEngine):
    """Same attacks and act progression, with the saved story branch determining victory."""

    def __init__(self, origin, erasure, seed, route):
        if route not in {"meyaya", "veyra"}:
            raise ValueError("A permanent worldline must be chosen before witnessing")
        super().__init__(origin, erasure, seed)
        self.chosen_id = origin.user_id if route == "meyaya" else erasure.user_id

    def absorb(self, fighter, amount):
        if fighter.user_id == self.chosen_id:
            amount = min(amount, max(0, fighter.hp + fighter.shield - 1))
        return super().absorb(fighter, amount)

    def attack(self, attacker, defender, signature=False):
        super().attack(attacker, defender, signature)
        if self.state.moves >= 11 and attacker.user_id == self.chosen_id and defender.hp:
            self.absorb(defender, defender.hp + defender.shield)
            self.state.finisher = attacker.last_move
            self.state.log.append(f"{attacker.name}'s final release settles the worldline you chose to stand behind.")


def story_clash(run, route):
    """Replay at most sixteen deterministic moves; no RNG blobs or live model calls."""
    origin = origin_fighter()
    erasure = Fighter.snapshot(veyra_boss_profile(), "Veyra")
    engine = WorldlineClashEngine(origin, erasure, run.seed, route)
    moves = run.state.get("clash_moves", 0)
    if not isinstance(moves, int) or not 0 <= moves <= CLASH_MAX_MOVES:
        raise ValueError("Invalid saved finale cursor")
    for _ in range(moves):
        if engine.state.finished:
            raise ValueError("Saved finale cursor exceeds the verdict")
        engine.advance_move()
    return engine


def advance_clash(run, route):
    engine = story_clash(run, route)
    frame = run.state.get("clash_frame", "opening")
    if frame == "verdict":
        if not engine.state.finished or engine.state.winner_id != engine.chosen_id:
            raise ValueError("The story verdict has not been earned")
        run.state = dict(run.state, sequence="ending", scene=0)
        return
    if frame == "exchange":
        if not engine.state.finished:
            raise ValueError("The final exchange has no combat result")
        run.state = dict(run.state, clash_frame="verdict", clash_winner=route)
        return
    if frame == "opening" or (frame == "attack" and engine.state.moves in {4, 8}):
        run.state = dict(run.state, clash_frame="awakening")
        return
    if frame not in {"attack", "awakening"} or engine.state.finished:
        raise ValueError("Invalid finale frame")
    engine.advance_move()
    run.state = dict(run.state, clash_moves=engine.state.moves,
                     clash_frame="exchange" if engine.state.finished else "attack")
