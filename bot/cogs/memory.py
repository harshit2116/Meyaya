"""Member-facing controls for Meyaya's permanent Memory System v2."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.app import MeyayaBot
from bot.models.memory import MemoryStatus
from bot.models.meyaya_state import MeyayaUserState
from bot.repositories.memories import MemoryRepository
from bot.services.memory import MemoryOutcome, MemoryService
from bot.utils.embeds import meyaya_embed

MAX_MEMORY_LIST_LENGTH = 3800


class MemoryCog(commands.Cog):
    """Allow members to inspect and delete their own permanent memories."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="memories",
        description="See what Meyaya remembers about you or another member.",
        with_app_command=True,
    )
    @app_commands.describe(member="Member to inspect; Manage Server is required for others.")
    async def memories(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """List categorized permanent memories without exposing other members."""

        target = member or ctx.author
        if target.id != ctx.author.id and not self._can_manage_guild(ctx.author):
            await self._send(ctx, "You can only inspect your own Meyaya memories.")
            return

        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)

        guild_id = ctx.guild.id if ctx.guild else None
        async with self.bot.db_session() as session:
            records = await MemoryRepository(session).list_for_user(
                guild_id,
                target.id,
                limit=50,
                include_conflicted=True,
            )

        if not records:
            await self._send(ctx, f"Meyaya has no permanent memories for {target.mention} yet.")
            return

        lines: list[str] = []
        current_length = 0
        for record in records:
            safe_value = discord.utils.escape_mentions(discord.utils.escape_markdown(record.value))
            confidence = round(record.confidence * 100)
            line = (
                f"`#{record.id}` - `{record.category}:{record.relation}` - "
                f"{confidence}% confidence\n{safe_value}"
            )
            if record.status == MemoryStatus.CONFLICTED and record.conflict_value:
                safe_conflict = discord.utils.escape_mentions(
                    discord.utils.escape_markdown(record.conflict_value)
                )
                line += (
                    "\n⚠️ Conflicts with: "
                    f"{safe_conflict}\nThis conflicting memory is withheld from chat."
                )
            if current_length + len(line) + 2 > MAX_MEMORY_LIST_LENGTH:
                lines.append("*Additional memories omitted to keep this response readable.*")
                break
            lines.append(line)
            current_length += len(line) + 2

        embed = meyaya_embed(
            f"What I Remember About {target.display_name}",
            "\n\n".join(lines),
            tone="soft",
            icon="🧠",
        )
        await self._send_memory_list(ctx, embed)

    @commands.hybrid_command(
        name="nicknames",
        description="See the nicknames Meyaya has given members in this server.",
        with_app_command=True,
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @app_commands.describe(member="Show only the nickname Meyaya gave this member.")
    async def nicknames(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """Show the stable nicknames Meyaya has assigned in this server."""

        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)

        filters = [
            MeyayaUserState.guild_id == ctx.guild.id,
            MeyayaUserState.nickname.is_not(None),
            MeyayaUserState.nickname != "",
        ]
        if member is not None:
            filters.append(MeyayaUserState.user_id == member.id)
        async with self.bot.db_session() as session:
            records = (
                await session.scalars(
                    select(MeyayaUserState)
                    .where(*filters)
                    .order_by(MeyayaUserState.familiarity.desc(), MeyayaUserState.updated_at.desc())
                    .limit(50)
                )
            ).all()

        if not records:
            target = f" for {member.display_name}" if member else " in this server"
            await self._send(ctx, f"Meyaya has not given anyone a nickname{target} yet.")
            return

        lines = []
        for record in records:
            guild_member = ctx.guild.get_member(record.user_id)
            display_name = guild_member.display_name if guild_member else f"User {record.user_id}"
            safe_name = discord.utils.escape_markdown(display_name)
            safe_nickname = discord.utils.escape_markdown(record.nickname or "")
            lines.append(f'**{safe_name}** - "{safe_nickname}"')
        embed = meyaya_embed(
            "Meyaya's Nickname Book",
            "\n".join(lines),
            tone="soft",
            icon="🌸",
        )
        await self._send(ctx, embed=embed)

    @staticmethod
    def _can_manage_guild(author: discord.abc.User) -> bool:
        permissions = getattr(author, "guild_permissions", None)
        return bool(permissions and permissions.manage_guild)

    @staticmethod
    async def _send(
        ctx: commands.Context,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
    ) -> None:
        await ctx.send(
            content=content,
            embed=embed,
            ephemeral=ctx.interaction is not None,
        )

    @staticmethod
    async def _send_memory_list(ctx: commands.Context, embed: discord.Embed) -> None:
        """Keep personal facts private for both slash and written commands."""

        if ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
            return
        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Use `/memories` so the result stays private.")
            return
        await ctx.send("I sent the memory list to your DMs.")


async def setup(bot: MeyayaBot) -> None:
    """Install the Memory System v2 commands."""

    await bot.add_cog(MemoryCog(bot))
