"""Temporary Veyra encounters and a seeded Origin-versus-Erasure spectacle."""

from bot.services.fantasy_duel import DuelEngine, MIN_MOVES
from bot.services.meyaya_boss_combat import BossDuelEngine


class VeyraDuelEngine(BossDuelEngine):
    def __init__(self, player, boss, seed):
        super().__init__(player, boss, seed)
        boss.class_name = self.state.boss_form = "Void Revenant"
        boss.subclass = "Erasure Active"
        self.state.counter_pattern = "ABYSS MEMORY / WARD FRACTURE / WORLD SEVER"
        self.state.dialogue = "There is no ending here. Only absence."
        self.abyss_marks = 0

    def attack(self, attacker, defender, signature=False):
        if attacker is self.player:
            DuelEngine.attack(self, attacker, defender, signature)
            self.state.log = [
                line.rsplit(" · ", 1)[0] + "." if "shield absorbed" in line else line
                for line in self.state.log
            ]
            self.abyss_marks = min(3, self.abyss_marks + 1)
            self.state.memory_count = self.abyss_marks
            self.memory_resistance = self.abyss_marks * 0.035
            if self.abyss_marks == 2:
                self.state.log.append("ABYSS MEMORY · Veyra has learned the shape of your soul.")
                self.state.dialogue = "I remember you. That is not a kindness."
            return
        self.boss_actions += 1
        sever = self.boss_actions % 3 == 0 and attacker.mp >= 24
        attacker.last_move = "World Sever" if sever else "Mournfang · Silent Ruin"
        if sever:
            attacker.mp -= 24
            attacker.skills_used += 1
            defender.shield = round(defender.shield * 0.35)
            defender.statuses.pop("resist", None)
            self.state.dialogue = "Even your protection has an ending."
        dodge = min(0.12, 0.025 + defender.dexterity * 0.0015)
        if self.rng.random() < dodge:
            defender.dodges += 1
            self.state.log.append(f"DODGE · {defender.name} escapes Mournfang's edge.")
            return
        pressure = 0.27 if sever else 0.17 + self.abyss_marks * 0.015
        damage = max(1, round(defender.max_hp * pressure * self.rng.uniform(0.90, 1.10)))
        if self.state.moves < MIN_MOVES - 1:
            damage = min(damage, max(0, defender.hp - 1))
        taken, _ = self.absorb(defender, damage)
        attacker.damage_dealt += taken
        self.state.log.append(f"{attacker.last_move} · {taken} damage to {defender.name}.")
        if not defender.hp:
            self.state.finisher = attacker.last_move


class PatronClashEngine(DuelEngine):
    def __init__(self, origin, erasure, seed):
        super().__init__(origin, erasure, seed)
        self.state.arena = ("Origin / Erasure · Worldfall", "#0c0916", "#ff617e", "prism")
        self.state.boss_form = "ORIGIN VERSUS ERASURE"
        self.state.counter_pattern = "TWO AUTHORITIES. ONE SURVIVING REALITY."
        self.state.dialogue = "Meyaya: Then I will write a beginning you cannot erase."
        for fighter in (origin, erasure):
            fighter.hp = fighter.max_hp = 2400
            fighter.mp = fighter.max_mp = 800
            fighter.passive = fighter.signature = fighter.alignment = ""
        self.used_phases = set()

    def attack(self, attacker, defender, signature=False):
        phase = min(2, self.state.moves // 4)
        phases = ("THE FIRST FRACTURE", "REALITY UNRAVELS", "THE LAST POSSIBLE WORLD")
        self.state.boss_form = phases[phase]
        self.state.memory_count = phase + 1
        if phase not in self.used_phases:
            self.used_phases.add(phase)
            self.state.log.append(f"WORLD EVENT · {phases[phase]}")
            self.state.dialogue = (
                "Meyaya: You can break the world. You cannot make me abandon it.",
                "Veyra: Then I will erase the place where hope begins.",
                "Meyaya: One last bloom. Veyra: One last silence.",
            )[phase]
        origin = attacker.boss_key == "meyaya"
        skill = (
            ("Prism Cascade", "Genesis Crown", "Origin Protocol · The First Dawn")
            if origin
            else ("World Sever", "Abyss Dominion", "Enemy of All · Absolute Erasure")
        )[phase]
        attacker.last_move = skill
        attacker.mp = max(0, attacker.mp - (40 + phase * 20))
        attacker.skills_used += 1
        damage = round(self.rng.uniform(220, 320) * (1 + phase * 0.35))
        if origin:
            attacker.shield = min(160, attacker.shield + 70)
        else:
            defender.shield = round(defender.shield * 0.4)
        if self.state.moves < 9:
            damage = min(damage, max(0, defender.hp - 1))
        taken, _ = self.absorb(defender, damage)
        attacker.damage_dealt += taken
        self.state.log.append(
            f"{attacker.name} · {skill} · "
            + ("a shattered sky blooms again." if origin else "the horizon vanishes into silence.")
        )
        if not defender.hp:
            self.state.finisher = skill

    def advance_move(self):
        self.state.dialogue = ""
        return super().advance_move()

    def end_round(self):
        super().end_round()
        if not self.state.finished and self.state.round >= 8:
            self.state.finished = True
            left, right = self.state.left, self.state.right
            self.state.winner_id = (
                None
                if left.hp == right.hp
                else left.user_id if left.hp > right.hp else right.user_id
            )
            self.state.verdict = "Worldfall verdict · the surviving authority"
