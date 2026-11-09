import random
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from app.config.music import (
    API_RADIOGARDEN_LISTEN,
    API_RADIOGARDEN_PAGE,
    API_RADIOGARDEN_PLACES,
    API_RADIOGARDEN_SEARCH,
)
from app.music.playback import MusicPlaybackService
from app.response_handler import defer_interaction, send
from app.utils import make_http_request

if TYPE_CHECKING:
    from app.client import KexoBotClient


def _parse_radiomap_stream_url(url: str) -> str:
    channel_id = url.rstrip("/").split("/")[-1]
    return f"{API_RADIOGARDEN_LISTEN}{channel_id}/channel.mp3"


class RadioCommands(commands.Cog):
    """Commands for finding and playing RadioGarden stations."""

    def __init__(self, bot: "KexoBotClient"):
        self._bot = bot
        self._session = bot.session
        self._playback = MusicPlaybackService(bot)
        self._radiomap_cache: list[str] = []

    radio = app_commands.Group(name="radio", description="All radio commands")

    @radio.command(name="random", description="Gets random radio from RadioMap.")
    @app_commands.describe(
        play_next="If enabled, inserts the station at the top of queue.",
    )
    @app_commands.checks.cooldown(1, 4, key=lambda i: i.user.id)
    @app_commands.guild_only()
    async def radio_random(
        self, ctx: discord.Interaction, play_next: bool = False
    ) -> None:
        """Gets a random radio station from RadioMap and plays it."""
        await defer_interaction(ctx)

        place_ids = await self._get_radiomap_data()
        if not place_ids:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        place_id = random.choice(place_ids)

        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_PAGE}{place_id}/channels",
            headers={"accept": "application/json"},
        )
        if not response:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            station_id = data["data"]["content"][0]["items"][0]["page"]["url"].split(
                "/"
            )[-1]
        except (KeyError, IndexError, ValueError):
            await send(ctx, code="RADIOMAP_ERROR")
            return
        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_LISTEN}{station_id}/channel.mp3",
            headers={"accept": "application/json"},
        )
        if not response:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        response_text = response.text
        url_match = re.search(
            r'(?:href="|Redirecting to )(https?://[^"\s]+)', response_text
        )
        if not url_match:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        station = url_match.group(1).removesuffix(".")
        await self._playback.execute_play(ctx, station, play_next)

    @radio.command(name="play", description="Search and play radio from RadioGarden")
    @app_commands.describe(
        station="Radio station name to search for.",
        country="Optional country filter (exact RadioGarden country name).",
        play_next="If enabled, inserts the station at the top of queue.",
    )
    @app_commands.checks.cooldown(1, 4, key=lambda i: i.user.id)
    @app_commands.guild_only()
    async def play_radio(
        self,
        ctx: discord.Interaction,
        station: str,
        country: str = "",
        play_next: bool = False,
    ) -> None:
        """Search and play a radio station from RadioGarden."""
        encoded_station = discord.utils.escape_markdown(station)
        response = await make_http_request(
            self._session,
            f"{API_RADIOGARDEN_SEARCH}{encoded_station}",
            headers={"accept": "application/json"},
        )
        if not response:
            await send(ctx, code="RADIOMAP_ERROR")
            return

        try:
            data = response.json()
            if not data["hits"]["hits"]:
                await send(ctx, code="RADIOMAP_NO_STATION_FOUND", search=station)
                return

            for station_data in data["hits"]["hits"]:
                station_source = station_data["_source"]["page"]
                if (
                    country
                    and country.lower()
                    not in station_source["country"]["title"].lower()
                ):
                    continue
                stream_url = _parse_radiomap_stream_url(station_source["url"])
                redirect_response = await make_http_request(
                    self._session,
                    stream_url,
                )
                if not redirect_response:
                    continue
                stream_url = redirect_response.headers.get("Location", stream_url)
                if not stream_url:
                    continue

                await self._playback.execute_play(ctx, stream_url, play_next)
                return

            await send(ctx, code="RADIOMAP_NO_STATION_FOUND", search=station)
        except (KeyError, ValueError):
            await send(ctx, code="RADIOMAP_ERROR")

    async def _get_radiomap_data(self) -> list[str]:
        """Get radio map data with caching."""
        if self._radiomap_cache:
            return self._radiomap_cache

        response = await make_http_request(
            self._session,
            API_RADIOGARDEN_PLACES,
            headers={"accept": "application/json"},
        )
        if not response:
            return self._radiomap_cache

        data = response.json()
        if "data" in data and "list" in data["data"]:
            place_ids = [
                item["url"].split("/")[-1]
                for item in data["data"]["list"]
                if "url" in item
            ]
            self._radiomap_cache = place_ids
            return place_ids
        return []


async def setup(bot: "KexoBotClient") -> None:
    cog = RadioCommands(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.radio, override=True)
