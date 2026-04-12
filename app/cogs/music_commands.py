import asyncio
import datetime
import logging
import random
import re
from typing import Optional, Union

import discord
import sonolink
from discord import app_commands
from discord.app_commands import Range
from discord.ext import commands
from sonolink import models as sl_models
from sonolink.models import AutoPlaySettings, HistorySettings

from app.constants import (
    API_RADIOGARDEN_LISTEN,
    API_RADIOGARDEN_PAGE,
    API_RADIOGARDEN_PLACES,
    API_RADIOGARDEN_SEARCH,
    ICON_YOUTUBE,
)
from app.decorators import is_joined, is_playing, is_queue_empty
from app.response_handler import defer_interaction, send_interaction, send_response
from app.utils import (
    QueuePaginator,
    find_track,
    fix_audio_title,
    get_guild_data,
    get_search_prefix,
    make_http_request,
    switch_node,
)


async def is_owner(interaction: discord.Interaction) -> bool:
    return await interaction.client.is_owner(interaction.user)


async def disconnect_after_timeout(player: sonolink.Player, timeout: float) -> None:
    """Disconnect the player after a timeout if no further activity.

    Parameters:
    -----------
    player: :class:`sonolink.Player`
        The player to disconnect.
    timeout: float
        The timeout in seconds.
    """
    try:
        await asyncio.sleep(timeout)
        if player and player.connected:
            player.cleanup()
            await player.disconnect()
    except asyncio.CancelledError:
        pass


def set_track_requester(
    track: sl_models.Playable,
    user: discord.abc.User,
    bot: commands.Bot | None = None,
) -> None:
    if track.data.user_data is None:
        track.data.user_data = {}

    track.data.user_data["requester_name"] = user.name
    avatar = getattr(getattr(user, "display_avatar", None), "url", None)
    if avatar:
        track.data.user_data["requester_avatar"] = avatar

    bot.track_requesters[track.encoded] = {
        "name": user.name,
        "avatar": avatar or "",
    }


def get_extra_value(track: sl_models.Playable, key: str) -> str | None:
    extras = getattr(track, "extras", None)
    if extras is None:
        return None

    getter = getattr(extras, "get", None)
    if callable(getter):
        return getter(key)

    return getattr(extras, key, None)


def get_track_requester_name(
    track: sl_models.Playable, bot: commands.Bot | None = None
) -> str:
    name = get_extra_value(track, "requester_name")
    if name:
        return name

    cached = bot.track_requesters.get(track.encoded)
    if cached and cached.get("name"):
        return cached["name"]

    return "Unknown"


def get_track_requester_avatar(
    track: sl_models.Playable, bot: commands.Bot | None = None
) -> str | None:
    avatar = get_extra_value(track, "requester_avatar")
    if avatar:
        return avatar

    cached = bot.track_requesters.get(track.encoded)
    if cached:
        return cached.get("avatar") or None

    return None


async def fetch_first_track(
    ctx: discord.Interaction,
    tracks: Union[
        sl_models.SearchResult,
        sl_models.Playlist,
        sl_models.Playable,
        list[sl_models.Playable],
    ],
) -> sl_models.Playable:
    player: sonolink.Player = ctx.guild.voice_client

    if isinstance(tracks, sl_models.SearchResult):
        if tracks.is_error() or tracks.is_empty():
            raise ValueError("Search returned no playable tracks")
        tracks = tracks.result

    # If it's a playlist
    if isinstance(tracks, sl_models.Playlist):
        if player.should_respond:
            await defer_interaction(ctx)

        for track in tracks:
            set_track_requester(track, ctx.user, ctx.client)

        track = tracks.pop(0)
        song_count: int = player.queue.put(tracks)

        embed = discord.Embed(
            title="",
            description=f"Added the playlist **`{tracks.name}`**"
            f" ({song_count} songs) to the queue.",
            color=discord.Color.blue(),
        )
        await send_interaction(ctx, embed=embed)

        player.should_respond = False
        return track

    if isinstance(tracks, sl_models.Playable):
        set_track_requester(tracks, ctx.user, ctx.client)
        return tracks

    track = tracks[0]
    set_track_requester(track, ctx.user, ctx.client)
    return track


