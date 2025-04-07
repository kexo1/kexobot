import discord
import wavelink

from discord.ext import commands
from typing import Union
from wavelink import (
    NodeDisconnectedEventPayload,
    NodeReadyEventPayload,
    TrackStartEventPayload,
    TrackExceptionEventPayload,
    TrackStuckEventPayload,
)


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        if not payload.player.should_respond:
            await payload.player.text_channel.send(
                embed=await self._playing_embed(payload)
            )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: NodeReadyEventPayload) -> None:
        print(f"Node {payload.node.uri} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(
        self, payload: NodeDisconnectedEventPayload
    ) -> None:
        print(f"Node {payload.node.uri} is disconnected, fetching new node...")
        await self.bot.connect_node()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(
        self, payload: TrackExceptionEventPayload
    ) -> None:
        embed = discord.Embed(
            title="",
            description=f":warning: An error occured when playing song, trying to connect to a new node.",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        await self._manage_node(embed, payload)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: TrackStuckEventPayload) -> None:
        embed = discord.Embed(
            title="",
            description=f":warning: Song got stuck, trying to connect to a new node.",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        await self._manage_node(embed, payload)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        player.cleanup()
        await player.disconnect()
        embed = discord.Embed(
            title="",
            description=f"**Left <#{player.channel.id}> after 10 minutes of inactivity.**",
            color=discord.Color.blue(),
        )
        await player.text_channel.send(embed=embed)

    # noinspection PyUnusedLocal
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.member.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        vc: wavelink.Player = member.guild.voice_client
        if vc is None:
            return

        if len(vc.channel.members) == 1:
            await vc.disconnect()

    async def _manage_node(
        self,
        embed: discord.Embed,
        payload: Union[TrackExceptionEventPayload, TrackStuckEventPayload],
    ) -> None:
        message: discord.Message = await payload.player.text_channel.send(embed=embed)
        is_switched: bool = await self._switch_node(payload.player)
        await self._node_status_message(message, is_switched)

    @staticmethod
    async def _node_status_message(message: discord.Message, is_switched: bool) -> None:
        if is_switched:
            embed = discord.Embed(
                title="",
                description=f":white_check_mark: Successfully connected to a new node.",
                color=discord.Color.from_rgb(r=0, g=255, b=0),
            )
        else:
            embed = discord.Embed(
                title="",
                description=f":x: Failed to connect to a new node.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
        await message.edit(embed=embed)

    async def _switch_node(self, player: wavelink.Player) -> bool:
        for i in range(5):
            try:
                node: wavelink.Node = await self.bot.get_node()
                await player.switch_node(node)
                if player.current:
                    await player.play(player.current)
                return True
            except RuntimeError:
                print(f"{i}. Failed to switch node ({node.uri}), trying again...")
                continue
        return False

    async def _playing_embed(self, payload: TrackStartEventPayload) -> discord.Embed:
        embed = discord.Embed(
            color=discord.Colour.green(),
            title="Now playing",
            description="[**{}**]({})".format(payload.track.title, payload.track.uri),
        )
        embed.set_footer(
            text=f"Requested by {payload.player.current.requester.name}",
            icon_url=await self._has_pfp(payload.player.current.requester),
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
