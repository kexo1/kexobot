import httpx
import matplotlib.pyplot as plt
import matplotlib as mpl
import mplcyberpunk
import datetime

from bs4 import BeautifulSoup
from typing import Union
from datetime import timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from constants import SFD_SERVER_URL, SFD_REQUEST, SFD_HEADERS, DB_SFD_ACTIVITY

plt.style.use("cyberpunk")
mpl.rcParams["font.family"] = "DejaVu Sans"
plt.rc("font", family="DejaVu Sans")


class Server:
    def __init__(
            self,
            address_ipv4,
            port,
            server_name,
            game_mode,
            map_name,
            players,
            max_players,
            bots,
            has_password,
            description,
            version,
    ):
        self.address_ipv4 = address_ipv4
        self.port = port
        self.server_name = server_name
        self.game_mode = game_mode
        self.map_name = map_name
        self.players = players
        self.max_players = max_players
        self.bots = bots
        self.has_password = has_password
        self.description = description
        self.version = version

    def __repr__(self) -> str:
        return f"Server({self.server_name}, {self.map_name}, {self.players}, {self.max_players}, {self.bots})"

    async def get_full_server_info(self):
        return self

    async def get_game_mode(self) -> str:
        game_modes = {1: "Versus", 2: "Custom", 3: "Campaign", 4: "Survival"}
        return game_modes.get(self.game_mode, "Unknown")


