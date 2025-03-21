import httpx
from constants import LAVALIST_URL, LAVAINFO_API_URLS


class LavalinkFetch:
    def __init__(self, bot, session: httpx.AsyncClient):
        self.bot = bot
        self.session = session

    async def get_lavalink_servers(self) -> None:
        try:
            await self.session.get(LAVAINFO_API_URLS[0], timeout=10)
            lavalink_servers = await self._lavainfo_fetch()
        except httpx.TimeoutException:
            print(f"The request to {url} timed out, trying lavalist.")
            lavalink_servers = await self._lavalist_fetch()

        return lavalink_servers

    async def _lavalist_fetch(self) -> None:
        lavalink_servers = []
        json_data = await self.session.get(url, timeout=30)
        json_data = json_data.json()

        for server in json_data:
            if server.get("version	") != "v4":
                continue

            lavalink_servers.append({"ip": f"http://{server["host"]}:{server["port"]}",
                                     "password": server["password"]})
        return lavalink_servers

    async def _lavainfo_fetch(self) -> None:
        lavalink_servers = []
        for url in LAVAINFO_API_URLS:
            json_data = await self.session.get(url, timeout=30)
            json_data = json_data.json()

            for server in json_data:
                if server.get("isConnected") is False:
                    continue

                if server.get("restVersion") != "v4":
                    continue

                connections = server.get("connections").split("/")
                # If noone is connected, skip
                if int(connections[0]) == 0:
                    continue
                # If full, skip
                if int(connections[0]) == int(connections[1]):
                    continue

                if not server.get("info")["plugins"]:
                    continue

                for plugin in server.get("info")["plugins"]:
                    if plugin.get("name") == "youtube-plugin" or plugin.get("name") == "lavasrc-plugin":
                        lavalink_servers.append({"ip": f"http://{server["host"]}:{server["port"]}",
                                                 "password": server["password"]})

        return lavalink_servers
