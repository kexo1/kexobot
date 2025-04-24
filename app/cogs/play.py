from typing import Union, Optional, List
import random
import re

import discord
import wavelink

from discord import option
from discord.ext import commands
from discord.commands import guild_only
from wavelink.exceptions import LavalinkLoadException, NodeException

from app.decorators import is_joined, is_playing, is_queue_empty
from app.constants import (
    COUNTRIES,
    RADIOGARDEN_PLACES_URL,
    RADIOGARDEN_PAGE_URL,
    RADIOGARDEN_SEARCH_URL,
    RADIOGARDEN_LISTEN_URL,
)
from app.utils import find_track, fix_audio_title, make_http_request
from app.errors import send_error


class Play(commands.Cog):
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
        if not ctx.voice_client:
            joined: bool = await self._join_channel(ctx)
            if not joined:
                return
            await self._prepare_wavelink(ctx)

        is_moved: bool = await self._should_move_to_channel(ctx)
        if not is_moved:
            return

        track = await self._fetch_track(ctx, search)
        if not track:
            return

        player: wavelink.Player = ctx.voice_client

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
            await send_error(ctx, "RADIOMAP_ERROR")
            return

        place_id = random.choice(place_ids)

        response = await make_http_request(
            self.session,
            f"{RADIOGARDEN_PAGE_URL}{place_id}/channels",
            headers={"accept": "application/json"},
        )
        if not response:
            await send_error(ctx, "RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            station_id = data["data"]["content"][0]["items"][0]["page"]["url"].split(
                "/"
            )[-1]
        except (KeyError, IndexError, ValueError):
            await send_error(ctx, "RADIOMAP_ERROR")
            return
        response = await make_http_request(
            self.session,
            f"{RADIOGARDEN_LISTEN_URL}{station_id}/channel.mp3",
            headers={"accept": "application/json"},
        )
        if not response:
            await send_error(ctx, "RADIOMAP_ERROR")
            return

        response_text = response.text
        url_match = re.search(
            r'(?:href="|Redirecting to )(https?://[^"\s]+)', response_text
        )
        if not url_match:
            await send_error(ctx, "RADIOMAP_ERROR")
            return

        station = url_match.group(1)
        if station.endswith("."):
            station = station[:-1]

        await self.play(ctx, station, play_next)

    @radio.command(name="play", description="Search and play radio from RadioGarden")
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
            await send_error(ctx, "RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            if not data["hits"]["hits"]:
                await send_error(ctx, "NO_TRACKS_FOUND", search=station)
                return

            for station_data in data["hits"]["hits"]:
                station_source = station_data["_source"]
                if country and station_source["page"]["country"]["title"] != country:
                    continue

                station_url = station_source["stream"].replace(";", "")
                await self.play(ctx, station_url, play_next)
                return

            await send_error(ctx, "NO_TRACKS", search=station)
        except (KeyError, ValueError):
            await send_error(ctx, "RADIOMAP_ERROR")

    @music.command(name="skip", description="Skip playing song.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @guild_only()
    @is_playing()
    async def skip_command(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client
        await player.skip()

        player.should_respond = False
        embed = discord.Embed(
            title="", description="**⏭️   Skipped**", color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

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
            await send_error(ctx, "NO_TRACK_FOUND_IN_QUEUE", search=to_find)
            return

        track = player.queue[track_pos - 1]
        player.queue.put_at(0, track)
        del player.queue[track_pos]
        await player.stop()

        embed = discord.Embed(
            title="",
            description=f"**Skipped to [{track.title}]({track.uri})**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @music.command(name="pause", description="Pauses song that is currently playing.")
    @guild_only()
    @is_playing()
    async def pause_command(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.paused:
            embed = discord.Embed(
                title="",
                description=f"{ctx.user.mention}, song is already paused, use `/resume`",
                color=discord.Color.blue(),
            )
            await ctx.response.send_message(embed=embed)
            return

        await player.pause(True)

        embed = discord.Embed(
            title="", description="**⏸️   Paused**", color=discord.Color.blue()
        )

        embed.set_footer(text="Deleting in 10s.")
        await ctx.respond(embed=embed, delete_after=10)

    @music.command(name="resume", description="Resumes paused song.")
    @guild_only()
    @is_playing()
    async def resume_command(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client
        await player.pause(False)

        embed = discord.Embed(
            title="",
            description="**:arrow_forward: Resumed**",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Deleting in 10s.")
        await ctx.respond(embed=embed, delete_after=10)

    @music.command(name="leave", description="Leaves voice channel.")
    @guild_only()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @is_joined()
    async def disconnect_command(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.channel.id != ctx.author.voice.channel.id:
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention},"
                f" join the voice channel the bot is playing in to disconnect it.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="",
            description=f"**✅ Left <#{player.channel.id}>**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)
        player.cleanup()
        await player.disconnect()

    # ----------------------- Helper functions ------------------------ #
    async def _fetch_track(
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

    @staticmethod
    async def _search_tracks(
        ctx: discord.ApplicationContext, search: str
    ) -> Optional[wavelink.Search]:
        sources = [
            "spsearch",
            "ytsearch",
            wavelink.TrackSource.SoundCloud
        ]

        found_tracks = None
        last_error = None
        for source in sources:
            try:
                tracks: wavelink.Search = await wavelink.Playable.search(search, source=source)
                if tracks:
                    found_tracks = tracks
                    break
            except LavalinkLoadException as e:
                print(e)
                if e.error == "Something went wrong while looking up the track.":
                    last_error = "YOUTUBE_ERROR"
                    continue
                last_error = "LAVALINK_ERROR"
                continue
            except NodeException as e:
                print(e)
                last_error = "NODE_UNRESPONSIVE"
                continue

        if found_tracks:
            return found_tracks

        if last_error:
            await send_error(ctx, last_error, search=search)
        else:
            await send_error(ctx, "NO_TRACKS_FOUND", search=search)
        return None

    @staticmethod
    async def _should_move_to_channel(ctx: discord.ApplicationContext) -> bool:
        player: wavelink.Player = ctx.voice_client
        if player and player.channel.id == ctx.author.voice.channel.id:
            return True

        if player.playing:
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention}, I'm playing in another channel,"
                f" wait till song finishes.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            return False

        await player.move_to(ctx.author.voice.channel)
        embed = discord.Embed(
            title="",
            description=f"**Moving to <#{ctx.author.voice.channel.id}>**.",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)
        player.should_respond = False
        return True

    @staticmethod
    async def _join_channel(ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await send_error(ctx, "NO_VOICE_CHANNEL")
            return False

        try:
            await ctx.author.voice.channel.connect(cls=wavelink.Player, timeout=3)
        except wavelink.InvalidChannelStateException:
            await send_error(ctx, "NO_PERMISSIONS")
            return False
        except wavelink.exceptions.InvalidNodeException:
            await send_error(ctx, "NO_NODES")
            return False
        except wavelink.exceptions.ChannelTimeoutException:
            await send_error(ctx, "CONNECTION_TIMEOUT")
            vc: wavelink.Player = ctx.guild.voice_client
            vc.cleanup()
            return False
        return True

    @staticmethod
    async def _play_track(
        ctx: discord.ApplicationContext, track: wavelink.Playable
    ) -> bool:
        player: wavelink.Player = ctx.voice_client

        try:
            await player.play(track)
        except wavelink.exceptions.NodeException:
            await send_error(ctx, "NODE_REQUEST_ERROR")
            return False

        player.temp_current = track  # To be used in case of switching nodes
        return True

    @staticmethod
    async def _prepare_wavelink(ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        player.autoplay = wavelink.AutoPlayMode.partial
        player.text_channel = ctx.channel
        player.should_respond = False
        player.just_joined = True

        embed = discord.Embed(
            title="",
            description=f"**✅ Joined to <#{player.channel.id}>"
            f" and set text channel to <#{ctx.channel.id}>.**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

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
    bot.add_cog(Play(bot))
