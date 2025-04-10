from typing import Union, Optional

import discord
import wavelink

from discord import option
from discord.ext import commands
from discord.commands import slash_command
from wavelink.exceptions import LavalinkLoadException
from decorators import is_joined, is_playing


class Play(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name="play", description="Plays song.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option(
        "search",
        description="You can either put a url or a name of the song,"
        " both youtube and spotify are supported.",
    )
    async def play(self, ctx: discord.ApplicationContext, search: str) -> None:
        if not ctx.voice_client:
            is_joined: bool = await self._join_channel(ctx)
            if not is_joined:
                return
            await self._prepare_wavelink(ctx)

        is_moved: bool = await self._should_move_to_channel(ctx)
        if not is_moved:
            return

        vc: wavelink.Player = ctx.voice_client
        await ctx.trigger_typing()

        track = await self._fetch_track(ctx, search)
        if not track:
            return

        if vc.playing:
            vc.queue.put(track)
            await ctx.respond(embed=self._queue_embed(track))
            return

        if vc.queue.is_empty:
            vc.should_respond = True

        is_playing: bool = await self._play_track(ctx, track)
        if not is_playing:
            return

        if vc.should_respond:
            await ctx.respond(embed=self._playing_embed(track))

    @slash_command(
        name="play-next", description="Put this song next in queue, bypassing others."
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option(
        "search",
        description="Links and words for youtube are supported, playlists work too.",
    )
    @is_joined()
    async def play_next(self, ctx: discord.ApplicationContext, search: str) -> None:
        vc: wavelink.Player = ctx.voice_client
        did_move: bool = await self._should_move_to_channel(ctx)
        if not did_move:
            return

        await ctx.trigger_typing()

        track = await self._fetch_track(ctx, search)
        if not track:
            return

        if vc.playing:
            await ctx.respond(embed=self._queue_embed(track))
            vc.queue.put_at(0, track)
            return

        is_playing: bool = await self._play_track(ctx, track)
        if not is_playing:
            return

        await ctx.respond(embed=self._playing_embed(track))
        vc.queue.remove(
            track
        )  # Due to autoplay the first song does not remove itself after skipping

    @slash_command(name="skip", description="Skip playing song.")
    @is_playing()
    async def skip_command(self, ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client
        await vc.skip()

        vc.should_respond = False
        embed = discord.Embed(
            title="", description="**⏭️   Skipped**", color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

    @slash_command(name="skip-to", description="Skips to selected song in queue.")
    @option(
        "to_find",
        description="Both position in the queue and name of the song are accepted.",
    )
    @is_playing()
    async def skip_to_command(
        self, ctx: discord.ApplicationContext, to_find: str
    ) -> None:
        vc: wavelink.Player = ctx.voice_client

        if vc.queue.is_empty:
            embed = discord.Embed(
                title="", description="**Queue is empty**", color=discord.Color.blue()
            )
            await ctx.respond(embed=embed)
            return

        if not to_find.isdigit():
            for i, track in enumerate(vc.queue):
                if to_find.lower() in track.title.lower():
                    to_find = i + 1
                    break

                if i != len(vc.queue) - 1:
                    continue

                embed = discord.Embed(
                    title="",
                    description=f":x: Song `{to_find}` was not found in queue,"
                    f" to show what's in queue, type `/q`",
                    color=discord.Color.blue(),
                )
                await ctx.respond(embed=embed)
                return
        else:
            to_find = int(to_find)

        try:
            track = vc.queue[to_find - 1]
            vc.queue.put_at(0, track)
            del vc.queue[to_find]
            await vc.stop()

            embed = discord.Embed(
                title="",
                description=f"**Skipped to [{track.title}]({track.uri})**",
                color=discord.Color.blue(),
            )
        except IndexError:
            embed = discord.Embed(
                title="",
                description=f":x: Song was not found on position `{to_find}`,"
                " to show what's in queue, type `/q`",
                color=discord.Color.blue(),
            )
        await ctx.respond(embed=embed)

    @slash_command(name="pause", description="Pauses song that is currently playing.")
    @is_playing()
    async def pause_command(self, ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client

        if vc.paused:
            embed = discord.Embed(
                title="",
                description=f"{ctx.user.mention}, song is already paused, use `/resume`",
                color=discord.Color.blue(),
            )
            await ctx.response.send_message(embed=embed)
            return

        await vc.pause(True)

        embed = discord.Embed(
            title="", description="**⏸️   Paused**", color=discord.Color.blue()
        )

        embed.set_footer(text="Deleting in 10s.")
        await ctx.respond(embed=embed, delete_after=10)

    @slash_command(name="resume", description="Resumes paused song.")
    @is_playing()
    async def resume_command(self, ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client
        await vc.pause(False)

        embed = discord.Embed(
            title="",
            description="**:arrow_forward: Resumed**",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Deleting in 10s.")
        await ctx.respond(embed=embed, delete_after=10)

    @slash_command(name="leave", description="Leaves voice channel.")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @is_joined()
    async def disconnect_command(self, ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client

        if vc.channel.id != ctx.author.voice.channel.id:
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
            description=f"**✅ Left <#{vc.channel.id}>**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)
        vc.cleanup()
        await vc.disconnect()

    # ----------------------- Helper functions ------------------------ #
    async def _fetch_track(
        self, ctx: discord.ApplicationContext, search: str
    ) -> Optional[wavelink.Playable]:
        tracks = await self._search_tracks(ctx, search)
        if not tracks:
            return None
        return await self._fetch_first_track(ctx, tracks)

    @staticmethod
    async def _fetch_first_track(
        ctx: discord.ApplicationContext,
        tracks: Union[wavelink.Playlist, list[wavelink.Playable]],
    ) -> wavelink.Playable:
        vc: wavelink.Player = ctx.voice_client
        # If it's a playlist
        if isinstance(tracks, wavelink.Playlist):
            for track in tracks:
                track.requester = ctx.author

            track = tracks[0]
            tracks.pop(0)
            song_count: int = vc.queue.put(tracks)

            embed = discord.Embed(
                title="",
                description=f"Added the playlist **`{tracks.name}`**"
                f" ({song_count} songs) to the queue.",
                color=discord.Color.blue(),
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
    async def _search_tracks(
        ctx: discord.ApplicationContext, search: str
    ) -> Optional[wavelink.Search]:
        try:
            tracks: wavelink.Search = await wavelink.Playable.search(search)
        except LavalinkLoadException:
            embed = discord.Embed(
                title="",
                description=":x: Failed to load tracks, you probably inputted"
                " wrong link or this Lavalink server "
                "doesn't have necessary plugins."
                " To fix this, use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            vc: wavelink.Player = ctx.voice_client
            vc.should_respond = True
            await ctx.respond(embed=embed)
            return None

        return tracks

    @staticmethod
    async def _should_move_to_channel(ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client
        if vc and vc.channel.id == ctx.author.voice.channel.id:
            return True

        if vc.playing:
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention}, I'm playing in another channel, wait till song finishes.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            return False

        await vc.move_to(ctx.author.voice.channel)
        embed = discord.Embed(
            title="",
            description=f"**Moving to <#{ctx.author.voice.channel.id}>**.",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)
        vc.should_respond = False
        return True

    @staticmethod
    async def _join_channel(ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice or not ctx.author.voice.channel:
            embed = discord.Embed(
                title="",
                description=f"{ctx.author.mention},"
                f" you're not in a voice channel. Type `/p` from vc.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False

        try:
            await ctx.author.voice.channel.connect(cls=wavelink.Player)
        except wavelink.InvalidChannelStateException:
            embed = discord.Embed(
                title="",
                description=":x: I don't have permissions to join your channel.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(embed=embed)
            return False
        except wavelink.exceptions.InvalidNodeException:
            embed = discord.Embed(
                title="",
                description=":x: No nodes are currently assigned to the bot."
                "\nTo fix this, use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(embed=embed)
            return False
        except wavelink.exceptions.ChannelTimeoutException as e:
            print(f"Timeout exception: {e}")
        return True

    @staticmethod
    async def _play_track(
        ctx: discord.ApplicationContext, track: wavelink.Playable
    ) -> None:
        vc: wavelink.Player = ctx.voice_client

        try:
            await vc.play(track)
        except wavelink.exceptions.NodeException:
            embed = discord.Embed(
                title="",
                description=":x: Failed to connect to send request to the node."
                "\nError might be caused by Discord serers not responding,"
                "give it a minute or  use command `/reconnect_node`",
                color=discord.Color.from_rgb(r=220, g=0, b=0),
            )
            await ctx.respond(embed=embed)
            return False

        vc.temp_current = track  # To be used in case of switching nodes
        return True

    @staticmethod
    async def _prepare_wavelink(ctx: discord.ApplicationContext) -> None:
        vc: wavelink.Player = ctx.voice_client

        vc.autoplay = wavelink.AutoPlayMode.partial
        vc.text_channel = ctx.channel
        vc.should_respond = False

        embed = discord.Embed(
            title="",
            description=f"**✅ Joined to <#{vc.channel.id}>"
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
