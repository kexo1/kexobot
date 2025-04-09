import discord
import httpx

from motor.motor_asyncio import AsyncIOMotorClient
from bs4 import BeautifulSoup
from constants import (
    DB_CACHE,
    DB_LISTS,
    ALIENWAREARENA_MAX_POSTS,
    ALIENWAREARENA_STRIP,
    ALIENWAREARENA_URL,
)


class AlienwareArena:
    def __init__(
        self,
        database: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        channel: discord.TextChannel,
    ) -> None:
        self.database = database
        self.session = session
        self.channel = channel

    async def run(self) -> None:
        alienwarearena_cache, to_filter = await self._load_database()

        try:
            json_data = await self.session.get(ALIENWAREARENA_URL)
        except httpx.ReadTimeout:
            print("AlienwareArena: Timeout")
            return

        await self._send_embed(json_data.json(), alienwarearena_cache, to_filter)

    async def _send_embed(
        self, json_data: dict, alienwarearena_cache: list, to_filter: list
    ) -> None:
        for giveaway in json_data["data"][:ALIENWAREARENA_MAX_POSTS]:
            url = "https://eu.alienwarearena.com" + giveaway["url"]

            if url in alienwarearena_cache:
                break

            title = giveaway["title"].lower()

            is_filtered = [k for k in to_filter if k in title]
            if is_filtered:
                continue

            for part in ALIENWAREARENA_STRIP:
                title = title.replace(part, "")

            del alienwarearena_cache[0]
            alienwarearena_cache.append(url)

            soup = BeautifulSoup(giveaway["description"], "html.parser")
            strong_element = soup.find("strong")
            strong_text = strong_element.text if strong_element else ""
            description = strong_text + f"\n\n**[eu.alienwarearena.com]({url})**"

            embed = discord.Embed(
                title=title, description=description, colour=discord.Colour.dark_theme()
            )
            embed.set_image(url=giveaway["image"])
            await self.channel.send(embed=embed)

        await self.database.update_one(
            DB_CACHE, {"$set": {"alienwarearena_cache": alienwarearena_cache}}
        )

    async def _load_database(self) -> tuple:
        alienwarearena_cache = await self.database.find_one(DB_CACHE)
        to_filter = await self.database.find_one(DB_LISTS)
        return alienwarearena_cache["alienwarearena_cache"], to_filter[
            "alienwarearena_exceptions"
        ]
