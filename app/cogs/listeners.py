import logging
import random
from typing import TYPE_CHECKING

import discord
import sonolink
from discord.ext import commands
from sonolink import models as sl_models
from sonolink.gateway import (
    DisconnectTriggerType,
    PlayerDisconnectEvent,
    ReadyEvent,
    TrackExceptionEvent,
    TrackStartEvent,
    TrackStuckEvent,
    WebSocketClosedEvent,
)

from app.constants import ICON_YOUTUBE
from app.response_handler import send_response
from app.utils import fix_audio_title, switch_node

if TYPE_CHECKING:
    from app.main import KexoBotClient


def is_bot_node_connected(bot: "KexoBotClient") -> bool:
    return bool(getattr(bot, "node", None))


def resolve_requester(
    bot: "KexoBotClient", track: sl_models.Playable
) -> tuple[str | None, str | None]:
    requester_name = None
    requester_avatar = None
    if track.data.user_data:
        requester_name = track.data.user_data.get("requester_name")
        requester_avatar = track.data.user_data.get("requester_avatar")
    if requester_name:
        return requester_name, requester_avatar

    cached = bot.state.get_track_requester(track.encoded)
    if cached:
        cached_avatar = cached.get("avatar") or None
        return cached.get("name"), cached_avatar

    return None, None


def playing_embed(bot: "KexoBotClient", payload: TrackStartEvent) -> discord.Embed:
    embed = discord.Embed(
        color=discord.Colour.green(),
        title="Now playing",
        description=f"[**{fix_audio_title(payload.track)}**]({payload.track.uri})",
    )
    track = payload.track
    requester_name, requester_avatar = resolve_requester(bot, track)
    if requester_name:
        embed.set_footer(
            text=f"Requested by {requester_name}",
            icon_url=requester_avatar,
        )
    else:
        embed.set_footer(
            text="YouTube Autoplay",
            icon_url=ICON_YOUTUBE,
        )
    embed.set_thumbnail(url=payload.track.artwork)
    return embed


def is_same_track(track: sl_models.Playable, payload_track: sl_models.Playable) -> bool:
    track_encoded = getattr(track, "encoded", None)
    payload_encoded = getattr(payload_track, "encoded", None)
    return bool(
        track == payload_track
        or (track_encoded and payload_encoded and track_encoded == payload_encoded)
    )


