"""Seeded, Discord-independent temporary combat. Never mutate an ORM profile."""

from dataclasses import dataclass, field
from random import Random

from bot.data.fantasy import CLASSES, RARITIES
from bot.data.fantasy_combat import (
    ARENAS,
    CLASS_COMBAT,
    WEAPON_COMBAT,
    ELEMENT_ADVANTAGES,
    CombatRule,
)

MAX_ROUNDS = 20  # Safety ceiling, not the intended length of a fight.
RULES_VERSION = 5
MIN_MOVES = 4


@dataclass
class Fighter:
    user_id: int
    name: str
    class_id: str
    class_name: str
    subclass: str
    title: str
    level: int
    affinity: str
    affinity_name: str
    weapon: str
    weapon_family: str
    rarity: int
    passive_name: str
    passive: str
    signature_name: str
    signature: str
    strength: int
    dexterity: int
    intelligence: int
    vitality: int
    luck: int
    max_hp: int
    max_mp: int
    hp: int
    mp: int
    rule: CombatRule
    statuses: dict[str, int] = field(default_factory=dict)
    shield: int = 0
    passive_used: bool = False
    damage_dealt: int = 0
    damage_taken: int = 0
    critical_hits: int = 0
    dodges: int = 0
    skills_used: int = 0
    last_move: str = ""
    is_boss: bool = False
    alignment: str = ""
    resonance_used: bool = False
    erasure_hits: int = 0
    boss_key: str = ""

    @classmethod
    def snapshot(cls, profile, name):
        rule = CLASS_COMBAT.get(profile.class_id, CombatRule("hybrid", "", ""))
        authored = CLASSES.get(profile.class_id)
        passive = (
            rule.passive
            if authored
            and profile.passive_name == authored.passive
            and profile.passive_id.startswith(profile.class_id + ":")
            else ""
        )
        signature = (
            rule.signature
            if authored
            and profile.signature_name == authored.signature
            and profile.signature_id.startswith(profile.class_id + ":")
            else ""
        )
        fighter = cls(
            profile.user_id,
            str(name)[:80],
            profile.class_id,
            profile.class_name,
            getattr(profile, "subclass_name", ""),
            getattr(profile, "fantasy_title", ""),
            getattr(profile, "level", 1),
            profile.affinity_id,
            profile.affinity_name,
            profile.weapon_name,
            profile.weapon_family,
            RARITIES.index(profile.weapon_rarity) if profile.weapon_rarity in RARITIES else 0,
            profile.passive_name,
            passive,
            profile.signature_name,
            signature,
            profile.strength,
            profile.dexterity,
            profile.intelligence,
            profile.vitality,
            profile.luck,
            profile.max_hp,
            profile.max_mp,
            profile.max_hp,
            profile.max_mp,
            rule,
        )
        fighter.is_boss = bool(getattr(profile, "is_meyaya_boss", False))
        fighter.boss_key = getattr(profile, "boss_key", "meyaya" if fighter.is_boss else "")
        from bot.data.fantasy_alignment import patron_for

        patron = patron_for(profile)
        fighter.alignment = getattr(profile, "alignment", "") if patron else ""
        return fighter


@dataclass
class Battle:
    left: Fighter
    right: Fighter
    seed: int
    arena: tuple
    round: int = 0
    moves: int = 0
    last_actor: int | None = None
    log: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    winner_id: int | None = None
    finished: bool = False
    verdict: str = ""
    finisher: str = ""
    boss_form: str = ""
    counter_pattern: str = ""
    memory_count: int = 0
    dialogue: str = ""


def element_multiplier(attacker, defender):
    if (attacker, defender) in ELEMENT_ADVANTAGES:
        return 1.1
    if (defender, attacker) in ELEMENT_ADVANTAGES:
        return 0.9
    return 1.0


