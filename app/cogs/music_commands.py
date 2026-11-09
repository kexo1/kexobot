import datetime
from typing import TYPE_CHECKING, cast

import discord
import sonolink
from discord import app_commands
from discord.app_commands import Range
from discord.ext import commands
from sonolink import models as sl_models
from sonolink.gateway.errors import QueueEmpty
from sonolink.models import AutoPlaySettings

from app.config.colors import COLOR_BLUE, COLOR_RED
from app.config.discord import ICON_YOUTUBE
from app.decorators import is_joined, is_playing, is_queue_empty
from app.music.playback import MusicPlaybackService
from app.player_types import caller_voice_channel, get_player, guild_of
from app.response_handler import defer_interaction, make_embed, send
from app.utils import (
    EmbedPaginator,
    find_track,
    fix_audio_title,
    get_track_requester_avatar,
    get_track_requester_name,
)

if TYPE_CHECKING:
    from app.client import KexoBotClient


class MusicCommands(commands.Cog):
    """Music commands for the bot.
    This class contains commands for:
    - Playing music
    - Searching for music
    - Skipping songs
    - Pausing and resuming songs
    - Leaving voice channels
    - Changing autoplay mode

    Parameters:
    bot: :class:`KexoBotClient`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: "KexoBotClient"):
        self._bot = bot
        self._playback = MusicPlaybackService(bot)

    music = app_commands.Group(name="music", description="All music commands")

    @music.command(name="play", description="Plays song.")
    @app_commands.describe(
        search="Song query or URL to play.",
        play_next="If enabled, inserts the track at the top of queue.",
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 4, key=lambda i: i.user.id)
    async def play(
        self,
        ctx: discord.Interaction,
        search: str,
        play_next: bool = False,
    ) -> None:
        """Plays a song from a given URL or name.

        This command will search for the song using the provided search query.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        search: :class:`str`
            The search query for the song.
        play_next: :class:`bool`
            If True, the song will be played next in the queue.
        """
        await self._playback.execute_play(ctx, search, play_next)

    @music.command(name="skip", description="Skip playing song.")
    @app_commands.guild_only()
    @is_playing()
    async def skip_command(self, ctx: discord.Interaction) -> None:
        """Skip the currently playing song.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        player = get_player(ctx)
        await defer_interaction(ctx)

        try:
            await player.skip()
        except QueueEmpty:
            pass

        await send(ctx, embed=make_embed("⏭️ Track skipped."), ephemeral=False)

    @music.command(name="skip-to", description="Skips to selected song in queue.")
    @app_commands.describe(
        to_find="Song name or queue index to skip to.",
    )
    @app_commands.guild_only()
    @is_playing()
    @is_queue_empty()
    async def skip_to_command(
        self,
        ctx: discord.Interaction,
        to_find: Range[str, 1, 120],
    ) -> None:
        """Skip to a specific song in the queue.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        to_find: str
            The name of the song or its position in the queue.
        """
        player = get_player(ctx)

        track_pos = find_track(player, to_find)
        if not track_pos:
            await send(ctx, code="NO_TRACK_FOUND_IN_QUEUE", to_find=to_find)
            return

        if track_pos > 1:
            track = player.queue.pop_at(track_pos - 1)
            player.queue.put_at(0, track)
        else:
            track = player.queue[track_pos - 1]

        try:
            await player.skip()
        except QueueEmpty:
            pass

        await send(
            ctx,
            embed=make_embed(f"⏭️ Skipped to [{track.title}]({track.uri})"),
            ephemeral=False,
        )

    @music.command(name="remove", description="Removes a song from the queue")
    @app_commands.describe(to_find="Song name or queue index to remove.")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def remove(
        self,
        ctx: discord.Interaction,
        to_find: Range[str, 1, 120],
    ) -> None:
        player = get_player(ctx)
        track_pos = find_track(player, to_find)
        if track_pos is None:
            await send(ctx, code="NO_TRACK_FOUND_IN_QUEUE", to_find=to_find)
            return

        track = player.queue.pop_at(track_pos - 1)
        await send(
            ctx,
            code="QUEUE_TRACK_REMOVED",
            ephemeral=False,
            title=track.title,
            uri=track.uri,
        )

    @music.command(name="shuffle", description="Shuffles the queue")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def shuffle(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)
        player.queue.shuffle()
        await send(ctx, code="QUEUE_SHUFFLED", ephemeral=False)

    @music.command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @app_commands.guild_only()
    @is_joined()
    async def loop_queue(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)

        if len(player.queue) == 0 and player.queue.mode != sonolink.QueueMode.LOOP_ALL:
            await send(ctx, code="NO_TRACKS_IN_QUEUE")
            return

        if player.queue.mode == sonolink.QueueMode.LOOP_ALL:
            await player.update(queue_mode=sonolink.QueueMode.NORMAL)
            await send(ctx, code="QUEUE_LOOP_DISABLED", ephemeral=False)
            return

        await player.update(queue_mode=sonolink.QueueMode.LOOP_ALL)
        await send(
            ctx,
            code="QUEUE_LOOP_ENABLED",
            ephemeral=False,
            count=len(player.queue),
        )

    @music.command(name="pause", description="Pauses song that is currently playing.")
    @app_commands.guild_only()
    @is_playing()
    async def pause(self, ctx: discord.Interaction) -> None:
        """Pause the currently playing song.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        player = get_player(ctx)

        if player.paused:
            await send(ctx, embed=make_embed(":x: Track is already paused."))
            return

        await player.pause()
        await send(
            ctx,
            embed=make_embed("⏸️ Track paused."),
            ephemeral=False,
            delete_after=10,
        )

    @music.command(name="resume", description="Resumes paused song.")
    @app_commands.guild_only()
    @is_playing()
    async def resume(self, ctx: discord.Interaction) -> None:
        """Resume the currently paused song.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        player = get_player(ctx)
        await player.resume()
        await send(
            ctx,
            embed=make_embed("▶️ Track resumed."),
            ephemeral=False,
            delete_after=10,
        )

    @music.command(name="seek", description="Seek to a position in the current track.")
    @app_commands.describe(
        seconds="Position to seek to in seconds (e.g., 30 for 30 seconds, 90 for 1:30)."
    )
    @app_commands.guild_only()
    @is_playing()
    async def seek(
        self, ctx: discord.Interaction, seconds: Range[int, 0, 3600]
    ) -> None:
        """Seek to a specific position in the currently playing track.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        seconds: int
            The position to seek to in seconds.
        """
        player = get_player(ctx)

        # Convert seconds to milliseconds
        position_ms = seconds * 1000

        # Check if position is within track duration
        if player.current and position_ms > player.current.length:
            await send(
                ctx,
                embed=make_embed(
                    f":x: Invalid seek position. Track duration is "
                    f"{int(player.current.length / 1000)} seconds.",
                    color=COLOR_RED,
                ),
                ephemeral=False,
            )
            return

        await player.seek(position_ms)
        await send(
            ctx,
            embed=make_embed(f"⏩ Seeked to {seconds} seconds."),
            ephemeral=False,
        )

    @music.command(name="previous", description="Play the previous track from history.")
    @app_commands.guild_only()
    @is_joined()
    async def previous(self, ctx: discord.Interaction) -> None:
        """Play the most recently played track from history.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        player = get_player(ctx)

        try:
            track = await player.previous()
        except sonolink.HistoryEmpty:
            await send(
                ctx,
                embed=make_embed(":x: No previous track in history."),
                ephemeral=False,
            )
            return

        await send(
            ctx,
            embed=make_embed(f"⏮️ Playing previous track [{track.title}]({track.uri})"),
            ephemeral=False,
        )

    @music.command(
        name="loop",
        description="Loops currently playing song, run command again to disable loop.",
    )
    @app_commands.guild_only()
    @is_playing()
    async def loop(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)

        if player.queue.mode == sonolink.QueueMode.LOOP:
            await player.update(queue_mode=sonolink.QueueMode.NORMAL)
            await send(ctx, code="TRACK_LOOP_DISABLED", ephemeral=False)
            return

        await player.update(queue_mode=sonolink.QueueMode.LOOP)
        current = cast(sl_models.Playable, player.current)  # guarded by @is_playing
        await send(
            ctx,
            code="TRACK_LOOP_ENABLED",
            ephemeral=False,
            title=current.title,
            uri=current.uri,
        )

    @music.command(name="clear-queue", description="Clears queue and history.")
    @app_commands.guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)
        player.queue.clear()
        player.queue.clear_history()
        await send(ctx, code="QUEUE_CLEARED", ephemeral=False)

    @music.command(name="volume", description="Sets audio volume.")
    @app_commands.describe(
        volume="New volume level (0-200). Leave empty to show current volume."
    )
    @app_commands.guild_only()
    @is_joined()
    async def change_volume(
        self,
        ctx: discord.Interaction,
        volume: Range[int, 0, 200] | None = None,
    ) -> None:
        player = get_player(ctx)

        if volume is None:
            await send(
                ctx,
                embed=make_embed(f"🔊 Current volume: {player.volume}"),
            )
            return

        guild = await self._bot.guild_data_manager.get(guild_of(ctx).id)
        guild.music.volume = volume
        await self._bot.guild_data_manager.save(guild_of(ctx).id, guild)
        await player.set_volume(volume)
        await send(
            ctx,
            embed=make_embed(f"🔊 Volume set to {volume}"),
            ephemeral=False,
        )

    @music.command(name="speed", description="Speeds up music.")
    @app_commands.describe(multiplier="Playback speed multiplier (1-4).")
    @app_commands.guild_only()
    @is_joined()
    async def speed(
        self,
        ctx: discord.Interaction,
        multiplier: Range[int, 1, 4] | None = 1,
    ) -> None:
        player = get_player(ctx)
        filters = sl_models.Filters(timescale=sl_models.Timescale(speed=multiplier))

        await player.set_filters(filters)
        await send(
            ctx,
            embed=make_embed(f"⏩ Speed set to {multiplier}x"),
            ephemeral=False,
        )

    @music.command(name="clear-effects", description="Clears all effects on player.")
    @app_commands.guild_only()
    @is_joined()
    async def clear_effects(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)
        filters = sl_models.Filters()
        await player.set_filters(filters)
        await send(ctx, embed=make_embed("🔇 Effects cleared."), ephemeral=False)

    @music.command(name="queue", description="Shows the current queue")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def queue(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)
        pages = self._build_queue_embeds(ctx, player)

        if len(pages) == 1:
            await send(ctx, embed=pages[0])
        else:
            view = EmbedPaginator(pages)
            await send(ctx, embed=pages[0], view=view)

    @music.command(name="playing", description="What track is currently playing")
    @app_commands.guild_only()
    @is_playing()
    async def playing_command(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)
        await send(ctx, embed=self._build_playing_embed(player))

    @music.command(name="leave", description="Leaves voice channel.")
    @app_commands.guild_only()
    @is_joined()
    async def disconnect(self, ctx: discord.Interaction) -> None:
        """Disconnect the bot from the voice channel.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        player = get_player(ctx)

        if player.channel.id != caller_voice_channel(ctx).id:
            await send(ctx, code="NOT_IN_SAME_VOICE_CHANNEL")
            return

        await send(
            ctx,
            embed=make_embed(f"Left <#{player.channel.id}>"),
            ephemeral=False,
        )
        player.cleanup()
        await player.disconnect()

    @music.command(
        name="autoplay_mode",
        description="Change autoplay mode when playing music.",
    )
    @app_commands.describe(
        mode="Autoplay mode to use, populated adds related tracks to autoplay."
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="normal", value="normal"),
            app_commands.Choice(name="populated", value="populated"),
        ]
    )
    @app_commands.guild_only()
    @is_joined()
    async def autoplay_mode(self, ctx: discord.Interaction, mode: str = "") -> None:
        """Change the autoplay mode for the bot.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        mode: str
            The autoplay mode to set. Can be either "normal" or "populated".
        """
        guild = await self._bot.guild_data_manager.get(guild_of(ctx).id)
        current_autoplay_mode = (
            "normal" if guild.music.autoplay_mode == 1 else "populated"
        )

        if not mode:
            await send(
                ctx,
                embed=make_embed(f"Autoplay mode: `{current_autoplay_mode}`"),
                ephemeral=False,
            )
            return

        new_autoplay_mode = (
            sonolink.AutoPlayMode.PARTIAL
            if mode == "normal"
            else sonolink.AutoPlayMode.ENABLED
        )
        player = get_player(ctx)
        await player.update(
            autoplay_settings=AutoPlaySettings(
                mode=new_autoplay_mode,
                discovery_count=10,
            )
        )

        guild.music.autoplay_mode = 1 if mode == "normal" else 2
        await self._bot.guild_data_manager.save(guild_of(ctx).id, guild)

        await send(
            ctx,
            embed=make_embed(f"Autoplay mode changed to `{mode}`"),
            ephemeral=False,
        )

    def _build_queue_embeds(
        self, ctx: discord.Interaction, player: sonolink.Player
    ) -> list[discord.Embed]:
        if not player.current:
            embed = discord.Embed(
                title="",
                description="Queue is currently empty.",
                color=COLOR_BLUE,
            )
            return [embed]

        queue_status = "Now Playing"
        if player.queue.mode == sonolink.QueueMode.LOOP_ALL:
            queue_status = "Looping queue"
        elif player.queue.mode == sonolink.QueueMode.LOOP:
            queue_status = "Looping currently playing song"

        current = player.current
        requester_label = (
            "Autoplay"
            if current.autoplay
            else f"Requested by: {get_track_requester_name(current)}"
        )
        header = (
            f"\n***__{queue_status}:__***\n "
            f"**[{fix_audio_title(current)}]({current.uri})**\n"
            f" `{int(divmod(current.length, 60000)[0])}:"
            f"{round(divmod(current.length, 60000)[1] / 1000):02} | "
            f"{requester_label}`\n\n ***__Next:__***\n"
        )

        pages: list[discord.Embed] = []
        current_description = header
        for pos, track in enumerate(player.queue):
            track_requester = get_track_requester_name(track)
            song_line = (
                f"`{pos + 1}.` **[{fix_audio_title(track)}]({track.uri})**\n"
                f" `{int(divmod(track.length, 60000)[0])}:"
                f"{round(divmod(track.length, 60000)[1] / 1000):02} | "
                f"Requested by: {track_requester}`\n"
            )

            if len(current_description) + len(song_line) > 4096:
                embed = discord.Embed(
                    title=f"Queue for {guild_of(ctx).name}",
                    description=current_description,
                    color=COLOR_BLUE,
                )
                embed.set_footer(text=f"{len(player.queue)} songs in queue")
                pages.append(embed)
                current_description = header + song_line
            else:
                current_description += song_line

        autoplay_tracks = player.queue.autoplay_tracks
        if autoplay_tracks:
            autoplay_header = "\n ***__Autoplay:__***\n"
            if len(current_description) + len(autoplay_header) > 4096:
                embed = discord.Embed(
                    title=f"Queue for {guild_of(ctx).name}",
                    description=current_description,
                    color=COLOR_BLUE,
                )
                embed.set_footer(text=f"{len(player.queue)} songs in queue")
                pages.append(embed)
                current_description = autoplay_header
            else:
                current_description += autoplay_header

            for pos, track in enumerate(autoplay_tracks):
                song_line = (
                    f"`#{pos + 1}.` **[{fix_audio_title(track)}]({track.uri})**\n"
                    f" `{int(divmod(track.length, 60000)[0])}:"
                    f"{round(divmod(track.length, 60000)[1] / 1000):02} | Autoplay`\n"
                )
                if len(current_description) + len(song_line) > 4096:
                    embed = discord.Embed(
                        title=f"Queue for {guild_of(ctx).name}",
                        description=current_description,
                        color=COLOR_BLUE,
                    )
                    embed.set_footer(text=f"{len(player.queue)} songs in queue")
                    pages.append(embed)
                    current_description = autoplay_header + song_line
                else:
                    current_description += song_line

        embed = discord.Embed(
            title=f"Queue for {guild_of(ctx).name}",
            description=current_description,
            color=COLOR_BLUE,
        )
        embed.set_footer(text=f"{len(player.queue)} songs in queue")
        pages.append(embed)
        return pages

    def _build_playing_embed(self, player: sonolink.Player) -> discord.Embed:
        embed = discord.Embed(
            title="Now playing",
            colour=discord.Colour.blue(),
            timestamp=datetime.datetime.now(datetime.UTC),
        )
        embed.set_author(name="Playback Information")

        current = cast(sl_models.Playable, player.current)  # embed implies a track
        requester_name = get_track_requester_name(current)
        requester_avatar = get_track_requester_avatar(current)
        if not current.autoplay:
            embed.set_footer(
                text=f"Requested by {requester_name}",
                icon_url=requester_avatar,
            )
        else:
            embed.set_footer(
                text="YouTube Autoplay",
                icon_url=ICON_YOUTUBE,
            )

        embed.add_field(
            name="Track title",
            value=f"**[{current.title}]({current.uri})**",
            inline=False,
        )
        embed.add_field(
            name="Artist",
            value=f"_{current.author if current.author else 'None'}_",
            inline=False,
        )
        embed.set_image(url=current.artwork)

        position = divmod(player.position, 60000)
        length = divmod(current.length, 60000)
        embed.add_field(
            name="Position",
            value=f"`{int(position[0])}:{round(position[1] / 1000):02}"
            f"/{int(length[0])}:{round(length[1] / 1000):02}`",
            inline=False,
        )
        return embed


async def setup(bot: "KexoBotClient") -> None:
    """Setup function for the MusicCommands cog."""
    cog = MusicCommands(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.music, override=True)
