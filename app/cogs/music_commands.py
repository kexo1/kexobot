import asyncio
import random
import re
from typing import Union, Optional, List

import discord
import wavelink
import logging
from discord import option
from discord.commands import guild_only
from discord.ext import commands
from wavelink.exceptions import LavalinkLoadException

from app.constants import (
    COUNTRIES,
    RADIOGARDEN_PLACES_URL,
    RADIOGARDEN_PAGE_URL,
    RADIOGARDEN_SEARCH_URL,
    RADIOGARDEN_LISTEN_URL,
    KEXO_SERVER,
)
from app.decorators import is_joined, is_playing, is_queue_empty
from app.response_handler import send_response
from app.utils import (
    find_track,
    fix_audio_title,
    make_http_request,
    switch_node,
    get_search_prefix,
    get_guild_data,
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
    bot: :class:`commands.Bot`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: commands.Bot):
        self._bot = bot
        self._session = self._bot.session
        self._node_is_switching: dict[int, bool] = {}
        self._radiomap_cache: List[str] = []

    music = discord.SlashCommandGroup("music", "All music commands")
    radio = discord.SlashCommandGroup("radio", "All radio commands")

    @music.command(name="play", description="Plays song.")
    @guild_only()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option(
        "search",
        description="You can either put a url or a name of the song,"
        " both youtube and spotify are supported.",
    )
    @option(
        "play_next",
        description="If you want to play this song next in queue, set this to true.",
        type=bool,
    )
    async def play(
        self,
        ctx: discord.ApplicationContext,
        search: str,
        play_next: bool = False,
    ) -> None:
        """Plays a song from a given URL or name.

        This command will search for the song using the provided search query.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        search: :class:`str`
            The search query for the song.
        play_next: :class:`bool`
            If True, the song will be played next in the queue.
        """

        # Check if response was already sent, for radio command
        if not ctx.interaction.response.is_done():
            await ctx.defer()

        if not ctx.voice_client:
            joined: bool = await self._join_channel(ctx)
            if not joined:
                self._bot.cached_lavalink_servers[self._bot.node.uri]["score"] -= 1
                return
            await self._prepare_wavelink(ctx)

        is_moved: bool = await self._should_move_to_channel(ctx)
        if not is_moved:
            return

        track = await self._fetch_tracks(ctx, search)
        if not track:
            return

        player: wavelink.Player = ctx.voice_client

        # Check if node is switching during play command and joining
        if player.node_is_switching or self._node_is_switching.get(ctx.guild_id, False):
            await send_response(ctx, "WAIT_UNTIL_NODE_SWITCHES")
            return

        player.temp_current = track  # To be used in case of switching nodes

        if player.playing:
            if play_next:
                player.queue.put_at(0, track)
            else:
                player.queue.put(track)
            await ctx.respond(embed=self._queue_embed(track))
            return

        if player.queue.is_empty:
            player.should_respond = True

        if player.just_joined:
            player.should_respond = False
            player.just_joined = False

        playing: bool = await self._play_track(ctx, track)
        if not playing:
            return

        if player.should_respond:
            await ctx.respond(embed=self._playing_embed(track))
            player.should_respond = False

    @radio.command(name="random", description="Gets random radio from RadioMap.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @guild_only()
    @option(
        "play_next",
        description="If you want to play this song next in queue, set this to true.",
    )
    async def radio_random(
        self, ctx: discord.ApplicationContext, play_next: bool = False
    ) -> None:
        """Gets a random radio station from RadioMap and plays it.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        play_next: bool
            If True, the radio station will be played next in the queue.
        """
        await ctx.defer()

        place_ids = await self._get_radiomap_data()
        if not place_ids:
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        place_id = random.choice(place_ids)

        response = await make_http_request(
            self._session,
            f"{RADIOGARDEN_PAGE_URL}{place_id}/channels",
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
            f"{RADIOGARDEN_LISTEN_URL}{station_id}/channel.mp3",
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
    @commands.cooldown(1, 4, commands.BucketType.user)
    @guild_only()
    @option("station", description="Name of the radio station.")
    @option(
        "play_next",
        description="If you want to play this song next in queue, set this to true.",
        type=bool,
    )
    @option(
        "country",
        description="Select one of the countries to narrow down the search.",
        choices=COUNTRIES,
    )
    async def play_radio(
        self,
        ctx: discord.ApplicationContext,
        station: str,
        country: str = "",
        play_next: bool = False,
    ) -> None:
        """Search and play a radio station from RadioGarden.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
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
            f"{RADIOGARDEN_SEARCH_URL}{encoded_station}",
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
    @guild_only()
    @is_playing()
    async def skip_command(self, ctx: discord.ApplicationContext) -> None:
        """Skip the currently playing song.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        player: wavelink.Player = ctx.voice_client
        await player.skip()
        player.should_respond = False
        await send_response(ctx, "TRACK_SKIPPED", ephemeral=False)

    @music.command(name="skip-to", description="Skips to selected song in queue.")
    @guild_only()
    @option(
        "to_find",
        description="Both position in the queue and name of the song are accepted.",
    )
    @is_playing()
    @is_queue_empty()
    async def skip_to_command(
        self, ctx: discord.ApplicationContext, to_find: str
    ) -> None:
        """Skip to a specific song in the queue.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        to_find: str
            The name of the song or its position in the queue.
        """
        player: wavelink.Player = ctx.voice_client

        track_pos = find_track(player, to_find)
        if not track_pos:
            await send_response(ctx, "NO_TRACK_FOUND_IN_QUEUE", search=to_find)
            return

        track = player.queue[track_pos - 1]
        player.queue.put_at(0, track)
        player.queue.pop(track_pos)
        await player.stop()

        await send_response(
            ctx,
            "TRACK_SKIPPED_TO",
            ephemeral=False,
            title=track.title,
            uri=track.uri,
        )

    @music.command(name="pause", description="Pauses song that is currently playing.")
    @guild_only()
    @is_playing()
    async def pause(self, ctx: discord.ApplicationContext) -> None:
        """Pause the currently playing song.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        player: wavelink.Player = ctx.voice_client

        if player.paused:
            await send_response(ctx, "ALREADY_PAUSED")
            return

        await player.pause(True)
        await send_response(ctx, "TRACK_PAUSED", ephemeral=False, delete_after=10)

    @music.command(name="resume", description="Resumes paused song.")
    @guild_only()
    @is_playing()
    async def resume(self, ctx: discord.ApplicationContext) -> None:
        """Resume the currently paused song.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        player: wavelink.Player = ctx.voice_client
        await player.pause(False)
        await send_response(ctx, "TRACK_RESUMED", ephemeral=False, delete_after=10)

    @music.command(name="leave", description="Leaves voice channel.")
    @guild_only()
    @is_joined()
    async def disconnect(self, ctx: discord.ApplicationContext) -> None:
        """Disconnect the bot from the voice channel.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        player: wavelink.Player = ctx.voice_client

        if player.channel.id != ctx.author.voice.channel.id:
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
    @option(
        "mode",
        description="Normal: Plays next track; Populated: For YouTube links,"
        " queues similar songs when the queue is empty",
        choices=["normal", "populated"],
    )
    @guild_only()
    @is_joined()
    async def autoplay_mode(
        self, ctx: discord.ApplicationContext, mode: str = "normal"
    ) -> None:
        """Change the autoplay mode for the bot.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        mode: str
            The autoplay mode to set. Can be either "normal" or "populated".
        """
        player: wavelink.Player = ctx.voice_client
        player.autoplay = (
            wavelink.AutoPlayMode.partial
            if mode == "normal"
            else wavelink.AutoPlayMode.enabled
        )

        guild_data, _ = await get_guild_data(self._bot, ctx.guild_id)
        guild_data["music"]["autoplay_mode"] = 1 if mode == "normal" else 2
        await self._bot.guild_data_db.update_one(
            {"_id": ctx.guild_id}, {"$set": guild_data}
        )
        self._bot.guild_data[ctx.guild_id] = guild_data
        await send_response(
            ctx, "AUTOPLAY_MODE_CHANGED", ephemeral=False, autoplay_mode=mode
        )

    @music.command(
        name="play_troll",
        description="Play music bot into typed channel.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("channel_id", description="ID of the channel to play music in.")
    @option("search", description="Search query for the song.")
    async def play_troll(
        self, ctx: discord.ApplicationContext, channel_id: str, search: str
    ) -> None:
        """Play a troll music bot into the specified channel.

        Parameters:
        -----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        channel_id: int
            The ID of the channel to play music in.
        """
        channel = self._bot.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.VoiceChannel):
            embed = discord.Embed(
                title="",
                description="Invalid channel ID or the channel is not a voice channel.",
                color=discord.Color.red(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        if not channel.guild.voice_client:
            await channel.connect(cls=wavelink.Player, timeout=3)

        player: wavelink.Player = channel.guild.voice_client
        player.should_respond = True
        player.is_troll = True

        tracks = await wavelink.Playable.search(search)
        if not tracks:
            await send_response(ctx, "NO_TRACKS_FOUND")
            return

        track = tracks[0]
        embed = discord.Embed(
            title="",
            description=f"Joined the channel `{channel.name}`"
            f" and started playing `{track.title}`",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed, ephemeral=True)

        if player.playing:
            player.queue.put_at(0, track)
        else:
            await player.play(track)

        disconnect_task = asyncio.create_task(
            self._disconnect_after_timeout(player, track.length / 1000 + 2)
        )
        player.disconnect_task = disconnect_task

    @staticmethod
    async def _disconnect_after_timeout(
        player: wavelink.Player, timeout: float
    ) -> None:
        """Disconnect the player after a timeout if no further activity.

        Parameters:
        -----------
        player: :class:`wavelink.Player`
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

    # ----------------------- Helper functions ------------------------ #
    async def _fetch_tracks(
        self, ctx: discord.ApplicationContext, search: str
    ) -> Optional[wavelink.Playable]:
        tracks = await self._search_tracks(ctx, search)
        if tracks:
            return await self._fetch_first_track(ctx, tracks)
        return None

    @staticmethod
    async def _fetch_first_track(
        ctx: discord.ApplicationContext,
        tracks: Union[wavelink.Playlist, list[wavelink.Playable]],
    ) -> wavelink.Playable:
        player: wavelink.Player = ctx.voice_client
        # If it's a playlist
        if isinstance(tracks, wavelink.Playlist):
            if player.should_respond:
                await ctx.defer()

            for track in tracks:
                track.requester = ctx.author

            track = tracks.pop(0)
            song_count: int = player.queue.put(tracks)

            embed = discord.Embed(
                title="",
                description=f"Added the playlist **`{tracks.name}`**"
                f" ({song_count} songs) to the queue.",
                color=discord.Color.blue(),
            )
            if player.should_respond:
                await ctx.respond(embed=embed)
            else:
                await ctx.send(embed=embed)

            player.should_respond = False
            return track

        track = tracks[0]
        track.requester = ctx.author
        return track

    async def _search_tracks(
        self, ctx: discord.ApplicationContext, search: str
    ) -> Optional[wavelink.Search]:
        is_spotify = False
        source = get_search_prefix(search)
        if source is None:
            source = "ytsearch"

        # Prefer youtube over spotify, but if youtube fails, try spotify
        if source == "spsearch":
            is_spotify = True
            source = "ytsearch"

        player: wavelink.Player = ctx.voice_client
        last_error = None
        for _ in range(2):
            try:
                tracks: wavelink.Search = await asyncio.wait_for(
                    wavelink.Playable.search(search, source=source), timeout=3
                )
                if tracks:
                    return tracks
            except (TimeoutError, AttributeError):
                last_error = "NODE_UNRESPONSIVE"
            except LavalinkLoadException:
                last_error = "LAVALINK_ERROR"

            if last_error:
                await switch_node(bot=self._bot, player=player, play_after=False)

            # Fallback to default search
            source = "ytsearch"
            if is_spotify:
                source = "spsearch"

        if last_error:
            await send_response(
                ctx,
                last_error,
                ephemeral=False,
                respond=not player.just_joined,
            )
        else:
            await send_response(
                ctx,
                "NO_TRACKS_FOUND",
                ephemeral=False,
                respond=not player.just_joined,
                search=search,
            )
        player.just_joined = False
        return None

    @staticmethod
    async def _should_move_to_channel(ctx: discord.ApplicationContext) -> bool:
        player: wavelink.Player = ctx.voice_client
        if player and player.channel.id == ctx.author.voice.channel.id:
            return True

        if player.playing:
            await send_response(ctx, "NOT_IN_SAME_VOICE_CHANNEL_PLAYING")
            return False

        await player.move_to(ctx.author.voice.channel)
        await send_response(
            ctx,
            "MOVED",
            ephemeral=False,
            channel_id=ctx.author.voice.channel.id,
        )
        player.should_respond = False
        return True

    async def _join_channel(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await send_response(ctx, "NO_VOICE_CHANNEL")
            return False

        # For some reason there's like a tiny chance the fucking node suddenly stops
        # responding, even though it was working minutes before, seems like some nodes
        # actively disconnect players if they are not used for a while
        is_connected = await self._find_working_node(ctx)
        if not is_connected:
            return False
        return True

    async def _find_working_node(self, ctx: discord.ApplicationContext) -> bool:
        """Retry joining the voice channel if the initial attempt fails.
        This function will attempt to reconnect to the voice channel up to 10 times"""
        self._node_is_switching[ctx.guild_id] = False
        is_connected = False
        for i in range(10):
            try:
                await ctx.author.voice.channel.connect(cls=wavelink.Player, timeout=3)
                is_connected = True

            except wavelink.InvalidChannelStateException:
                await send_response(ctx, "NO_PERMISSIONS")
                is_connected = False

            except Exception:
                logging.warning(f"[Lavalink] Node join timeout. ({self._bot.node.uri})")
                self._node_is_switching[ctx.guild_id] = True
                self._bot.cached_lavalink_servers[self._bot.node.uri]["score"] -= 1
                if i == 0:
                    await send_response(
                        ctx,
                        "NODE_UNRESPONSIVE",
                        respond=False,
                        ephemeral=False,
                    )
                await self._bot.connect_node()
                is_connected = False
                continue

            break

        self._node_is_switching.pop(ctx.guild_id, None)
        if not is_connected:
            await send_response(ctx, "CONNECTION_TIMEOUT", ephemeral=False)
            return False
        return True

    async def _play_track(
        self, ctx: discord.ApplicationContext, track: wavelink.Playable
    ) -> bool:
        player: wavelink.Player = ctx.voice_client

        try:
            await player.play(track)
        except (wavelink.exceptions.LavalinkException,) as e:
            await send_response(
                ctx, "NODE_REQUEST_ERROR", ephemeral=False, error=e.error
            )
            await switch_node(bot=self._bot, player=player)
        except wavelink.exceptions.NodeException:
            await send_response(ctx, "NODE_UNRESPONSIVE", ephemeral=False)
            await switch_node(bot=self._bot, player=player)

        self._bot.cached_lavalink_servers[player.node.uri]["score"] += 1
        return True

    async def _prepare_wavelink(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if hasattr(player, "disconnect_task") and player.disconnect_task:
            player.disconnect_task.cancel()
            player.disconnect_task = None

        player.text_channel = ctx.channel
        player.should_respond = False
        player.just_joined = True
        player.is_troll = False
        player.node_is_switching = False

        guild_data, _ = await get_guild_data(self._bot, ctx.guild_id)
        await player.set_volume(guild_data["music"]["volume"])

        if guild_data["music"]["autoplay_mode"] == 1:
            player.autoplay = wavelink.AutoPlayMode.partial
        else:
            player.autoplay = wavelink.AutoPlayMode.enabled

        await send_response(
            ctx,
            "JOINED",
            ephemeral=False,
            channel_id=player.channel.id,
            text_channel_id=player.text_channel.id,
        )

    @staticmethod
    def _queue_embed(track: wavelink.Playable) -> discord.Embed:
        return discord.Embed(
            title="",
            description=f"**Added to queue:\n [{fix_audio_title(track)}]({track.uri})**",
            color=discord.Color.blue(),
        )

    @staticmethod
    def _playing_embed(track: wavelink.Playable) -> discord.Embed:
        author_pfp = None
        if hasattr(track.requester.avatar, "url"):
            author_pfp = track.requester.avatar.url

        embed = discord.Embed(
            title="Now playing",
            description=f"[**{fix_audio_title(track)}**]({track.uri})",
            color=discord.Colour.green(),
        )
        embed.set_footer(
            text=f"Requested by {track.requester.name}", icon_url=author_pfp
        )
        embed.set_thumbnail(url=track.artwork)
        return embed

    async def _get_radiomap_data(self) -> List[str]:
        """Get radio map data with caching."""
        if self._radiomap_cache:
            return self._radiomap_cache

        response = await make_http_request(
            self._session,
            RADIOGARDEN_PLACES_URL,
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


def setup(bot: commands.Bot) -> None:
    """Setup function for the MusicCommands cog."""
    bot.add_cog(MusicCommands(bot))
