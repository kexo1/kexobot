from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

import sonolink

if TYPE_CHECKING:
    from app.main import KexoBotClient

from app.utils import node_health_check


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
        """
        node_entry = self.bot.cached_lavalink_servers.get(node_uri)
        if not node_entry:
            return
        node_entry["score"] += delta

    async def ensure_bot_node_ready(self) -> sonolink.Node | None:
        """Best-effort guard against stale node sessions.

        This does not clear ``bot.node``. If the current node looks unhealthy, we try to
        connect to a different one (excluding the current URI). If that fails, we keep
        the existing node reference and return it.
        """
        node: sonolink.Node | None = getattr(self.bot, "node", None)
        if node is None:
            return await self.bot.connect_node()

        if node.is_connected:
            if await node_health_check(node):
                return node

        logging.warning("[Sonolink] Node health check failed (%s)", node.uri)

        new_node = await self.bot.connect_node(exclude_nodes=[node.uri])
        return new_node

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
            if not await node_health_check(node):
                logging.info(
                    f"[Sonolink] Node failed health check when attempting to connect: ({node.uri})"
                )
                return False
            return True

        except Exception:
            logging.info(f"[Sonolink] Node failed to connect: ({node.uri})")

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

    def clear_joke_caches(self) -> None:
        """Clear all in-memory joke caches in-place."""
        self.bot.loaded_jokes.clear()
        self.bot.loaded_dad_jokes.clear()
        self.bot.loaded_yo_mama_jokes.clear()

    def cache_track_requester(self, track_encoded: str, name: str, avatar: str) -> None:
        """Cache requester metadata by encoded track ID.

        Parameters
        ----------
        track_encoded: str
            Encoded track ID used as cache key.
        name: str
            Requesting user's display name.
        avatar: str
            Requesting user's avatar URL. May be empty string.
        """
        self.bot.track_requesters[track_encoded] = {"name": name, "avatar": avatar}

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

    def reset_temp_guild_data(self, factory: Callable[[], dict[str, Any]]) -> None:
        """Reset temporary guild data for all guilds.

        Parameters
        ----------
        factory: Callable[[], dict[str, Any]]
            Factory function that returns default temp guild data.
        """
        for guild_id in self.bot.temp_guild_data:
            self.bot.temp_guild_data[guild_id] = factory()

    def clear_stale_temp_reddit_data(
        self,
        *,
        is_older_than_fn: Callable[[int, datetime], bool],
        stale_hours: int = 5,
    ) -> None:
        """Clear stale temporary reddit user data.

        Parameters
        ----------
        is_older_than_fn: Callable[[int, datetime], bool]
            Function used to check data age.
        stale_hours: int, optional
            Number of hours after which temp data is reset.
        """
        for user_data in self.bot.temp_user_data.values():
            reddit_data = user_data["reddit"]
            last_used = reddit_data["last_used"]
            if not last_used:
                continue
            if is_older_than_fn(stale_hours, last_used):
                reddit_data["last_used"] = None
                reddit_data["viewed_posts"] = set()
                reddit_data["search_limit"] = 3
