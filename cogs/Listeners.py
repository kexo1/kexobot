import discord
import wavelink

from discord.ext import commands
from cogs.Disconnect import Disconnect
from wavelink import NodeDisconnectedEventPayload, NodeReadyEventPayload, TrackStartEventPayload, \
    TrackExceptionEventPayload, TrackStuckEventPayload


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        if not payload.player.should_respond:
            await payload.player.text_channel.send(embed=await self._playing_embed(payload))

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: NodeReadyEventPayload) -> None:
        print(f"Node {payload.node.uri} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: NodeDisconnectedEventPayload) -> None:
        print(f"Node {payload.node.uri} is disconnected, fetching new node...")
        await asyncio.sleep(1)
        await self.bot.connect_node()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: TrackExceptionEventPayload) -> None:
        embed = discord.Embed(
            title="",
            description=f":x: An error occured when playing song, skip song or re-join bot.",
            color=discord.Color.from_rgb(r=255, g=0, b=0)
        )
        await payload.player.text_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: TrackStuckEventPayload) -> None:
        embed = discord.Embed(
            title="",
            description=f":x: Song got stuck, skip song or re-join bot.",
            color=discord.Color.from_rgb(r=255, g=0, b=0)
        )
        await payload.player.text_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        await Disconnect.disconnect_player(player.guild)
        embed = discord.Embed(title="",
                              description=f"**Left <#{player.channel.id}> after 10 minutes of inactivity.**",
                              color=discord.Color.blue())
        await player.text_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
            self,
            member: discord.member.Member,
            before: discord.VoiceState,
            after: discord.VoiceState) -> None:

        voice_state = member.guild.voice_client
        if voice_state is None:
            return

        if len(voice_state.channel.members) == 1:
            await Disconnect.disconnect_player(member.guild)

    async def _playing_embed(self, payload: TrackStartEventPayload) -> discord.Embed:
        embed = discord.Embed(
            color=discord.Colour.green(),
            title='Now playing',
            description='[**{}**]({})'.format(payload.track.title, payload.track.uri)
        )
        embed.set_footer(
            text=f'Requested by {payload.player.current.requester.name}',
            icon_url=await self._has_pfp(payload.player.current.requester)
        )
        embed.set_thumbnail(url=payload.track.artwork)
        return embed

    @staticmethod
    async def _has_pfp(member: discord.Member) -> str:
        if hasattr(member.avatar, "url"):
            return member.avatar.url
        return None


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Listeners(bot))
