"""Authored Erasure dialogue and the Origin/Erasure clash finale."""

import asyncio
from bot.services.meyaya_boss_presentation import BossPresentation, INTRO_GIF, VICTORY_GIF

VEYRA_INTRO_GIF = "https://klipy.com/gifs/skadi-alter"
VEYRA_VICTORY_GIF = "https://klipy.com/gifs/arknigh-skadi-arknights"
VEYRA_INTRO_SECONDS = 9.2


class VeyraPresentation(BossPresentation):
    embed_colour = 0xDC143C
    embed_title = "Mournfang"

    async def intro(self, state):
        await self.beat(
            "# Veyra.\n-# ENEMY OF ALL\n\n> **The Soul Interface did not invite her.**\n> **It cannot make her leave.**",
            gif=VEYRA_INTRO_GIF,
        )
        await asyncio.sleep(VEYRA_INTRO_SECONDS + 2 if self.message_has_gif else 2)
        self.message_has_gif = False
        await self.beat(
            "# ⚠ Hostile presence detected\n\n**Authority verification: REJECTED**\n**Containment: FAILED**\n\n*Something is erasing the spaces between your heartbeats.*"
        )
        await asyncio.sleep(1.5)
        await self.beat(
            "# Void Revenant\n\n**ABYSS MEMORY / WORLD SEVER**\n\n*I have seen the end of every world. You will not be the exception.*"
        )

    async def speak(self, state):
        if state.dialogue and self.speeches < 3:
            self.speeches += 1
            await self.beat(f"# Veyra\n\n**{state.dialogue}**")

    async def finish(self, state, *, history_note=""):
        won = state.winner_id == state.right.user_id
        text = (
            "# No one answers.\n\n> **You thought this was a battle.**\n\n## It was your final warning.\n\n-# VEYRA · ENEMY OF ALL"
            if won
            else (
                "# An impossible survivor.\n\n**You remain. Even after everything.**\n\n*Veyra lowers Mournfang. For the first time, the silence hesitates.*"
                if state.winner_id is not None
                else "# The silence breaks evenly.\n\n**Neither soul disappears. The world does not know what to call this.**"
            )
        )
        if history_note:
            text += "\n\n" + history_note
        await self.beat(text, gif=VEYRA_VICTORY_GIF if won else None, new_message=True)


class PatronClashPresentation(BossPresentation):
    async def intro(self, state):
        await self.beat(
            "# ORIGIN // ERASURE\n-# TWO AUTHORITIES. ONE WORLD.\n\n**Meyaya:** Every ending still belongs to a story.\n**Veyra:** Then I will erase the author.\n\n*The Soul Interface disconnects its limiters.*",
            gif=INTRO_GIF,
        )
        await asyncio.sleep(6.66 if self.message_has_gif else 2)
        self.message_has_gif = False
        await self.beat(
            "# WORLD COLLISION AUTHORIZED\n\n**Everbloom answers Mournfang.**\n**Origin faces its own extinction.**\n\n*There are no spectators left in the sky.*"
        )

    async def speak(self, state):
        if state.dialogue and self.speeches < 3:
            self.speeches += 1
            await self.beat(f"# {state.boss_form}\n\n**{state.dialogue}**")

    async def finish(self, state, *, history_note=""):
        origin_won = state.winner_id == state.left.user_id
        erasure_won = state.winner_id == state.right.user_id
        text = (
            "# THE FIRST DAWN RETURNS\n\n**Meyaya stands where the world ended.**\n\n> You forgot something, Veyra.\n> **I can begin again.**\n\n-# ORIGIN PREVAILS · MEYAYA WINS"
            if origin_won
            else (
                "# THE LAST BLOOM GOES SILENT\n\n**Veyra walks through the fallen crown.**\n\n> No author. No ending.\n> **Only me.**\n\n-# ERASURE PREVAILS · VEYRA WINS"
                if erasure_won
                else "# A WORLD WITHOUT A VERDICT\n\n**Origin cannot be erased. Erasure cannot be undone.**\n\n*Both authorities remain. Reality pays the price.*"
            )
        )
        if history_note:
            text += "\n\n" + history_note
        await self.beat(
            text,
            gif=VICTORY_GIF if origin_won else VEYRA_VICTORY_GIF if erasure_won else None,
            new_message=True,
        )
