from typing import Optional

import discord
import wavelink

from discord.ext import commands
from discord import option
from discord.commands import slash_command, guild_only
from pycord.multicog import subcommand
from app.decorators import is_joined


class Audio(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @subcommand("music")
    @slash_command(name="volume", description="Sets audio volume.")
    @guild_only()
    @option(
        "vol",
        type=int,
        required=False,
        description="Max is 100.",
        min_value=1,
        max_value=200,
    )
    @is_joined()
    async def change_volume(
        self, ctx: discord.ApplicationContext, vol: Optional[int] = None
    ) -> None:
        vc: wavelink.Player = ctx.voice_client

        if vol is None:
            embed = discord.Embed(
                title="",
                description=f"🔊 **{int(vc.volume)}%**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            return

        await vc.set_volume(vol)
        embed = discord.Embed(
            title="",
            description=f"**🔊 Volume set to `{vol}%`**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    @subcommand("music")
    @slash_command(name="speed", description="Speeds up music.")
    @guild_only()
    @option(
        "multiplier",
        type=int,
        required=False,
        description="It might take 3-5 seconds to start speeding up,"
        " no value sets it to normal speed",
        min_value=1,
        max_value=8,
    )
    @is_joined()
    async def speed(
        self, ctx: discord.ApplicationContext, multiplier: Optional[int] = 2
    ) -> None:
        player: wavelink.Player = ctx.voice_client
        filters: wavelink.Filters = player.filters
        filters.timescale.set(speed=multiplier)

        await player.set_filters(filters)
        embed = discord.Embed(
            title="",
            description=f"**⏩ Sped up by `{multiplier}x`**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    @subcommand("music")
    @slash_command(name="clear-effects", description="Clears all effects on player.")
    @guild_only()
    @is_joined()
    async def clear_effects(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client
        filters: wavelink.Filters = player.filters
        filters.reset()
        await player.set_filters(filters)
        embed = discord.Embed(
            title="",
            description="**✅ Effects were cleared.**",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="takes 3 seconds to apply")
        await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Audio(bot))
