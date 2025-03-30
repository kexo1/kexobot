import discord
import httpx

from constants import DB_CACHE, FANATICAL_MAX_POSTS
from utils import iso_to_timestamp


class Fanatical:
    def __init__(self, database, session, channel):
        self.database = database
        self.session = session
        self.channel = channel

    async def run(self) -> None:
        fanatical_cache = await self._load_database()

        try:
            json_data = await self.session.get(
                "https://www.fanatical.com/api/all-promotions/en"
            )
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
                continue

            fanatical_cache = [fanatical_cache[-1]] + fanatical_cache[:-1]
            fanatical_cache[0] = url

            title = product_info["name"]
            img_url = (
                "https://cdn-ext.fanatical.com/production/product/1280x720/"
                + product_info["cover"]
            )
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