class SFDServers:
    def __init__(self, session: httpx.AsyncClient, database: AsyncIOMotorClient):
        self.session = session
        self.database = database

    class GraphTypes:
        Day = "Day"
        Week = "Week"

    async def load_sfd_servers(self) -> str:
        try:
            response = await self.session.post(
                SFD_SERVER_URL, data=SFD_REQUEST, headers=SFD_HEADERS
            )
            return response.text
        except httpx.ReadTimeout:
            print("SFD Servers: Request timed out")
        return []

    async def generate_activity_graph(self, graph_type: str):
        if graph_type == self.GraphTypes.Day:
            await self.generate_graph_daily()
            return
        await self.generate_graph_week()

    async def generate_graph_week(self):
        players, servers = await self._fetch_stats()
        now = datetime.datetime.now()

        # Define the starting time for the graph (1 week ago).
        start_time = now - timedelta(hours=168)
        group_size = 4
        total_groups = len(players) // group_size   # e.g. 1680 // 4 = 420

        # Aggregate each group by averaging.
        avg_players = []
        avg_servers = []
        for i in range(total_groups):
            start_index = i * group_size
            end_index = (i + 1) * group_size

            average_players = sum(players[start_index:end_index]) / group_size
            avg_players.append(average_players)

            average_servers = sum(servers[start_index:end_index]) / group_size
            avg_servers.append(average_servers)

        # Define tick positions on the aggregated data. For example, every 10 points.
        time_positions = [i * 10 for i in range((total_groups // 10) + 1)]
        # Calculate tick labels mapping each tick position to a time between start_time and now.
        tick_labels = [
            (start_time + timedelta(hours=(pos / (total_groups - 1)) * 168)).strftime("%a %#I%p")
            for pos in time_positions
        ]

        x_positions = list(range(total_groups))
        await self.generate_lines(x_positions, avg_players, avg_servers)

        plt.xticks(time_positions, tick_labels, rotation=45)
        max_value = int(max(max(avg_players), max(avg_servers)))
        plt.yticks(range(0, max_value + 1))

        plt.tight_layout()
        plt.savefig("sfd_activity_week.png", dpi=300)

    async def generate_graph_daily(self):
        players, servers = await self._fetch_stats()
        now = datetime.datetime.now()

        hours = [
            (now - timedelta(hours=i)).strftime("%I%p").lstrip("0")
            for i in range(23, -1, -1)
        ]
        x_positions = list(range(240))
        players = players[-240:]
        servers = servers[-240:]

        await self.generate_lines(x_positions, players, servers)

        # Set x-tick positions: One tick per hour
        time_positions = [i * 10 + 5 for i in range(24)]
        plt.xticks(time_positions, hours)

        max_value = int(max(max(players), max(servers)))
        plt.yticks(range(0, max_value + 1))

        plt.tight_layout()
        plt.savefig("sfd_activity_day.png", dpi=300)

    @staticmethod
    async def generate_lines(x_positions, players, servers):
        plt.figure(figsize=(14, 7))
        plt.plot(x_positions, players, color="cyan", label="Players")
        plt.plot(x_positions, servers, color="magenta", label="Servers")
        plt.legend(loc="upper center", fontsize=12, bbox_to_anchor=(0.5, 1.05), ncol=2)

        mplcyberpunk.add_glow_effects()
        mplcyberpunk.add_gradient_fill(alpha_gradientglow=0.5)
        plt.grid(True)

    async def _fetch_stats(self) -> tuple:
        players, servers = await self._load_database()
        current_players, current_servers = await self.get_players_and_servers()

        players.pop(0)
        servers.pop(0)
        players.append(current_players)
        servers.append(current_servers)

        await self.database.update_many(DB_SFD_ACTIVITY, {"$set": {"players": players, "servers": servers}})
        return players, servers

    async def _load_database(self) -> tuple:
        activity = await self.database.find_one(DB_SFD_ACTIVITY)
        return activity["players"], activity["servers"]

    async def get_players_and_servers(self) -> tuple:
        servers = await self._parse_servers(None)
        players = 0
        for server in servers:
            players += server.players
        return players, len(servers)

    async def get_servers_info(self) -> tuple:
        servers = await self._parse_servers(None)
        servers_dict = {"server_name": [], "maps": [], "players": []}
        all_players = 0

        for server in servers:
            servers_dict["server_name"].append(server.server_name)
            servers_dict["maps"].append(server.map_name)
            if server.bots == 0:
                players = f"{server.players}/{server.max_players}"
            else:
                players = f"{server.players}(+{server.bots})/{server.max_players}"
            servers_dict["players"].append(players)
            all_players += server.players

        return servers_dict, all_players

    async def get_servers(self) -> list:
        servers = await self._parse_servers(None)
        return [server for server in servers]

    async def get_server(self, search: str) -> Server:
        return await self._parse_servers(search)

    async def _parse_servers(self, search: str) -> Union[list, Server]:
        response = await self.load_sfd_servers()
        if not response:
            return []

        soup = BeautifulSoup(response, "xml")
        servers_element = soup.find("GetGameServersResult").find("Servers")

        servers = []
        if not servers_element:
            return []

        all_servers = servers_element.find_all("SFDGameServer")
        for server_element in all_servers:
            if int(server_element.find("VersionNr").text) == 0:
                continue  # Skip servers with version 0

            server_name = (
                server_element.find("GameName").text
                if server_element.find("GameName")
                else None
            )

            address_ipv4 = (
                server_element.find("AddressIPv4").text
                if server_element.find("AddressIPv4")
                else None
            )
            port = (
                int(server_element.find("Port").text)
                if server_element.find("Port")
                else 0
            )

            game_mode = (
                int(server_element.find("GameMode").text)
                if server_element.find("GameMode")
                else 0
            )
            map_name = (
                server_element.find("MapName").text
                if server_element.find("MapName")
                else None
            )
            players = (
                int(server_element.find("Players").text)
                if server_element.find("Players")
                else 0
            )
            max_players = (
                int(server_element.find("MaxPlayers").text)
                if server_element.find("MaxPlayers")
                else 0
            )
            bots = (
                int(server_element.find("Bots").text)
                if server_element.find("Bots")
                else 0
            )
            has_password = (
                True
                if server_element.find("HasPassword").text == "true"
                else False
            )
            description = (
                server_element.find("Description").text
                if server_element.find("Description")
                else None
            )
            version = (
                server_element.find("Version").text
                if server_element.find("Version")
                else None
            )

            server = Server(
                address_ipv4,
                port,
                server_name,
                game_mode,
                map_name,
                players,
                max_players,
                bots,
                has_password,
                description,
                version,
            )

            if search and search.lower() in server_name.lower():
                return server

            servers.append(server)

        if search:
            return None
        return servers
