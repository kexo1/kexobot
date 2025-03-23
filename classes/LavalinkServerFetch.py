import httpx
from discord.ext import tasks
from constants import LAVALIST_URL, LAVAINFO_API_URLS


class LavalinkServerFetch:
    def __init__(self, bot, session: httpx.AsyncClient):
        self.bot = bot
        self.session = session
        self.repeated_hostnames: list[str] = []

    async def get_lavalink_servers(self) -> list:
        lavalink_servers = []
        import json

        try:
            for url in LAVAINFO_API_URLS:
                json_data = await self.session.get(url, timeout=10)
                lavalink_servers += await self._lavainfo_fetch(json_data.json())
        except httpx.TimeoutException:
            print(f"The request to {LAVAINFO_API_URLS[0]} timed out.")
        except json.decoder.JSONDecodeError:
            print(f"Failed to decode JSON from {LAVAINFO_API_URLS[0]}")

        try:
            json_data = await self.session.get(LAVALIST_URL, timeout=10)
            lavalink_servers += await self._lavalist_fetch(json_data.json())
        except httpx.TimeoutException:
            print(f"The request to {LAVALIST_URL} timed out.")
        except json.decoder.JSONDecodeError:
            print(f"Failed to decode JSON from {LAVALIST_URL}")

        return lavalink_servers

    async def _lavalist_fetch(self, json_data: list) -> list:
        lavalink_servers = []

        for server in json_data:
            if server["host"] in self.repeated_hostnames:
                continue

            if server.get("version") != "v4":
                continue

            lavalink_servers.append(
                {
                    "ip": f"http://{server['host']}:{server['port']}",
                    "password": server["password"],
                }
            )
        return lavalink_servers

    async def _lavainfo_fetch(self, json_data: list) -> list:
        lavalink_servers = []

        for server in json_data:
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
                    lavalink_servers.append(
                        {
                            "ip": f"http://{server['host']}:{server['port']}",
                            "password": server["password"],
                        }
                    )
                    break

        self.repeated_hostnames = [server["host"] for server in json_data]
        return lavalink_servers
