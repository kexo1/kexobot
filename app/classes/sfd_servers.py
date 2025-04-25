import datetime
import os
from datetime import timedelta
from typing import Union, cast
from zoneinfo import ZoneInfo

import httpx
import matplotlib.pyplot as plt
import mplcyberpunk
from bs4 import BeautifulSoup
from motor.motor_asyncio import AsyncIOMotorClient

from app.constants import (
    SFD_SERVER_URL,
    SFD_REQUEST,
    SFD_HEADERS,
    DB_SFD_ACTIVITY,
    TIMEZONES,
)
from app.utils import average, is_older_than, make_http_request

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

    def get_full_server_info(self):
        return self

    def get_game_mode(self) -> str:
        game_modes = {1: "Versus", 2: "Custom", 3: "Campaign", 4: "Survival"}
        return game_modes.get(self.game_mode, "Unknown")


class SFDServers:
    def __init__(self, bot_config: AsyncIOMotorClient, session: httpx.AsyncClient):
        self.session = session
        self.bot_config = bot_config
        self.graphs_dir = os.path.join(os.getcwd(), "graphs")
        os.makedirs(self.graphs_dir, exist_ok=True)

    async def generate_graph_day(self, timezone: str):
        activity = await self._load_sfd_activity_data()
        players, servers = activity["players_day"], activity["servers_day"]

        selected_timezone = ZoneInfo(TIMEZONES[timezone])
        now = datetime.datetime.now(selected_timezone)

        hours = [
            (now - timedelta(hours=i)).strftime("%I%p").lstrip("0")
            for i in range(23, -1, -1)
        ]

        self._generate_lines_and_effects(list(range(240)), players, servers)

        # One time position per hour
        time_positions = [i * 10 + 5 for i in range(24)]
        plt.xticks(time_positions, hours)
        plt.savefig(
            os.path.join(self.graphs_dir, f"sfd_activity_day_{timezone}.png"), dpi=300
        )
        plt.close("all")

    async def generate_graph_week(self, timezone: str):
        activity = await self._load_sfd_activity_data()
        players, servers = activity["players_week"], activity["servers_week"]
        selected_timezone = ZoneInfo(TIMEZONES[timezone])

        now = datetime.datetime.now(selected_timezone)
        hours_since_six = now.hour % 6
        minutes = now.minute
        seconds = now.second

        last_update = now - timedelta(
            hours=hours_since_six,
            minutes=minutes,
            seconds=seconds,
        )

        hours = []
        # Generate 28 labels (one for each 6-hour period, going backwards)
        for i in range(27, -1, -1):
            time = last_update - timedelta(hours=i * 6)
            day_str = time.strftime("%a")
            hour = int(time.strftime("%I"))
            ampm = time.strftime("%p")
            hours.append(f"{day_str} {hour}{ampm}")

        self._generate_lines_and_effects(list(range(280)), players, servers)

        time_positions = [i * 10 + 5 for i in range(28)]
        plt.xticks(time_positions, hours, rotation=45)
        plt.subplots_adjust(bottom=0.2)
        plt.savefig(
            os.path.join(self.graphs_dir, f"sfd_activity_week_{timezone}.png"),
            dpi=300,
            bbox_inches="tight",
        )
        plt.close("all")

    async def update_stats(self, now) -> None:
        activity = await self._load_sfd_activity_data()
        players_day, servers_day = activity["players_day"], activity["servers_day"]
        current_players, current_servers = await self._get_players_and_servers()

        players_day.pop(0)
        servers_day.pop(0)
        players_day.append(current_players)
        servers_day.append(current_servers)

        # Update daily stats
        await self.bot_config.update_many(
            DB_SFD_ACTIVITY,
            {
                "$set": {
                    "players_day": players_day,
                    "servers_day": servers_day,
                }
            },
        )

        last_update_week = activity["last_update_week"]
        # Convert last_update_week to the same timezone as now
        if last_update_week.tzinfo is None:
            last_update_week = last_update_week.replace(tzinfo=now.tzinfo)
        elif last_update_week.tzinfo != now.tzinfo:
            last_update_week = last_update_week.astimezone(now.tzinfo)

        if not is_older_than(6, last_update_week):
            return

        time_diff = now - last_update_week
        hours_diff = time_diff.total_seconds() / 3600
        update_count = min(4, max(1, int(hours_diff // 6)))
        print(f"Updating weekly stats: {update_count} updates")
        print(now)
        players_week, servers_week = activity["players_week"], activity["servers_week"]

        recent_players = players_day[-60 * update_count :]
        recent_servers = servers_day[-60 * update_count :]

        new_players_averages = []
        new_servers_averages = []

        for group in range(10 * update_count):
            start_index = group * 6
            end_index = (group + 1) * 6

            players_group = recent_players[start_index:end_index]
            servers_group = recent_servers[start_index:end_index]

            new_players_averages.append(round(average(players_group)))
            new_servers_averages.append(round(average(servers_group)))

        for _ in range(10 * update_count):
            players_week.pop(0)
            servers_week.pop(0)

        players_week.extend(new_players_averages)
        servers_week.extend(new_servers_averages)

        # Round the current time to the nearest 6-hour mark
        current_hour = now.hour
        rounded_hour = (current_hour // 6) * 6
        next_update = now.replace(hour=rounded_hour, minute=0, second=0, microsecond=0)

        # Ensure next_update is in the correct timezone
        if next_update.tzinfo is None:
            next_update = next_update.replace(tzinfo=ZoneInfo("Europe/Bratislava"))

        await self.bot_config.update_many(
            DB_SFD_ACTIVITY,
            {
                "$set": {
                    "players_week": players_week,
                    "servers_week": servers_week,
                    "last_update_week": next_update,
                }
            },
        )

    async def get_servers_info(self) -> tuple:
        servers: list[Server] = cast(list[Server], await self._parse_servers())
        servers_dict: dict = {"server_name": [], "maps": [], "players": []}
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

    async def get_servers(self) -> list[Server]:
        servers: list[Server] = await self._parse_servers()
        return servers

    async def get_server(self, search: str) -> Server:
        return await self._parse_servers(search)

    async def _load_sfd_servers(self) -> str:
        response = await make_http_request(
            self.session, SFD_SERVER_URL, data=SFD_REQUEST, headers=SFD_HEADERS
        )
        if not response:
            return ""
        return response.text

    async def _get_players_and_servers(self) -> tuple:
        servers = await self._parse_servers()
        players = 0
        for server in servers:
            players += server.players
        return players, len(servers)

    async def _load_sfd_activity_data(self) -> dict:
        return await self.bot_config.find_one(DB_SFD_ACTIVITY)

    async def _parse_servers(
        self, search: str = None
    ) -> Union[list[Server], Server, None]:
        response = await self._load_sfd_servers()
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

            servers.append(server)

        if search:
            filtered_servers = [
                s
                for s in servers
                if s.server_name and search.lower() in s.server_name.lower()
            ]
            return filtered_servers

        return servers

    @staticmethod
    def _generate_lines_and_effects(x_positions, players, servers):
        plt.switch_backend("Agg")
        plt.figure(figsize=(14, 7))
        plt.plot(x_positions, players, color="cyan", label="Players")
        plt.plot(x_positions, servers, color="magenta", label="Servers")
        plt.legend(loc="upper center", fontsize=12, bbox_to_anchor=(0.5, 1.05), ncol=2)

        mplcyberpunk.add_glow_effects()
        mplcyberpunk.add_gradient_fill(alpha_gradientglow=0.5)
        plt.tight_layout()
        plt.grid(True)
