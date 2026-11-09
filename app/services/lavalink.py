from __future__ import annotations

import asyncio
import copy
import logging

import httpx
import sonolink

from app.client import KexoBotClient
from app.config.mongo import DB_CACHE
from app.utils import get_url_response_time

MAX_NODES = 2
logger = logging.getLogger(__name__)


class LavalinkNodeService:
    """Manage Lavalink node connections, cached scores, and health checks."""

    def __init__(self, bot: KexoBotClient) -> None:
        self._bot = bot

    async def connect_node(
        self,
        exclude_nodes: list[str] | None = None,
    ) -> sonolink.Node | None:
        """Connect to a cached node, preferring higher-scored candidates."""
        async with self._bot.connect_node_lock:
            node_candidates = copy.deepcopy(self._bot.cached_lavalink_servers)
            node: sonolink.Node | None = None

            for exclude_node in exclude_nodes or []:
                node_candidates.pop(exclude_node, None)

            is_connected = False
            prioritized_nodes = sorted(
                node_candidates.items(),
                key=lambda item: item[1]["score"],
                reverse=True,
            )[:MAX_NODES]

            for node_uri, node_info in prioritized_nodes:
                existing_node = next(
                    (
                        candidate
                        for candidate in self._bot.sonolink_client.nodes
                        if candidate.uri == node_uri
                    ),
                    None,
                )

                if existing_node is not None and existing_node.is_connected:
                    node = existing_node
                    is_connected = True
                else:
                    if existing_node is not None:
                        await self._bot.state.close_and_remove_node(existing_node)

                    node = self._bot.state.build_node(
                        node_uri,
                        node_info["password"],
                    )
                    is_connected = await self._bot.state.node_attempt_connection(node)
                    if not is_connected:
                        await self._bot.state.close_and_remove_node(node)

                if is_connected:
                    break

            await self.upload_cached_servers()

            if not is_connected:
                logger.critical("[Lavalink] No lavalink servers available.")
                return None

            if node is None:
                logger.error("[Lavalink] Connection succeeded without selecting a node.")
                return None

        self._bot.node = node
        return node

    async def upload_cached_servers(self) -> None:
        """Persist the cached Lavalink server scores and ping data."""
        await self._bot.config_manager.save("lavalink_servers", DB_CACHE)

    async def test_all_node_pings(self, session: httpx.AsyncClient) -> None:
        """Refresh cached node ping measurements and persist the results."""
        uris = list(self._bot.cached_lavalink_servers)

        async def ping_one(uri: str) -> None:
            ping = await get_url_response_time(session, uri)
            self._bot.state.change_node_ping(uri, ping)

        await asyncio.gather(*(ping_one(uri) for uri in uris))
        await self.upload_cached_servers()
        logger.info("[Lavalink] Daily ping test completed and saved to database.")
