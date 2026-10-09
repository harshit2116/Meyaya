"""Consent and confirmation UI for Meyaya relationships."""

from __future__ import annotations

import asyncio

import discord
from bot.utils.components_v2 import MeyayaView

from bot.app import MeyayaBot
from bot.services.marriage import (
    AlreadyMarriedError,
    PendingProposalRegistry,
    StaleMarriageConfirmationError,
)
from bot.utils.embeds import MeyayaColors, meyaya_embed


class MarriageProposalView(MeyayaView):
    """Allow only the intended member to accept or decline a proposal."""

    def __init__(
        self,
        bot: MeyayaBot,
        proposer_id: int,
        target_id: int,
        pending: PendingProposalRegistry,
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.pending = pending
        self.message: discord.Message | None = None
        self._resolution_lock = asyncio.Lock()
        self._resolved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.target_id:
            return True
        await interaction.response.send_message(
            "This proposal is not addressed to you.",
            ephemeral=True,
        )
        return False

    async def _release(self) -> None:
        await self.pending.release(self.proposer_id, self.target_id)

    def _disable(self) -> None:
        for item in self.children:
            item.disabled = True

    async def _claim_resolution(self) -> bool:
        async with self._resolution_lock:
            if self._resolved:
                return False
            self._resolved = True
            return True

    @discord.ui.button(label="Accept", emoji="💍", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._claim_resolution():
            await interaction.response.send_message(
                "This proposal was already answered.", ephemeral=True
            )
            return
        self._disable()
        await interaction.response.defer()
        try:
            async with self.bot.db_session() as session:
                result = await self.bot.build_marriage_service(session).marry(
                    self.proposer_id,
                    self.target_id,
                )
        except (AlreadyMarriedError, ValueError):
            await self._release()
            self.stop()
            embed = meyaya_embed(
                "Proposal Unavailable",
                "One of you is already married, so this proposal can no longer continue.",
                tone="muted",
                icon="💭",
            )
            if interaction.message is not None:
                await interaction.message.edit(embed=embed, content=None, view=self)
            return
        except Exception:
            await self._release()
            raise

        await self._release()
        self.stop()
        accepted = meyaya_embed(
            "Proposal Accepted",
            (
                f"<@{self.target_id}> accepted <@{self.proposer_id}>'s proposal. "
                "Meyaya has made it official."
            ),
            tone="soft",
            icon="💗",
        )
        if interaction.message is not None:
            await interaction.message.edit(embed=accepted, content=None, view=self)

        wedding = meyaya_embed(
            "Meyaya Wedding Announcement",
            (
                f"## <@{self.proposer_id}> + <@{self.target_id}>\n"
                "You are now officially married in the Meyaya universe.\n\n"
                f"**Married:** <t:{int(result.married_at.timestamp())}:D>"
            ),
            icon="💍",
        )
        target = interaction.guild.get_member(self.target_id) if interaction.guild else None
        if target is not None:
            wedding.set_thumbnail(url=str(target.display_avatar.url))
        await interaction.followup.send(
            embed=wedding,
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @discord.ui.button(label="Decline", emoji="💔", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._claim_resolution():
            await interaction.response.send_message(
                "This proposal was already answered.", ephemeral=True
            )
            return
        self._disable()
        await self._release()
        self.stop()
        embed = meyaya_embed(
            "Proposal Declined",
            f"<@{self.target_id}> declined <@{self.proposer_id}>'s proposal.",
            tone="muted",
            icon="💔",
        )
        await interaction.response.edit_message(embed=embed, content=None, view=self)

    async def on_timeout(self) -> None:
        if not await self._claim_resolution():
            return
        self._disable()
        await self._release()
        if self.message is not None:
            try:
                embed = (
                    self.message.embeds[0].copy()
                    if self.message.embeds
                    else meyaya_embed("Proposal Expired", tone="muted", icon="⌛")
                )
                embed.title = "Proposal expired"
                embed.color = discord.Color(MeyayaColors.MUTED)
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class DivorceConfirmationView(MeyayaView):
    """Require explicit confirmation before deleting a marriage."""

    def __init__(
        self,
        bot: MeyayaBot,
        requester_id: int,
        partner_id: int,
        marriage_id: int,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.requester_id = requester_id
        self.partner_id = partner_id
        self.marriage_id = marriage_id
        self.message: discord.Message | None = None
        self._resolution_lock = asyncio.Lock()
        self._resolved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "Only the member who requested this divorce can confirm it.",
            ephemeral=True,
        )
        return False

    def _disable(self) -> None:
        for item in self.children:
            item.disabled = True

    async def _claim_resolution(self) -> bool:
        async with self._resolution_lock:
            if self._resolved:
                return False
            self._resolved = True
            return True

    @discord.ui.button(label="Confirm divorce", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._claim_resolution():
            await interaction.response.send_message(
                "This divorce request was already answered.", ephemeral=True
            )
            return
        self._disable()
        await interaction.response.defer()
        try:
            async with self.bot.db_session() as session:
                await self.bot.build_marriage_service(session).divorce(
                    self.requester_id,
                    marriage_id=self.marriage_id,
                    partner_id=self.partner_id,
                )
        except StaleMarriageConfirmationError:
            title = "Divorce Not Changed"
            tone = "warning"
            description = (
                "This confirmation is outdated, so no marriage was changed. "
                "Run `/divorce` again if you still want to continue."
            )
        else:
            title = "Divorce Finalized"
            tone = "muted"
            description = f"<@{self.requester_id}> and <@{self.partner_id}> are no longer married."
        self.stop()
        embed = meyaya_embed(
            title,
            description,
            tone=tone,
            icon="💔",
        )
        if interaction.message is not None:
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Stay married", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._claim_resolution():
            await interaction.response.send_message(
                "This divorce request was already answered.", ephemeral=True
            )
            return
        self._disable()
        self.stop()
        embed = meyaya_embed(
            "Divorce Cancelled",
            "The marriage remains intact.",
            tone="success",
            icon="💞",
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        if not await self._claim_resolution():
            return
        self._disable()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
