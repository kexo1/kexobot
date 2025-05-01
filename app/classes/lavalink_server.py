import httpx
import wavelink

from app.constants import LAVALIST_URL, LAVAINFO_GITHUB_URL
from app.utils import make_http_request


class LavalinkServerManager:
    def __init__(self, session: httpx.AsyncClient) -> None:
        self.session = session
        self.repeated_hostnames: list[str] = []
        self.low_quality_nodes: list[str] = ["lavalink-v2.pericsq.ro"]
        self.offline_lavalink_servers: list[str] = []

    async def get_lavalink_servers(
        self, offline_lavalink_servers: list[str]
    ) -> list[wavelink.Node]:
        self.offline_lavalink_servers = offline_lavalink_servers
        lavalink_servers = []
        # Lavainfo from github
        json_data: list = await make_http_request(
            self.session, LAVAINFO_GITHUB_URL, retries=2, get_json=True
        )
        if json_data:
            lavalink_servers.extend(await self._lavainfo_github_fetch(json_data))

        # Lavalist
        json_data: list = await make_http_request(
            self.session, LAVALIST_URL, retries=2, get_json=True
        )
        if json_data:
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
                server["host"] in self.offline_lavalink_servers
                or server["host"] in self.repeated_hostnames
                or server["host"] in self.low_quality_nodes
            ):
                continue

            if server.get("version") != "v4":
                continue

            node: wavelink.Node = self._return_node(
                server["host"],
                server["port"],
                server["password"],
                True if server["secure"] else False,
            )
            lavalink_servers.append(node)

        return lavalink_servers

    async def _lavainfo_github_fetch(self, json_data: list) -> list[wavelink.Node]:
        lavalink_servers = []
        for server in json_data:
            if (
                server["host"] in self.offline_lavalink_servers
                or server["host"] in self.low_quality_nodes
            ):
                continue

            if server["restVersion"] != "v4":
                continue

            node: wavelink.Node = self._return_node(
                server["host"],
                server["port"],
                server["password"],
                True if server["secure"] else False,
            )
            lavalink_servers.append(node)
            self.repeated_hostnames.append(server["host"])

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
