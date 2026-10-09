"""Interactive dungeon turns reusing the existing Fighter and DuelEngine rules."""

from dataclasses import asdict, replace
from random import Random
from types import SimpleNamespace

from bot.data.fantasy_dungeon import world_for
from bot.data.fantasy_combat import CombatRule
from bot.services.fantasy_duel import DuelEngine, Fighter
from bot.services.fantasy_generation import generate_identity


def enemy_fighter(floor, encounter, alignment):
    if floor == 10:
        raise ValueError("The Memory Core uses a witnessed cinematic confrontation.")
    world = world_for(floor)
    spec = world.boss if encounter == 3 else world.enemies[encounter]
    npc_id = -(floor * 10 + encounter + 1)
    values = generate_identity(abs(npc_id), rng=Random(abs(npc_id)), class_id=spec.class_id)
    values.update(user_id=npc_id, affinity_id=spec.affinity, affinity_name=spec.affinity.title())
    stats = dict(strength=11 + floor * 2, dexterity=9 + floor, intelligence=11 + floor * 2,
                 vitality=10 + floor * 2, luck=8 + floor)
    hp = (145 + floor * 40) if encounter == 3 else (60 + floor * 19)
    mp = 50 + floor * 5
    values.update(**stats, max_hp=hp, hp=hp, max_mp=mp, mp=mp)
    fighter = Fighter.snapshot(SimpleNamespace(**values), spec.name)
    # Same authored class/affinity mechanics, lower NPC damage for attrition
    # across four encounters; bosses differ through their named action policy.
    fighter.rule = replace(fighter.rule, damage_scale=fighter.rule.damage_scale * (0.42 if encounter == 3 else 0.24))
    fighter.signature_name = spec.abilities[1]
    fighter.weapon = spec.abilities[0]
    if floor == 4 and encounter == 1 and alignment == "veyra":
        fighter.name = "Oathbound Iron Penitent"
        fighter.affinity, fighter.affinity_name = "shadow", "Shadow"
    return fighter


def restore_fighter(values):
    copied = dict(values)
    copied["rule"] = CombatRule(**copied["rule"])
    return Fighter(**copied)


def enemy_intent(floor, encounter, battle):
    """Telegraph the existing deterministic action policy without advancing it."""
    world = world_for(floor)
    spec = world.boss if encounter == 3 else world.enemies[encounter]
    turn = battle.get("turn", 0) + 1
    move = spec.abilities[(turn - 1) % len(spec.abilities)]
    detail = "attack"
    if turn % 3 == 0 and spec.behavior in {"recover", "ward"}:
        detail = "restore HP" if spec.behavior == "recover" else "raise a shield"
    elif spec.behavior == "drain" and turn % 2 == 0:
        detail = "attack and drain MP"
    elif spec.behavior == "execute":
        detail = "attack; stronger below half player HP"
    elif spec.behavior == "pressure":
        detail = "attack; stronger above half enemy HP"
    elif spec.behavior == "mirror":
        detail = "attack; gains evasion against a signature"
    return f"{battle['enemy']['name']} prepares {move} ({detail})."


class DungeonCombat(DuelEngine):
    def __init__(self, player, enemy, seed, *, floor, encounter, turn=0):
        super().__init__(player, enemy, seed)
        self.floor, self.encounter = floor, encounter
        self.state.round = turn

    @classmethod
    def restore(cls, saved, seed, floor, encounter):
        return cls(restore_fighter(saved["player"]), restore_fighter(saved["enemy"]),
                   seed, floor=floor, encounter=encounter, turn=saved["turn"])

    def export(self):
        return dict(player=asdict(self.state.left), enemy=asdict(self.state.right),
                    turn=self.state.round, log=self.state.log[-8:])

    def player_turn(self, action):
        if action not in {"attack", "ability", "guard"}:
            raise ValueError("Choose Attack, Ability or Guard")
        state = self.state
        player, enemy = state.left, state.right
        if action == "ability" and not player.signature:
            raise ValueError("Your saved signature has no supported combat effect")
        if action == "ability" and (player.mp < (16 if player.passive == "discount" and player.skills_used == 0 else 22) or player.skills_used >= 2):
            raise ValueError("This encounter's ability is exhausted or needs more MP")
        state.log = []
        state.round += 1
        state.moves = state.round * 2
        # Seed + turn is recoverable after restart; failed transactions replay
        # exactly the same turn without persisting a large random-state array.
        self.rng = Random(state.seed + state.round * 7919)
        if state.round == 1:
            self.activate_passive(player)
            self.activate_passive(enemy)
        if action == "guard":
            old_shield, old_mp = player.shield, player.mp
            player.shield = min(round(player.max_hp * 0.30), player.shield + round(player.max_hp * 0.12))
            player.mp = min(player.max_mp, player.mp + 8)
            state.log.append(f"You guard: +{player.shield - old_shield} shield for incoming damage "
                             f"({player.shield} total); +{player.mp - old_mp} MP.")
        else:
            self.attack(player, enemy, action == "ability")
        if enemy.hp:
            self.enemy_turn()
        # Reuse status/affinity DOT handling, but our separate 60-turn ceiling
        # replaces the ordinary duel's automatic time-limit verdict.
        if state.round < 20:
            self.end_round()
        else:
            old_round = state.round
            state.round = 1
            self.end_round()
            state.round = old_round
        if state.round >= 60 and not state.finished:
            player.hp = 0
            state.log.append("Your soul can no longer sustain this battle. Return to sanctuary.")
        if not player.hp or not enemy.hp:
            state.finished = True
            state.winner_id = player.user_id if player.hp else enemy.user_id
        return state

    def enemy_turn(self):
        state = self.state
        enemy, player = state.right, state.left
        world = world_for(self.floor)
        spec = world.boss if self.encounter == 3 else world.enemies[self.encounter]
        turn = state.round
        move = spec.abilities[(turn - 1) % len(spec.abilities)]
        enemy.weapon = move
        if spec.behavior == "recover" and turn % 3 == 0:
            amount = self.heal(enemy, enemy.max_hp // 12)
            state.log.append(f"{enemy.name} uses {move}: restores {amount} HP.")
        elif spec.behavior == "ward" and turn % 3 == 0:
            enemy.shield = min(enemy.max_hp // 5, enemy.shield + enemy.max_hp // 10)
            state.log.append(f"{enemy.name} uses {move}: a ward rises.")
        else:
            original = enemy.rule
            if spec.behavior == "execute" and player.hp < player.max_hp // 2:
                enemy.rule = replace(original, damage_scale=original.damage_scale * 1.4)
            elif spec.behavior == "pressure" and enemy.hp > enemy.max_hp // 2:
                enemy.rule = replace(original, damage_scale=original.damage_scale * 1.2)
            elif spec.behavior == "mirror" and player.last_move == player.signature_name:
                self.status(enemy, "evasion", 1)
            self.attack(enemy, player, False)
            enemy.rule = original
            if spec.behavior == "drain" and turn % 2 == 0:
                drained = min(player.mp, 5 + self.floor)
                player.mp -= drained
                state.log.append(f"{move} drains {drained} MP.")
