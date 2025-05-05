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

from app.constants import DISCORD_LOGO, YOUTUBE_LOGO
from app.response_handler import send_response
from app.utils import fix_audio_title, switch_node


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()  # noinspection PyUnusedLocal
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        if not payload.player.should_respond:
            await payload.player.text_channel.send(embed=self._playing_embed(payload))

        if payload.player.queue.history.count == 3:
            await payload.player.text_channel.send(
                f"-# Not happy with the current node performance?\n"
                f"-# You can switch between {self.bot.get_avaiable_nodes()} nodes by using /node reconnect."
            )

        if payload.player.queue.history.count == 10:
            await payload.player.text_channel.send(
                f"-# Would you like to see which platforms are supported by this node? Use the /node supported_platforms."
            )

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
        await send_response(
            payload.player.text_channel,
            "TRACK_EXCEPTION",
            respond=False,
            message=payload.exception["message"],
            severity=payload.exception["severity"],
        )
        await switch_node(self.bot.connect_node, payload.player)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: TrackStuckEventPayload) -> None:
        await send_response(payload.player.text_channel, "TRACK_STUCK", respond=False)
        await switch_node(
            self.bot.connect_node, player=payload.player, play_after=False
        )

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        player.cleanup()
        await player.disconnect()
        await send_response(
            player.text_channel,
            "DISCONNECTED_INACTIVITY",
            respond=False,
            channel_id=player.channel.id,
        )

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
            await send_response(
                player.text_channel,
                "DISCONNECTED_NO_USERS",
                respond=False,
                channel_id=player.channel.id,
            )
            player.cleanup()
            await player.disconnect()
            return

    def _playing_embed(self, payload: TrackStartEventPayload) -> discord.Embed:
        embed = discord.Embed(
            color=discord.Colour.green(),
            title="Now playing",
            description=f"[**{fix_audio_title(payload.track)}**]({payload.track.uri})",
        )
        if hasattr(payload.player.current, "requester"):
            embed.set_footer(
                text=f"Requested by {payload.player.current.requester.name}",
                icon_url=self._has_pfp(payload.player.current.requester),
            )
        else:
            embed.set_footer(
                text=f"YouTube Autoplay",
                icon_url=YOUTUBE_LOGO,
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
