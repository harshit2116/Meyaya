"""Single continuous, seeded boss encounter; no profile mutations or AI calls."""

from dataclasses import asdict
from bot.data.fantasy_combat import CombatRule, ELEMENT_ADVANTAGES
from bot.services.fantasy_duel import DuelEngine, MIN_MOVES, element_multiplier

FORMS = {
    "physical": ("Glassblade Seraph", "PHYSICAL RESIST / REACTIVE WARD"),
    "magic": ("Prism Oracle", "MAGIC RESIST / COUNTER-CAST"),
    "tank": ("Bloom Executioner", "WARD PIERCE / PRESSURE"),
    "agile": ("Mirror Huntress", "PREDICTION / ANTI-EVASION"),
    "support": ("Ego Sovereign", "ANTI-HEAL / DISPEL"),
    "hybrid": ("Star-Petal Arcanist", "PRISM RESIST / INITIATIVE"),
}


def archetype(fighter):
    # Authored mechanics, not guessed class-name substring matches.
    if fighter.signature == "heal" or fighter.passive == "renew":
        return "support"
    if fighter.signature == "guard" or fighter.rule.mitigation >= 0.04:
        return "tank"
    if fighter.rule.mode == "agile":
        return "agile"
    return fighter.rule.mode if fighter.rule.mode in FORMS else "hybrid"


def public_fighter(fighter):
    """Use at every serialization boundary, including AI-visible command memory."""
    if not fighter.is_boss:
        return asdict(fighter)
    return dict(
        user_id=fighter.user_id,
        name=fighter.name,
        class_name=fighter.class_name,
        recorded_class="Soulweaver",
        title=fighter.title,
        weapon=fighter.weapon,
        affinity=fighter.affinity_name,
        hp="UNKNOWN",
        max_hp="UNKNOWN",
        mp="UNKNOWN",
        max_mp="UNKNOWN",
        potential="ANALYSIS FAILED",
        passive="Spell Memory",
        signature="Prism Cascade",
        threat="BEYOND MEASUREMENT",
    )


