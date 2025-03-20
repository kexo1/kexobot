import discord
import wavelink

from datetime import datetime
from discord import option
from discord.ext import commands
from discord.commands import slash_command


class Queue(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @slash_command(name="queue", description="Shows songs in queue.")
    async def queue(self, ctx: discord.ApplicationContext) -> None:

        is_joined = await self.is_joined(ctx)
        if not is_joined:
            return

        vc: wavelink.Player = ctx.voice_client

        if not vc.queue.is_empty:
            await ctx.respond(embed=await self.get_queue_embed(ctx, vc))
        else:
            embed = discord.Embed(title="", description="**Queue is empty**", color=discord.Color.blue())
            await ctx.respond(embed=embed)

    @slash_command(name="playing", description="What song is currently playing.")
    async def playing_command(self, ctx: discord.ApplicationContext) -> None:

        is_playing = await self.is_playing(ctx)
        if not is_playing:
            return

        await ctx.respond(embed=await self.get_playing_embed(ctx))

    @slash_command(name="remove", description="Clears position in queue.")
    @option("pos", description="Value 1 Removes the first one.", min_value=1, required=False)
    async def remove(self, ctx: discord.ApplicationContext, pos: int):

        is_joined = await self.is_joined(ctx)
        if not is_joined:
            return
        
        vc: wavelink.Player = ctx.voice_client

        if pos is None:
            vc.queue.pop()
        else:
            try:
                track = vc.queue[pos - 1]
                del vc.queue[pos - 1]
                embed = discord.Embed(title="",
                                      description=f"**Removed [{track.title}]({track.uri})**",
                                      color=discord.Color.blue())
                await ctx.respond(embed=embed)
            except IndexError:
                embed = discord.Embed(title="",
                                      description=f"**:x: Song was not found on `{pos}`, to show what's in queue, "
                                                  f"type /q.**",
                                      color=discord.Color.blue())
                await ctx.respond(embed=embed, ephemeral=True)

    @slash_command(name="shuffle", description="Shuffles you queue, queue must contain more than 2 songs.")
    async def shuffle(self, ctx: discord.ApplicationContext):

        is_joined = await self.is_joined(ctx)
        if not is_joined:
            return
        
        vc: wavelink.Player = ctx.voice_client

        if not vc.queue.is_empty:
            if len(vc.queue) < 2:
                embed = discord.Embed(title="", description=ctx.author.mention + ", can't shuffle 1 song in queue.",
                                      color=discord.Color.blue())
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                vc.queue.shuffle()

                embed = discord.Embed(title="", description="**🔀 Queue shuffled!**", color=discord.Color.blue())
                await ctx.respond(embed=embed)
        else:
            embed = discord.Embed(title="", description="**Queue is empty.**", color=discord.Color.blue())
            await ctx.respond(embed=embed, ephemeral=True)

    @slash_command(name="loop-queue", description="Loops queue, run command again to disable queue loop")
    async def loop_queue(self, ctx: discord.ApplicationContext) -> None:

        is_playing = await self.is_playing(ctx)
        if not is_playing:
            return
        
        vc: wavelink.Player = ctx.voice_client

        if vc.queue.is_empty:
            embed = discord.Embed(title="", description="**Queue is empty**", color=discord.Color.blue())
            return await ctx.respond(embed=embed)

        if vc.queue.mode == wavelink.QueueMode.loop_all:

            vc.queue.mode = wavelink.QueueMode.loop_all
            embed = discord.Embed(title="",
                                  description="**No longer looping queue.**",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed)
        else:
            vc.queue.mode = wavelink.QueueMode.loop_all
            embed = discord.Embed(title="",
                                  description=f"🔁 **Looping current queue ({vc.queue.count} songs)**",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed)

    @slash_command(name="loop", description="Loops currently playing song, run command again to disable loop.")
    async def loop(self, ctx: discord.ApplicationContext) -> None:

        is_playing = await self.is_playing(ctx)
        if not is_playing:
            return
        
        vc: wavelink.Player = ctx.voice_client

        if vc.queue.mode == wavelink.QueueMode.loop:

            vc.queue.mode = wavelink.QueueMode.normal
            embed = discord.Embed(title="",
                                  description="**No longer looping current song.**",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed)
        else:
            vc.queue.mode = wavelink.QueueMode.loop
            embed = discord.Embed(title="",
                                  description=f"🔁 **Looping [{vc.current.title}]({vc.current.uri}).**",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed)

    @slash_command(name="clear-queue", description="Clears queue")
    async def clear_(self, ctx: discord.ApplicationContext):

        is_joined = await self.is_joined(ctx)
        if not is_joined:
            return
        
        vc: wavelink.Player = ctx.voice_client
        vc.queue.clear()

        embed = discord.Embed(title="", description="🗑️ **Cleared**", color=discord.Color.blue())
        await ctx.respond(embed=embed)

    @staticmethod
    async def get_queue_embed(ctx: discord.ApplicationContext, vc: wavelink.Player) -> discord.Embed:

        if vc.queue.mode == wavelink.QueueMode.loop_all:
            status = "Looping queue"
            footer = "🔁 "
        elif vc.queue.mode == wavelink.QueueMode.loop:
            status = "Looping currently playing song"
            footer = "🔁 "
        else:
            status = "Now Playing"
            footer = ""

        fmt = []
        for pos, track in enumerate(vc.queue):
            fmt.append(f"`{pos + 1}.` **[{track.title[:1023]}]({track.uri})**"
                       f" \n `{int(divmod(track.length, 60000)[0])}:"
                       f"{round(divmod(track.length, 60000)[1] / 1000):02} | Requested by: {track.requester.name}`\n")
        fmt = "\n".join(fmt)

        fmt = (f"\n***__{status}:__***\n **[{vc.current.title[:1023]}]({vc.current.uri})**"
               f" \n `{int(divmod(vc.current.length, 60000)[0])}:"
               f"{round(divmod(vc.current.length, 60000)[1] / 1000):02} | Requested by:"
               f" {vc.current.requester.name}`\n\n ***__Next:__***\n") + fmt[:3800]
        embed = discord.Embed(title=f"Queue for {ctx.guild.name}", description=fmt, color=discord.Color.blue())
        embed.set_footer(text=f"\n{footer}{vc.queue.count} songs in queue")
        return embed

    @staticmethod
    async def get_playing_embed(ctx: discord.ApplicationContext) -> discord.Embed:

        vc: wavelink.Player = ctx.voice_client

        embed = discord.Embed(
            title="Now playing",
            colour=discord.Colour.blue(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(name="Playback Information")
        embed.set_footer(
            text=f"Requested by {vc.current.requester.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        embed.add_field(name="Track title", value=f"**[{vc.current.title}]({vc.current.uri})**", inline=False)
        embed.add_field(
            name="Artist",
            value=f"_{vc.current.author if vc.current.author else "None"}_",
            inline=False,
        )

        embed.set_image(url=vc.current.artwork)

        position = divmod(vc.position, 60000)
        length = divmod(vc.current.length, 60000)
        embed.add_field(
            name="Position",
            value=f"`{int(position[0])}:{round(position[1] / 1000):02}/{int(length[0])}:{round(length[1] / 1000):02}`",
            inline=False,
        )

        return embed

    @staticmethod
    async def check_join(ctx: discord.ApplicationContext) -> bool:
        embed = discord.Embed(title="",
                              description=ctx.mention + ", you're not joined into vc. Type `/p` from vc.",
                              color=discord.Color.blue())
        return embed

    async def is_joined(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice:
            await ctx.respond(embed=self.check_join(ctx.author), ephemeral=True)
            return False

        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.connected:
            embed = discord.Embed(title="",
                                  description=ctx.author.mention + ", I'm not joined to vc",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed, ephemeral=True)
            return False
        return True

    async def is_playing(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice:
            await ctx.respond(embed=self.check_join(ctx.author), ephemeral=True)
            return False

        vc: wavelink.Player = ctx.voice_client

        if not vc.playing or not vc.current or not vc:
            embed = discord.Embed(title="",
                                  description=ctx.author.mention + ", bot is not playing anything. Type `/p` from vc.",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed, ephemeral=True)
            return False
        return True


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Queue(bot))
