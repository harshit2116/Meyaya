"""On-demand AniList summons backed by Meyaya-owned gameplay configuration."""

from io import BytesIO
import logging

import discord
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot.cogs.admin import private_owner
from bot.services.character_catalog import CatalogService, NOTICE, RARITY_NAMES
from bot.services.summon_card import SummonCardRenderer, RARITY_COLORS
from bot.services.character_provider import (
    AniListCharacterProvider,
    CharacterNotFound,
    CharacterProviderError,
)

log = logging.getLogger(__name__)


class CharacterCatalogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.catalog = CatalogService(bot)
        self.provider: AniListCharacterProvider | None = None
        self.card_renderer = SummonCardRenderer(bot.http_session)

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

        rendered = await self.card_renderer.render(gameplay, display, member)
        accent = int(RARITY_COLORS[gameplay.rarity_stars][1:], 16)
        view = discord.ui.LayoutView(timeout=180)
        summary = (
            f"Summoned for {member.mention} · **{discord.utils.escape_markdown(display.name)}**\n"
            f"{RARITY_NAMES[gameplay.rarity_stars]} · {gameplay.rarity_stars} stars · "
            f"Roster #{gameplay.internal_id:04d}"
        )
        if display.native_name:
            summary += "\n" + discord.utils.escape_markdown(display.native_name)
        # Native text provides a readable compact summary on smaller screens.
        summary += (
            f"\n**Class:** {discord.utils.escape_markdown(gameplay.class_name)}"
            f" · **Traits:** {discord.utils.escape_markdown(' · '.join(gameplay.traits) or 'Mysterious')}"
            f"\n**Passive:** {discord.utils.escape_markdown(gameplay.passive or 'Unknown potential')}"
        )
        view.add_item(
            discord.ui.Container(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                        "attachment://meyaya-summon.png",
                        description=f"{display.name} · {display.series}",
                    )
                ),
                discord.ui.TextDisplay(summary),
                discord.ui.ActionRow(
                    discord.ui.Button(label="View on AniList", url=display.source_url, emoji="🌸")
                ),
                discord.ui.TextDisplay("-# " + NOTICE),
                accent_color=accent,
            )
        )
        await ctx.send(
            file=discord.File(BytesIO(rendered), filename="meyaya-summon.png"),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

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
