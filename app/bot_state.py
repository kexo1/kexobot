from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast, runtime_checkable

import discord
import sonolink
from sonolink.models import AutoPlaySettings, CacheSettings, InactivitySettings

from app.config.colors import COLOR_GREEN, COLOR_RED
from app.data.bot_data import NodeCacheEntry


@runtime_checkable
class _BotProtocol(Protocol):
    """Minimal bot interface required by BotState operations.

    Defined as a Protocol to avoid importing ``KexoBotClient`` from
    ``app.main``, which would create a cyclic import chain.
    """

    sonolink_client: sonolink.Client | None
    cached_lavalink_servers: dict[str, NodeCacheEntry] | None
    track_exceptions: (
        dict[int, tuple[sonolink.models.Playable | None, asyncio.Event]] | None
    )
    close_nodes_lock: asyncio.Lock | None
    node_is_switching: dict[int, bool] | None
    connect_node: Callable[..., Awaitable[sonolink.Node | None]] | None


@dataclass(slots=True)
class BotState:
    """Typed state operations for mutable bot runtime data.

    This class centralizes write/read operations for mutable bot state so cogs
    and helpers do not duplicate direct dictionary/list manipulation logic.
    """

    bot: _BotProtocol

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
        assert self.bot.cached_lavalink_servers is not None
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
        assert self.bot.sonolink_client is not None
        return len(
            [node for node in self.bot.sonolink_client.nodes if node.is_connected]
        )

    def get_available_nodes(self) -> int:
        """Get the number of available lavalink nodes.

        Returns the count of cached lavalink nodes.
        """
        assert self.bot.cached_lavalink_servers is not None
        return len(self.bot.cached_lavalink_servers)

    async def close_unused_nodes(self) -> None:
        """Clear unused lavalink nodes.

        This function will check if there are any lavalink nodes
        that are not being used and will close them.
        """
        assert self.bot.sonolink_client is not None
        assert self.bot.close_nodes_lock is not None
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
        assert self.bot.cached_lavalink_servers is not None, (
            "BotState requires bot.cached_lavalink_servers to be set"
        )
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
        assert self.bot.cached_lavalink_servers is not None, (
            "BotState requires bot.cached_lavalink_servers to be set"
        )
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
        assert self.bot.cached_lavalink_servers is not None, (
            "BotState requires bot.cached_lavalink_servers to be set"
        )
        node_entry = self.bot.cached_lavalink_servers.get(node_uri)
        if not node_entry:
            return None
        return node_entry["ping"]

    def set_track_exception_probe(
        self,
        guild_id: int,
        track: sonolink.models.Playable | None,
        failed_event: asyncio.Event,
    ) -> None:
        """Store temporary probe entry for node-switch validation.

        Parameters
        ----------
        guild_id: int
            Guild ID the probe belongs to.
        track: :class:`sonolink.models.Playable | None
            Track object being validated after switch.
        failed_event: :class:`asyncio.Event`
            Event set by listeners when track fails on new node.
        """
        assert self.bot.track_exceptions is not None
        self.bot.track_exceptions[guild_id] = (track, failed_event)

    def get_track_exception_probe(
        self, guild_id: int
    ) -> tuple[sonolink.models.Playable | None, asyncio.Event] | None:
        """Get stored track exception probe for guild.

        Parameters
        ----------
        guild_id: int
            Guild ID to look up.

        Returns
        -------
        tuple[sonolink.models.Playable | None, asyncio.Event] | None
            Probe tuple ``(track, event)`` if present, else ``None``.
        """
        assert self.bot.track_exceptions is not None
        return self.bot.track_exceptions.get(guild_id)

    def clear_track_exception_probe(self, guild_id: int) -> None:
        """Remove stored track exception probe for guild."""
        assert self.bot.track_exceptions is not None
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
        assert self.bot.sonolink_client is not None, (
            "BotState requires bot.sonolink_client to be set"
        )
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

    async def switch_node(
        self,
        player: sonolink.Player,
        play_after: bool = False,
        send_success_message: bool = True,
        send_failure_message: bool = True,
        search_mode: bool = False,
        search_callback: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        """Attempt to switch to a new node for audio playback or search retry.

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
        search_mode: bool
            If True, skip all playback-related logic (autoplay disable, track resume, playback probe).
            Use this when switching nodes for search retries.
        search_callback: Callable[[], Awaitable[Any]] | None
            When in search_mode, this callback is invoked up to 5 times per node to verify
            the node can successfully perform a search. If the callback times out or fails
            on all attempts for a node, the next node is tried. If all nodes are exhausted,
            returns None.
        """
        guild_id: int = cast(int, player.guild.id)  # pyright: ignore[reportAny]
        assert self.bot.node_is_switching is not None, (
            "BotState requires bot.node_is_switching to be set"
        )
        switching_map = self.bot.node_is_switching
        if switching_map.get(guild_id):
            return

        # Set switching to True for guild
        switching_map[guild_id] = True
        excluded_nodes: set[str] = set()
        _node: sonolink.Node | None = cast(sonolink.Node | None, player.node)
        if _node:
            excluded_nodes.add(_node.uri)

        original_autoplay_mode: sonolink.AutoPlayMode = player.autoplay
        if not search_mode:
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
                player._stop_inactivity_timer()  # pyright: ignore[reportPrivateUsage]
                await player.move_to(target_node)
                track = _resume_track()
                # Only when we didn't even get to play the track, moving won't play it, so we have to do it manually here.
                if play_after and track:
                    await player.play(track)

                # Check for inactivity after moving to the new node
                player._check_inactivity()  # pyright: ignore[reportPrivateUsage]
                return True
            except Exception:
                self.change_node_score(target_node.uri, -5)
                return False

        async def _try_move_and_search(target_node: sonolink.Node) -> bool:
            """Move player and test the search callback once."""
            try:
                await player.move_to(target_node)
            except Exception:
                self.change_node_score(target_node.uri, -5)
                return False

            if not search_callback:
                return True

            try:
                await asyncio.wait_for(search_callback(), timeout=5)
                return True
            except Exception:
                self.change_node_score(target_node.uri, -5)
                return False

        async def _playback_probe_failed(target_node: sonolink.Node) -> bool:
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

        assert self.bot.connect_node is not None, (
            "BotState requires bot.connect_node to be set"
        )
        try:
            for attempt in range(10):
                node: sonolink.Node | None = await self.bot.connect_node(
                    exclude_nodes=list(excluded_nodes)
                )
                excluded_nodes.add(node.uri) if node else None

                if not node:
                    continue

                if search_mode:
                    is_working = await _try_move_and_search(node)
                else:
                    is_working = await _try_move_and_resume(node)
                    if is_working and await _playback_probe_failed(node):
                        is_working = False

                if not is_working:
                    continue

                logging.info(f"[Sonolink] {attempt + 1}. Node switched ({node.uri})")
                if send_success_message:
                    embed = discord.Embed(
                        title="",
                        description=f"**:white_check_mark: Successfully connected to `{node.uri}`**",
                        color=COLOR_GREEN,
                    )
                    _success_channel: discord.abc.Messageable = cast(
                        discord.abc.Messageable, player.text_channel
                    )
                    await _success_channel.send(embed=embed)
                return

            if send_failure_message:
                embed = discord.Embed(
                    title="",
                    description=":x: Failed to find node to play requested track.",
                    color=COLOR_RED,
                )
                _failure_channel: discord.abc.Messageable = cast(
                    discord.abc.Messageable, player.text_channel
                )
                await _failure_channel.send(embed=embed)
        finally:
            if not search_mode:
                await player.update(
                    autoplay_settings=AutoPlaySettings(
                        mode=original_autoplay_mode,
                    )
                )
            switching_map[guild_id] = False
