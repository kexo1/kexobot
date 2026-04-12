import logging
import random

import discord
import sonolink
from discord.ext import commands
from sonolink import models as sl_models
from sonolink.gateway import (
    ReadyEvent,
    TrackExceptionEvent,
    TrackStartEvent,
    TrackStuckEvent,
)

from app.constants import ICON_YOUTUBE
from app.response_handler import send_response
from app.utils import fix_audio_title, switch_node


def is_bot_node_connected(bot: commands.Bot) -> bool:
    return bool(getattr(bot, "node", None))


def get_extra_value(track: sl_models.Playable, key: str) -> str | None:
    extras = getattr(track, "extras", None)
    if extras is None:
        return None

    getter = getattr(extras, "get", None)
    if callable(getter):
        return getter(key)

    return getattr(extras, key, None)


def resolve_requester(
    bot: commands.Bot, track: sl_models.Playable
) -> tuple[str | None, str | None]:
    name = get_extra_value(track, "requester_name")
    avatar = get_extra_value(track, "requester_avatar")
    if name:
        return name, avatar

    cached = bot.track_requesters.get(track.encoded)
    if cached:
        cached_avatar = cached.get("avatar") or None
        return cached.get("name"), cached_avatar

    return None, None


def playing_embed(
    bot: commands.Bot, player: sonolink.Player, payload: TrackStartEvent
) -> discord.Embed:
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


class Listeners(commands.Cog):
    """Handles various events from the sonolink library.

    This class listens for events such as track start, node ready, node disconnected,
    track exception, track stuck, and inactive player. It also handles voice state updates
    to manage player connections and disconnections based on user presence in voice channels.

    Parameters
    ----------
    bot: :class:`commands.Bot`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: commands.Bot):
        self._bot = bot

    @commands.Cog.listener()
    async def on_sonolink_node_ready(self, payload: ReadyEvent) -> None:
        """This event is triggered when a sonolink node is ready.

        It checks if the bot is connected to the node and closes any unused nodes if necessary.

        Parameters
        ----------
        payload: :class:`NodeReadyEventPayload`
            The payload containing information about the node that is ready.
        """
        logging.info("[Lavalink] A node is ready.")
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
                f"[Lavalink] Node got disconnected, connecting new node. ({node.uri})"
            )
            node_data = self._bot.cached_lavalink_servers.get(node.uri)
            if node_data:
                node_data["score"] -= 1
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

        if getattr(player, "node_is_switching", False):
            return

        current_track = player.current or payload.track
        requester_name = None
        if current_track:
            requester_name, _ = resolve_requester(self._bot, current_track)

        # Avoid noisy autoplay spam: announce only requested tracks or explicit response flow.
        if player.should_respond or requester_name:
            await player.text_channel.send(
                embed=playing_embed(self._bot, player, payload)
            )
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
        # Temporarily disabled track_exceptions synchronization check.
        # data = self._bot.track_exceptions.get(player.guild.id)
        # if data:
        #     track, track_failed_event = data
        #     if track == payload.track:
        #         track_failed_event.set()
        #         return

        if not hasattr(payload, "player"):
            logging.warning("Player not found, skipping track exception message.")
            return

        await send_response(
            payload.player.text_channel,
            "TRACK_EXCEPTION",
            respond=False,
            message=payload.exception["message"],
            severity=payload.exception["severity"],
        )
        await switch_node(bot=self._bot, player=payload.player)
        payload.player.should_respond = False

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
        # Temporarily disabled track_exceptions synchronization check.
        # data = self._bot.track_exceptions.get(player.guild.id)
        # if data:
        #     track, track_failed_event = data
        #     if track == payload.track:
        #         track_failed_event.set()
        #         return

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
    async def on_sonolink_inactive_player(self, player: sonolink.Player) -> None:
        """This event is triggered when a player becomes inactive.

        It sends a message to the text channel and disconnects the player.

        Parameters
        ----------
        player: :class:`sonolink.Player`
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
        player: sonolink.Player = member.guild.voice_client
        if player is None:
            return

        if len(player.channel.members) == 1:
            try:
                await send_response(
                    player.text_channel,
                    "DISCONNECTED_NO_USERS",
                    respond=False,
                    channel_id=player.channel.id,
                )
                player.cleanup()
                await player.disconnect()
            except AttributeError:
                pass
            return


async def setup(bot: commands.Bot) -> None:
    """Adds the Listeners cog to the bot."""
    await bot.add_cog(Listeners(bot))
