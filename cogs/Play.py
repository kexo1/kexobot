import discord
import wavelink

from typing import Union
from discord import option
from discord.ext import commands
from discord.commands import slash_command
from aiohttp.client_exceptions import ClientConnectorError
from wavelink import TrackStartEventPayload, Playable
from wavelink.exceptions import LavalinkLoadException, LavalinkException


class Play(commands.Cog):
    # noinspection RegExpRedundantEscape,RegExpSimplifiable
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lavalink_servers_site = "https://lavainfo.netlify.app/"

    @staticmethod
    def queue_embed(track: wavelink.Playable) -> discord.Embed:
        return discord.Embed(title="", description=f"**Added to queue:\n [{track.title}]({track.uri})**",
                             color=discord.Color.blue())

    @staticmethod
    def queue_embed_list(playlist: str, count: int) -> discord.Embed:
        return discord.Embed(title="", description=f"Added the playlist **`{playlist}`** ({count} songs) to the queue.",
                             color=discord.Color.blue())

    @staticmethod
    def _playing_embed(track) -> discord.Embed:
        author_pfp = None
        if hasattr(track.requester.avatar, "url"):
            author_pfp = track.requester.avatar.url

        embed = discord.Embed(color=discord.Colour.green(), title='Now playing',
                              description='[**{}**]({})'.format(track.title, track.uri))
        embed.set_footer(text=f'Requested by {track.requester.name}', icon_url=author_pfp)
        embed.set_thumbnail(url=track.artwork)
        return embed

    @slash_command(name='play', description='Plays song.')
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option('search', description='URLs and youtube video titles, playlists soundcloud urls,  work too are supported.')
    async def play(self, ctx: discord.ApplicationContext, search: str) -> None:

        if not await self.is_playable(ctx):
            return

        if not ctx.voice_client:
            try:
                try:
                    vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                except wavelink.exceptions.InvalidNodeException:
                    embed = discord.Embed(title="",
                                          description=f":x: No nodes are currently assigned to the bot."
                                                      f"\nTo fix this, use command `recconnect_node`",
                                          color=discord.Color.from_rgb(r=255, g=0, b=0))
                    return await ctx.respond(embed=embed)

                # await ctx.defer()
            except wavelink.InvalidChannelStateException:
                embed = discord.Embed(title="",
                                      description=f":x: I don't have permissions to join your channel.",
                                      color=discord.Color.from_rgb(r=255, g=0, b=0))
                return await ctx.respond(embed=embed)

            embed = discord.Embed(title="",
                                  description=f'**✅ Joined to <#{ctx.voice_client.channel.id}> and set text channel '
                                              f'to <#{ctx.channel.id}>.**',
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed)

            vc.autoplay = wavelink.AutoPlayMode.partial
            vc.text_channel = ctx.channel
        else:
            vc: wavelink.Player = ctx.voice_client

        await ctx.trigger_typing()

        try:
            tracks: wavelink.Search = await wavelink.Playable.search(search)
        except (LavalinkLoadException, ClientConnectorError):
            embed = discord.Embed(title="",
                                  description=f":x: Failed to load tracks, this Lavalink server doesn't have Youtube "
                                              f"plugin. To fix this, use command `recconnect_node`.",
                                  color=discord.Color.from_rgb(r=255, g=0, b=0))
            return await ctx.respond(embed=embed)

        track = await self.fetch_first_track(tracks, ctx)

        if vc.playing or vc.paused:
            vc.first = False  # Defines if it's first song, if True bot will use respond() instead of send
            await ctx.respond(embed=self.queue_embed(track))
            vc.queue.put(track)
            return

        vc.first = True
        await ctx.respond(embed=self._playing_embed(track))
        try:
            await vc.play(track)
        except LavalinkException:
            embed = discord.Embed(title="",
                                  description=f":x: Failed to play track, if error persists, use command "
                                              f"`recconnect_node`.",
                                  color=discord.Color.from_rgb(r=255, g=0, b=0))

    @slash_command(name='play-next', description='Put this song next in queue, bypassing others.')
    @commands.cooldown(1, 4, commands.BucketType.user)
    @option('search',
            description='Links and words for youtube are supported, playlists work too.')
    async def play_next(self, ctx: discord.ApplicationContext, search: str) -> None:

        if not await self.is_playable(ctx) is False:
            return

        if not ctx.voice_client:
            try:
                vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                # await ctx.defer()
            except wavelink.InvalidChannelStateException:
                embed = discord.Embed(title="",
                                      description=f":x: I don't have permissions to join your channel.",
                                      color=discord.Color.from_rgb(r=255, g=0, b=0))
                return await ctx.respond(embed=embed)

            embed = discord.Embed(title="",
                                  description=f'**✅ Joined to <#{ctx.voice_client.channel.id}> and set text channel '
                                              f'to <#{ctx.channel.id}>.**',
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed)

            vc.autoplay = wavelink.AutoPlayMode.partial
            # vc.auto_queue = True
            vc.text_channel = ctx.channel
        else:
            vc: wavelink.Player = ctx.voice_client

        await ctx.trigger_typing()

        tracks: wavelink.Search = await wavelink.Playable.search(search)
        track = await self.fetch_first_track(tracks, ctx)

        if vc.playing or vc.paused:
            vc.first = False
            await ctx.respond(embed=self.queue_embed(track))
            vc.queue.put_at(0, track)
        else:
            vc.first = True
            await vc.play(track)
            await ctx.respond(embed=self._playing_embed(track))
            vc.queue.remove(track)  # Due to autoplay the first song does not remove itself after skipping

    @slash_command(name='skip', description='Skip playing song.')
    async def skip_command(self, ctx: discord.ApplicationContext) -> None:

        try:
            vc = ctx.voice_client
        except AttributeError:
            vc = ctx.guild.voice_client

        vc: wavelink.Player = vc

        if not vc or not vc.connected:
            embed = discord.Embed(title="",
                                  description=str(ctx.user.mention) + ", I'm not joined to vc",
                                  color=discord.Color.blue())
            return await ctx.response.send_message(embed=embed)

        elif not vc.playing:
            embed = discord.Embed(title="",
                                  description=str(ctx.user.mention) + ', no song is playing',
                                  color=discord.Color.blue())
            return await ctx.response.send_message(embed=embed)

        await vc.skip()
        vc.first = False

        embed = discord.Embed(title="", description="**⏭️   Skipped**", color=discord.Color.blue())

        await ctx.response.send_message(embed=embed)

    @slash_command(name='skip-to', description='Skips to selected song in queue.')
    @option('pos', description='Value 2 skips to second song in queue.', min_value=1, required=True)
    async def skip_to_command(self, ctx: discord.ApplicationContext, pos: int) -> None:

        if not ctx.author.voice:
            embed = discord.Embed(title="",
                                  description=str(
                                      ctx.author.mention) + ", you're not joined into vc. Type `/p` from vc.",
                                  color=discord.Color.blue())
            return await ctx.respond(embed=embed, ephemeral=True)

        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.connected:
            embed = discord.Embed(title="",
                                  description=str(ctx.user.mention) + "**, I'm not joined to vc**",
                                  color=discord.Color.blue())
            return await ctx.response.send_message(embed=embed)

        if vc.queue.is_empty:
            embed = discord.Embed(title="", description="**Queue is empty**", color=discord.Color.blue())
            return await ctx.respond(embed=embed)

        try:
            track = vc.queue[pos - 1]
            vc.queue.put_at(0, track)
            del vc.queue[pos - 1]
            await vc.stop()

            embed = discord.Embed(title="",
                                  description=f"**Skipped to [{track.title}]({track.uri})**",
                                  color=discord.Color.blue())
        except IndexError:
            embed = discord.Embed(title="",
                                  description=f"**:x: Song was not found on position `{pos}`, to show what's in "
                                              f"queue, type /q.**",
                                  color=discord.Color.blue())
        await ctx.respond(embed=embed)

    @slash_command(name='pause', description='Pauses song that is currently playing.')
    async def pause_command(self, ctx: discord.ApplicationContext) -> None:

        try:
            vc = ctx.voice_client
        except AttributeError:
            vc = ctx.guild.voice_client

        vc: wavelink.Player = vc

        if not vc or vc.paused:
            embed = discord.Embed(title="",
                                  description=str(ctx.user.mention) + ', no song is playing.',
                                  color=discord.Color.blue())
            return await ctx.response.send_message(embed=embed)

        await vc.pause(True)

        embed = discord.Embed(title="",
                              description="**⏸️   Paused**",
                              color=discord.Color.blue())

        embed.set_footer(text=f'Deleting in 10s.')
        await ctx.response.send_message(embed=embed, delete_after=10)

    @slash_command(name='resume', description='Resumes paused song.')
    async def resume_command(self, ctx: discord.ApplicationContext) -> None:

        try:
            vc = ctx.voice_client
        except AttributeError:
            vc = ctx.guild.voice_client

        vc: wavelink.Player = vc

        if not vc:
            embed = discord.Embed(title="",
                                  description=str(ctx.user.mention) + ', no song playing.',
                                  color=discord.Color.blue())
            return await ctx.response.send_message(embed=embed)

        await vc.pause(False)

        embed = discord.Embed(title="",
                              description="**:arrow_forward: Resumed**",
                              color=discord.Color.blue())

        embed.set_footer(text=f'Deleting in 10s.')
        await ctx.response.send_message(embed=embed, delete_after=10)

    async def fetch_first_track(self, tracks: Union[Playable, TrackStartEventPayload], ctx: discord.ApplicationContext) \
            -> wavelink.Playable:
        vc: wavelink.Player = ctx.voice_client

        if isinstance(tracks, wavelink.Playlist):
            added: int = vc.queue.put(tracks)

            for track in tracks:
                track.requester = ctx.author  # Append author

            track: wavelink.Playable = tracks[0]
            await ctx.respond(embed=self.queue_embed_list(tracks.name, added))
        else:
            if not tracks:
                embed = discord.Embed(title="",
                                      description=f":x: Couldn't fetch any songs, are you sure your playlist is set "
                                                  f"to public?",
                                      color=discord.Color.from_rgb(r=255, g=0, b=0))
                return await ctx.respond(embed=embed)

            track: wavelink.Playable = tracks[0]
            track.requester = ctx.author  # Append request author
        return track

    @staticmethod
    async def is_playable(ctx: discord.ApplicationContext) -> bool:
        if not ctx.author.voice:
            embed = discord.Embed(title="",
                                  description=str(ctx.author.mention) + ", you're not in vc, type `/p` from vc.",
                                  color=discord.Color.blue())
            await ctx.respond(embed=embed)
            return False

        if ctx.voice_client:
            if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
                embed = discord.Embed(title="", description=str(
                    ctx.author.mention) + ", bot is already playing in a voice channel.", color=discord.Color.blue())
                await ctx.respond(embed=embed)
                return False
        return True


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Play(bot))
