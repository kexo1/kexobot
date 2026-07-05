import asyncio
import datetime
import logging
import random
import re
from typing import TYPE_CHECKING, Optional, Union

import discord
import sonolink
from discord import app_commands
from discord.app_commands import Range
from discord.ext import commands
from sonolink import models as sl_models
from sonolink.gateway.errors import QueueEmpty
from sonolink.models import AutoPlaySettings, HistorySettings

from app.config.colors import COLOR_BLUE, COLOR_RED, COLOR_YELLOW
from app.config.discord import ICON_YOUTUBE
from app.config.music import (
    API_RADIOGARDEN_LISTEN,
    API_RADIOGARDEN_PAGE,
    API_RADIOGARDEN_PLACES,
    API_RADIOGARDEN_SEARCH,
    MUSIC_SOURCES,
)
from app.decorators import is_joined, is_playing, is_queue_empty
from app.response_handler import defer_interaction, make_embed, send
from app.utils import (
    EmbedPaginator,
    find_track,
    fix_audio_title,
    get_track_requester_avatar,
    get_track_requester_name,
    make_http_request,
    make_now_playing_embed,
)

if TYPE_CHECKING:
    from app.main import KexoBotClient


def get_search_prefix(query: str) -> str | None:
    """Get the search prefix for a given query."""
    for pattern, prefix in MUSIC_SOURCES:
        if pattern.search(query):
            return prefix
    return None


def set_track_requester(
    track: sl_models.Playable,
    user: discord.abc.User,
) -> None:
    track.extras.requester_name = user.name
    avatar = getattr(getattr(user, "display_avatar", None), "url", None)
    if avatar:
        track.extras.requester_avatar = avatar


def _parse_radiomap_stream_url(url: str) -> Optional[str]:
    channel_id = url.rstrip("/").split("/")[-1]
    return f"{API_RADIOGARDEN_LISTEN}{channel_id}/channel.mp3"


async def fetch_first_track(
    ctx: discord.Interaction,
    tracks: Union[
        sl_models.SearchResult,
        sl_models.Playlist,
        sl_models.Playable,
        list[sl_models.Playable],
    ],
) -> Optional[sl_models.Playable]:
    player: sonolink.Player = ctx.guild.voice_client

    # Unwrap SearchResult
    if isinstance(tracks, sl_models.SearchResult):
        tracks = tracks.result

    # Handle Playlist
    if isinstance(tracks, sl_models.Playlist):
        return await _handle_playlist(ctx, player, tracks)

    # Handle single Playable
    if isinstance(tracks, sl_models.Playable):
        set_track_requester(tracks, ctx.user)
        return tracks

    if not tracks:
        return None

    first_track = tracks[0]
    set_track_requester(first_track, ctx.user)
    return first_track


async def _handle_playlist(
    ctx: discord.Interaction,
    player: sonolink.Player,
    playlist: sl_models.Playlist,
) -> sl_models.Playable:
    for track in playlist:
        set_track_requester(track, ctx.user)

    first_track = playlist.tracks.pop(0)
    song_count = player.queue.put(playlist)

    embed = discord.Embed(
        title="",
        description=f"Added the playlist **`{playlist.name}`** ({song_count} songs) to the queue.",
        color=COLOR_BLUE,
    )

    await send(ctx, embed=embed)
    return first_track


async def should_move_to_channel(ctx: discord.Interaction) -> bool:
    player: sonolink.Player = ctx.guild.voice_client
    if player and player.channel.id == ctx.user.voice.channel.id:
        return True

    if player.current:
        await send(
            ctx,
            embed=make_embed(
                ":x: I am playing in a different voice channel, wait till the song finishes."
            ),
        )
        return False

    await player.move_to(ctx.user.voice.channel)
    await send(
        ctx,
        embed=make_embed(f":wheelchair: Moving to <#{ctx.user.voice.channel.id}>"),
        ephemeral=False,
    )
    return True


