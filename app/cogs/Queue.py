import datetime
from typing import Optional

import discord
import wavelink

from discord.ext import commands
from discord.commands import slash_command, option, guild_only
from decorators import is_playing, is_joined


# noinspection PyUnusedLocal
class QueuePaginator(discord.ui.View):
    def __init__(self, embeds: list, timeout: int = 600) -> None:
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0

    async def update_message(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if self.current_page > 0:
            self.current_page -= 1
        else:
            self.current_page = len(self.embeds) - 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
        else:
            self.current_page = 0
        await self.update_message(interaction)


class Queue(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @slash_command(name="queue", description="Shows songs in queue.")
    @guild_only()
    @is_joined()
    async def queue(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.queue.is_empty:
            embed = discord.Embed(
                title="", description="**Queue is empty**", color=discord.Color.blue()
            )
            await ctx.respond(embed=embed)
            return

        pages = await self._get_queue_embeds(ctx, player)

        if len(pages) == 1:
            await ctx.respond(embed=pages[0])
        else:
            view = QueuePaginator(pages)
            await ctx.respond(embed=pages[0], view=view)

    @slash_command(name="playing", description="What song is currently playing.")
    @guild_only()
    @is_playing()
    async def playing_command(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond(embed=await self._get_playing_embed(ctx))

    @slash_command(name="remove", description="Clears position in queue.")
    @guild_only()
    @option(
        "pos",
        description="Value 1 Removes the first one.",
        min_value=1,
        required=False,
        type=int,
    )
    @is_joined()
    async def remove(self, ctx: discord.ApplicationContext, pos: Optional[int] = None):
        player: wavelink.Player = ctx.voice_client

        if not pos:
            embed = discord.Embed(
                title="",
                description=f"**Removed [{player.queue[0].title}]({player.queue[0].uri})**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            player.queue.pop()
            return

        try:
            track = player.queue[pos - 1]
            del player.queue[pos - 1]
            embed = discord.Embed(
                title="",
                description=f"**Removed [{track.title}]({track.uri})**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
        except IndexError:
            embed = discord.Embed(
                title="",
                description=f"**:x: Song was not found on `{pos}`,"
                f" to show what's in queue, type /q.**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)

    @slash_command(
        name="shuffle",
        description="Shuffles you queue, queue must contain more than 2 songs.",
    )
    @guild_only()
    @is_joined()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player: wavelink.Player = ctx.voice_client

        if player.queue.is_empty:
            embed = discord.Embed(
                title="", description="**Queue is empty.**", color=discord.Color.blue()
            )
            await ctx.respond(embed=embed, ephemeral=True)

        if len(player.queue) < 2:
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention}, can't shuffle 1 song in queue.",
                color=discord.Color.blue(),
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        player.queue.shuffle()
        embed = discord.Embed(
            title="", description="**🔀 Queue shuffled!**", color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

    @slash_command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @guild_only()
    @is_joined()
    async def loop_queue(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.queue.is_empty:
            embed = discord.Embed(
                title="", description="**Queue is empty**", color=discord.Color.blue()
            )
            await ctx.respond(embed=embed)
            return

        if player.queue.mode == wavelink.QueueMode.loop_all:
            player.queue.mode = wavelink.QueueMode.loop_all
            embed = discord.Embed(
                title="",
                description="**No longer looping queue.**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            return

        player.queue.mode = wavelink.QueueMode.loop_all
        embed = discord.Embed(
            title="",
            description=f"🔁 **Looping current queue ({player.queue.count} songs)**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    @slash_command(
        name="loop",
        description="Loops currently playing song, run command again to disable loop.",
    )
    @guild_only()
    @is_playing()
    async def loop(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.normal
            embed = discord.Embed(
                title="",
                description="**No longer looping current song.**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            return

        player.queue.mode = wavelink.QueueMode.loop
        embed = discord.Embed(
            title="",
            description=f"🔁 **Looping [{player.current.title}]({player.current.uri}).**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    @slash_command(name="clear-queue", description="Clears queue")
    @guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.ApplicationContext):
        player: wavelink.Player = ctx.voice_client
        player.queue.clear()

        embed = discord.Embed(
            title="", description="🗑️ **Cleared**", color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

    async def _get_queue_embeds(
        self, ctx: discord.ApplicationContext, player: wavelink.Player
    ) -> list:
        queue_status, footer = await self._get_queue_status(player.queue.mode)

        header = (
            f"\n***__{queue_status}:__***\n **[{player.current.title}]({player.current.uri})**\n"
            f" `{int(divmod(player.current.length, 60000)[0])}:{round(divmod(player.current.length, 60000)[1] / 1000):02} | "
            f"Requested by: {player.current.requester.name}`\n\n ***__Next:__***\n"
        )

        pages = []
        current_description = header

        for pos, track in enumerate(player.queue):
            track_title = track.title.replace("*", "")

            song_line = (
                f"`{pos + 1}.` **[{track_title}]({track.uri})**\n"
                f" `{int(divmod(track.length, 60000)[0])}:{round(divmod(track.length, 60000)[1] / 1000):02} | "
                f"Requested by: {track.requester.name}`\n"
            )
            if len(current_description) + len(song_line) > 4000:
                embed = discord.Embed(
                    title=f"Queue for {ctx.guild.name}",
                    description=current_description,
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"\n{footer}{player.queue.count} songs in queue")
                pages.append(embed)
                current_description = header + song_line
            else:
                current_description += song_line

        embed = discord.Embed(
            title=f"Queue for {ctx.guild.name}",
            description=current_description,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"\n{footer}{player.queue.count} songs in queue")
        pages.append(embed)
        return pages

    @staticmethod
    async def _get_queue_status(queue_mode: wavelink.QueueMode) -> tuple:
        if queue_mode == wavelink.QueueMode.loop_all:
            return "Looping queue", "🔁 "

        if queue_mode == wavelink.QueueMode.loop:
            return "Looping currently playing song", "🔁 "

        return "Now Playing", ""

    @staticmethod
    async def _get_playing_embed(ctx: discord.ApplicationContext) -> discord.Embed:
        player: wavelink.Player = ctx.voice_client

        embed = discord.Embed(
            title="Now playing",
            colour=discord.Colour.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_author(name="Playback Information")
        embed.set_footer(
            text=f"Requested by {player.current.requester.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        embed.add_field(
            name="Track title",
            value=f"**[{player.current.title}]({player.current.uri})**",
            inline=False,
        )
        embed.add_field(
            name="Artist",
            value=f"_{player.current.author if player.current.author else 'None'}_",
            inline=False,
        )
        embed.set_image(url=player.current.artwork)
        position = divmod(player.position, 60000)
        length = divmod(player.current.length, 60000)
        embed.add_field(
            name="Position",
            value=f"`{int(position[0])}:{round(position[1] / 1000):02}"
            f"/{int(length[0])}:{round(length[1] / 1000):02}`",
            inline=False,
        )
        return embed


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Queue(bot))