class Listeners(commands.Cog):
    """Handles various events from the sonolink library.

    This class listens for events such as track start, node ready, node disconnected,
    track exception, track stuck, and inactive player. It also handles voice state updates
    to manage player connections and disconnections based on user presence in voice channels.

    Parameters
    ----------
    bot: :class:`KexoBotClient`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: "KexoBotClient"):
        self._bot = bot

    async def _handle_track_error_probe(
        self,
        player: sonolink.Player,
        payload_track: sl_models.Playable,
    ) -> bool:
        """Check switching state and exception probe; penalize node if neither applies.

        Returns True if the caller should return early (already handled), False otherwise.
        """
        # Check if currently switching nodes for this guild
        if self._bot.node_is_switching.get(player.guild.id):
            return True

        # Check if this track matches the one in the exception probe
        # If it does, we set the event to unblock the waiting code in the command and return early without penalizing the node.
        data = self._bot.state.get_track_exception_probe(player.guild.id)
        if data:
            track, track_failed_event = data
            if is_same_track(track, payload_track):
                track_failed_event.set()
                return True

        self._bot.state.change_node_score(player.node.uri, -2)
        return False

    @commands.Cog.listener()
    async def on_sonolink_node_ready(self, payload: ReadyEvent) -> None:
        """This event is triggered when a sonolink node is ready.

        It checks if the bot is connected to the node and closes any unused nodes if necessary.

        Parameters
        ----------
        payload: :class:`NodeReadyEventPayload`
            The payload containing information about the node that is ready.
        """
        logging.info(f"[Sonolink] A node is ready ({payload.node.uri})")
        if self._bot.get_online_nodes() > 1 and is_bot_node_connected(self._bot):
            await self._bot.close_unused_nodes()

    @commands.Cog.listener()
    async def on_sonolink_node_close(self, node: sonolink.Node) -> None:
        """This event is triggered when a sonolink node is closed.

        It checks if the bot is connected to the node and attempts to reconnect if necessary.

        Parameters
        ----------
        node: :class:`sonolink.Node`
            The node that was closed.
        """
        if self._bot.get_online_nodes() == 0 and is_bot_node_connected(self._bot):
            logging.warning(
                f"[Sonolink] Node got disconnected, connecting new node. ({node.uri})"
            )
            self._bot.state.change_node_score(node.uri, -1)
            await self._bot.connect_node()

    @commands.Cog.listener()  # noinspection PyUnusedLocal
    async def on_sonolink_track_start(
        self, player: sonolink.Player, payload: TrackStartEvent
    ) -> None:
        """This event is triggered when a track starts playing.

        It sends a message to the text channel with the track information.

        Parameters
        ----------
        payload: :class:`TrackStartEventPayload`
            The payload containing information about the track that started playing.
        """
        if self._bot.node_is_switching.get(player.guild.id):
            return

        self._bot.state.change_node_score(player.node.uri, 1)
        current_track = player.current or payload.track
        temp_current = getattr(player, "temp_current", None)
        if (
            current_track
            and temp_current
            and not current_track.data.user_data
            and temp_current.data.user_data
        ):
            current_track.data.user_data = dict(temp_current.data.user_data)

        requester_name = None
        if current_track:
            requester_name, _ = resolve_requester(self._bot, current_track)

        # Avoid noisy autoplay spam: announce only requested trackS.
        if player.should_respond or requester_name:
            await player.text_channel.send(embed=playing_embed(self._bot, payload))
            player.should_respond = False

        history_count = len(player.queue.history)
        if player.autoplay != sonolink.AutoPlayMode.ENABLED:
            tips: dict[int, str] = {
                3: (
                    "-# Not happy with the current node performance?\n"
                    f"-# You can switch between {self._bot.get_available_nodes()} nodes "
                    "by using /node reconnect."
                ),
                10: (
                    "-# Use the /music autoplay_mode command and\n"
                    "-# set the mode to populated to enable automatic queuing of "
                    "similar tracks."
                ),
                15: (
                    "-# Would you like to see which platforms are supported by this "
                    "node? Use the /node supported_platforms."
                ),
            }

            tip = tips.get(history_count)
            if tip and random.randint(0, 2) == 0:
                await player.text_channel.send(tip)

    @commands.Cog.listener()
    async def on_sonolink_websocket_closed(
        self, player: sonolink.Player, payload: WebSocketClosedEvent
    ) -> None:
        """This event is triggered when the websocket connection to the node is closed.

        It sends a message to the text channel and attempts to reconnect to the node.

        Parameters
        ----------
        payload: :class:`WebSocketClosedEventPayload`
            The payload containing information about the websocket closure.
        """
        logging.warning(
            f"[Sonolink] Websocket closed for node {player.node.uri}, reason: {payload.reason}, by_remote: {payload.by_remote}"
        )
        # Disconnected either by admin or by the node itself, no need to attempt reconnection or switch nodes.
        if payload.by_remote and "Disconnected." in payload.reason:
            return

        if self._bot.get_online_nodes() == 0:
            await self._bot.connect_node()
            return

        if await self._handle_track_error_probe(player, payload.track):
            return

        await send_response(
            player.text_channel,
            "NODE_WEBSOCKET_CLOSED",
            respond=False,
            reason=payload.reason,
            by_remote=payload.by_remote,
        )

        await switch_node(bot=self._bot, player=player)
        player.should_respond = False

    @commands.Cog.listener()
    async def on_sonolink_track_exception(
        self, player: sonolink.Player, payload: TrackExceptionEvent
    ) -> None:
        """This event is triggered when a track encounters an exception.

        It sends a message to the text channel with the exception information.

        Parameters
        ----------
        payload: :class:`TrackExceptionEventPayload`
            The payload containing information about the track exception.
        """

        if await self._handle_track_error_probe(player, payload.track):
            return

        await send_response(
            player.text_channel,
            "TRACK_EXCEPTION",
            respond=False,
            message=payload.exception.message,
            severity=payload.exception.severity.value,
        )
        await switch_node(bot=self._bot, player=player)
        player.should_respond = False

    @commands.Cog.listener()
    async def on_sonolink_track_stuck(
        self, player: sonolink.Player, payload: TrackStuckEvent
    ) -> None:
        """This event is triggered when a track gets stuck.

        It sends a message to the text channel and attempts to switch nodes.

        Parameters
        ----------
        payload: :class:`TrackStuckEventPayload`
            The payload containing information about the track that got stuck.
        """

        if await self._handle_track_error_probe(player, payload.track):
            return

        await send_response(player.text_channel, "TRACK_STUCK", respond=False)
        await switch_node(
            bot=self._bot,
            player=player,
            play_after=False,
            send_success_message=False,
            send_failure_message=False,
        )
        player.should_respond = False

    @commands.Cog.listener()
    async def on_sonolink_player_disconnect(
        self, player: sonolink.Player, payload: PlayerDisconnectEvent
    ) -> None:
        """This event is triggered when a player gets disconnected due to inactivity.

        Parameters
        ----------
        player: :class:`sonolink.Player`
            The player that got disconnected.
        """

        if payload.trigger == DisconnectTriggerType.INACTIVITY:
            await send_response(
                player.text_channel,
                "DISCONNECTED_INACTIVITY",
                respond=False,
                channel_id=player.channel.id,
            )

        if payload.extra_data:
            logging.info(
                f"[Sonolink] Player disconnected for guild {player.guild.id}, trigger: {payload.trigger}, extra_data: {payload.extra_data}"
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
        player: sonolink.Player = member.guild.voice_client
        if player is None:
            return

        if before.channel != player.channel and after.channel != player.channel:
            return

        if len(player.channel.members) == 1:
            await player.disconnect(force=True)

        if player.channel.members[0] == player.guild.me:
            try:
                await send_response(
                    player.text_channel,
                    "DISCONNECTED_NO_USERS",
                    respond=False,
                    channel_id=player.channel.id,
                )
            except AttributeError:
                pass


async def setup(bot: "KexoBotClient") -> None:
    """Adds the Listeners cog to the bot."""
    await bot.add_cog(Listeners(bot))
