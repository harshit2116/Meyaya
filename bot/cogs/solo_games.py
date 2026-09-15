"""Small replayable solo games. All choices and scoring are local - no model calls."""

from __future__ import annotations
import asyncio
from random import SystemRandom
import discord
from discord.ext import commands
from bot.utils.embeds import meyaya_embed

RNG = SystemRandom()
QUESTIONS = (
    (
        "The group chat has 300 unread messages.",
        ("Read every message", "Ask for a summary", "Send a meme"),
        (0, 1, 2),
    ),
    (
        "Your team finds a mysterious button.",
        ("Check the manual", "Ask everyone first", "Press it with a stick"),
        (0, 1, 2),
    ),
    (
        "A dragon wants your lunch.",
        ("Negotiate a trade", "Share half", "Offer yesterday's homework"),
        (0, 1, 2),
    ),
    (
        "The server needs a new mascot.",
        ("Run a vote", "Adopt the shy cat", "Nominate the broken printer"),
        (0, 1, 2),
    ),
    ("You arrive early to a party.", ("Help set up", "Find the host", "Become the DJ"), (0, 1, 2)),
    (
        "Someone challenges you to karaoke.",
        ("Pick a song you know", "Sing a duet", "Perform the loading music"),
        (0, 1, 2),
    ),
    (
        "Your spaceship has one spare room.",
        ("Build a workshop", "Make a cozy lounge", "Install a ball pit"),
        (0, 1, 2),
    ),
    (
        "A wizard offers a tiny power.",
        ("Always find your keys", "Make friends with cats", "Summon one dramatic spotlight"),
        (0, 1, 2),
    ),
)
# Each step's outcome changes resources and the next scene shown.
ESCAPES = (
    (
        "The mall after closing",
        [
            (
                "The shutters are down. How do you start?",
                ("Find the floor map", "Call out for security", "Climb a display"),
                (2, 1, -1),
            ),
            (
                "A security robot rolls toward you.",
                ("Show your shopping receipt", "Ask it for directions", "Race it"),
                (2, 1, -2),
            ),
            (
                "The exit corridor is dark.",
                ("Use the emergency lights", "Follow the wall", "Sprint blindly"),
                (2, 1, -2),
            ),
            (
                "The staff door needs a code.",
                ("Check the evacuation notice", "Wait for the guard", "Try 1234"),
                (2, 1, -1),
            ),
        ],
    ),
    (
        "The runaway snack train",
        [
            (
                "Your train has passed your stop.",
                ("Check the route display", "Ask the conductor", "Pull a random lever"),
                (2, 1, -2),
            ),
            (
                "A trolley blocks the corridor.",
                ("Secure its wheels", "Ask another passenger to help", "Surf on it"),
                (2, 1, -1),
            ),
            (
                "The intercom crackles.",
                ("Read the carriage number", "Explain calmly", "Sing for attention"),
                (2, 1, -1),
            ),
            (
                "The next platform approaches.",
                ("Use the marked exit", "Follow the conductor", "Jump before it stops"),
                (2, 1, -2),
            ),
        ],
    ),
)
SUSPECTS = ("Pip the baker", "Nova the DJ", "Ash the gardener")
MYSTERIES = (
    (
        "Who took the festival trophy?",
        0,
        (
            "A floury handprint is on the empty shelf.",
            "Nova was onstage in a continuous recording.",
            "Ash's muddy boots never entered the trophy room.",
        ),
    ),
    (
        "Who hid the karaoke microphone?",
        1,
        (
            "The hiding box contains a fresh playlist in Nova's handwriting.",
            "Pip was handing out cakes on the terrace.",
            "Ash found the box but could not open its DJ-only lock.",
        ),
    ),
    (
        "Who swapped the prize roses for plastic ones?",
        2,
        (
            "The real roses are in Ash's locked greenhouse.",
            "Nova's delivery contained only speakers.",
            "Pip's sealed bakery order had no flowers.",
        ),
    ),
)