def make_added_to_queue_embed(track: sl_models.Playable) -> discord.Embed:
    return discord.Embed(
        title="",
        description=f"**Added to queue:\n [{fix_audio_title(track)}]({track.uri})**",
        color=COLOR_BLUE,
    )


class MusicCommands(commands.Cog):
    """Music commands for the bot.
    This class contains commands for:
    - Playing music
    - Searching for music
    - Playing radio stations
    - Skipping songs
    - Pausing and resuming songs
    - Leaving voice channels
    - Changing autoplay mode
    - Getting random radio stations

    Parameters:
    bot: :class:`KexoBotClient`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: "KexoBotClient"):
        self._bot = bot
        self._session = self._bot.session
        self._radiomap_cache: list[str] = []

    music = app_commands.Group(name="music", description="All music commands")
    radio = app_commands.Group(name="radio", description="All radio commands")

    async def _execute_play(
        self,
        ctx: discord.Interaction,
        search: str,
        play_next: bool = False,
    ) -> None:
        """Shared play flow used by /music play and radio commands."""
        await defer_interaction(ctx)

        if self._bot.node_is_switching.get(ctx.guild.id, False):
            await send(
                ctx,
                embed=make_embed(
                    ":hourglass_flowing_sand: Please wait until the bot finishes switching nodes.",
                    color=COLOR_YELLOW,
                ),
            )
            return

        if not self._bot.node:
            await send(ctx, code="NODE_NOT_FOUND", ephemeral=False)
            return

        if not ctx.guild.voice_client:
            joined: bool = await self._join_channel(ctx)

            if not joined:
                return

            await self._prepare_sonolink(ctx)

        is_moved: bool = await should_move_to_channel(ctx)
        if not is_moved:
            return

        player: sonolink.Player = ctx.guild.voice_client

        tracks = await self._search_tracks(ctx, search)
        if not tracks:
            return

        track: sl_models.Playable = await fetch_first_track(ctx, tracks)
        if not track:
            return

        player.temp_current = track  # To be used in case of switching nodes

        if player.current:
            if play_next:
                player.queue.put_at(0, track)
            else:
                player.queue.put(track)

            await send(ctx, embed=make_added_to_queue_embed(track))
            return

        player._now_playing_sent = True  # Prevent listener from duplicating
        await send(ctx, embed=make_now_playing_embed(track))
        await self._play_track(ctx, track)

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
        await self._execute_play(ctx, search, play_next)

    @radio.command(name="random", description="Gets random radio from RadioMap.")
    @app_commands.describe(
        play_next="If enabled, inserts the station at the top of queue.",
    )
    @app_commands.checks.cooldown(1, 4, key=lambda i: i.user.id)
    @app_commands.guild_only()
    async def radio_random(
        self, ctx: discord.Interaction, play_next: bool = False
    ) -> None:
        """Gets a random radio station from RadioMap and plays it.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        play_next: bool
            If True, the radio station will be played next in the queue.
        """
        await defer_interaction(ctx)

        place_ids = await self._get_radiomap_data()
        if not place_ids:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        place_id = random.choice(place_ids)

        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_PAGE}{place_id}/channels",
            headers={"accept": "application/json"},
        )
        if not response:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            station_id = data["data"]["content"][0]["items"][0]["page"]["url"].split(
                "/"
            )[-1]
        except (KeyError, IndexError, ValueError):
            await send(ctx, code="RADIOMAP_ERROR")
            return
        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_LISTEN}{station_id}/channel.mp3",
            headers={"accept": "application/json"},
        )
        if not response:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        response_text = response.text
        url_match = re.search(
            r'(?:href="|Redirecting to )(https?://[^"\s]+)', response_text
        )
        if not url_match:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        station = url_match.group(1)
        if station.endswith("."):
            station = station[:-1]

        await self._execute_play(ctx, station, play_next)

    @radio.command(name="play", description="Search and play radio from RadioGarden")
    @app_commands.describe(
        station="Radio station name to search for.",
        country="Optional country filter (exact RadioGarden country name).",
        play_next="If enabled, inserts the station at the top of queue.",
    )
    @app_commands.checks.cooldown(1, 4, key=lambda i: i.user.id)
    @app_commands.guild_only()
    async def play_radio(
        self,
        ctx: discord.Interaction,
        station: str,
        country: str = "",
        play_next: bool = False,
    ) -> None:
        """Search and play a radio station from RadioGarden.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        station: str
            The name of the radio station to search for.
        country: str
            The country to narrow down the search.
        play_next: bool
            If True, the radio station will be played next in the queue.
        """
        encoded_station = discord.utils.escape_markdown(station)
        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_SEARCH}{encoded_station}",
            headers={"accept": "application/json"},
        )
        if not response:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            if not data["hits"]["hits"]:
                await send(ctx, code="RADIOMAP_NO_STATION_FOUND", search=station)
                return

            for station_data in data["hits"]["hits"]:
                station_source = station_data["_source"]["page"]
                if (
                    country
                    and country.lower()
                    not in station_source["country"]["title"].lower()
                ):
                    continue
                stream_url = _parse_radiomap_stream_url(station_source["url"])
                redirect_response = await make_http_request(
                    self._session,
                    stream_url,
                )
                stream_url = redirect_response.headers.get("Location", stream_url)
                if not stream_url:
                    continue

                await self._execute_play(ctx, stream_url, play_next)
                return

            await send(ctx, code="RADIOMAP_NO_STATION_FOUND", search=station)
        except (KeyError, ValueError):
            await send(ctx, code="RADIOMAP_ERROR")

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
        player: sonolink.Player = ctx.guild.voice_client
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
        player: sonolink.Player = ctx.guild.voice_client

        track_pos = find_track(player, to_find)
        if not track_pos:
            await send(ctx, code="NO_TRACK_FOUND_IN_QUEUE", to_find=to_find)
            return

        if track_pos > 1:
            track = player.queue.pop_at(track_pos - 1)
            player.queue.put_at(0, track)

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
        player: sonolink.Player = ctx.guild.voice_client
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
        player: sonolink.Player = ctx.guild.voice_client
        player.queue.shuffle()
        await send(ctx, code="QUEUE_SHUFFLED", ephemeral=False)

    @music.command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @app_commands.guild_only()
    @is_joined()
    async def loop_queue(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client

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
        player: sonolink.Player = ctx.guild.voice_client

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
        player: sonolink.Player = ctx.guild.voice_client
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
        player: sonolink.Player = ctx.guild.voice_client

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
        player: sonolink.Player = ctx.guild.voice_client

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
        player: sonolink.Player = ctx.guild.voice_client

        if player.queue.mode == sonolink.QueueMode.LOOP:
            await player.update(queue_mode=sonolink.QueueMode.NORMAL)
            await send(ctx, code="TRACK_LOOP_DISABLED", ephemeral=False)
            return

        await player.update(queue_mode=sonolink.QueueMode.LOOP)
        await send(
            ctx,
            code="TRACK_LOOP_ENABLED",
            ephemeral=False,
            title=player.current.title,
            uri=player.current.uri,
        )

    @music.command(name="clear-queue", description="Clears queue and history.")
    @app_commands.guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
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
        volume: Optional[Range[int, 0, 200]] = None,
    ) -> None:
        player: sonolink.Player = ctx.guild.voice_client

        if volume is None:
            await send(
                ctx,
                embed=make_embed(f"🔊 Current volume: {player.volume}"),
            )
            return

        guild = await self._bot.guild_data_manager.get(ctx.guild.id)
        guild.music.volume = volume
        await self._bot.guild_data_manager.save(ctx.guild.id, guild)
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
        multiplier: Optional[Range[int, 1, 4]] = 1,
    ) -> None:
        player: sonolink.Player = ctx.guild.voice_client
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
        player: sonolink.Player = ctx.guild.voice_client
        filters = sl_models.Filters()
        await player.set_filters(filters)
        await send(ctx, embed=make_embed("🔇 Effects cleared."), ephemeral=False)

    @music.command(name="queue", description="Shows the current queue")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def queue(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
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
        player: sonolink.Player = ctx.guild.voice_client
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
        player: sonolink.Player = ctx.guild.voice_client

        if player.channel.id != ctx.user.voice.channel.id:
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
        guild = await self._bot.guild_data_manager.get(ctx.guild.id)
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
        player: sonolink.Player = ctx.guild.voice_client
        await player.update(
            autoplay_settings=AutoPlaySettings(
                mode=new_autoplay_mode,
                discovery_count=10,
            )
        )

        guild.music.autoplay_mode = 1 if mode == "normal" else 2
        await self._bot.guild_data_manager.save(ctx.guild.id, guild)

        await send(
            ctx,
            embed=make_embed(f"Autoplay mode changed to `{mode}`"),
            ephemeral=False,
        )

    async def _search_tracks(
        self, ctx: discord.Interaction, search: str
    ) -> Optional[
        Union[
            sl_models.SearchResult,
            sl_models.Playlist,
            sl_models.Playable,
            list[sl_models.Playable],
        ]
    ]:
        source = get_search_prefix(search)
        # If it's not a URL with a recognizable prefix, default to YouTube search
        if source is None:
            if search.startswith("http://") or search.startswith("https://"):
                source = None
            else:
                source = "ytsearch"

        # Prefer youtube over spotify, but if youtube fails, try spotify
        if source == "spsearch":
            spotify_search = True
            source = "ytsearch"
        else:
            spotify_search = False

        player: sonolink.Player = ctx.guild.voice_client

        for i in range(2):
            try:
                tracks: sl_models.SearchResult = await asyncio.wait_for(
                    self._bot.sonolink_client.search_track(search, source=source),
                    timeout=5,
                )
                if not tracks.is_error() and not tracks.is_empty() and tracks.result:
                    return tracks

                if spotify_search:
                    # Keep one lightweight fallback without switching nodes.
                    tracks = await asyncio.wait_for(
                        self._bot.sonolink_client.search_track(
                            search, source="spsearch"
                        ),
                        timeout=5,
                    )
                    if (
                        not tracks.is_error()
                        and not tracks.is_empty()
                        and tracks.result
                    ):
                        return tracks

            except asyncio.TimeoutError:
                await send(
                    ctx,
                    embed=make_embed(
                        ":warning: Node timed out finding tracks, switching to another node.",
                        color=COLOR_YELLOW,
                    ),
                    ephemeral=False,
                )
                await self._bot.state.switch_node(
                    player=player,
                    play_after=True,
                    send_failure_message=False,
                )
                continue

            except Exception as e:
                await send(
                    ctx,
                    embed=make_embed(
                        ":x: Failed to load tracks. You likely entered a wrong link or "
                        "this Lavalink server lacks necessary plugins.\n"
                        "Try using command `/node reconnect`",
                        color=COLOR_RED,
                    ),
                    ephemeral=False,
                )
                logging.error("[sonolink] Error searching for tracks: %s", e)
                return None

        await send(
            ctx,
            code="NO_TRACKS_FOUND",
            ephemeral=False,
            search=search,
        )
        return None

    async def _join_channel(self, ctx: discord.Interaction) -> bool:
        if not ctx.user.voice or not ctx.user.voice.channel:
            await send(ctx, code="NO_VOICE_CHANNEL")
            return False

        channel = ctx.user.voice.channel
        guild = await self._bot.guild_data_manager.get(ctx.guild.id)
        autoplay_mode = (
            sonolink.AutoPlayMode.PARTIAL
            if guild.music.autoplay_mode == 1
            else sonolink.AutoPlayMode.ENABLED
        )

        last_error: Exception | None = None
        failed_uris = set()
        node = self._bot.node

        for attempt in range(4):
            if attempt == 0:
                if not await self._bot.state.node_health_check(node):
                    failed_uris.add(node.uri)
                    continue
            else:
                node = await self._bot.connect_node(
                    exclude_nodes=list(failed_uris),
                )
            if not node:
                await send(ctx, code="NODE_NOT_FOUND", ephemeral=False)
                return False

            try:
                player_cls = self._build_player_class(node, autoplay_mode)
                await channel.connect(cls=player_cls, timeout=10)
                return True

            except (discord.Forbidden, discord.ClientException):
                await send(ctx, code="NO_PERMISSIONS", ephemeral=False)
                return False

            except Exception as e:
                last_error = e
                failed_uris.add(node.uri)
                score = self._bot.state.get_node_score(node.uri)
                # Punish the node on voice connection failure
                score = -score - 1
                self._bot.state.change_node_score(node.uri, score)
                logging.warning(
                    "[Sonolink] Voice connect attempt %s failed for node %s: %s",
                    attempt + 1,
                    node.uri,
                    e,
                )

        await send(
            ctx,
            embed=make_embed(
                ":x: Failed to connect to voice channel, try again later.",
                color=COLOR_RED,
            ),
            ephemeral=False,
        )
        if last_error:
            logging.error(
                "[Sonolink] Error connecting to voice channel: %s",
                last_error,
            )

        return False

    def _build_player_class(
        self,
        node: sonolink.Node,
        autoplay_mode: sonolink.AutoPlayMode = sonolink.AutoPlayMode.PARTIAL,
    ):
        return node.create_player(
            autoplay_settings=AutoPlaySettings(
                mode=autoplay_mode,
                discovery_count=10,
            ),
            history_settings=HistorySettings(
                enabled=True,
                max_items=16,
            ),
        )

    async def _play_track(
        self, ctx: discord.Interaction, track: sl_models.Playable
    ) -> bool:
        player: sonolink.Player = ctx.guild.voice_client
        for i in range(3):
            try:
                await player.play(track)
                break
            except Exception as e:
                logging.error(
                    f"[sonolink] {i + 1}. Error playing track, retrying: %s", e
                )

        set_track_requester(track, ctx.user)
        return True

    async def _prepare_sonolink(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
        player.text_channel = ctx.channel

        guild = await self._bot.guild_data_manager.get(ctx.guild.id)
        volume = guild.music.volume
        try:
            await player.set_volume(volume)
        except Exception as e:
            if "Session not found" not in str(e):
                raise

            await self._bot.state.switch_node(
                player=player,
                send_success_message=False,
                send_failure_message=False,
            )
            await player.set_volume(volume)

        await send(
            ctx,
            embed=make_embed(
                f"Joined <#{player.channel.id}>, text channel set to <#{player.text_channel.id}>."
            ),
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
                    title=f"Queue for {ctx.guild.name}",
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
                    title=f"Queue for {ctx.guild.name}",
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
                        title=f"Queue for {ctx.guild.name}",
                        description=current_description,
                        color=COLOR_BLUE,
                    )
                    embed.set_footer(text=f"{len(player.queue)} songs in queue")
                    pages.append(embed)
                    current_description = autoplay_header + song_line
                else:
                    current_description += song_line

        embed = discord.Embed(
            title=f"Queue for {ctx.guild.name}",
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
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_author(name="Playback Information")

        requester_name = get_track_requester_name(player.current)
        requester_avatar = get_track_requester_avatar(player.current)
        if not player.current.autoplay:
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

    async def _get_radiomap_data(self) -> list[str]:
        """Get radio map data with caching."""
        if self._radiomap_cache:
            return self._radiomap_cache

        response = await make_http_request(
            self._session,
            API_RADIOGARDEN_PLACES,
            headers={"accept": "application/json"},
        )
        if not response:
            return self._radiomap_cache

        data = response.json()
        if "data" in data and "list" in data["data"]:
            place_ids = [
                item["url"].split("/")[-1]
                for item in data["data"]["list"]
                if "url" in item
            ]
            self._radiomap_cache = place_ids
            return place_ids
        return []


async def setup(bot: "KexoBotClient") -> None:
    """Setup function for the MusicCommands cog."""
    cog = MusicCommands(bot)
    await bot.add_cog(cog)
    # Add command groups
    bot.tree.add_command(cog.music, override=True)
    bot.tree.add_command(cog.radio, override=True)
