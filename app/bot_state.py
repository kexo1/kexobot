from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
import sonolink
import sonolink.models as sl_models
from sonolink.models import AutoPlaySettings, CacheSettings, InactivitySettings

from app.config.colors import COLOR_GREEN, COLOR_RED
from app.config.discord import ICON_YOUTUBE
from app.config.music import TRACK_REQUESTER_MAXSIZE
from app.utils import fix_audio_title

if TYPE_CHECKING:
    from app.main import KexoBotClient


@dataclass(slots=True)
class BotState:
    """Typed state operations for mutable bot runtime data.

    This class centralizes write/read operations for mutable bot state so cogs
    and helpers do not duplicate direct dictionary/list manipulation logic.
    """

    bot: KexoBotClient

    def change_node_score(self, node_uri: str, delta: int) -> None:
        """Apply score delta to cached Lavalink node.

        Parameters
        ----------
        node_uri: str
            URI of the node in the cache.
        delta: int
            Score delta to apply. Negative values punish node score.

        Notes
        -----
        Score +1 = successful track load
        Score -1 = health check failed
        Score -1 = node closed
        Score -5 = track exception or stuck
        Score set to -1 = failed voice connection attempt
        """
        node_entry = self.bot.cached_lavalink_servers.get(node_uri)
        if not node_entry:
            return
        node_entry["score"] += delta

    async def node_health_check(self, node: sonolink.Node) -> bool:
        """Check the health of a lavalink node by attempting to fetch its info.

        Parameters
        ----------
        node: :class:`sonolink.Node`
            The lavalink node to check.

        Returns
        -------
        bool
            True if the node is healthy and responsive, False otherwise.
        """
        try:
            await asyncio.wait_for(node.fetch_info(), timeout=3)
            return True
        except Exception:
            logging.info("[Sonolink] Node health check failed (%s)", node.uri)

        self.change_node_score(node.uri, -1)
        return False

    def get_online_nodes(self) -> int:
        """Get the number of online lavalink nodes,
        returns ``int`` of online nodes.
        """
        return len(
            [node for node in self.bot.sonolink_client.nodes if node.is_connected]
        )

    def get_available_nodes(self) -> int:
        """Get the number of available lavalink nodes.

        Returns the count of cached lavalink nodes.
        """
        return len(self.bot.cached_lavalink_servers)

    async def close_unused_nodes(self) -> None:
        """Clear unused lavalink nodes.

        This function will check if there are any lavalink nodes
        that are not being used and will close them.
        """
        async with self.bot.close_nodes_lock:
            nodes: list[sonolink.Node] = list(self.bot.sonolink_client.nodes)
            for node in nodes:
                if len(self.bot.sonolink_client.nodes) == 1:
                    break

                if node.is_connected:
                    continue

                try:
                    await node.close()
                    logging.info(f"[Sonolink] Closed unused node: {node.uri}")
                except RuntimeError:
                    pass

    async def node_attempt_connection(self, node: sonolink.Node) -> bool:
        """Attempt to connect to a lavalink node.
        This function will try to connect to the lavalink node

        Parameters
        ----------
        node: sonolink.Node
            The lavalink node to check the status of.
        Returns
        -------
        bool
            True if the node is connected, False otherwise.
        """
        try:
            await asyncio.wait_for(node.connect(), timeout=3)
            # Some fucking nodes secretly don't respond,
            # I've played these games before!!!
            if not await self.node_health_check(node):
                logging.info(
                    f"[Sonolink] Node failed health check when attempting to connect: ({node.uri})"
                )
                self.change_node_score(node.uri, -1)
                return False
            return True

        except Exception:
            logging.info(f"[Sonolink] Node failed to connect: ({node.uri})")

        self.change_node_score(node.uri, -1)
        return False

    def get_node_score(self, node_uri: str) -> int | None:
        """Get cached score of Lavalink node.

        Parameters
        ----------
        node_uri: str
            URI of the node in the cache.

        Returns
        -------
        int | None
            Node score if node is cached, otherwise ``None``.
        """
        node_entry = self.bot.cached_lavalink_servers.get(node_uri)
        if not node_entry:
            return None
        return node_entry["score"]

    def change_node_ping(self, node_uri: str, ping: int) -> None:
        """Update the ping value for a cached Lavalink node.

        Parameters
        ----------
        node_uri: str
            URI of the node in the cache.
        ping: int
            The new ping value in milliseconds.
        """
        node_entry = self.bot.cached_lavalink_servers.get(node_uri)
        if not node_entry:
            return
        node_entry["ping"] = ping

    def get_node_ping(self, node_uri: str) -> int | None:
        """Get cached ping of Lavalink node.

        Parameters
        ----------
        node_uri: str
            URI of the node in the cache.

        Returns
        -------
        int | None
            Node ping in ms if node is cached, otherwise ``None``.
        """
        node_entry = self.bot.cached_lavalink_servers.get(node_uri)
        if not node_entry:
            return None
        return node_entry["ping"]

    def cache_track_requester(self, track_encoded: str, name: str, avatar: str) -> None:
        """Cache requester metadata by encoded track ID.

        Evicts the oldest entries when the cache exceeds ``TRACK_REQUESTER_MAXSIZE``.

        Parameters
        ----------
        track_encoded: str
            Encoded track ID used as cache key.
        name: str
            Requesting user's display name.
        avatar: str
            Requesting user's avatar URL. May be empty string.
        """
        requesters = self.bot.track_requesters
        if (
            track_encoded not in requesters
            and len(requesters) >= TRACK_REQUESTER_MAXSIZE
        ):
            # Evict the oldest entry (first inserted key)
            try:
                oldest_key = next(iter(requesters))
                del requesters[oldest_key]
            except StopIteration:
                pass
        requesters[track_encoded] = {"name": name, "avatar": avatar}

    def get_track_requester(self, track_encoded: str) -> dict[str, str] | None:
        """Get cached requester metadata for encoded track.

        Parameters
        ----------
        track_encoded: str
            Encoded track ID used as cache key.

        Returns
        -------
        dict[str, str] | None
            Cached requester mapping if present, else ``None``.
        """
        return self.bot.track_requesters.get(track_encoded)

    def set_track_exception_probe(
        self, guild_id: int, track: Any, failed_event: Any
    ) -> None:
        """Store temporary probe entry for node-switch validation.

        Parameters
        ----------
        guild_id: int
            Guild ID the probe belongs to.
        track: Any
            Track object being validated after switch.
        failed_event: Any
            Event set by listeners when track fails on new node.
        """
        self.bot.track_exceptions[guild_id] = (track, failed_event)

    def get_track_exception_probe(self, guild_id: int) -> tuple[Any, Any] | None:
        """Get stored track exception probe for guild.

        Parameters
        ----------
        guild_id: int
            Guild ID to look up.

        Returns
        -------
        tuple[Any, Any] | None
            Probe tuple ``(track, event)`` if present, else ``None``.
        """
        return self.bot.track_exceptions.get(guild_id)

    def clear_track_exception_probe(self, guild_id: int) -> None:
        """Remove stored track exception probe for guild."""
        self.bot.track_exceptions.pop(guild_id, None)

    def build_node(self, uri: str, password: str) -> sonolink.Node:
        """Create a new Lavalink node with default settings.

        Parameters
        ----------
        uri: str
            The URI of the Lavalink node (host:port).
        password: str
            The password for the Lavalink node.

        Returns
        -------
        :class:`sonolink.Node`
            The created Lavalink node instance.
        """
        return self.bot.sonolink_client.create_node(
            uri=uri,
            password=password,
            retries=1,
            resume_timeout=60,
            inactivity_settings=InactivitySettings(
                timeout=600,
                mode=sonolink.InactivityMode.ALL_BOTS,
            ),
            cache_settings=CacheSettings(enabled=True, max_items=100),
        )

    def make_now_playing_embed(self, track: sl_models.Playable) -> discord.Embed:
        """Create a 'Now playing' embed for a given track.

        Parameters
        ----------
        track: :class:`sonolink.Playable`
            The track to create the embed for.

        Returns
        -------
        :class:`discord.Embed`
            The embed to send.
        """
        embed = discord.Embed(
            color=COLOR_GREEN,
            title="Now playing",
            description=f"[**{fix_audio_title(track)}**]({track.uri})",
        )

        requester_name = None
        requester_avatar = None

        if track.data.user_data:
            requester_name = track.data.user_data.get("requester_name")
            requester_avatar = track.data.user_data.get("requester_avatar")

        if not requester_name:
            cached = self.get_track_requester(track.encoded)
            if cached:
                requester_name = cached.get("name")
                requester_avatar = cached.get("avatar")

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

        embed.set_thumbnail(url=track.artwork)
        return embed

    async def switch_node(
        self,
        player: sonolink.Player,
        play_after: bool = False,
        send_success_message: bool = True,
        send_failure_message: bool = True,
    ) -> sonolink.Node | None:
        """Attempt to switch to a new node for audio playback.

        Parameters
        ----------
        player: :class:`sonolink.Player`
            The sonolink Player instance to switch the node for.
        play_after: bool
            Whether to play the current track after switching nodes.
        send_success_message: bool
            Whether to send a success message in the text channel upon successful node switch.
        send_failure_message: bool
            Whether to send a failure message in the text channel if no suitable node is found.

        Returns
        -------
        :class:`sonolink.Node` | None
            The new sonolink.Node instance if successful, None otherwise.
        """
        guild_id = player.guild.id
        switching_map = self.bot.node_is_switching
        if switching_map.get(guild_id):
            return None

        # Set switching to True for guild
        switching_map[guild_id] = True
        excluded_nodes = set()
        excluded_nodes.add(player.node.uri) if player.node else None

        original_autoplay_mode = player.autoplay
        await player.update(
            autoplay_settings=AutoPlaySettings(
                mode=sonolink.AutoPlayMode.DISABLED,
            )
        )

        def _resume_track() -> sonolink.models.Playable | None:
            return getattr(player, "temp_current", None) or player.current

        async def _try_move_and_resume(target_node: sonolink.Node) -> bool:
            try:
                # Stop the inactivity timer on previous node to prevent it from disconnecting
                player._stop_inactivity_timer()
                await player.move_to(target_node)
                track = _resume_track()
                # Only when we didn't even get to play the track, moving won't play it, so we have to do it manually here.
                if play_after and track:
                    await player.play(track)

                # Check for inactivity after moving to the new node
                player._check_inactivity()
                return True
            except Exception:
                self.change_node_score(target_node.uri, -5)
                return False

        async def _playback_probe_failed(target_node: sonolink.Node) -> bool:
            # if not play_after:
            #    return False

            # Test only if we were playing something before
            track = _resume_track()
            if not track:
                return False

            track_failed_event = asyncio.Event()
            self.set_track_exception_probe(guild_id, track, track_failed_event)
            try:
                await asyncio.wait_for(track_failed_event.wait(), timeout=3)
                self.change_node_score(target_node.uri, -5)
                return True
            except asyncio.TimeoutError:
                return False
            finally:
                self.clear_track_exception_probe(guild_id)

        try:
            for attempt in range(10):
                node: sonolink.Node | None = await self.bot.connect_node(
                    exclude_nodes=excluded_nodes
                )
                excluded_nodes.add(node.uri) if node else None

                if not node:
                    continue

                is_moved = await _try_move_and_resume(node)
                if not is_moved:
                    continue

                if await _playback_probe_failed(node):
                    continue

                logging.info(f"[Sonolink] {attempt + 1}. Node switched ({node.uri})")
                if send_success_message:
                    embed = discord.Embed(
                        title="",
                        description=f"**:white_check_mark: Successfully connected to `{node.uri}`**",
                        color=COLOR_GREEN,
                    )
                    await player.text_channel.send(embed=embed)

                return node

            if send_failure_message:
                embed = discord.Embed(
                    title="",
                    description=":x: Failed to find node to play requested track.",
                    color=COLOR_RED,
                )
                await player.text_channel.send(embed=embed)

            return None
        finally:
            await player.update(
                autoplay_settings=AutoPlaySettings(
                    mode=original_autoplay_mode,
                )
            )
            switching_map[guild_id] = False
