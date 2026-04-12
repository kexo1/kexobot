import datetime

import discord
import sonolink
from discord import app_commands
from discord.ext import commands

from app.constants import ICON_YOUTUBE
from app.decorators import is_joined, is_playing, is_queue_empty
from app.response_handler import send_interaction, send_response
from app.utils import QueuePaginator, find_track, fix_audio_title, has_pfp


def get_queue_status(queue_mode: sonolink.QueueMode) -> tuple[str, str]:
    if queue_mode == sonolink.QueueMode.LOOP_ALL:
        return "Looping queue", "🔁 "

    if queue_mode == sonolink.QueueMode.LOOP:
        return "Looping currently playing song", "🔁 "

    return "Now Playing", ""


def get_queue_embeds(
    ctx: discord.Interaction, player: sonolink.Player
) -> list[discord.Embed]:
    queue_status, footer = get_queue_status(player.queue.mode)

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
            embed.set_footer(text=f"\n{footer}{len(player.queue)} songs in queue")
            pages.append(embed)
            current_description = header + song_line
        else:
            current_description += song_line

    embed = discord.Embed(
        title=f"Queue for {ctx.guild.name}",
        description=current_description,
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"\n{footer}{len(player.queue)} songs in queue")
    pages.append(embed)
    return pages


def get_playing_embed(
    ctx: discord.Interaction,
) -> discord.Embed:
    player: sonolink.Player = ctx.guild.voice_client

    embed = discord.Embed(
        title="Now playing",
        colour=discord.Colour.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_author(name="Playback Information")

    if hasattr(player.current, "requester"):
        embed.set_footer(
            text=f"Requested by {player.current.requester.name}",
            icon_url=has_pfp(player.current.requester),
        )
    else:
        embed.set_footer(
            text="YouTube Autoplay",
            icon_url=ICON_YOUTUBE,
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

    @app_commands.command(name="queue", description="Shows the current queue")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def queue(self, ctx: discord.Interaction) -> None:
        """This method displays the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        player: sonolink.Player = ctx.guild.voice_client
        pages = get_queue_embeds(ctx, player)

        if len(pages) == 1:
            await send_interaction(ctx, embed=pages[0])
        else:
            view = QueuePaginator(pages)
            await send_interaction(ctx, embed=pages[0], view=view)

    @app_commands.command(name="playing", description="What track is currently playing")
    @app_commands.guild_only()
    @is_playing()
    async def playing_command(self, ctx: discord.Interaction) -> None:
        """This method displays the currently playing track.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        await send_interaction(ctx, embed=get_playing_embed(ctx))

    @app_commands.command(name="remove", description="Removes a song from the queue")
    @app_commands.describe(to_find="Song name or queue index to remove.")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def remove(
        self,
        ctx: discord.Interaction,
        to_find: app_commands.Range[str, 1, 120],
    ):
        """This method removes a song from the queue.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        to_find: str
            The name of the song to be removed from the queue.
        """
        player: sonolink.Player = ctx.guild.voice_client
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

    @app_commands.command(
        name="shuffle",
        description="Shuffles the queue",
    )
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def shuffle(self, ctx: discord.Interaction):
        """This method shuffles the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        player: sonolink.Player = ctx.guild.voice_client

        if len(player.queue) < 2:
            await send_response(ctx, "CANT_SHUFFLE")
            return

        player.queue.shuffle()
        await send_response(ctx, "QUEUE_SHUFFLED", ephemeral=False)

    @app_commands.command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def loop_queue(self, ctx: discord.Interaction) -> None:
        """This method loops the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        player: sonolink.Player = ctx.guild.voice_client

        if player.queue.mode == sonolink.QueueMode.LOOP_ALL:
            player.queue.mode = sonolink.QueueMode.NORMAL
            await send_response(ctx, "QUEUE_LOOP_DISABLED")
            return

        player.queue.mode = sonolink.QueueMode.LOOP_ALL
        await send_response(
            ctx,
            "QUEUE_LOOP_ENABLED",
            ephemeral=False,
            count=len(player.queue),
        )

    @app_commands.command(
        name="loop",
        description="Loops currently playing song, run command again to disable loop.",
    )
    @app_commands.guild_only()
    @is_playing()
    async def loop(self, ctx: discord.Interaction) -> None:
        """This method loops the currently playing song.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        player: sonolink.Player = ctx.guild.voice_client

        if player.queue.mode == sonolink.QueueMode.LOOP:
            player.queue.mode = sonolink.QueueMode.NORMAL
            await send_response(ctx, "TRACK_LOOP_DISABLED")
            return

        player.queue.mode = sonolink.QueueMode.LOOP
        await send_response(
            ctx,
            "TRACK_LOOP_ENABLED",
            ephemeral=False,
            title=player.current.title,
            uri=player.current.uri,
        )

    @app_commands.command(name="clear", description="Clears queue")
    @app_commands.guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.Interaction):
        """This method clears the current music queue.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        player: sonolink.Player = ctx.guild.voice_client
        player.queue.clear()
        await send_response(ctx, "QUEUE_CLEARED", ephemeral=False)


async def setup(bot: commands.Bot) -> None:
    """This function sets up the Queue cog."""
    await bot.add_cog(Queue(bot))