class DuelEngine:
    def __init__(self, left, right, seed):
        self.rng = Random(seed)
        self.state = Battle(left, right, seed, self.rng.choice(ARENAS))
        self._turns = []

    def initiative(self, fighter):
        return fighter.dexterity + fighter.rule.initiative + self.rng.uniform(-2, 2)

    def heal(self, fighter, amount):
        if fighter.alignment == "meyaya":
            amount = round(amount * 1.10)
        recovered = min(max(0, amount), fighter.max_hp - fighter.hp)
        fighter.hp += recovered
        return recovered

    def absorb(self, fighter, amount):
        blocked = min(fighter.shield, amount)
        fighter.shield -= blocked
        taken = min(fighter.hp, amount - blocked)
        fighter.hp -= taken
        fighter.damage_taken += taken
        return taken, blocked

    def status(self, fighter, name, turns=2):
        if name in fighter.statuses or len(fighter.statuses) < 3:
            fighter.statuses[name] = turns

    def activate_passive(self, f):
        if f.alignment == "meyaya" and not f.resonance_used:
            f.resonance_used = True
            f.shield += max(1, round(f.max_hp * 0.04))
            self.state.log.append(f"🌸 {f.name}'s Origin Resonance raises Prismatic Guard.")
        if f.passive_used or not f.passive:
            return
        if f.passive == "renew" and f.hp > f.max_hp * 0.5:
            return
        f.passive_used = True
        effect = f.passive
        if effect == "shield":
            f.shield += round(f.max_hp * 0.05)
        elif effect == "renew":
            self.heal(f, round(f.max_hp * 0.06))
        elif effect in {"evasion", "empower", "crit", "resist", "precision"}:
            self.status(f, effect, 2)
        self.state.log.append(f"✦ {f.name}'s {f.passive_name} awakens ({effect}).")

    def attack(self, a, b, signature=False):
        family_mult, weapon_crit, _ = WEAPON_COMBAT.get(a.weapon_family, (1, 0, 0))
        skill = a.signature_name if signature else a.weapon
        a.last_move = skill
        if signature:
            cost = 22 - (6 if a.passive == "discount" and a.skills_used == 0 else 0)
            if a.mp < cost or a.skills_used >= 2:
                return self.attack(a, b, False)
            a.mp -= cost
            a.skills_used += 1
            if a.passive == "refund" and a.skills_used == 1:
                a.mp = min(a.max_mp, a.mp + 5)
            if a.signature == "heal":
                amount = self.heal(a, round(a.max_hp * 0.10))
                self.state.log.append(f"☾ {a.name} invokes {skill}, restoring {amount} HP.")
            elif a.signature == "guard":
                a.shield = min(round(a.max_hp * 0.25), a.shield + round(a.max_hp * 0.12))
                self.state.log.append(f"◇ {a.name}'s {skill} raises a {a.shield} HP ward.")
            elif a.signature == "evasion":
                self.status(a, "evasion", 2)
            elif a.signature == "weaken":
                self.status(b, "weaken", 2)

        dodge = min(
            0.20,
            0.025
            + b.dexterity * 0.0025
            + WEAPON_COMBAT.get(b.weapon_family, (1, 0, 0))[2]
            + (0.05 if "evasion" in b.statuses else 0),
        )
        if signature and a.signature == "precise":
            dodge *= 0.3
        if "precision" in a.statuses:
            dodge *= 0.5
        if self.rng.random() < dodge:
            b.dodges += 1
            self.state.log.append(f"✧ DODGE · {b.name} avoids {a.name}'s {skill}! No damage.")
            return
        crit_chance = min(
            0.22, 0.035 + a.luck * 0.003 + weapon_crit + (0.04 if "crit" in a.statuses else 0)
        )
        critical = self.rng.random() < crit_chance
        offense = (
            a.intelligence
            if a.rule.mode == "magic"
            else (
                max(a.strength, a.dexterity)
                if a.rule.mode == "agile"
                else (
                    a.strength
                    if a.rule.mode == "physical"
                    else max(a.strength, a.intelligence) * 0.75
                    + min(a.strength, a.intelligence) * 0.25
                )
            )
        )
        # Saved resource distribution favours tanks. Bounded caster/agile scaling
        # offsets that advantage without replacing anyone's actual HP/stat rolls.
        mode_scale = {"physical": 1.05, "agile": 1.15, "hybrid": 1.22, "magic": 1.30}[a.rule.mode]
        raw = (
            (18 + offense * 1.10 + a.dexterity * 0.12 - b.vitality * 0.20)
            * mode_scale
            * a.rule.damage_scale
        )
        if a.class_id == "starcaller":
            raw *= 0.97  # Retune burst scaling for knockout-led v4 pacing.
        raw *= family_mult * (1 + a.rarity * 0.01) * self.rng.uniform(0.90, 1.10)
        raw *= element_multiplier(a.affinity, b.affinity)
        raw *= 1 - min(0.12, b.rule.mitigation + (0.05 if "resist" in b.statuses else 0))
        if "empower" in a.statuses:
            raw *= 1.08
        if "weaken" in a.statuses:
            raw *= 0.9
        if signature:
            raw *= (
                1.38
                if a.signature == "burst"
                else (
                    1.28
                    if a.signature in {"break", "precise"}
                    else 0.90 if a.signature in {"heal", "guard"} else 1.12
                )
            )
        if critical:
            raw *= 1.30
            a.critical_hits += 1
        # Only the opening exchange is paced: two hits plus DOT stay below full
        # HP. From move four onward, actual offence/defence and skills decide KOs.
        endurance_scale = min(1.3, max(0.8, (b.max_hp / 160) ** 0.5))
        damage = max(1, round(raw * 0.95 * endurance_scale))
        if self.state.moves < MIN_MOVES - 1:
            damage = min(damage, max(1, int(b.max_hp * 0.45)))
        if signature and a.signature == "break":
            b.shield = round(b.shield * 0.5)
        if a.alignment == "veyra" and a.erasure_hits < 2:
            a.erasure_hits += 1
            b.shield = round(b.shield * 0.85)
            if not a.resonance_used:
                a.resonance_used = True
                self.status(b, "erasure_trace", 2)
                self.state.log.append(f"🩸 {a.name}'s Erasure Resonance leaves an Erasure Trace.")
        taken, blocked = self.absorb(b, damage)
        a.damage_dealt += taken
        verb = self.rng.choice(("unleashes", "channels", "answers with"))
        self.state.log.append(
            f"{'✹ CRITICAL · ' if critical else '⚔ '}{a.name} {verb} {skill} - {taken} damage{' · ' + str(blocked) + ' shield absorbed' if blocked else ''}."
        )
        if signature and a.affinity in {"fire", "blood"} and b.hp:
            self.status(b, "burn" if a.affinity == "fire" else "bleed", 2)
        if not b.hp:
            self.state.finisher = skill

    def end_round(self):
        for f in (self.state.left, self.state.right):
            for status in tuple(f.statuses):
                if status in {"burn", "bleed", "erasure_trace"} and f.hp:
                    scale = 0.015 if status == "erasure_trace" else 0.01
                    damage, _ = self.absorb(f, max(1, int(f.max_hp * scale)))
                    other = self.state.right if f is self.state.left else self.state.left
                    other.damage_dealt += damage
                    if not f.hp:
                        self.state.finisher = status.title()
                    label = status.replace("_", " ").title()
                    self.state.log.append(f"✦ {f.name}'s {label} deals {damage} damage.")
                f.statuses[status] -= 1
                if f.statuses[status] <= 0:
                    del f.statuses[status]
        a, b = self.state.left, self.state.right
        if not a.hp or not b.hp:
            self.state.finished = True
            self.state.winner_id = a.user_id if a.hp else b.user_id if b.hp else None
            self.state.verdict = "Knockout" if self.state.winner_id else "Simultaneous knockout"
        elif self.state.round >= MAX_ROUNDS:
            self.state.finished = True
            difference = a.hp / a.max_hp - b.hp / b.max_hp
            self.state.winner_id = (
                None if abs(difference) <= 0.03 else a.user_id if difference > 0 else b.user_id
            )
            self.state.verdict = (
                "Arena verdict · remaining HP percentage"
                if self.state.winner_id
                else "Arena verdict · evenly matched"
            )

    def advance_move(self):
        """One fighter action, including misses; round-end effects join its last move."""
        if self.state.finished:
            return self.state
        self.state.log = []
        if not self._turns:
            self.state.round += 1
            self._turns = [self.state.left, self.state.right]
            self.rng.shuffle(self._turns)
            self._turns.sort(key=self.initiative, reverse=True)
        a = self._turns.pop(0)
        b = self.state.right if a is self.state.left else self.state.left
        if a.hp and b.hp:
            self.activate_passive(a)
            self.activate_passive(b)
            self.attack(a, b, bool(a.signature) and self.state.round in {2, 4})
            self.state.moves += 1
            self.state.last_actor = a.user_id
        if not self._turns or not a.hp or not b.hp:
            self.end_round()
        if self.state.finished:
            self._turns.clear()
        self.state.history = (self.state.history + self.state.log)[-3:]
        return self.state

    def advance(self):
        """Compatibility helper for offline simulations: finish the current round."""
        self.advance_move()
        while self._turns and not self.state.finished:
            self.advance_move()
        return self.state
