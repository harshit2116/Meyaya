"""Reusable random-pair controls for ship and friendship cards."""
import asyncio
import logging
import time
from types import SimpleNamespace
from uuid import uuid4

import discord
from discord.ext import commands

from bot.utils.components_v2 import MeyayaView
from bot.utils.command_context import remember_output_message
from bot.utils.image_work import ImageBusy

logger = logging.getLogger(__name__)


class RandomPairView(MeyayaView):
    def __init__(self, cog, guild_id, kind):
        super().__init__(timeout=900)
        self.cog = cog
        self.bot = cog.bot
        self.guild_id = guild_id
        self.kind = kind
        self.token = uuid4().hex
        self.message = None
        self._lock = asyncio.Lock()
        self._last_click = -float('inf')
        self.random_pair.custom_id = f'meyaya:pair:{self.token}:random'
        self.random_pair.disabled = guild_id is None
        cog.pair_views.add(self)

    def stop(self):
        self.cog.pair_views.discard(self)
        super().stop()

    async def interaction_check(self, interaction):
        if self.is_finished() or interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message('Open a fresh `/ship` or `/bestiescore` in this server.', ephemeral=True)
            return False
        blacklist = getattr(self.bot, 'chat_blacklist', None)
        if blacklist is not None:
            blocked = getattr(blacklist, 'is_command_blocked', blacklist.is_blocked)
            if blocked(self.guild_id, interaction.user.id):
                await interaction.response.defer(ephemeral=True, thinking=True)
                await interaction.delete_original_response()
                return False
        if not getattr(self.bot, 'feature_enabled', lambda *_: True)(self.guild_id, 'Fun and Scores'):
            await interaction.response.send_message('Fun and Scores is disabled in this server.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Random pair', emoji='🎲', style=discord.ButtonStyle.secondary)
    async def random_pair(self, interaction, button):
        # Do not queue clicks: a burst should produce one render and one edit.
        if self._lock.locked() or time.monotonic() - self._last_click < 2:
            await interaction.response.send_message('Give this pair a moment before rolling again.', ephemeral=True)
            return
        async with self._lock:
            self._last_click = time.monotonic()
            await interaction.response.defer()
            file = None
            previous = (self._card_content, list(self._card_embeds), list(self._card_media))
            try:
                ctx = SimpleNamespace(guild=interaction.guild, channel=interaction.channel,
                                      author=interaction.user, interaction=interaction)
                first, second = await self.cog._random_ship_pair(ctx)
                if self.kind == 'ship':
                    embed, file = await self.cog._build_ship_response(first, second, ctx=ctx)
                else:
                    embed, file = await self.cog._build_bestie_response(first, second, ctx=ctx)
                message = await interaction.edit_original_response(
                    embed=embed, attachments=[file] if file is not None else [],
                    view=self, allowed_mentions=discord.AllowedMentions.none())
                self.message = message
                remember_output_message(self.bot, interaction.channel.id, message.id,
                    self.kind, interaction.user, getattr(ctx, '_meyaya_result_summary', ''))
            except (commands.CommandError, ImageBusy) as error:
                await interaction.followup.send(str(error), ephemeral=True)
            except Exception:
                self.present(content=previous[0], embeds=previous[1], media=previous[2])
                logger.exception('Random %s pair failed in guild=%s', self.kind, self.guild_id)
                await interaction.followup.send('I could not build a new pair right now. Your previous card is kept; try again shortly.', ephemeral=True)
            finally:
                if file is not None:
                    file.close()

    async def on_timeout(self):
        self.random_pair.disabled = True
        self.cog.pair_views.discard(self)
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
