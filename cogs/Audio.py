import discord
import wavelink

from discord.ext import commands
from discord import option
from discord.commands import slash_command


class Audio(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name="volume", description="Sets volume.")
    @option(
        "vol",
        description="Max is 100.",
        min_value=1,
        max_value=200
    )
    async def change_volume(self, ctx, vol: float = None) -> None:

        if not ctx.author.voice:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", you're not joined into vc. Type `/p` from vc.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.connected:
            embed = discord.Embed(title="",
                                  description=str(ctx.author.mention) + ", I'm not joined to vc",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        if not vol:
            embed = discord.Embed(title="",
                                  description=f"🔊 **{int(vc.volume)}%**",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed)

        await vc.set_volume(vol)

        embed = discord.Embed(title="", description=f"**🔊 Volume set to `{int(vol)}%`**",
                              color=discord.Color.blue())
        await ctx.respond(embed=embed)

    @slash_command(name="speed", description="Speeds up music.")
    @option(
        "multiplier",
        description="It might take 3-5 seconds to start speeding up, no value sets it to normal speed",
        min_value=1,
        max_value=8
    )
    async def speed(self, ctx, multiplier: float = None) -> None:

        if not ctx.author.voice:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", you're not joined into vc. Type `/p` from vc.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.connected:
            embed = discord.Embed(title="",
                                  description=str(ctx.author.mention) + ", I'm not joined to vc",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        elif multiplier:
            filters: wavelink.Filters = vc.filters
            filters.timescale.set(speed=multiplier)

            await vc.set_filters(filters)

            embed = discord.Embed(title="", description=f"**⏩ Sped up by `{int(multiplier)}x`.**",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed)

    @slash_command(name="clear-effects", description="Clears all effects on player.")
    async def clear_effects(self, ctx) -> None:

        if not ctx.author.voice:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", you're not joined into vc. Type `/p` from vc.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.connected:
            embed = discord.Embed(title="",
                                  description=str(ctx.author.mention) + ", I'm not joined to vc",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)
        else:
            filters: wavelink.Filters = vc.filters
            filters.timescale.reset()

            await vc.set_filters(filters)

            embed = discord.Embed(title="", description=f"**✅ Effects were cleared.**",
                                  color=discord.Color.blue())
            embed.set_footer(text="takes 3 seconds to apply")
            await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Audio(bot))
