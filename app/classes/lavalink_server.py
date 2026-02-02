import copy
import logging

import discord
import httpx

from app.constants import API_LAVALIST, DB_CACHE, RAW_LAVALINK
from app.utils import make_http_request


def get_full_node_url(host: str, port: int, secure: bool = False) -> str:
    """Construct a full Lavalink node URL."""
    protocol = "https" if secure else "http"
    return f"{protocol}://{host}:{port}"


class LavalinkServerManager:
    """Class to manage lavalink servers. Checks from various sources and returns
    a list of lavalink servers.

    It also checks if the server is online or offline and if it is a low quality node.
    The class is used to get lavalink servers from lavalist and lavainfo GitHub.

    Parameters
    ----------
    session: :class:`httpx.AsyncClient`
        HTTP client for making requests.
    offline_lavalink_servers: list[str]
        List of offline lavalink servers.
    """

    def __init__(self, bot: discord.Bot, session: httpx.AsyncClient) -> None:
        self._bot = bot
        self._session = session
        self._cached_lavalink_servers = self._bot.cached_lavalink_servers
        self._cached_lavalink_servers_copy = copy.deepcopy(
            self._cached_lavalink_servers
        )
        self._fresh_nodes: list[str] = []

    async def fetch(self) -> None:
        """Get new Lavalink servers from Lavainfo GitHub and Lavalist."""
        # Lavainfo from github
        json_data: list = await make_http_request(
            self._session, RAW_LAVALINK, get_json=True
        )
        if json_data:
            self._parse_lavalink_servers(json_data)

        # Lavalist
        json_data: list = await make_http_request(
            self._session, API_LAVALIST, get_json=True
        )
        if json_data:
            self._parse_lavalink_servers(json_data)

        self._clear_removed_nodes()

        if self._cached_lavalink_servers != self._cached_lavalink_servers_copy:
            await self._bot.bot_config.update_one(
                DB_CACHE,
                {"$set": {"lavalink_servers": self._cached_lavalink_servers}},
            )
            self._cached_lavalink_servers_copy = copy.deepcopy(
                self._cached_lavalink_servers
            )
            logging.info(
                "[Lavalink] Lavalink servers list got updated, updating cache."
            )

    def _parse_lavalink_servers(self, json_data: list) -> None:
        for server in json_data:
            if (
                (server.get("restVersion") not in (None, "v4"))
                or (server.get("version") not in (None, "v4"))
                or not server.get("host")
            ):
                continue

            uri = get_full_node_url(
                server["host"], server["port"], server.get("secure", False)
            )
            self._fresh_nodes.append(uri)

            if uri in self._cached_lavalink_servers_copy:
                continue

            self._cached_lavalink_servers[uri] = {
                "password": server["password"],
                "score": 0,
            }

    def _clear_removed_nodes(self) -> None:
        """Method to clear old nodes from the cached lavalink servers."""
        fresh_set = set(self._fresh_nodes)
        for uri in list(self._cached_lavalink_servers.keys()):
            if uri not in fresh_set:
                del self._cached_lavalink_servers[uri]
