import copy

import discord
import httpx
import wavelink

from app.constants import LAVALIST_URL, LAVAINFO_GITHUB_URL, DB_CACHE
from app.utils import make_http_request


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

    async def fetch(self):
        """Method to get new lavalink servers from lavalist and lavainfo GitHub.

        Returns
        -------
        list[wavelink.Node]
            List of lavalink nodes.
        """
        # Lavainfo from github
        json_data: list = await make_http_request(
            self._session, LAVAINFO_GITHUB_URL, get_json=True
        )
        if json_data:
            self._parse_lavalink_servers(json_data, "lavainfo")

        # Lavalist
        json_data: list = await make_http_request(
            self._session, LAVALIST_URL, get_json=True
        )
        if json_data:
            self._parse_lavalink_servers(json_data, "lavalist")

        if self._cached_lavalink_servers != self._cached_lavalink_servers_copy:
            await self._bot.bot_config.update_one(
                DB_CACHE, {"$set": {"lavalink_servers": self._cached_lavalink_servers}}
            )
            self._cached_lavalink_servers_copy = copy.deepcopy(
                self._cached_lavalink_servers
            )
            print("Found new lavalink servers, updating cache.")

    def _parse_lavalink_servers(
        self, json_data: list, site: str
    ) -> list[wavelink.Node]:
        for server in json_data:
            if site == "lavalist" and server.get("version") != "v4":
                continue
            if site == "lavainfo" and server.get("restVersion") != "v4":
                continue

            uri = self._get_full_node_url(
                server["host"], server["port"], server.get("secure", False)
            )
            if uri in self._cached_lavalink_servers_copy:
                continue

            self._cached_lavalink_servers[uri] = {
                "password": server["password"],
                "score": 0,
            }

    @staticmethod
    def _get_full_node_url(host: str, port: int, secure: bool = False) -> dict:
        """Helper method to get the full node URI."""
        return f"{'https://' if secure else 'http://'}{host}:{port}"
