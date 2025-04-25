import datetime
from io import BytesIO

import discord
import httpx
from bs4 import BeautifulSoup, Tag
from motor.motor_asyncio import AsyncIOMotorClient

from app.constants import ESUTAZE_URL, ESUTAZE_ICON, DB_CACHE, DB_LISTS
from app.utils import make_http_request


class Esutaze:
    def __init__(
        self,
        bot_config: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        channel: discord.TextChannel,
    ) -> None:
        self.session = session
        self.bot_config = bot_config
        self.channel = channel

    async def run(self) -> None:
        to_filter, esutaze_cache = await self._load_bot_config()
        esutaze_cache_upload = esutaze_cache.copy()
        articles = await self._get_articles()

        if not articles:
            return

        for article in articles:
            url = article.find("link").text

            if url in esutaze_cache:
                break

            title = article.find("title").text
            is_filtered = [k for k in to_filter if k.lower() in title]
            if is_filtered:
                continue

            del esutaze_cache_upload[0]
            esutaze_cache_upload.append(url)

            await self._send_article(article)

        await self.bot_config.update_one(
            DB_CACHE, {"$set": {"esutaze_cache": esutaze_cache_upload}}
        )

    async def _send_article(self, article) -> None:
        title = article.find("title").text
        url = article.find("link").text
        contest_description = article.find("description")
        contest_description = (
            BeautifulSoup(contest_description.text, "html.parser").find("p").text
        )
        unix_time = article.find("pubDate").text
        timestamp = datetime.datetime.strptime(unix_time, "%a, %d %b %Y %H:%M:%S %z")

        article_content = article.find("content:encoded").text
        soup = BeautifulSoup(article_content, "html.parser")
        contest_ending_time = soup.find("h4").text.strip()

        img_tag = soup.find("img")
        if not isinstance(img_tag, Tag):
            print("Esutaze: Image tag not found")
            return

        img_url = img_tag.get("src")
        image_response = await make_http_request(self.session, img_url, binary=True)
        image = BytesIO(image_response.content)

        embed = discord.Embed(
            title=title,
            url=url,
            description=f"{contest_description}\n\n**{contest_ending_time}**",
            colour=discord.Colour.brand_red(),
            timestamp=timestamp,
        )
        embed.set_image(url="attachment://image.png")
        embed.set_footer(
            text="www.esutaze.sk",
            icon_url=ESUTAZE_ICON,
        )
        await self.channel.send(embed=embed, file=discord.File(image, "image.png"))

    async def _get_articles(self) -> list:
        html_content = await make_http_request(self.session, ESUTAZE_URL)
        if not html_content:
            return []

        soup = BeautifulSoup(html_content.content, "xml")
        return soup.find_all("item")

    async def _load_bot_config(self) -> tuple:
        to_filter = await self.bot_config.find_one(DB_LISTS)
        esutaze_cache = await self.bot_config.find_one(DB_CACHE)
        return to_filter["esutaze_exceptions"], esutaze_cache["esutaze_cache"]
