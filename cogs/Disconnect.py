import discord

from discord.ext import commands
from discord.commands import slash_command
import wavelink


class Disconnect(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name='leave', description='Leaves voice channel.')
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def disconnect_command(self, ctx) -> None:
        if not ctx.author.voice or ctx.voice_client is None:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", you're not connected to any vc.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed)

        if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", join the voice channel the bot is playing in to "
                                                            "disconnect it.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed)

        vc: wavelink.Player = ctx.voice_client

        if not vc.playing or not vc.current:
            embed = discord.Embed(title="",
                                  description=ctx.author.mention + ", bot is not playing anything. Type `/p` from vc.",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed, ephemeral=True)

        embed = discord.Embed(title="", description=f'**✅ Left <#{ctx.voice_client.channel.id}>**',
                              color=discord.Color.blue())
        await ctx.respond(embed=embed)
        await Disconnect.disconnect_player(ctx.guild)

    @staticmethod
    async def disconnect_player(guild: discord.Guild) -> None:
        vc: wavelink.Player = guild.voice_client
        await vc.disconnect()


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Disconnect(bot))
