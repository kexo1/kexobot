import discord
import wavelink

from typing import Union
from discord import option
from discord.ext import commands
from discord.commands import slash_command
from aiohttp.client_exceptions import ClientConnectorError
from wavelink import TrackStartEventPayload, Playable
from wavelink.exceptions import LavalinkLoadException
from decorators import is_joined, is_playing


class Play(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name="play", description="Plays song.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option("search", description="URLs and youtube video titles, playlists soundcloud urls,  work too are supported.")
    async def play(self, ctx: discord.ApplicationContext, search: str) -> None:
        if not ctx.voice_client:
            is_joined = await self._join_channel(ctx)
            if not is_joined:
                return
            await self._prepare_wavelink(ctx)

        vc: wavelink.Player = ctx.voice_client
        await ctx.trigger_typing()

        track = await self._fetch_track(ctx, search)
        if not track:
            return

        if vc.playing:
            vc.queue.put(track)
            return await ctx.respond(embed=self._queue_embed(track))

        if not vc.just_connected and vc.queue.is_empty:
            vc.should_respond = True

        await vc.play(track)
        if not vc.just_connected:
            if vc.should_respond:
                await ctx.respond(embed=self._playing_embed(track))
            return
        vc.just_connected = False

    @slash_command(name="play-next", description="Put this song next in queue, bypassing others.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option("search",
            description="Links and words for youtube are supported, playlists work too.")
    @is_joined()
    async def play_next(self, ctx: discord.ApplicationContext, search: str) -> None:
        vc = ctx.voice_client

        await ctx.trigger_typing()

        track = await self._fetch_track(ctx, search)
        if not track:
            return

        if vc.playing:
            await ctx.respond(embed=self._queue_embed(track))
            vc.queue.put_at(0, track)
        else:
            await vc.play(track)
            await ctx.respond(embed=self._playing_embed(track))
            vc.queue.remove(track)  # Due to autoplay the first song does not remove itself after skipping

    @slash_command(name="skip", description="Skip playing song.")
    @is_playing()
    async def skip_command(self, ctx: discord.ApplicationContext) -> None:
        vc = ctx.voice_client
        await vc.skip()

        vc.should_respond = False
        embed = discord.Embed(title="", description="**⏭️   Skipped**", color=discord.Color.blue())
        await ctx.respond(embed=embed)

    @slash_command(name="skip-to", description="Skips to selected song in queue.")
    @option("pos", description="Value 2 skips to second song in queue.", min_value=1, required=True)
    @is_playing()
    async def skip_to_command(self, ctx: discord.ApplicationContext, pos: int) -> None:
        vc = ctx.voice_client

        if vc.queue.is_empty:
            embed = discord.Embed(title="", description="**Queue is empty**", color=discord.Color.blue())
            return await ctx.respond(embed=embed)

        try:
            track = vc.queue[pos - 1]
            vc.queue.put_at(0, track)
            del vc.queue[pos - 1]
            await vc.stop()

            embed = discord.Embed(
                title="",
                description=f"**Skipped to [{track.title}]({track.uri})**",
                color=discord.Color.blue()
            )
        except IndexError:
            embed = discord.Embed(
                title="",
                description=f"**:x: Song was not found on position `{pos}`, to show what's in queue, type `/q`**",
                color=discord.Color.blue()
            )
        await ctx.respond(embed=embed)

    @slash_command(name="pause", description="Pauses song that is currently playing.")
    @is_playing()
    async def pause_command(self, ctx: discord.ApplicationContext) -> None:
        vc = ctx.voice_client

        if vc.paused:
            embed = discord.Embed(
                title="",
                description=f"{ctx.user.mention}, song is already paused, use `/resume`",
                color=discord.Color.blue()
            )
            return await ctx.response.send_message(embed=embed)

        await vc.pause(True)

        embed = discord.Embed(
            title="",
            description="**⏸️   Paused**",
            color=discord.Color.blue()
        )

        embed.set_footer(text=f"Deleting in 10s.")
        await ctx.respond(embed=embed, delete_after=10)

    @slash_command(name="resume", description="Resumes paused song.")
    @is_playing()
    async def resume_command(self, ctx: discord.ApplicationContext) -> None:
        vc = ctx.voice_client
        await vc.pause(False)

        embed = discord.Embed(
            title="",
            description="**:arrow_forward: Resumed**",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Deleting in 10s.")
        await ctx.respond(embed=embed, delete_after=10)

    async def _fetch_track(self, ctx: discord.ApplicationContext, search: str) -> wavelink.Playable:
        tracks = await self._search_tracks(ctx, search)
        if not tracks:
            return None
        return await self._fetch_first_track(ctx, tracks)

    @staticmethod
    async def _fetch_first_track(ctx: discord.ApplicationContext, tracks: Union[Playable, TrackStartEventPayload]) \
            -> wavelink.Playable:
        vc = ctx.voice_client
        # If it's a playlist
        if isinstance(tracks, wavelink.Playlist):
            for track in tracks:
                track.requester = ctx.author

            track = tracks[0]
            tracks.pop(0)
            song_count: int = vc.queue.put(tracks)

            embed = discord.Embed(
                title="",
                description=f"Added the playlist **`{tracks.name}`** ({song_count} songs) to the queue.",
                color=discord.Color.blue()
            )
            if vc.should_respond:
                await ctx.respond(embed=embed)
            else:
                await ctx.send(embed=embed)
            return track

        track = tracks[0]
        track.requester = ctx.author
        return track

    @staticmethod
    async def _search_tracks(ctx: discord.ApplicationContext, search: str) -> wavelink.Search:
        try:
            tracks: wavelink.Search = await wavelink.Playable.search(search)
        except (LavalinkLoadException, ClientConnectorError):
            embed = discord.Embed(
                title="",
                description=f":x: Failed to load tracks, you probably inputted wrong link or this Lavalink server "
                            f"doesn't have Youtube plugin. To fix this, use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=255, g=0, b=0)
            )
            await ctx.respond(embed=embed)
            return None

        return tracks

    @staticmethod
    async def _join_channel(ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice or not ctx.author.voice.channel:
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention}, you're not in a voice channel. Type `/p` from vc.",
                color=discord.Color.blue()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False

        try:
            await ctx.author.voice.channel.connect(cls=wavelink.Player)
        except wavelink.InvalidChannelStateException:
            embed = discord.Embed(
                title="",
                description=f":x: I don't have permissions to join your channel.",
                color=discord.Color.from_rgb(r=255, g=0, b=0)
            )
            await ctx.respond(embed=embed)
            return False
        except wavelink.exceptions.InvalidNodeException:
            embed = discord.Embed(
                title="",
                description=f":x: No nodes are currently assigned to the bot.\nTo fix this, use command "
                            f"`/reconnect_node`",
                color=discord.Color.from_rgb(r=255, g=0, b=0)
            )
            await ctx.respond(embed=embed)
            return False
        return True

    @staticmethod
    async def _prepare_wavelink(ctx: discord.ApplicationContext) -> None:
        vc = ctx.voice_client
        vc.autoplay = wavelink.AutoPlayMode.partial
        vc.text_channel = ctx.channel
        vc.should_respond = False
        vc.just_connected = True
        embed = discord.Embed(
            title="",
            description=f"**✅ Joined to <#{vc.channel.id}> and set text channel to <#{ctx.channel.id}>.**",
            color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

    @staticmethod
    def _queue_embed(track: wavelink.Playable) -> discord.Embed:
        return discord.Embed(
            title="",
            description=f"**Added to queue:\n [{track.title}]({track.uri})**",
            color=discord.Color.blue()
        )

    @staticmethod
    def _playing_embed(track) -> discord.Embed:
        author_pfp = None
        if hasattr(track.requester.avatar, "url"):
            author_pfp = track.requester.avatar.url

        embed = discord.Embed(
            title="Now playing",
            description="[**{}**]({})".format(track.title, track.uri),
            color=discord.Colour.green()
        )
        embed.set_footer(text=f"Requested by {track.requester.name}", icon_url=author_pfp)
        embed.set_thumbnail(url=track.artwork)
        return embed


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Play(bot))
