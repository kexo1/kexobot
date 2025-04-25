import discord
import httpx

from motor.motor_asyncio import AsyncIOMotorClient
from app.constants import DB_CACHE, FANATICAL_MAX_POSTS, FANATICAL_URL, FANATICAL_IMG_URL
from app.utils import iso_to_timestamp, make_http_request


class Fanatical:
    def __init__(
        self,
        bot_config: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        channel: discord.TextChannel,
    ) -> None:
        self.bot_config = bot_config
        self.session = session
        self.channel = channel

    async def run(self) -> None:
        fanatical_cache = await self._load_bot_config()
        json_data = await make_http_request(
            self.session, FANATICAL_URL, get_json=True)
        if not json_data:
            return
        await self._send_embed(json_data, fanatical_cache)

    async def _send_embed(self, json_data: dict, fanatical_cache: list) -> None:
        for giveaway in json_data["freeProducts"][:FANATICAL_MAX_POSTS]:
            if giveaway["min_spend"]["EUR"] != 0:
                continue  # Skip if not free

            product_info = giveaway["required_products"][0]
            url = "https://www.fanatical.com/en/game/" + product_info["slug"]

            if url in fanatical_cache:
                break

            del fanatical_cache[0]
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

        await self.bot_config.update_one(
            DB_CACHE, {"$set": {"fanatical_cache": fanatical_cache}}
        )

    async def _load_bot_config(self) -> list:
        fanatical_cache = await self.bot_config.find_one(DB_CACHE)
        return fanatical_cache["fanatical_cache"]
