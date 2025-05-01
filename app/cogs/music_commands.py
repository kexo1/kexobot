import asyncio
import random
import re
from typing import Union, Optional, List

import discord
import wavelink
from discord import option
from discord.commands import guild_only
from discord.ext import commands
from wavelink.exceptions import LavalinkLoadException, NodeException

from app.constants import (
    COUNTRIES,
    RADIOGARDEN_PLACES_URL,
    RADIOGARDEN_PAGE_URL,
    RADIOGARDEN_SEARCH_URL,
    RADIOGARDEN_LISTEN_URL,
)
from app.decorators import is_joined, is_playing, is_queue_empty
from app.response_handler import send_response
from app.utils import (
    find_track,
    fix_audio_title,
    make_http_request,
    switch_node,
    get_search_prefix,
)


class MusicCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = self.bot.session
        self.radiomap_cache: List[str] = []

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
        self, ctx: discord.ApplicationContext, search: str, play_next: bool = False
    ) -> None:
        # Defer the response right away to avoid interaction timeout
        await ctx.defer(ephemeral=False)

        if not ctx.voice_client:
            joined: bool = await self._join_channel(ctx)
            if not joined:
                return
            await self._prepare_wavelink(ctx)

        is_moved: bool = await self._should_move_to_channel(ctx)
        if not is_moved:
            return

        track = await self._fetch_tracks(ctx, search)
        if not track:
            return

        player: wavelink.Player = ctx.voice_client
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
        await ctx.defer()

        place_ids = await self._get_radiomap_data()
        if not place_ids:
            await send_response(ctx, "RADIOMAP_ERROR")
            return

        place_id = random.choice(place_ids)

        response = await make_http_request(
            self.session,
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
            self.session,
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
        encoded_station = discord.utils.escape_markdown(station)
        response = await make_http_request(
            self.session,
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
                station_source = station_data["_source"]
                if country and station_source["page"]["country"]["title"] != country:
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
        player: wavelink.Player = ctx.voice_client

        track_pos = find_track(player, to_find)
        if not track_pos:
            await send_response(ctx, "NO_TRACK_FOUND_IN_QUEUE", search=to_find)
            return

        track = player.queue[track_pos - 1]
        player.queue.put_at(0, track)
        del player.queue[track_pos]
        await player.stop()

        await send_response(
            ctx, "TRACK_SKIPPED_TO", ephemeral=False, title=track.title, uri=track.uri
        )

    @music.command(name="pause", description="Pauses song that is currently playing.")
    @guild_only()
    @is_playing()
    async def pause(self, ctx: discord.ApplicationContext) -> None:
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
        player: wavelink.Player = ctx.voice_client
        await player.pause(False)
        await send_response(ctx, "TRACK_RESUMED", ephemeral=False, delete_after=10)

    @music.command(name="leave", description="Leaves voice channel.")
    @guild_only()
    @is_joined()
    async def disconnect(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.channel.id != ctx.author.voice.channel.id:
            await send_response(ctx, "NOT_IN_SAME_VOICE_CHANNEL")
            return

        await send_response(
            ctx, "DISCONNECTED", ephemeral=False, channel_id=player.channel.id
        )
        player.cleanup()
        await player.disconnect()

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
        source = get_search_prefix(search)
        if source is None:
            source = "ytsearch"

        player = ctx.voice_client
        last_error = None
        for i in range(2):
            try:
                tracks: wavelink.Search = await asyncio.wait_for(
                    wavelink.Playable.search(search, source=source), timeout=3
                )
                if tracks:
                    return tracks
            except TimeoutError:
                last_error = "NODE_UNRESPONSIVE"
                await switch_node(
                    self.bot.connect_node, player=player, play_after=False
                )
            except LavalinkLoadException as e:
                print("LavalinkLoadException: ", e)
                last_error = "LAVALINK_ERROR"
            except NodeException as e:
                print("NodeException: ", e)
                last_error = "NODE_UNRESPONSIVE"
                await switch_node(
                    self.bot.connect_node, player=player, play_after=False
                )
            except AttributeError:
                last_error = "NODE_UNRESPONSIVE"
                await switch_node(
                    self.bot.connect_node, player=player, play_after=False
                )
            # Fallback to default search
            source = "ytsearch"

        should_respond = False if player.just_joined else True
        if last_error:
            await send_response(
                ctx,
                last_error,
                ephemeral=False,
                respond=should_respond,
            )
        else:
            await send_response(
                ctx,
                "NO_TRACKS_FOUND",
                ephemeral=False,
                respond=should_respond,
                search=search,
            )
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
            ctx, "MOVED", ephemeral=False, channel_id=ctx.author.voice.channel.id
        )
        player.should_respond = False
        return True

    @staticmethod
    async def _join_channel(ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await send_response(ctx, "NO_VOICE_CHANNEL")
            return False

        if not ctx.response:
            await ctx.defer()

        try:
            await ctx.author.voice.channel.connect(cls=wavelink.Player, timeout=3)
        except wavelink.InvalidChannelStateException:
            await send_response(ctx, "NO_PERMISSIONS")
            return False
        except wavelink.exceptions.InvalidNodeException:
            await send_response(ctx, "NO_NODES")
            return False
        except wavelink.exceptions.ChannelTimeoutException:
            await send_response(ctx, "CONNECTION_TIMEOUT")
            vc: wavelink.Player = ctx.guild.voice_client
            print(vc.channel.name)
            vc.cleanup()
            return False
        return True

    async def _play_track(
        self, ctx: discord.ApplicationContext, track: wavelink.Playable
    ) -> bool:
        player: wavelink.Player = ctx.voice_client

        try:
            await player.play(track)
        except (
            wavelink.exceptions.NodeException,
            wavelink.exceptions.LavalinkException,
        ) as e:
            await send_response(
                ctx, "NODE_REQUEST_ERROR", ephemeral=False, error=e.error
            )
            await switch_node(self.bot.connect_node, player=player)

        return True

    @staticmethod
    async def _prepare_wavelink(ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        player.autoplay = wavelink.AutoPlayMode.partial
        player.text_channel = ctx.channel
        player.should_respond = False
        player.just_joined = True

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
        if self.radiomap_cache:
            return self.radiomap_cache

        response = await make_http_request(
            self.session, RADIOGARDEN_PLACES_URL, headers={"accept": "application/json"}
        )
        if not response:
            return self.radiomap_cache

        data = response.json()
        if "data" in data and "list" in data["data"]:
            place_ids = [
                item["url"].split("/")[-1]
                for item in data["data"]["list"]
                if "url" in item
            ]
            self.radiomap_cache = place_ids
            return place_ids
        return []


def setup(bot: commands.Bot) -> None:
    bot.add_cog(MusicCommands(bot))
