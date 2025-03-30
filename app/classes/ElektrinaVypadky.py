import discord
import httpx

from bs4 import BeautifulSoup
from constants import ELEKTRINA_MAX_ARTICLES, DB_CACHE
from utils import iso_to_timestamp


class ElektrinaVypadky:
    def __init__(self, session, database, user_kexo):
        self.session = session
        self.database = database
        self.user_kexo = user_kexo

    async def run(self) -> None:
        elektrinavypadky_cache = await self._load_database()
        try:
            html_content = await self.session.get(
                "https://www.hliniknadhronom.sk/get_rss.php?id=1_atom_1947"
            )
        except httpx.ReadTimeout:
            print("ElektrinaVypadky: Timeout")
            return

        articles = await self._get_articles(html_content.text)
        if articles:
            await self._process_articles(articles, elektrinavypadky_cache)
            return
        print("ElektrinaVypadky: No articles found")

    @staticmethod
    async def _get_articles(html_content: str) -> list:
        soup = BeautifulSoup(html_content, "xml")

        articles = soup.find_all("entry")
        return articles[:ELEKTRINA_MAX_ARTICLES]

    async def _process_articles(
        self, articles: list, elektrinavypadky_cache: list
    ) -> None:
        elektrinavypadky_cache_upload = elektrinavypadky_cache
        above_limit = False

        for article in articles:
            description = article.find("content").text
            url = article.find("link")["href"]
            if url in elektrinavypadky_cache:
                continue

            title = article.find("title").text

            if not (
                "elektrin" in description
                or "elektrin" in title.lower()
                or "odstávka vody" in title.lower()
            ):
                continue

            elektrinavypadky_cache_upload = [
                elektrinavypadky_cache_upload[-1]
            ] + elektrinavypadky_cache_upload[:-1]
            elektrinavypadky_cache_upload[0] = url

            iso_time = article.find("published").text
            timestamp = iso_to_timestamp(iso_time)

            if len(description) > 2048:
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description="Under embed (amount of text in embed is restricted",
                    timestamp=timestamp,
                )
                above_limit = True
            else:
                embed = discord.Embed(
                    title=title, url=url, description=description, timestamp=timestamp
                )

            embed.set_footer(
                text="",
                icon_url="https://www.hliniknadhronom.sk/portals_pictures/i_006868/i_6868718.png",
            )
            await self.user_kexo.send(embed=embed)

            if above_limit:
                await self.user_kexo.send(description)
        await self.database.update_one(
            DB_CACHE,
            {"$set": {"elektrinavypadky_cache": elektrinavypadky_cache_upload}},
        )

    async def _load_database(self) -> list:
        elektrinavypadky_cache = await self.database.find_one(DB_CACHE)
        return elektrinavypadky_cache["elektrinavypadky_cache"]
