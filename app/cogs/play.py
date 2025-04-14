from typing import Union, Optional

import discord
import wavelink

from discord import option
from discord.ext import commands
from discord.commands import slash_command, guild_only
from wavelink.exceptions import LavalinkLoadException, NodeException

from app.decorators import is_joined, is_playing, is_song_in_queue, is_queue_empty
from app.utils import find_track


class Play(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    music = discord.SlashCommandGroup("music", "All music commands")

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
        required=False,
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

        await ctx.trigger_typing()

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

    @music.command(name="skip", description="Skip playing song.")
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
    @is_song_in_queue()
    async def skip_to_command(
        self, ctx: discord.ApplicationContext, to_find: str
    ) -> None:
        player: wavelink.Player = ctx.voice_client
        track_pos = find_track(player, to_find)

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
        player: wavelink.Player = ctx.voice_client
        player.should_respond = True
        try:
            tracks: wavelink.Search = await wavelink.Playable.search(search)
        except LavalinkLoadException:
            embed = discord.Embed(
                title="",
                description=":x: Failed to load tracks, you probably inputted"
                " wrong link or this Lavalink server "
                "doesn't have necessary plugins."
                " To fix this, use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=220, g=0, b=0),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return None
        except NodeException:
            embed = discord.Embed(
                title="",
                description=":x: Node is unresponsive, please use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=220, g=0, b=0),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return None

        if not tracks:
            embed = discord.Embed(
                title="",
                description=f":x: No tracks were found for `{search}`.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return None

        return tracks

    @staticmethod
    async def _should_move_to_channel(ctx: discord.ApplicationContext) -> None:
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
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention},"
                f" you're not in a voice channel. Type `/play` from vc.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False

        try:
            await ctx.author.voice.channel.connect(cls=wavelink.Player, timeout=3)
        except wavelink.InvalidChannelStateException:
            embed = discord.Embed(
                title="",
                description=":x: I don't have permissions to join your channel.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False

        except wavelink.exceptions.InvalidNodeException:
            embed = discord.Embed(
                title="",
                description=":x: No nodes are currently assigned to the bot."
                "\nTo fix this, use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False

        except wavelink.exceptions.ChannelTimeoutException:
            embed = discord.Embed(
                title="",
                description=":x: Failed to connect to the voice channel,"
                " was bot moved manually? If yes disconnect it and try again.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(embed=embed)
            return False
        return True

    @staticmethod
    async def _play_track(
        ctx: discord.ApplicationContext, track: wavelink.Playable
    ) -> None:
        player: wavelink.Player = ctx.voice_client

        try:
            await player.play(track)
        except wavelink.exceptions.NodeException:
            embed = discord.Embed(
                title="",
                description=":x: Failed to connect to send request to the node."
                "\nError might be caused by Discord serers not responding,"
                " give it a minute or use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=220, g=0, b=0),
            )
            await ctx.respond(embed=embed)
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
            description=f"**Added to queue:\n [{track.title}]({track.uri})**",
            color=discord.Color.blue(),
        )

    @staticmethod
    def _playing_embed(track) -> discord.Embed:
        author_pfp = None
        if hasattr(track.requester.avatar, "url"):
            author_pfp = track.requester.avatar.url

        embed = discord.Embed(
            title="Now playing",
            description=f"[**{track.title}**]({track.uri})",
            color=discord.Colour.green(),
        )
        embed.set_footer(
            text=f"Requested by {track.requester.name}", icon_url=author_pfp
        )
        embed.set_thumbnail(url=track.artwork)
        return embed


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Play(bot))
