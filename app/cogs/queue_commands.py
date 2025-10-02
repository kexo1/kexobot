import datetime

import discord
import wavelink
from discord.commands import slash_command, option, guild_only
from discord.ext import commands
from pycord.multicog import subcommand

from app.constants import YOUTUBE_ICON
from app.decorators import is_playing, is_joined, is_queue_empty
from app.response_handler import send_response
from app.utils import find_track, fix_audio_title, has_pfp, QueuePaginator


class Queue(commands.Cog):
    """A cog that handles queue commands for a music bot.

    This cog provides commands to manage the music queue, including
    displaying the current queue, removing tracks, shuffling the queue,
    looping the queue, and clearing the queue.
    It also provides a paginator for the queue command to navigate
    through multiple pages of the queue.

    Parameters
    ----------
    bot: :class:`discord.ext.commands.Bot`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot

    @subcommand("music")
    @slash_command(name="queue", description="Shows the current queue")
    @guild_only()
    @is_joined()
    @is_queue_empty()
    async def queue(self, ctx: discord.ApplicationContext) -> None:
        """This method displays the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        player: wavelink.Player = ctx.voice_client
        pages = await self._get_queue_embeds(ctx, player)

        if len(pages) == 1:
            await ctx.respond(embed=pages[0])
        else:
            view = QueuePaginator(pages)
            await ctx.respond(embed=pages[0], view=view)

    @subcommand("music")
    @slash_command(name="playing", description="What track is currently playing")
    @guild_only()
    @is_playing()
    async def playing_command(self, ctx: discord.ApplicationContext) -> None:
        """This method displays the currently playing track.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        await ctx.respond(embed=await self._get_playing_embed(ctx))

    @subcommand("music")
    @slash_command(name="remove", description="Removes a song from the queue")
    @guild_only()
    @option(
        "to_find",
        description="Both position in the queue and name of the song are accepted.",
    )
    @is_joined()
    @is_queue_empty()
    async def remove(self, ctx: discord.ApplicationContext, to_find: str):
        """This method removes a song from the queue.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        to_find: str
            The name of the song to be removed from the queue.
        """
        player: wavelink.Player = ctx.voice_client
        track_pos = find_track(player, to_find)
        if track_pos is None:
            await send_response(ctx, "NO_TRACK_FOUND_IN_QUEUE", to_find=to_find)
            return

        track = player.queue[track_pos - 1]
        player.queue.pop(track_pos - 1)
        await send_response(
            ctx,
            "QUEUE_TRACK_REMOVED",
            ephemeral=False,
            title=track.title,
            uri=track.uri,
        )

    @subcommand("music")
    @slash_command(
        name="shuffle",
        description="Shuffles the queue",
    )
    @guild_only()
    @is_joined()
    @is_queue_empty()
    async def shuffle(self, ctx: discord.ApplicationContext):
        """This method shuffles the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        player: wavelink.Player = ctx.voice_client

        if len(player.queue) < 2:
            await send_response(ctx, "CANT_SHUFFLE")
            return

        player.queue.shuffle()
        await send_response(ctx, "QUEUE_SHUFFLED", ephemeral=False)

    @subcommand("music")
    @slash_command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @guild_only()
    @is_joined()
    @is_queue_empty()
    async def loop_queue(self, ctx: discord.ApplicationContext) -> None:
        """This method loops the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        player: wavelink.Player = ctx.voice_client

        if player.queue.mode == wavelink.QueueMode.loop_all:
            player.queue.mode = wavelink.QueueMode.loop_all
            await send_response(ctx, "QUEUE_LOOP_DISABLED")
            return

        player.queue.mode = wavelink.QueueMode.loop_all
        await send_response(
            ctx,
            "QUEUE_LOOP_ENABLED",
            ephemeral=False,
            count=player.queue.count,
        )

    @subcommand("music")
    @slash_command(
        name="loop",
        description="Loops currently playing song, run command again to disable loop.",
    )
    @guild_only()
    @is_playing()
    async def loop(self, ctx: discord.ApplicationContext) -> None:
        """This method loops the currently playing song.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        player: wavelink.Player = ctx.voice_client

        if player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.normal
            await send_response(ctx, "TRACK_LOOP_DISABLED")
            return

        player.queue.mode = wavelink.QueueMode.loop
        await send_response(
            ctx,
            "TRACK_LOOP_ENABLED",
            ephemeral=False,
            title=player.current.title,
            uri=player.current.uri,
        )

    @subcommand("music")
    @slash_command(name="clear", description="Clears queue")
    @guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.ApplicationContext):
        """This method clears the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        player: wavelink.Player = ctx.voice_client
        player.queue.clear()
        await send_response(ctx, "QUEUE_CLEARED", ephemeral=False)

    async def _get_queue_embeds(
        self, ctx: discord.ApplicationContext, player: wavelink.Player
    ) -> list:
        queue_status, footer = await self._get_queue_status(player.queue.mode)

        header = (
            f"\n***__{queue_status}:__***\n **[{fix_audio_title(player.current)}]"
            f"({player.current.uri})**\n"
            f" `{int(divmod(player.current.length, 60000)[0])}:"
            f"{round(divmod(player.current.length, 60000)[1] / 1000):02} | "
            f"Requested by: {player.current.requester.name}`\n\n ***__Next:__***\n"
        )

        pages = []
        current_description = header

        for pos, track in enumerate(player.queue):
            song_line = (
                f"`{pos + 1}.` **[{fix_audio_title(track)}]({track.uri})**\n"
                f" `{int(divmod(track.length, 60000)[0])}:"
                f"{round(divmod(track.length, 60000)[1] / 1000):02} | "
                f"Requested by: {track.requester.name}`\n"
            )
            if len(current_description) + len(song_line) > 4096:
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
    async def _get_playing_embed(
        ctx: discord.ApplicationContext,
    ) -> discord.Embed:
        player: wavelink.Player = ctx.voice_client

        embed = discord.Embed(
            title="Now playing",
            colour=discord.Colour.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_author(name="Playback Information")

        if hasattr(player.current, "requester"):
            embed.set_footer(
                text=f"Requested by {player.current.requester.name}",
                icon_url=has_pfp(ctx.author),
            )
        else:
            embed.set_footer(
                text="YouTube Autoplay",
                icon_url=YOUTUBE_ICON,
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
    """This function sets up the Queue cog."""
    bot.add_cog(Queue(bot))