async def should_move_to_channel(ctx: discord.Interaction) -> bool:
    player: sonolink.Player = ctx.guild.voice_client
    if player and player.channel.id == ctx.user.voice.channel.id:
        return True

    if player.current:
        await send_response(ctx, "NOT_IN_SAME_VOICE_CHANNEL_PLAYING")
        return False

    await player.move_to(ctx.user.voice.channel)
    await send_response(
        ctx,
        "MOVED",
        ephemeral=False,
        channel_id=ctx.user.voice.channel.id,
    )
    player.should_respond = False
    return True


def queue_embed(track: sl_models.Playable) -> discord.Embed:
    return discord.Embed(
        title="",
        description=f"**Added to queue:\n [{fix_audio_title(track)}]({track.uri})**",
        color=discord.Color.blue(),
    )


def playing_embed(track: sl_models.Playable) -> discord.Embed:
    author_pfp = get_track_requester_avatar(track)

    embed = discord.Embed(
        title="Now playing",
        description=f"[**{fix_audio_title(track)}**]({track.uri})",
        color=discord.Colour.green(),
    )
    embed.set_footer(
        text=f"Requested by {get_track_requester_name(track)}", icon_url=author_pfp
    )
    embed.set_thumbnail(url=track.artwork)
    return embed


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
    bot: :class:`commands.Bot`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: commands.Bot):
        self._bot = bot
        self._session = self._bot.session
        # self._node_is_switching: dict[int, bool] = {}
        self._radiomap_cache: list[str] = []

    music = app_commands.Group(name="music", description="All music commands")
    radio = app_commands.Group(name="radio", description="All radio commands")

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

        # Check if response was already sent, for radio command
        if not ctx.response.is_done():
            await defer_interaction(ctx)

        if not ctx.guild.voice_client:
            joined: bool = await self._join_channel(ctx)
            if not joined:
                node = self._bot.cached_lavalink_servers.get(self._bot.node.uri)
                if node:
                    node["score"] -= 1
                return
            await self._prepare_sonolink(ctx)

        is_moved: bool = await should_move_to_channel(ctx)
        if not is_moved:
            return

        tracks = await self._search_tracks(ctx, search)
        if not tracks:
            return

        track = await fetch_first_track(ctx, tracks)
        if not track:
            return

        player: sonolink.Player = ctx.guild.voice_client

        # if getattr(player, "node_is_switching", False) or self._node_is_switching.get(ctx.guild.id, False):
        #     await send_response(ctx, "WAIT_UNTIL_NODE_SWITCHES")
        #     return

        player.temp_current = track  # To be used in case of switching nodes

        if player.current:
            if play_next:
                self._queue_insert_front(player, track)
            else:
                player.queue.put(track)
            await send_interaction(ctx, embed=queue_embed(track))
            return

        if len(player.queue) == 0:
            player.should_respond = True

        if player.just_joined:
            player.should_respond = False
            player.just_joined = False

        playing: bool = await self._play_track(ctx, track)
        if not playing:
            return

        if player.should_respond:
            await send_interaction(ctx, embed=playing_embed(track))
            player.should_respond = False

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
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        place_id = random.choice(place_ids)

        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_PAGE}{place_id}/channels",
            headers={"accept": "application/json"},
        )
        if not response:
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            station_id = data["data"]["content"][0]["items"][0]["page"]["url"].split(
                "/"
            )[-1]
        except (KeyError, IndexError, ValueError):
            await send_response(ctx, "RADIOMAP_ERROR")
            return
        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_LISTEN}{station_id}/channel.mp3",
            headers={"accept": "application/json"},
        )
        if not response:
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        response_text = response.text
        url_match = re.search(
            r'(?:href="|Redirecting to )(https?://[^"\s]+)', response_text
        )
        if not url_match:
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        station = url_match.group(1)
        if station.endswith("."):
            station = station[:-1]

        await self.play(ctx, station, play_next)

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
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            if not data["hits"]["hits"]:
                await send_response(ctx, "RADIOMAP_NO_STATION_FOUND", search=station)
                return

            for station_data in data["hits"]["hits"]:
                station_source = station_data["_source"]["page"]
                if country and station_source["country"]["title"] != country:
                    continue

                await self.play(ctx, station_source["stream"], play_next)
                return

            await send_response(ctx, "RADIOMAP_NO_STATION_FOUND", search=station)
        except (KeyError, ValueError):
            await send_response(ctx, "RADIOMAP_ERROR")

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
        await player.skip()
        player.should_respond = False
        await send_response(ctx, "TRACK_SKIPPED", ephemeral=False)

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
            await send_response(ctx, "NO_TRACK_FOUND_IN_QUEUE", search=to_find)
            return

        track = player.queue[track_pos - 1]
        if track_pos > 1:
            self._queue_remove_at(player, track_pos - 1)
            self._queue_insert_front(player, track)

        await player.skip()
        player.should_respond = False

        await send_response(
            ctx,
            "TRACK_SKIPPED_TO",
            ephemeral=False,
            title=track.title,
            uri=track.uri,
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
            await send_response(ctx, "NO_TRACK_FOUND_IN_QUEUE", to_find=to_find)
            return

        track = player.queue[track_pos - 1]
        self._queue_remove_at(player, track_pos - 1)
        await send_response(
            ctx,
            "QUEUE_TRACK_REMOVED",
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
        if len(player.queue) < 2:
            await send_response(ctx, "CANT_SHUFFLE")
            return

        player.queue.shuffle()
        await send_response(ctx, "QUEUE_SHUFFLED", ephemeral=False)

    @music.command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @app_commands.guild_only()
    @is_joined()
    async def loop_queue(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client

        if len(player.queue) == 0 and player.queue.mode != sonolink.QueueMode.LOOP_ALL:
            await send_response(ctx, "NO_TRACKS_IN_QUEUE")
            return

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
            await send_response(ctx, "ALREADY_PAUSED")
            return

        await player.pause(True)
        await send_response(ctx, "TRACK_PAUSED", ephemeral=False, delete_after=10)

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
        await player.pause(False)
        await send_response(ctx, "TRACK_RESUMED", ephemeral=False, delete_after=10)

    @music.command(
        name="loop",
        description="Loops currently playing song, run command again to disable loop.",
    )
    @app_commands.guild_only()
    @is_playing()
    async def loop(self, ctx: discord.Interaction) -> None:
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

    @music.command(name="clear", description="Clears queue")
    @app_commands.guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
        player.queue.clear()
        await send_response(ctx, "QUEUE_CLEARED", ephemeral=False)

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
            await send_response(ctx, "CURRENT_VOLUME", volume=player.volume)
            return

        guild_data, _ = await get_guild_data(self._bot, ctx.guild.id)
        guild_data["music"]["volume"] = volume
        await self._bot.guild_data_db.update_one(
            {"_id": ctx.guild.id}, {"$set": guild_data}
        )
        self._bot.guild_data[ctx.guild.id] = guild_data
        await player.set_volume(volume)
        await send_response(ctx, "VOLUME_CHANGED", ephemeral=False, volume=volume)

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
        await send_response(
            ctx, "SPEED_CHANGED", ephemeral=False, multiplier=multiplier
        )

    @music.command(name="clear-effects", description="Clears all effects on player.")
    @app_commands.guild_only()
    @is_joined()
    async def clear_effects(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
        filters = sl_models.Filters()
        await player.set_filters(filters)
        await send_response(ctx, "EFFECTS_CLEARED", ephemeral=False)

    @music.command(name="queue", description="Shows the current queue")
    @app_commands.guild_only()
    @is_joined()
    @is_queue_empty()
    async def queue(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
        pages = self._build_queue_embeds(ctx, player)

        if len(pages) == 1:
            await send_interaction(ctx, embed=pages[0])
        else:
            view = QueuePaginator(pages)
            await send_interaction(ctx, embed=pages[0], view=view)

    @music.command(name="playing", description="What track is currently playing")
    @app_commands.guild_only()
    @is_playing()
    async def playing_command(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client
        await send_interaction(ctx, embed=self._build_playing_embed(player))

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
            await send_response(ctx, "NOT_IN_SAME_VOICE_CHANNEL")
            return

        await send_response(
            ctx, "DISCONNECTED", ephemeral=False, channel_id=player.channel.id
        )
        player.cleanup()
        await player.disconnect()

    @music.command(
        name="autoplay_mode",
        description="Change autoplay mode when playing music.",
    )
    @app_commands.describe(mode="Autoplay mode to use.")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="normal", value="normal"),
            app_commands.Choice(name="populated", value="populated"),
        ]
    )
    @app_commands.guild_only()
    @is_joined()
    async def autoplay_mode(
        self, ctx: discord.Interaction, mode: str = "normal"
    ) -> None:
        """Change the autoplay mode for the bot.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        mode: str
            The autoplay mode to set. Can be either "normal" or "populated".
        """
        player: sonolink.Player = ctx.guild.voice_client
        player.autoplay = (
            sonolink.AutoPlayMode.PARTIAL
            if mode == "normal"
            else sonolink.AutoPlayMode.ENABLED
        )

        guild_data, _ = await get_guild_data(self._bot, ctx.guild.id)
        guild_data["music"]["autoplay_mode"] = 1 if mode == "normal" else 2
        await self._bot.guild_data_db.update_one(
            {"_id": ctx.guild.id}, {"$set": guild_data}
        )
        self._bot.guild_data[ctx.guild.id] = guild_data
        await send_response(
            ctx, "AUTOPLAY_MODE_CHANGED", ephemeral=False, autoplay_mode=mode
        )

    @music.command(
        name="play_troll",
        description="Play music bot into typed channel.",
    )
    @app_commands.describe(
        channel_id="Voice channel ID where troll playback should start.",
        search="Song query or URL to play in that channel.",
    )
    @app_commands.checks.check(is_owner)
    async def play_troll(
        self,
        ctx: discord.Interaction,
        channel_id: Range[int, 1],
        search: str,
    ) -> None:
        """Play a troll music bot into the specified channel.

        Parameters:
        -----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        channel_id: int
            The ID of the channel to play music in.
        """

        channel = self._bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            embed = discord.Embed(
                title="",
                description="Invalid channel ID or the channel is not a voice channel.",
                color=discord.Color.red(),
            )
            await send_interaction(ctx, embed=embed, ephemeral=True)
            return

        if not channel.guild.voice_client:
            try:
                await self._connect_voice_channel(channel)
            except (discord.Forbidden, discord.ClientException):
                await send_response(ctx, "NO_PERMISSIONS")
                return
            except Exception:
                await send_response(ctx, "NODE_UNRESPONSIVE", ephemeral=False)
                return

        player: sonolink.Player = channel.guild.voice_client
        player.just_joined = False
        player.text_channel = ctx.channel
        player.should_respond = True
        player.is_troll = True

        search_result = await self._bot.sonolink_client.search_track(search)
        if (
            search_result.is_error()
            or search_result.is_empty()
            or not search_result.result
        ):
            await send_response(ctx, "NO_TRACKS_FOUND")
            return

        result = search_result.result
        if isinstance(result, sl_models.Playlist):
            if len(result) == 0:
                await send_response(ctx, "NO_TRACKS_FOUND")
                return
            track = result[0]
        elif isinstance(result, list):
            track = result[0]
        else:
            track = result

        embed = discord.Embed(
            title="",
            description=f"Joined the channel `{channel.name}`"
            f" and started playing `{track.title}`",
            color=discord.Color.blue(),
        )
        await send_interaction(ctx, embed=embed, ephemeral=True)

        if player.current:
            self._queue_insert_front(player, track)
        else:
            playing_track = await player.play(track)
            set_track_requester(playing_track, ctx.user, self._bot)

        disconnect_task = asyncio.create_task(
            disconnect_after_timeout(player, track.length / 1000 + 2)
        )
        player.disconnect_task = disconnect_task

    # ----------------------- Helper functions ------------------------ #
    def _queue_insert_front(
        self, player: sonolink.Player, track: sl_models.Playable
    ) -> None:
        queue_items = list(player.queue)
        player.queue.clear()
        player.queue.put([track, *queue_items])

    def _queue_remove_at(
        self, player: sonolink.Player, index: int
    ) -> sl_models.Playable:
        queue_items = list(player.queue)
        removed = queue_items.pop(index)
        player.queue.clear()
        if queue_items:
            player.queue.put(queue_items)
        return removed

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
        is_spotify = False
        source = get_search_prefix(search)
        if source is None:
            source = "ytsearch"

        # Prefer youtube over spotify, but if youtube fails, try spotify
        if source == "spsearch":
            is_spotify = True
            source = "ytsearch"

        player: sonolink.Player = ctx.guild.voice_client
        try:
            tracks = await asyncio.wait_for(
                self._bot.sonolink_client.search_track(search, source=source), timeout=3
            )
            if not tracks.is_error() and not tracks.is_empty() and tracks.result:
                return tracks

            if is_spotify:
                # Keep one lightweight fallback without switching nodes.
                tracks = await asyncio.wait_for(
                    self._bot.sonolink_client.search_track(search, source="spsearch"),
                    timeout=3,
                )
                if not tracks.is_error() and not tracks.is_empty() and tracks.result:
                    return tracks

        except (asyncio.TimeoutError, AttributeError):
            await send_response(
                ctx,
                "NODE_NOT_FOUND",
                ephemeral=False,
                respond=not player.just_joined,
            )
            player.just_joined = False
            return None

        except Exception as e:
            await send_response(
                ctx,
                "LAVALINK_ERROR",
                ephemeral=False,
                respond=not player.just_joined,
            )
            player.just_joined = False
            logging.error("[sonolink] Error searching for tracks: %s", e)
            return None

        await send_response(
            ctx,
            "NO_TRACKS_FOUND",
            ephemeral=False,
            respond=not player.just_joined,
            search=search,
        )
        player.just_joined = False
        return None

    async def _join_channel(self, ctx: discord.Interaction) -> bool:
        if not ctx.user.voice or not ctx.user.voice.channel:
            await send_response(ctx, "NO_VOICE_CHANNEL")
            return False

        try:
            await self._connect_voice_channel(ctx.user.voice.channel)
        except (discord.Forbidden, discord.ClientException):
            await send_response(ctx, "NO_PERMISSIONS")
            return False
        except Exception:
            await send_response(ctx, "NO_NODES", ephemeral=False)
            return False

        return True

    def _build_player_class(self, node: sonolink.Node):
        return node.create_player(
            autoplay_settings=AutoPlaySettings(
                mode=sonolink.AutoPlayMode.ENABLED,
                discovery_count=10,
            ),
            history_settings=HistorySettings(
                enabled=True,
                max_items=100,
            ),
        )

    async def _connect_voice_channel(
        self,
        channel: discord.VoiceChannel,
    ) -> None:
        node = self._bot.node
        if not node:
            raise RuntimeError("No connected node available")

        wait_session = getattr(node, "_wait_session", None)
        if callable(wait_session):
            await wait_session()

        player_cls = self._build_player_class(node)
        await channel.connect(cls=player_cls, timeout=5)

    async def _play_track(
        self, ctx: discord.Interaction, track: sl_models.Playable
    ) -> bool:
        player: sonolink.Player = ctx.guild.voice_client
        playing_track = await player.play(track)
        set_track_requester(playing_track, ctx.user, self._bot)

        node = self._bot.cached_lavalink_servers.get(self._bot.node.uri)
        if node:
            node["score"] += 1
        return True

    async def _prepare_sonolink(self, ctx: discord.Interaction) -> None:
        player: sonolink.Player = ctx.guild.voice_client

        if hasattr(player, "disconnect_task") and player.disconnect_task:
            player.disconnect_task.cancel()
            player.disconnect_task = None

        player.text_channel = ctx.channel
        player.should_respond = False
        player.just_joined = True
        player.is_troll = False

        guild_data, _ = await get_guild_data(self._bot, ctx.guild.id)
        volume = guild_data["music"]["volume"]
        try:
            await player.set_volume(volume)
        except Exception as e:
            if "Session not found" not in str(e):
                raise

            await switch_node(
                bot=self._bot,
                player=player,
                play_after=False,
                send_success_message=False,
                send_failure_message=False,
            )

            try:
                await player.set_volume(volume)
            except Exception as retry_error:
                logging.warning(
                    "[Lavalink] Volume sync skipped after retry failure: %s",
                    retry_error,
                )
                await send_response(
                    ctx,
                    "NODE_UNRESPONSIVE",
                    ephemeral=False,
                )
                return

        if guild_data["music"]["autoplay_mode"] == 1:
            player.autoplay = sonolink.AutoPlayMode.PARTIAL
        else:
            player.autoplay = sonolink.AutoPlayMode.ENABLED

        await send_response(
            ctx,
            "JOINED",
            ephemeral=False,
            channel_id=player.channel.id,
            text_channel_id=player.text_channel.id,
        )

    def _build_queue_embeds(
        self, ctx: discord.Interaction, player: sonolink.Player
    ) -> list[discord.Embed]:
        if not player.current:
            embed = discord.Embed(
                title="",
                description="Queue is currently empty.",
                color=discord.Color.blue(),
            )
            return [embed]

        queue_status = "Now Playing"
        if player.queue.mode == sonolink.QueueMode.LOOP_ALL:
            queue_status = "Looping queue"
        elif player.queue.mode == sonolink.QueueMode.LOOP:
            queue_status = "Looping currently playing song"

        current = player.current
        requester = get_track_requester_name(current, self._bot)
        header = (
            f"\n***__{queue_status}:__***\n "
            f"**[{fix_audio_title(current)}]({current.uri})**\n"
            f" `{int(divmod(current.length, 60000)[0])}:"
            f"{round(divmod(current.length, 60000)[1] / 1000):02} | "
            f"Requested by: {requester}`\n\n ***__Next:__***\n"
        )

        pages: list[discord.Embed] = []
        current_description = header
        for pos, track in enumerate(player.queue):
            track_requester = get_track_requester_name(track, self._bot)
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
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"{len(player.queue)} songs in queue")
                pages.append(embed)
                current_description = header + song_line
            else:
                current_description += song_line

        embed = discord.Embed(
            title=f"Queue for {ctx.guild.name}",
            description=current_description,
            color=discord.Color.blue(),
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

        requester_name = get_track_requester_name(player.current, self._bot)
        requester_avatar = get_track_requester_avatar(player.current, self._bot)
        if requester_name != "Unknown":
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


async def setup(bot: commands.Bot) -> None:
    """Setup function for the MusicCommands cog."""
    cog = MusicCommands(bot)
    await bot.add_cog(cog)
    # Add command groups
    bot.tree.add_command(cog.music, override=True)
    bot.tree.add_command(cog.radio, override=True)