class SoloView(discord.ui.View):
    def __init__(self, owner, kind, release):
        super().__init__(timeout=180)
        self.owner, self.kind, self.release = owner, kind, release
        self.lock = asyncio.Lock()
        self.message = None
        self.step = 0
        self.score = 0
        self.scores = [0, 0, 0]
        self.closed = False
        self.revision = 0
        self.questions = RNG.sample(QUESTIONS, 6)
        self.escape = RNG.choice(ESCAPES)
        self.mystery = RNG.choice(MYSTERIES)
        self.clues = []
        self.feedback = ""
        self.render_buttons()

    def choices(self):
        if self.kind == "escape":
            return self.escape_scene()[1]
        if self.kind == "personalitytest":
            return self.questions[self.step][1]
        return ("Inspect clue",) + SUSPECTS

    def escape_scene(self):
        if self.step == 2 and self.score <= 0:
            return (
                "Your detour leads to a locked maintenance room. A radio is blinking.",
                ("Radio for a safe route", "Read the wall map", "Shake the locked door"),
                (2, 1, -2),
            )
        if self.step == 3 and self.score < 4:
            return (
                "You reach a staffed checkpoint instead of the exit. How do you get help?",
                ("Explain what happened", "Show where you got lost", "Pretend to be the manager"),
                (2, 1, -2),
            )
        return self.escape[1][self.step]

    def render_buttons(self):
        self.clear_items()
        revision = self.revision
        for index, label in enumerate(self.choices()):
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
            if self.kind == "detective" and index == 0 and len(self.clues) >= 2:
                button.disabled = True

            async def callback(interaction, choice=index, version=revision):
                await self.choose(interaction, choice, version)

            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner:
            await interaction.response.send_message(
                "Start your own game to make choices.", ephemeral=True
            )
            return False
        return True

    def embed(self):
        if self.kind == "escape":
            text = self.escape_scene()[0]
            return meyaya_embed(
                self.escape[0], f"Turn {self.step + 1}/4\n{self.feedback}\n\n{text}", icon="🔑"
            )
        if self.kind == "personalitytest":
            return meyaya_embed(
                "Personality Test",
                f"Question {self.step + 1}/6\n\n{self.questions[self.step][0]}",
                icon="🎭",
            )
        return meyaya_embed(
            "Detective",
            self.mystery[0]
            + "\nInspect up to two clues, then accuse one suspect.\n\n"
            + "\n".join(self.clues),
            icon="🔎",
        )

    async def choose(self, interaction, choice, revision):
        async with self.lock:
            if self.closed or revision != self.revision:
                await interaction.response.send_message(
                    "That choice has already been processed.", ephemeral=True
                )
                return
            self.revision += 1
            result = None
            if self.kind == "detective":
                if choice == 0:
                    if len(self.clues) >= 2:
                        await interaction.response.send_message(
                            "No clues left. Make your accusation.", ephemeral=True
                        )
                        return
                    self.clues.append(self.mystery[2][len(self.clues)])
                else:
                    correct = choice - 1 == self.mystery[1]
                    result = (
                        ("Case solved!" if correct else "Wrong suspect!")
                        + "\n"
                        + SUSPECTS[self.mystery[1]]
                        + " did it.\n\n"
                        + "\n".join(self.mystery[2])
                    )
            elif self.kind == "escape":
                change = self.escape_scene()[2][choice]
                self.score += change
                self.feedback = (
                    "That helped. You found a safer route."
                    if change > 0
                    else "That backfired. You lost time and had to retreat."
                )
                self.step += 1
                if self.score < -2 and self.step >= 3:
                    result = "Your shortcut went sideways. Staff rescued you - along with your bruised dignity."
                elif self.step == 4:
                    result = (
                        "You escaped smoothly, with snacks intact!"
                        if self.score >= 6
                        else "You made it out, just as staff arrived to ask what happened."
                    )
            else:
                self.scores[self.questions[self.step][2][choice]] += 1
                self.step += 1
                if self.step == 6:
                    winner = max(range(3), key=lambda i: self.scores[i])
                    result = (
                        "The Pocket Strategist - you bring a plan, a backup plan and spare batteries.",
                        "The Cozy Diplomat - you could negotiate peace over a shared cookie.",
                        "The Plot Twist - nobody knows your next move, including you.",
                    )[winner]
                    
            if result:
                self.closed = True
                self.clear_items()
                self.stop()
                self.release()
                await interaction.response.edit_message(
                    embed=meyaya_embed("Game Result", result, icon="✨"), view=self
                )
            else:
                self.render_buttons()
                await interaction.response.edit_message(embed=self.embed(), view=self)

    async def on_timeout(self):
        async with self.lock:
            self.closed = True
            self.clear_items()
            self.release()
            if self.message:
                try:
                    await self.message.edit(
                        embed=meyaya_embed(
                            "Game expired",
                            "No choice for 3 minutes. Start again whenever you're ready.",
                        ),
                        view=self,
                    )
                except discord.HTTPException:
                    pass


class SoloGamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = {}

    async def start(self, ctx, kind):
        key = (ctx.guild.id if ctx.guild else 0, ctx.author.id)
        if key in self.active:
            await ctx.send(
                "Finish your current solo game or wait for its 3-minute inactivity timeout."
            )
            return
        view = SoloView(ctx.author.id, kind, lambda: self.active.pop(key, None))
        self.active[key] = view
        try:
            view.message = await ctx.send(embed=view.embed(), view=view)
        except Exception:
            self.active.pop(key, None)
            view.stop()
            raise

    async def cog_unload(self):
        for view in list(self.active.values()):
            view.stop()
        self.active.clear()

    @commands.hybrid_command(
        description="Escape a short adventure using four branching choices. No AI."
    )
    async def escape(self, ctx):
        await self.start(ctx, "escape")

    @commands.hybrid_command(description="Inspect clues and accuse one of three suspects. No AI.")
    async def detective(self, ctx):
        await self.start(ctx, "detective")

    @commands.hybrid_command(
        description="Answer six funny questions for a playful personality result. No AI."
    )
    async def personalitytest(self, ctx):
        await self.start(ctx, "personalitytest")


async def setup(bot):
    await bot.add_cog(SoloGamesCog(bot))
