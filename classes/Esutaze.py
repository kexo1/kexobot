import discord
import datetime

from io import BytesIO

import httpx
from bs4 import BeautifulSoup, Tag
from constants import DB_CACHE, DB_LISTS


class Esutaze:
    def __init__(self, session, database, channel):
        self.session = session
        self.database = database
        self.channel = channel

    async def run(self) -> None:
        to_filter, esutaze_cache = await self._load_database()
        esutaze_cache_upload = esutaze_cache
        articles = await self._get_articles()

        if not articles:
            return

        for article in articles:
            header = article.find("header")
            a_tag = header.find("a")
            url = a_tag.get("href")

            if url in esutaze_cache:
                return  # If first url is already in cache, all the rest are too

            title = a_tag.get("title")
            is_filtered = [k for k in to_filter if k.lower() in title]
            if is_filtered:
                continue

            esutaze_cache_upload = [esutaze_cache_upload[-1]] + esutaze_cache_upload[:-1]
            esutaze_cache_upload[0] = url
            await self._send_article(url, title)

        await self.database.update_one(
            DB_CACHE, {"$set": {"esutaze_cache": esutaze_cache_upload}}
        )

    async def _send_article(self, url: str, title: str) -> None:
        article_content = await self.session.get(url)
        soup = BeautifulSoup(article_content.text, "html.parser")
        article_body = soup.find("div", class_="thecontent")

        if not isinstance(article_body, Tag):
            return

        article_description = article_body.find_all("p")
        contest_description = article_description[0].text
        contest_requirements = article_description[2].text

        contest_ending_time_tag = article_body.find("h4")
        contest_ending_time: str = (
            contest_ending_time_tag.text if contest_ending_time_tag else ""
        )

        img_tag = article_body.find("img")
        if not isinstance(img_tag, Tag):
            print("Esutaze: Image tag not found")
            return

        img_url = img_tag.get("src")
        image_response = await self.session.get(img_url)
        image = BytesIO(image_response.content)

        embed = discord.Embed(
            title=title,
            url=url,
            description=f"{contest_description}\n\n"
            f"{contest_requirements}\n\n"
            f"**{contest_ending_time}**",
            colour=discord.Colour.brand_red(),
        )
        embed.set_image(url="attachment://image.png")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        embed.set_footer(
            text="www.esutaze.sk",
            icon_url="https://www.esutaze.sk/wp-content/uploads/2014/07/esutaze-logo2.jpg",
        )
        await self.channel.send(embed=embed, file=discord.File(image, "image.png"))

    async def _get_articles(self) -> list:
        try:
            html_content = await self.session.get(
                "https://www.esutaze.sk/category/internetove-sutaze/"
            )
        except httpx.ReadTimeout:
            print("Esutaze: ReadTimeout")
            return []

        soup = BeautifulSoup(html_content.text, "html.parser")
        content_box = soup.find("div", id="content_box")

        if not isinstance(content_box, Tag):
            print(f"Esutaze: Expected a Tag but got {type(content_box)}")
            return []

        return content_box.find_all("article")

    async def _load_database(self) -> tuple:
        to_filter = await self.database.find_one(DB_LISTS)
        esutaze_cache = await self.database.find_one(DB_CACHE)
        return to_filter["esutaze_exceptions"], esutaze_cache["esutaze_cache"]
