"""Interactive solo adventures with local scoring and recoverable message edits."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
from time import monotonic

import discord
from bot.utils.components_v2 import MeyayaView
from discord.ext import commands

from bot.logging.health import health
from bot.services.solo_games import SoloGame
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)
ICONS = {"escape": "🔑", "detective": "🔎", "personalitytest": "🎭"}


class SoloView(MeyayaView):
    def __init__(self, owner, kind, release, *, acquire=None, forget=None):
        super().__init__(timeout=180)
        self.owner, self.kind, self.release = owner, kind, release
        self.acquire = acquire or (lambda: True)
        self.forget = forget or (lambda: None)
        self.game = SoloGame(kind)
        self.lock = asyncio.Lock()
        self.message = None
        self.revision = 0
        self.has_slot = True
        self.disposed = False
        self.started = monotonic()
        self.duration = None
        self.render_buttons()

    @property
    def closed(self):
        return self.game.done

    @property
    def step(self):
        return self.game.step

    def release_slot(self):
        if self.has_slot:
            self.has_slot = False
            self.release()

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.release_slot()
        self.clear_items()
        self.stop()
        self.forget()

    def render_buttons(self):
        self.clear_items()
        revision = self.revision
        if self.game.done:
            actions = [("replay", "Play again", True, discord.ButtonStyle.primary, 0)]
        else:
            actions = [(a.key, a.label, a.enabled, discord.ButtonStyle.primary,
                        index // (2 if self.kind == "detective" and not self.game.accusing else 3))
                       for index, a in enumerate(self.game.actions())]
            actions.append(("quit", "End game", True, discord.ButtonStyle.secondary, 3))
        for key, label, enabled, style, row in actions:
            button = discord.ui.Button(label=label, disabled=not enabled, style=style, row=row,
                                       custom_id=f"meyaya:solo:{self.id}:{revision}:{key}")

            async def callback(interaction, choice=key, version=revision):
                await self.choose(interaction, choice, version)

            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is another player's run. Start your own with `/" + self.kind + "`.", ephemeral=True)
            return False
        return True

    def embed(self):
        title, text, fields = self.game.presentation()
        tone = "magic"
        if self.closed:
            tone = "success"
            if self.game.title in {"Run ended", "Game paused too long"}:
                tone = "muted"
            elif self.game.correct is False or self.game.title == "The scenic rescue":
                tone = "warning"
        embed = meyaya_embed(title, text, icon=ICONS[self.kind],
                             tone=tone)
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
        if self.closed:
            elapsed = self.duration if self.duration is not None else int(monotonic() - self.started)
            footer = f"Run time {elapsed // 60}:{elapsed % 60:02d} • Replay available for 3 minutes"
        else:
            footer = "Your choices only • Ends after 3 minutes without a choice"
        if self.kind == "personalitytest":
            footer += " • Just for fun"
        embed.set_footer(text=footer)
        return embed

    async def choose(self, interaction, choice, revision):
        # Acknowledge before any lock or Discord edit wait. Concurrent clicks
        # never silently become a choice on the next scene.
        await interaction.response.defer()
        if self.lock.locked():
            await interaction.followup.send("Your last choice is updating. Try again when the next turn appears.", ephemeral=True)
            return
        async with self.lock:
            if self.disposed or revision != self.revision:
                await interaction.followup.send("That turn has already been handled. Use the current buttons.", ephemeral=True)
                return
            replay = choice == "replay"
            old_game, old_started, old_duration = self.game, self.started, self.duration
            old_buttons = list(self.children)
            next_game = deepcopy(old_game)
            if replay:
                if not self.closed:
                    return
                if monotonic() - self.started < 2:
                    await interaction.followup.send("Give this run a moment before starting the next one.", ephemeral=True)
                    return
                if not self.acquire():
                    await interaction.followup.send("Finish your other solo game first, or try again when a game slot is available.", ephemeral=True)
                    return
                self.has_slot = True
                next_game = SoloGame(self.kind, previous=old_game)
                self.started = monotonic()
                self.duration = None
            elif self.closed:
                return
            elif choice == "quit":
                next_game.quit()
            else:
                try:
                    next_game.apply(choice)
                except ValueError:
                    await interaction.followup.send("That choice isn't available. Check the current buttons.", ephemeral=True)
                    return
            self.game = next_game
            self.revision += 1
            if self.closed:
                self.duration = int(monotonic() - self.started)
            self.render_buttons()
            try:
                await interaction.edit_original_response(embed=self.embed(), view=self,
                                                          allowed_mentions=discord.AllowedMentions.none())
            except BaseException:
                # A failed edit must leave the last visible turn usable.
                self.game, self.started, self.duration = old_game, old_started, old_duration
                self.revision -= 1
                self.clear_items()
                for button in old_buttons:
                    self.add_item(button)
                if replay:
                    self.release_slot()
                raise
            if self.closed:
                self.release_slot()

    async def on_timeout(self):
        async with self.lock:
            if self.disposed:
                return
            completed = self.closed
            if not completed:
                self.game.quit()
                self.game.title = "Game paused too long"
                self.game.result = f"No choice for three minutes. Start a fresh run with `/{self.kind}`."
            self.dispose()
            if self.message:
                try:
                    if completed:
                        embed = self.embed()
                        embed.set_footer(text=f"Run finished • Start a fresh one with /{self.kind}")
                        await self.message.edit(embed=embed, view=self)
                    else:
                        embed = self.embed()
                        embed.set_footer(text="Run expired • Start again whenever you're ready")
                        await self.message.edit(embed=embed, view=self)
                except discord.HTTPException:
                    pass

    async def on_error(self, interaction, error, item):
        error_id = health.capture(error, command=self.kind,
                                  guild_id=getattr(interaction, "guild_id", None),
                                  channel_id=getattr(interaction, "channel_id", None),
                                  invocation="component", stage="solo_turn_delivery")
        logger.error("solo_game_update_failed kind=%s error_id=%s exception=%s",
                     self.kind, error_id, type(error).__name__)
        if isinstance(error, discord.NotFound):
            self.dispose()
            message = f"That game message is no longer available. Start again with `/{self.kind}`."
        else:
            message = "I couldn't update that turn. Your choice wasn't saved; please try again."
        try:
            await interaction.followup.send(message + f"\nError ID: `{error_id}`", ephemeral=True)
        except discord.HTTPException:
            pass


class SoloGamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = {}
        self.views = set()

    async def start(self, ctx, kind):
        key = (ctx.guild.id if ctx.guild else 0, ctx.author.id)
        if key in self.active:
            await ctx.send("You already have a solo game running. Use its **End game** button to leave it first.")
            return
        if len(self.active) >= 64 or len(self.views) >= 128:
            await ctx.send("All game tables are busy. Please try again shortly.")
            return

        def release():
            if self.active.get(key) is view:
                self.active.pop(key, None)

        def acquire():
            if key in self.active or len(self.active) >= 64:
                return False
            self.active[key] = view
            return True

        view = SoloView(ctx.author.id, kind, release, acquire=acquire,
                        forget=lambda: self.views.discard(view))
        self.active[key] = view
        self.views.add(view)
        try:
            view.message = await ctx.send(embed=view.embed(), view=view,
                                          allowed_mentions=discord.AllowedMentions.none())
        except BaseException:
            view.dispose()
            raise

    async def cog_unload(self):
        for view in tuple(self.views):
            view.dispose()

    @commands.hybrid_command(description="Escape with branching routes, useful items, and a ticking clock.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def escape(self, ctx):
        await self.start(ctx, "escape")

    @commands.hybrid_command(description="Choose your leads, study the evidence, and name the culprit.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def detective(self, ctx):
        await self.start(ctx, "detective")

    @commands.hybrid_command(description="Answer six questions and discover your personality mix.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def personalitytest(self, ctx):
        await self.start(ctx, "personalitytest")


async def setup(bot):
    await bot.add_cog(SoloGamesCog(bot))
