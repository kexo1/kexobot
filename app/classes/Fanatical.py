import discord
import httpx

from motor.motor_asyncio import AsyncIOMotorClient
from constants import DB_CACHE, FANATICAL_MAX_POSTS, FANATICAL_URL, FANATICAL_IMG_URL
from utils import iso_to_timestamp


class Fanatical:
    def __init__(self, database: AsyncIOMotorClient, session: httpx.AsyncClient, channel: discord.TextChannel) -> None:
        self.database = database
        self.session = session
        self.channel = channel

    async def run(self) -> None:
        fanatical_cache = await self._load_database()

        try:
            json_data = await self.session.get(FANATICAL_URL)
        except httpx.ReadTimeout:
            print("Fanatical: Timeout")
            return

        await self._send_embed(json_data.json(), fanatical_cache)

    async def _send_embed(self, json_data: dict, fanatical_cache: list) -> None:
        for giveaway in json_data["freeProducts"][:FANATICAL_MAX_POSTS]:
            if giveaway["min_spend"]["EUR"] != 0:
                continue  # Skip if not free

            product_info = giveaway["required_products"][0]
            url = "https://www.fanatical.com/en/game/" + product_info["slug"]

            if url in fanatical_cache:
                break

            fanatical_cache.pop(0)
            fanatical_cache.append(url)

            title = product_info["name"]
            img_url = FANATICAL_IMG_URL + product_info["cover"]
            timestamp = (
                f"<t:{int(iso_to_timestamp(giveaway['valid_until']).timestamp())}:F>"
            )

            embed = discord.Embed(
                title=title,
                description=f"Get the key before {timestamp}\n\n**[www.fanatical.com]({url})**",
                colour=discord.Colour.dark_theme(),
                timestamp=iso_to_timestamp(giveaway["valid_from"]),
            )
            embed.set_image(url=img_url)
            await self.channel.send(embed=embed)

        await self.database.update_one(
            DB_CACHE, {"$set": {"fanatical_cache": fanatical_cache}}
        )

    async def _load_database(self) -> list:
        fanatical_cache = await self.database.find_one(DB_CACHE)
        return fanatical_cache["fanatical_cache"]
