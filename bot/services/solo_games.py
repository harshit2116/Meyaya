"""Local single-player state, independent of Discord message delivery."""

from dataclasses import dataclass
from random import SystemRandom

from bot.data.solo_games import ADVENTURES, CASES, PERSONALITIES, QUESTIONS, SUSPECT_NAMES, TRAITS

RNG = SystemRandom()
KINDS = ("escape", "detective", "personalitytest")


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    enabled: bool = True


class SoloGame:
    def __init__(self, kind, *, previous=None, rng=None):
        if kind not in KINDS:
            raise ValueError("Unknown solo game")
        rng = rng or RNG
        self.kind = kind
        self.step = 0
        self.done = False
        self.title = ""
        self.result = ""
        self.feedback = ""
        self.history = []
        self.inventory = set()
        self.time_left = 8
        self.scene = "start"
        self.scores = [0, 0, 0]
        self.clues = []
        self.accusing = False
        self.correct = None
        self.personality = None
        self.adventure_index = rng.choice([i for i in range(len(ADVENTURES))
                                          if previous is None or i != previous.adventure_index])
        self.case_index = rng.choice([i for i in range(len(CASES))
                                     if previous is None or i != previous.case_index])
        self.questions = rng.sample(list(QUESTIONS), 6)
        self.names = dict(zip(("a", "b", "c"), rng.sample(list(SUSPECT_NAMES), 3)))
        self.suspect_order = rng.sample(["a", "b", "c"], 3)
        self.order = []
        self.shuffle_options(rng)

    @property
    def adventure(self):
        return ADVENTURES[self.adventure_index]

    @property
    def case(self):
        return CASES[self.case_index]

    def shuffle_options(self, rng=None):
        rng = rng or RNG
        if self.kind == "escape":
            self.order = list(range(len(self.adventure.scenes[self.scene].choices)))
        elif self.kind == "personalitytest":
            self.order = list(range(3))
        else:
            return
        rng.shuffle(self.order)

    def actions(self):
        if self.done:
            return []
        if self.kind == "escape":
            choices = self.adventure.scenes[self.scene].choices
            return [Action(choices[i].key, choices[i].label +
                           (f" · needs {choices[i].requires}" if choices[i].requires and
                            choices[i].requires not in self.inventory else ""),
                           not choices[i].requires or choices[i].requires in self.inventory)
                    for i in self.order]
        if self.kind == "personalitytest":
            return [Action(str(i), self.questions[self.step][1][i]) for i in self.order]
        if self.accusing:
            return [Action("accuse:" + key, self.names[key]) for key in self.suspect_order] + [
                Action("back", "Back to evidence")]
        return [Action("clue:" + str(i), label, i not in self.clues)
                for i, (label, _) in enumerate(self.case.evidence)] + [
            Action("accuse", "Make an accusation", len(self.clues) >= 2)]

    def apply(self, key):
        if not any(a.key == key and a.enabled for a in self.actions()):
            raise ValueError("That choice is not available")
        if self.kind == "escape":
            choice = next(c for c in self.adventure.scenes[self.scene].choices if c.key == key)
            self.time_left = max(0, self.time_left - choice.cost)
            self.step += 1
            self.feedback = choice.outcome + f" (−{choice.cost} min)"
            self.history.append(choice.label)
            if choice.item:
                self.inventory.add(choice.item)
                self.feedback += f"\nCollected: **{choice.item}**."
            if self.time_left == 0:
                self.done = True
                self.title = "The scenic rescue"
                self.result = "The clock ran out before you reached the exit. Staff guide you out safely, with a story you will be hearing about for weeks."
            elif not choice.next_scene:
                self.done = True
                self.title = self.adventure.special_ending if key == "special" else "Made it out"
                self.result = choice.outcome + f"\n\nYou finished with **{self.time_left} minute{'s' if self.time_left != 1 else ''} to spare**."
            else:
                self.scene = choice.next_scene
                self.shuffle_options()
        elif self.kind == "detective":
            if key.startswith("clue:"):
                self.clues.append(int(key.split(":")[1]))
                self.feedback = "Evidence added to your notebook."
            elif key == "accuse":
                self.accusing = True
            elif key == "back":
                self.accusing = False
            else:
                accused = key.split(":")[1]
                self.correct = accused == "c"
                self.done = True
                self.title = "Case solved" if self.correct else "The wrong suspect"
                self.result = (f"You accused **{self.names[accused]}**. " +
                               ("The evidence supports your conclusion." if self.correct else
                                f"The culprit was **{self.names['c']}**.") +
                               "\n\n" + self.case.explanation.format(**self.names))
        else:
            selected = int(key)
            self.scores[selected] += 1
            self.history.append((self.questions[self.step][0], self.questions[self.step][1][selected], selected))
            self.step += 1
            if self.step == 6:
                self.done = True
                leaders = tuple(i for i, count in enumerate(self.scores) if count == max(self.scores))
                self.personality = leaders
                self.title, self.result = PERSONALITIES[leaders]
            else:
                self.shuffle_options()

    def quit(self):
        if not self.done:
            self.done = True
            self.title = "Run ended"
            self.result = "You ended this run. A fresh one is ready whenever you are."

    def presentation(self):
        """Title, description and compact fields for one message at every stage."""
        fields = []
        if self.done:
            title, text = self.title, self.result
            if self.kind == "escape":
                fields.extend((("Adventure", self.adventure.title, False),
                               ("Your route", " → ".join(self.history) or "No choices yet", False)))
            elif self.kind == "detective":
                fields.extend((("Case", self.case.title, False),
                               ("Evidence examined", f"{len(self.clues)}/4 leads", True)))
            else:
                fields.append(("Your mix", "\n".join(
                    f"**{trait}**  {'▰' * count}{'▱' * (6 - count)}  {count}/6"
                    for trait, count in zip(TRAITS, self.scores)), False))
                if self.history:
                    _, answer, trait = self.history[-1]
                    fields.append(("One choice that shaped this", f'“{answer}” leaned toward {TRAITS[trait].lower()}.', False))
        elif self.kind == "escape":
            title = self.adventure.title
            text = self.adventure.intro + "\n\n" + self.adventure.scenes[self.scene].text
            fields.append(("Progress", f"Scene {self.step + 1}/5", True))
            if self.feedback:
                fields.append(("Your last move", self.feedback, False))
        elif self.kind == "personalitytest":
            title = "Personality Test"
            text = self.questions[self.step][0] + "\n\nChoose what sounds most like you. There are no wrong answers."
            fields.append(("Progress", "▰" * self.step + "▱" * (6 - self.step) + f"  {self.step}/6 answered", False))
        else:
            title = self.case.title
            text = self.case.intro + "\n\n**Suspects:** " + ", ".join(self.names[k] for k in self.suspect_order)
            text += ("\n\nWho does the evidence point to? This decision closes the case." if self.accusing else
                     "\n\nChoose a lead to investigate. Examine at least two before making an accusation; you may inspect all four.")
            for i in self.clues:
                label, evidence = self.case.evidence[i]
                fields.append((label, evidence.format(**self.names), False))
            if not self.clues:
                fields.append(("Evidence notebook", "No evidence yet. Start with any lead below.", False))
        if self.kind == "escape":
            fields.extend((("In-game time", f"{'▰' * self.time_left}{'▱' * (8 - self.time_left)}  {self.time_left}/8 min", True),
                           ("Inventory", ", ".join(sorted(self.inventory)) or "Empty", True)))
        return title, text, fields
