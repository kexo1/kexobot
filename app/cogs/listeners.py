from typing import Union

import discord
import wavelink
from discord.ext import commands
from wavelink import (
    NodeDisconnectedEventPayload,
    NodeReadyEventPayload,
    TrackStartEventPayload,
    TrackExceptionEventPayload,
    TrackStuckEventPayload,
)

from app.constants import DISCORD_LOGO
from app.utils import fix_audio_title, switch_node


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()  # noinspection PyUnusedLocal
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        if not payload.player.should_respond:
            await payload.player.text_channel.send(embed=self._playing_embed(payload))

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: NodeReadyEventPayload) -> None:
        print(f"Node ({payload.node.uri}) is ready!")
        if self.bot.get_online_nodes() > 1 and self.is_bot_node_connected():
            await self.bot.close_unused_nodes()

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(
        self, payload: NodeDisconnectedEventPayload
    ) -> None:
        if self.bot.get_online_nodes() == 0 and self.is_bot_node_connected():
            print(f"Node got disconnected, connecting new node. ({payload.node.uri})")
            await self.bot.connect_node()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(
        self, payload: TrackExceptionEventPayload
    ) -> None:
        embed = discord.Embed(
            title="",
            description=":warning: An error occured when playing song, trying to connect to a new node."
            f"\n\n**Message**: {payload.exception['message']}"
            f"\n**Severity**: {payload.exception['severity']}",
            color=discord.Color.yellow(),
        )
        await self._manage_node(embed, payload)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: TrackStuckEventPayload) -> None:
        embed = discord.Embed(
            title="",
            description=":warning: Song got stuck, trying to connect to a new node.",
            color=discord.Colour.yellow(),
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
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        player: wavelink.Player = member.guild.voice_client
        if player is None:
            return

        if len(player.channel.members) == 1:
            await player.text_channel.send(
                embed=discord.Embed(
                    title="",
                    description=f"**Left <#{player.channel.id}>, no users in channel.**",
                    color=discord.Color.blue(),
                )
            )
            player.cleanup()
            await player.disconnect()
            return

    async def _manage_node(
        self,
        embed: discord.Embed,
        payload: Union[TrackExceptionEventPayload, TrackStuckEventPayload],
    ) -> None:
        await payload.player.text_channel.send(embed=embed)
        await switch_node(self.bot.connect_node, payload.player, payload.player.text_channel)

    async def _switch_node(self, player: wavelink.Player) -> bool:
        try:
            node: wavelink.Node = await self.bot.connect_node()
            await player.switch_node(node)
            await player.play(player.temp_current)
            print(f"Node switched. ({node.uri})")
            return True
        except (
            RuntimeError,
            wavelink.LavalinkException,
            wavelink.InvalidNodeException,
        ):
            return False

    def _playing_embed(self, payload: TrackStartEventPayload) -> discord.Embed:
        embed = discord.Embed(
            color=discord.Colour.green(),
            title="Now playing",
            description=f"[**{fix_audio_title(payload.track)}**]({payload.track.uri})",
        )
        embed.set_footer(
            text=f"Requested by {payload.player.current.requester.name}",
            icon_url=self._has_pfp(payload.player.current.requester),
        )
        embed.set_thumbnail(url=payload.track.artwork)
        return embed

    def is_bot_node_connected(self) -> bool:
        return hasattr(self.bot, "node")

    @staticmethod
    def _has_pfp(member: discord.Member) -> str:
        if hasattr(member.avatar, "url"):
            return member.avatar.url
        return DISCORD_LOGO


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Listeners(bot))
