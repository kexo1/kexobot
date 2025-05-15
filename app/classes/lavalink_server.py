import httpx
import wavelink

from app.constants import LAVALIST_URL, LAVAINFO_GITHUB_URL
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
    """

    def __init__(self, session: httpx.AsyncClient) -> None:
        self._session = session
        self._repeated_hostnames: list[str] = []
        self._offline_lavalink_servers: list[str] = []
        self._unwanted_servers: list[str] = [
            "lava-v4.ajieblogs.eu.org",
            "lava.inzeworld.com",
            "lavalink.jirayu.net",
        ]

    async def get_lavalink_servers(
        self, offline_lavalink_servers: list[str]
    ) -> list[wavelink.Node]:
        """Method to get lavalink servers from lavalist and lavainfo GitHub.

        Args:
        ----------
            offline_lavalink_servers (list[str]): List of offline lavalink servers.
        Returns:
            list[wavelink.Node]: List of lavalink nodes.
        """
        self._offline_lavalink_servers = offline_lavalink_servers
        lavalink_servers = []
        # Lavainfo from github
        json_data: list = await make_http_request(
            self._session, LAVAINFO_GITHUB_URL, get_json=True
        )
        lavalink_servers.extend(await self._lavainfo_github_fetch(json_data))

        # Lavalist
        json_data: list = await make_http_request(
            self._session, LAVALIST_URL, get_json=True
        )
        lavalink_servers.extend(await self._lavalist_fetch(json_data))

        # Use as a last resort
        if not lavalink_servers:
            lavalink_servers = [
                self._return_node(
                    "lavalink.kexoservers.online", "443", "kexobot", secure=True
                )
            ]

        return lavalink_servers

    async def _lavalist_fetch(self, json_data: list) -> list[wavelink.Node]:
        lavalink_servers = []

        for server in json_data:
            if (
                server["host"] in self._offline_lavalink_servers
                or server["host"] in self._repeated_hostnames
                or server["host"] in self._unwanted_servers
            ):
                continue

            if server.get("version") != "v4":
                continue

            node: wavelink.Node = self._return_node(
                server["host"],
                server["port"],
                server["password"],
                server["secure"],
            )
            lavalink_servers.append(node)

        return lavalink_servers

    async def _lavainfo_github_fetch(self, json_data: list) -> list[wavelink.Node]:
        lavalink_servers = []
        for server in json_data:
            if (
                server["host"] in self._offline_lavalink_servers
                or server["host"] in self._unwanted_servers
            ):
                continue

            if server["restVersion"] != "v4":
                continue

            node: wavelink.Node = self._return_node(
                server["host"],
                server["port"],
                server["password"],
                server["secure"],
            )
            lavalink_servers.append(node)
            self._repeated_hostnames.append(server["host"])

        return lavalink_servers

    @staticmethod
    def _return_node(
        host: str, port: int, password: str, secure: bool = False
    ) -> wavelink.Node:
        return wavelink.Node(
            uri=f"{'https://' if secure else 'http://'}{host}:{port}",
            password=password,
            retries=1,
            inactive_player_timeout=600,
        )
