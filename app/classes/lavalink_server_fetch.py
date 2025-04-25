import httpx
import wavelink

from app.constants import LAVALIST_URL, LAVAINFO_URLS, LAVAINFO_GITHUB_URL
from app.utils import make_http_request


class LavalinkServerFetch:
    def __init__(self, session: httpx.AsyncClient) -> None:
        self.session = session
        self.repeated_hostnames: list[str] = []
        self.low_quality_nodes: list[str] = ["lavalink-v2.pericsq.ro"]

    async def get_lavalink_servers(self) -> list[wavelink.Node]:
        lavalink_servers = []
        # To remove, site doesn't seem to be alive anymore
        for url in LAVAINFO_URLS:
            json_data: list = await make_http_request(
                self.session, url, retries=2, get_json=True
            )
            if not json_data:
                continue
            lavalink_servers.extend(await self._lavainfo_fetch(json_data))

        if not lavalink_servers:
            json_data: list = await make_http_request(
                self.session, LAVAINFO_GITHUB_URL, retries=2, get_json=True
            )
            if json_data:
                lavalink_servers.extend(await self._lavainfo_github_fetch(json_data))

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
                server["host"] in self.repeated_hostnames
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

    async def _lavainfo_fetch(self, json_data: list) -> list[wavelink.Node]:
        lavalink_servers = []

        for server in json_data:
            if "error" in server:
                print("Error in lavainfo response: ", json_data.get("error"))
                return []

            if server["host"] in self.low_quality_nodes:
                continue

            if server["isConnected"] is False:
                continue

            if server["restVersion"] != "v4":
                continue

            connections = server["connections"].split("/")
            # If noone is connected, skip
            if int(connections[0]) == 0:
                continue
            # If full, skip
            if int(connections[0]) == int(connections[1]):
                continue

            if not server.get("info")["plugins"]:
                continue

            for plugin in server["info"]["plugins"]:
                if (
                    plugin["name"] == "youtube-plugin"
                    or plugin["name"] == "lavasrc-plugin"
                ):
                    node: wavelink.Node = self._return_node(
                        server["host"],
                        server["port"],
                        server["password"],
                        True if server["secure"] else False,
                    )
                    lavalink_servers.append(node)
                    self.repeated_hostnames.append(server["host"])
                    break

        return lavalink_servers

    async def _lavainfo_github_fetch(self, json_data: list) -> list[wavelink.Node]:
        lavalink_servers = []

        for server in json_data:
            if server["host"] in self.low_quality_nodes:
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
