import datetime
import os
from datetime import timedelta
from zoneinfo import ZoneInfo
from typing import Union

import httpx
import matplotlib.pyplot as plt
import mplcyberpunk
import numpy as np

from bs4 import BeautifulSoup
from motor.motor_asyncio import AsyncIOMotorClient
from constants import (
    SFD_SERVER_URL,
    SFD_REQUEST,
    SFD_HEADERS,
    DB_SFD_ACTIVITY,
    TIMEZONES,
)
from utils import average


plt.style.use("cyberpunk")


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
    def __init__(self, database: AsyncIOMotorClient, session: httpx.AsyncClient):
        self.session = session
        self.database = database
        self.graphs_dir = os.path.join(os.getcwd(), "graphs")
        os.makedirs(self.graphs_dir, exist_ok=True)

    async def load_sfd_servers(self) -> str:
        try:
            response = await self.session.post(
                SFD_SERVER_URL, data=SFD_REQUEST, headers=SFD_HEADERS
            )
            return response.text
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            print("SFD Servers: Request timed out")
        return []

    async def generate_graph_week(self, timezone: str):
        players, servers = await self._load_database_week()
        selected_timezone = ZoneInfo(TIMEZONES[timezone])
        now = datetime.datetime.now(selected_timezone)

        start_time = now - timedelta(hours=168)
        await self.generate_lines_and_effects(list(range(280)), players, servers)

        num_ticks = 28
        tick_positions = np.linspace(0, 280 - 1, num_ticks, dtype=int)
        tick_labels = [
            (start_time + timedelta(hours=(pos / (280 - 1)) * 168)).strftime("%a %#I%p")
            for pos in tick_positions
        ]
        plt.xticks(tick_positions, tick_labels, rotation=45)
        plt.subplots_adjust(bottom=0.1)
        plt.savefig(
            os.path.join(self.graphs_dir, f"sfd_activity_week_{timezone}.png"), dpi=300
        )
        plt.close("all")

    async def generate_graph_day(self, timezone: str):
        players, servers = await self._load_database_day()
        selected_timezone = ZoneInfo(TIMEZONES[timezone])
        now = datetime.datetime.now(selected_timezone)

        hours = [
            (now - timedelta(hours=i)).strftime("%I%p").lstrip("0")
            for i in range(23, -1, -1)
        ]

        await self.generate_lines_and_effects(list(range(240)), players, servers)

        # One time position per hour
        time_positions = [i * 10 + 5 for i in range(24)]
        plt.xticks(time_positions, hours)
        plt.savefig(
            os.path.join(self.graphs_dir, f"sfd_activity_day_{timezone}.png"), dpi=300
        )
        plt.close("all")

    @staticmethod
    async def generate_lines_and_effects(x_positions, players, servers):
        plt.figure(figsize=(14, 7))
        plt.plot(x_positions, players, color="cyan", label="Players")
        plt.plot(x_positions, servers, color="magenta", label="Servers")
        plt.legend(loc="upper center", fontsize=12, bbox_to_anchor=(0.5, 1.05), ncol=2)

        mplcyberpunk.add_glow_effects()
        mplcyberpunk.add_gradient_fill(alpha_gradientglow=0.5)
        plt.tight_layout()
        plt.grid(True)

    async def update_stats(self) -> tuple:
        players_day, servers_day = await self._load_database_day()
        current_players, current_servers = await self.get_players_and_servers()
        now = datetime.datetime.now()

        players_day.pop(0)
        servers_day.pop(0)
        players_day.append(current_players)
        servers_day.append(current_servers)

        await self.database.update_many(
            DB_SFD_ACTIVITY,
            {"$set": {"players_day": players_day, "servers_day": servers_day}},
        )

        if not (now.hour % 4 == 0 and now.minute == 0):
            return

        players_week, servers_week = await self._load_database_week()

        # Use the last 40 ticks and split them into 10 groups of 4 ticks each.
        # This means every 4 hours will have 10 ticks that were averaged from 40 ticks.
        recent_players = players_day[-40:]
        recent_servers = servers_day[-40:]

        new_players_averages = []
        new_servers_averages = []

        for group in range(10):
            start_index = group * 4
            end_index = (group + 1) * 4

            players_group = recent_players[start_index:end_index]
            servers_group = recent_servers[start_index:end_index]

            new_players_averages.append(round(average(players_group)))
            new_servers_averages.append(round(average(servers_group)))

        for _ in range(10):
            players_week.pop(0)
            servers_week.pop(0)

        players_week.extend(new_players_averages)
        servers_week.extend(new_servers_averages)

        await self.database.update_many(
            DB_SFD_ACTIVITY,
            {"$set": {"players_week": players_week, "servers_week": servers_week}},
        )

    async def _load_database_day(self) -> tuple:
        activity = await self.database.find_one(DB_SFD_ACTIVITY)
        return activity["players_day"], activity["servers_day"]

    async def _load_database_week(self) -> tuple:
        activity = await self.database.find_one(DB_SFD_ACTIVITY)
        return activity["players_week"], activity["servers_week"]

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
        return servers

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
            has_password = server_element.find("HasPassword").text == "true"
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
