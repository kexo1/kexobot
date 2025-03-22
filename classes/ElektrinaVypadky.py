import discord
import logging
import datetime

from bs4 import BeautifulSoup
from constants import ELEKTRINA_MAX_ARTICLES, DB_CACHE


class ElektrinaVypadky:
    def __init__(self, session, database, user_kexo):
        self.session = session
        self.database = database
        self.user_kexo = user_kexo

    async def run(self) -> None:
        elektrinavypadky_cache = await self._load_database()
        html_content = await self.session.get(
            "https://www.hliniknadhronom.sk/mid/492460/ma0/all/.html"
        )
        articles = await self._get_articles(html_content.text)
        if articles:
            await self._process_articles(articles, elektrinavypadky_cache)

    @staticmethod
    async def _get_articles(html_content: list) -> None:
        soup = BeautifulSoup(html_content, "html.parser")
        collumn = soup.find(
            class_="oznamy-new-columns-all-list-default oznamy-new-columns-all-list"
        )
        # If site is unreachable
        if not collumn:
            logging.error("ElektrinaVypadky: Site is unreachable")
            return None
        articles = collumn.find_all(
            "div", class_="short-text-envelope-default short-text-envelope"
        )
        return articles[:ELEKTRINA_MAX_ARTICLES]

    async def _process_articles(
        self, articles: list, elektrinavypadky_cache: list
    ) -> None:
        above_limit = False
        for article in articles:
            description = article.find("div").text.lower()
            title = article.find("a")["aria-label"]

            if not (
                "elektriny" in description
                or "elektriny" in title.lower()
                or "odstávka vody" in title.lower()
            ):
                continue

            url = f"https://www.hliniknadhronom.sk{article.find("a")["href"]}"

            if url in elektrinavypadky_cache:
                return

            elektrinavypadky_cache = [
                elektrinavypadky_cache[-1]
            ] + elektrinavypadky_cache[:-1]
            elektrinavypadky_cache[0] = url

            article_content = await self.session.get(url)
            soup = BeautifulSoup(article_content.text, "html.parser")
            description = soup.find(class_="ci-full").text

            if len(description) > 2048:
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description="Under embed (amount of text in embed is restricted",
                )
                above_limit = True
            else:
                embed = discord.Embed(title=title, url=url, description=description)

            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            embed.set_footer(
                text="",
                icon_url="https://www.hliniknadhronom.sk/portals_pictures/i_006868/i_6868718.png",
            )
            await self.user_kexo.send(embed=embed)

            if above_limit:
                await self.user_kexo.send(description)
        await self.database.update_one(
            DB_CACHE, {"$set": {"elektrinavypadky_cache": elektrinavypadky_cache}}
        )

    async def _load_database(self) -> list:
        elektrinavypadky_cache = await self.database.find_one(DB_CACHE)
        return elektrinavypadky_cache["elektrinavypadky_cache"]