class BossDuelEngine(DuelEngine):
    def __init__(self, player, boss, seed):
        super().__init__(player, boss, seed)
        self.player, self.boss = player, boss
        # Encounter-local only: never mutate either saved fantasy profile.
        boss.hp = boss.max_hp = max(10, player.max_hp * 10)
        boss.mp = boss.max_mp = max(10, player.max_mp * 10)
        for stat in ("strength", "dexterity", "intelligence", "vitality", "luck"):
            setattr(boss, stat, max(30, getattr(player, stat) * 2))
        self.pattern = archetype(player)
        self.ray_affinity = next(
            (a for a, b in sorted(ELEMENT_ADVANTAGES) if b == player.affinity), "arcane"
        )
        self.state.boss_form, self.state.counter_pattern = FORMS[self.pattern]
        boss.class_name = self.state.boss_form
        boss.subclass = "Recorded: Soulweaver"
        boss.passive, boss.signature = "", ""
        boss.rule = CombatRule(
            "magic", "", "", initiative=2 if self.pattern in {"agile", "hybrid"} else 0
        )
        self.observations = {}
        self.memory_resistance = 0.0
        self.reflected = False
        self.learned_signature = ""
        self.reactive_ward = False
        self.dialogue_seen = set()
        self.boss_actions = 0
        self.state.dialogue = {
            "physical": "You hit hard. I noticed.",
            "magic": "Spells are such honest little things. People aren't.",
            "tank": "You plan to outlast me? Adorable.",
            "support": "You came prepared to endure me. How sweet.",
            "agile": "I already know where your next step lands.",
            "hybrid": "Show me what makes your soul different.",
        }[self.pattern]

    def heal(self, fighter, amount):
        if fighter is self.player and self.pattern in {"support", "tank"}:
            amount = round(amount * 0.75)
        return super().heal(fighter, amount)

    def absorb(self, fighter, amount):
        if fighter is self.boss:
            resistance = (
                0.10
                if self.pattern in {"physical", "magic"}
                else 0.06 if self.pattern == "hybrid" else 0
            )
            amount = max(1, round(amount * (1 - resistance - self.memory_resistance)))
        return super().absorb(fighter, amount)

    def speak(self, trigger, line):
        if trigger not in self.dialogue_seen and len(self.dialogue_seen) < 3:
            self.dialogue_seen.add(trigger)
            self.state.dialogue = line

    def attack(self, a, b, signature=False):
        if a is self.player:
            old_crit = a.critical_hits
            old_skills = a.skills_used
            super().attack(a, b, signature)
            # Ordinary logs include numeric shield absorption. Mask that boss-only
            # detail without obscuring the player's own dealt damage.
            self.state.log = [
                line.rsplit(" · ", 1)[0] + "." if "shield absorbed" in line else line
                for line in self.state.log
            ]
            used_signature = a.skills_used > old_skills
            for key in (a.signature_name if used_signature else a.weapon_family, a.affinity_name):
                self.observations[key] = self.observations.get(key, 0) + 1
                if self.observations[key] == 2 and self.state.memory_count < 3:
                    self.state.memory_count += 1
                    self.memory_resistance = min(0.12, self.state.memory_count * 0.04)
                    self.state.log.append(f"✦ SPELL MEMORY · Meyaya has understood {key}.")
                    self.speak("memory", "Thank you. I understand it now.")
            if used_signature and not self.learned_signature:
                self.learned_signature = a.signature_name[:100]
                self.state.log.append(
                    f"🪞 SPELL MEMORY · {self.learned_signature} recorded for one reflection."
                )
            if self.pattern == "physical" and not self.reactive_ward:
                self.reactive_ward = True
                b.shield += round(b.max_hp * 0.06)
                self.status(b, "evasion", 2)
                self.state.log.append("◇ Everbloom opens a single reactive ward.")
            if a.critical_hits > old_crit:
                self.speak("critical", "Oh, that one actually hurt.")
            if b.hp <= b.max_hp * 0.25:
                self.speak("close", "Now you're making this interesting.")
            return
        self.boss_actions += 1
        reflected = bool(
            self.learned_signature and not self.reflected and self.boss_actions >= 3 and a.mp >= 18
        )
        cascade = self.boss_actions in {2, 4} and a.mp >= (16 if self.pattern == "magic" else 22)
        if reflected:
            # Only normalize a label into one capped attack, never execute copied
            # player skill code, chains, summons, or recursive reflections.
            self.reflected = True
            a.mp -= 18
            skill = f"Prism Reflection · {self.learned_signature}"
        else:
            skill = "Prism Cascade" if cascade else "Everbloom · Crystal Petals"
        a.last_move = skill
        if cascade:
            a.mp -= 16 if self.pattern == "magic" else 22
            a.skills_used += 1
        dodge = min(0.18, 0.025 + b.dexterity * 0.0025 + (0.05 if "evasion" in b.statuses else 0))
        if self.pattern == "agile":
            dodge *= 0.40
        if self.rng.random() < dodge:
            b.dodges += 1
            self.state.log.append(f"✧ DODGE · {b.name} escapes {skill}.")
            return
        critical = self.rng.random() < min(0.18, 0.04 + a.luck * 0.003)
        raw = 19 + a.intelligence * 1.1 + a.dexterity * 0.12 - b.vitality * 0.20
        raw *= self.rng.uniform(0.9, 1.1) * (1.22 if cascade else 1.12 if reflected else 1)
        raw *= 1.25 if critical else 1
        raw *= 1 - min(0.12, b.rule.mitigation + (0.05 if "resist" in b.statuses else 0))
        if "weaken" in a.statuses:
            raw *= 0.90
        if cascade:
            raw *= element_multiplier(self.ray_affinity, b.affinity)
        pressure = round(b.max_hp * 0.02) if self.pattern in {"tank", "support"} else 0
        damage = min(round(b.max_hp * 0.32), max(1, round(raw) + pressure))
        if self.state.moves < MIN_MOVES - 1:
            damage = min(damage, max(1, int(b.max_hp * 0.45)))
        if self.pattern == "tank":
            b.shield = round(b.shield * 0.65)
        elif self.pattern == "support" and cascade:
            b.statuses.pop("resist", None)  # One bounded dispel per Cascade.
        self.cascade_hits = []
        if cascade:
            taken = blocked = 0
            for ray in range(5):
                part = damage // 5 + int(ray < damage % 5)
                hit, ward = self.absorb(b, part)
                self.cascade_hits.append(hit)
                taken += hit
                blocked += ward
        else:
            taken, blocked = self.absorb(b, damage)
        a.damage_dealt += taken
        a.critical_hits += int(critical)
        self.state.log.append(
            f"{f'✦ Five {self.ray_affinity} flowering rays · ' if cascade else '🪞 ' if reflected else '🌸 '}{skill} - {taken} damage to {b.name}{' · ward softened the blow' if blocked else ''}."
        )
        if not b.hp:
            self.state.finisher = skill

    def advance_move(self):
        self.state.dialogue = ""
        return super().advance_move()
