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

from app.constants import DISCORD_ICON, YOUTUBE_ICON
from app.response_handler import send_response
from app.utils import fix_audio_title, switch_node


class Listeners(commands.Cog):
    """Handles various events from the Wavelink library.

    This class listens for events such as track start, node ready, node disconnected,
    track exception, track stuck, and inactive player. It also handles voice state updates
    to manage player connections and disconnections based on user presence in voice channels.

    Parameters
    ----------
    bot: :class:`commands.Bot`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()  # noinspection PyUnusedLocal
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        """This event is triggered when a track starts playing.

        It sends a message to the text channel with the track information.

        Parameters
        ----------
        payload: :class:`TrackStartEventPayload`
            The payload containing information about the track that started playing.
        """
        if not payload.player.should_respond:
            await payload.player.text_channel.send(embed=self._playing_embed(payload))

        if payload.player.queue.history.count == 3:
            await payload.player.text_channel.send(
                "-# Not happy with the current node performance?\n"
                f"-# You can switch between {self.bot.get_avaiable_nodes()}"
                " nodes by using /node reconnect."
            )

        if payload.player.queue.history.count == 10:
            await payload.player.text_channel.send(
                "-# Would you like to see which platforms are supported by this node?"
                " Use the /node supported_platforms."
            )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: NodeReadyEventPayload) -> None:
        """This event is triggered when a Wavelink node is ready.

        It checks if the bot is connected to the node and closes any unused nodes if necessary.

        Parameters
        ----------
        payload: :class:`NodeReadyEventPayload`
            The payload containing information about the node that is ready.
        """
        print(f"Node ({payload.node.uri}) is ready!")
        if self.bot.get_online_nodes() > 1 and self._is_bot_node_connected():
            await self.bot.close_unused_nodes()

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(
        self, payload: NodeDisconnectedEventPayload
    ) -> None:
        """This event is triggered when a Wavelink node is disconnected.

        It checks if the bot is connected to the node and attempts to reconnect if necessary.

        Parameters
        ----------
        payload: :class:`NodeDisconnectedEventPayload`
            The payload containing information about the node that is disconnected.
        """
        if self.bot.get_online_nodes() == 0 and self._is_bot_node_connected():
            print(f"Node got disconnected, connecting new node. ({payload.node.uri})")
            await self.bot.connect_node()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(
        self, payload: TrackExceptionEventPayload
    ) -> None:
        """This event is triggered when a track encounters an exception.

        It sends a message to the text channel with the exception information.

        Parameters
        ----------
        payload: :class:`TrackExceptionEventPayload`
            The payload containing information about the track exception.
        """
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
        """This event is triggered when a track gets stuck.

        It sends a message to the text channel and attempts to switch nodes.

        Parameters
        ----------
        payload: :class:`TrackStuckEventPayload`
            The payload containing information about the track that got stuck.
        """
        await send_response(payload.player.text_channel, "TRACK_STUCK", respond=False)
        await switch_node(
            self.bot.connect_node, player=payload.player, play_after=False
        )

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        """This event is triggered when a player becomes inactive.

        It sends a message to the text channel and disconnects the player.

        Parameters
        ----------
        player: :class:`wavelink.Player`
            The player that became inactive.
        """
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
        """This event is triggered when a voice state update occurs.

        It checks if the user is the last one in the voice
        channel and disconnects the player if necessary.

        Parameters
        ----------
        member: :class:`discord.Member`
            The member whose voice state has changed.
        before: :class:`discord.VoiceState`
            The voice state before the change.
        after: :class:`discord.VoiceState`
            The voice state after the change.
        """
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
                text="YouTube Autoplay",
                icon_url=YOUTUBE_ICON,
            )
        embed.set_thumbnail(url=payload.track.artwork)
        return embed

    def _is_bot_node_connected(self) -> bool:
        return hasattr(self.bot, "node")

    @staticmethod
    def _has_pfp(member: discord.Member) -> str:
        if hasattr(member.avatar, "url"):
            return member.avatar.url
        return DISCORD_ICON


def setup(bot: commands.Bot) -> None:
    """Adds the Listeners cog to the bot."""
    bot.add_cog(Listeners(bot))
