from geniusdotpy.genius_builder import GeniusBuilder
import discord
import wavelink
from discord.ext import commands
from discord.commands import slash_command


class Lyrics(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.genius = GeniusBuilder(client_access_token='TQTApd5TKlHCCaYhhD9te_j-Hl9CS47VMFx5vNyW_5TRmwVNsjQ8V71b-2CeUN0z')

    @slash_command(name='lyrics', description='Searches lyrics for current song.', context={discord.InteractionContextType.guild})
    async def lyrics(self, ctx):

        if not ctx.author.voice:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", you're not joined into vc. Type `/p` from vc.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        vc: wavelink.Player = ctx.voice_client

        if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", join the voice channel the bot is playing in to disconnect it.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        if not vc.is_playing or not vc.current:
            embed = discord.Embed(title="",
                                  description=ctx.author.mention + ", bot is not playing anything. Type `/p` from vc.",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed, ephemeral=True)
        print(vc.current.title)
        song = self.genius.search(vc.current.title)
        for _ in song:
            print(_)


def setup(bot: commands.Bot):
    bot.add_cog(Lyrics(bot))
