"""On-demand AniList summons backed by Meyaya-owned gameplay configuration."""

from hashlib import sha256
import logging

import discord
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot.cogs.admin import private_owner
from bot.services.character_catalog import CatalogService, NOTICE, RARITY_NAMES
from bot.services.character_provider import (
    AniListCharacterProvider,
    CharacterNotFound,
    CharacterProviderError,
)

RARITY_STYLE = {
    2: (0x95A1B2, "◇", "UNCOMMON"),
    3: (0x55D6A0, "◆", "RARE"),
    4: (0xA970FF, "✦", "EPIC"),
    5: (0xFFD166, "♛", "LEGENDARY"),
    6: (0xFF5BB7, "✧", "MYTHIC"),
}
SERIES_SIGILS = ("☾", "⚔", "✦", "♜", "❖", "☄")
log = logging.getLogger(__name__)


class CharacterCatalogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.catalog = CatalogService(bot)
        self.provider: AniListCharacterProvider | None = None

    async def cog_load(self) -> None:
        self.provider = AniListCharacterProvider(self.bot.http_session)
        if self.bot.http_session is not None:
            try:
                await self.catalog.seed_curated_roster()
            except SQLAlchemyError:
                log.exception("Could not seed the gameplay summon roster")

    @commands.hybrid_command(description="Summon a real anime character from Meyaya's roster.")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def summon(self, ctx, member: discord.Member = None):
        await ctx.defer()
        member = member or ctx.author
        try:
            assert self.provider is not None
            gameplay = await self.catalog.draw()
            if gameplay is None:
                await ctx.send("The summon roster is currently unavailable or disabled.")
                return
            display = await self.provider.fetch(gameplay.provider_character_id)
        except CharacterProviderError as exc:
            await ctx.send(str(exc))
            return
        except SQLAlchemyError:
            await ctx.send(
                "The summon roster is unavailable. The database migration may be missing."
            )
            return

        stars = gameplay.rarity_stars
        color, ornament, tier = RARITY_STYLE[stars]
        sigil_index = int.from_bytes(sha256(display.series.encode("utf-8")).digest()[:2], "big")
        sigil = SERIES_SIGILS[sigil_index % len(SERIES_SIGILS)]
        traits = " · ".join(discord.utils.escape_markdown(value) for value in gameplay.traits)
        embed = discord.Embed(
            title=f"{ornament} {discord.utils.escape_markdown(display.name)} {ornament}",
            url=display.source_url,
            color=color,
            description=(
                f"**{'★' * stars}  {tier}**\n"
                f"{sigil} **{discord.utils.escape_markdown(display.series)}**\n\n"
                f"Summoned for {member.mention}"
            ),
        )
        embed.set_author(name=f"MEYAYA SUMMON · {RARITY_NAMES[stars].upper()}")
        embed.set_thumbnail(url=str(member.display_avatar.url))
        embed.add_field(name="Class", value=gameplay.class_name, inline=True)
        embed.add_field(name="Traits", value=traits or "Mysterious", inline=True)
        embed.add_field(name="Passive", value=gameplay.passive or "Unknown potential", inline=False)
        embed.add_field(name="Roster ID", value=f"#{gameplay.internal_id:04d}", inline=True)
        embed.add_field(name="Provider", value="AniList", inline=True)
        if display.image_url and not gameplay.image_disabled:
            embed.set_image(url=display.image_url)
        else:
            embed.add_field(name="Artwork", value="Disabled for this roster entry.", inline=False)
        embed.set_footer(text=NOTICE)
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(label="View on AniList", url=display.source_url, emoji="↗️")
        )
        await ctx.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(hidden=True)
    @commands.check(private_owner)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def catalogadmin(self, ctx, action: str, target: str = "", *, value: str = ""):
        """Owner DM controls: add, disable, enable, setrarity, settraits, reload, status."""
        if ctx.guild:
            await ctx.send("Use catalogadmin in a DM.")
            return
        try:
            if action == "status":
                status = await self.catalog.status()
                await ctx.send(
                    f"Roster: {status['enabled']}/{status['total']} enabled\n"
                    f"AniList access: {'blocked' if status['blocked'] else 'enabled'}\n"
                    "Display cache: memory only, expires after 3 hours"
                )
            elif action == "reload":
                assert self.provider is not None
                count = await self.catalog.reload_curated_roster(ctx.author.id)
                self.provider.clear_cache()
                await ctx.send(f"Reloaded {count} curated gameplay entries.")
            elif action == "add":
                assert self.provider is not None
                provider_id = int(target)
                await self.provider.fetch(
                    provider_id
                )  # Verify without retaining metadata in PostgreSQL.
                internal_id = await self.catalog.add_character(provider_id, ctx.author.id)
                await ctx.send(f"Added verified AniList ID {provider_id} as roster #{internal_id}.")
            else:
                await self.catalog.manage(action, target, value, ctx.author.id)
                if action in {"disableimage", "enableimage"}:
                    assert self.provider is not None
                    self.provider.clear_cache()
                await ctx.send("Summon roster updated.")
        except CharacterNotFound:
            await ctx.send(
                "AniList did not return that explicit character ID, so it was not added."
            )
        except (CharacterProviderError, ValueError, SQLAlchemyError) as exc:
            await ctx.send(
                str(exc)[:300]
                if not isinstance(exc, SQLAlchemyError)
                else "Database unavailable; check migrations."
            )


async def setup(bot):
    await bot.add_cog(CharacterCatalogCog(bot))
