"""Community support command."""

import discord
from discord.ext import commands

from bot.utils.embeds import meyaya_embed

LOUNGE_URL = "https://discord.gg/e9bK5ZbUZS"


class ExtrasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="feedback", description="Report a bug or suggest a feature in Pondside Lounge.")
    async def feedback(self, ctx):
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Join Pondside Lounge", url=LOUNGE_URL))
        await ctx.send(embed=meyaya_embed("Pondside Lounge", "Found a bug or have an idea? Join us to report an issue, suggest a feature, or try Meyaya without the server chat limit.", icon="🌸"), view=view)


async def setup(bot):
    await bot.add_cog(ExtrasCog(bot))
