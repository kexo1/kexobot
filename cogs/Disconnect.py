import discord

from discord.ext import commands
from discord.commands import slash_command
from decorators import is_joined
import wavelink


class Disconnect(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name="leave", description="Leaves voice channel.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @is_joined()
    async def disconnect_command(self, ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.channel.id != ctx.author.voice.channel.id:  # type: ignore
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention}, join the voice channel the bot is playing in to disconnect it.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="",
            description=f"**✅ Left <#{vc.channel.id}>**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)
        await self.disconnect_player(ctx.guild)

    @staticmethod
    async def disconnect_player(guild: discord.Guild) -> None:
        vc: wavelink.Player = guild.voice_client  # type: ignore
        await vc.disconnect()


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Disconnect(bot))
