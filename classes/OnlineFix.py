import re
import discord
import datetime
import httpx

from deep_translator import GoogleTranslator  # type: ignore
from bs4 import BeautifulSoup, Tag
from httpx import Response
from constants import ONLINEFIX_MAX_GAMES, DB_CACHE, DB_LISTS


class OnlineFix:
    def __init__(self, session, database, channel):
        self.session = session
        self.database = database
        self.channel = channel

    async def run(self) -> None:
        onlinefix_cache, games = await self._load_database()
        try:
            chat_log = await self.session.get("https://online-fix.me/chat.php")
        except httpx.ReadTimeout:
            print("OnlineFix: Read timeout")
            return

        chat_messages = await self._get_messages(chat_log.text)
        await self._process_messages(chat_messages, onlinefix_cache, games)

    async def _send_embed(self, url: str, game_title: str) -> None:
        onlinefix_article = await self.session.get(url)
        soup = BeautifulSoup(onlinefix_article.text, "html.parser")
        head_tag = soup.find("head")
        if not isinstance(head_tag, Tag):
            print("OnlineFix: Image tag not found")
            return

        meta_tag = head_tag.find("meta", attrs={"property": "og:image"})
        if not isinstance(meta_tag, Tag):
            print("OnlineFix: Image tag not found")
            return

        img_url = meta_tag.get("content")
        article_description = soup.find("article")
        if not isinstance(article_description, Tag):
            print("OnlineFix: Article tag not found")
            return

        description_element = article_description.find(
            "div", class_="edited-block right"
        )
        description: str = description_element.text if description_element else ""
        description = GoogleTranslator(source="ru").translate(text=description)
        description = description.replace(". ", "\n")

        pattern = re.compile(r"version\s*(\d+(\.\d+)*)")
        version_pattern = pattern.findall(description)
        version: str = f" v{version_pattern[0][0]}" if version else ""

        embed = discord.Embed(
            title=game_title + version,
            url=url,
            description=description,
            color=discord.Color.blue(),
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        embed.set_footer(
            text="online-fix.me",
            icon_url="https://media.discordapp.net/attachments/796453724713123870"
            "/1035951759505506364/favicon-1.png",
        )
        embed.set_thumbnail(url=img_url)
        await self.channel.send(embed=embed)

    async def _process_messages(
        self, messages: list, onlinefix_cache: list, games: list
    ) -> None:
        limit = ONLINEFIX_MAX_GAMES
        to_upload = []
        for message in messages:
            message_text = message.find("div", class_="lc_chat_li_text")
            message_id = message_text.get("id")
            message_text = message_text.text

            if "@0xdeadc0de обновил: " not in message_text:
                continue

            url = message.find_all("a")[1].get("href")

            if message_id in onlinefix_cache:
                return

            game_title = message.find_all("a")[1].text.replace(" по сети", "")
            if game_title not in games:
                continue

            await self._send_embed(url, game_title)
            to_upload.append(message_id)

            limit -= 1
            if limit == 0:
                break

        if to_upload:
            await self.database.update_one(
                DB_CACHE, {"$set": {"onlinefix_cache": to_upload}}
            )

    @staticmethod
    async def _get_messages(chat_log: str) -> list:
        soup = BeautifulSoup(chat_log, "html.parser")
        chat_element = soup.find("ul", id="lc_chat")
        if not isinstance(chat_element, Tag):
            print("OnlineFix: Chat element not found")
            return []
        return chat_element.find_all("li", class_="lc_chat_li lc_chat_li_foto")

    async def _load_database(self) -> tuple:
        onlinefix_cache = await self.database.find_one(DB_CACHE)
        games = await self.database.find_one(DB_LISTS)
        # Remove quotes due to online-fix.me not using quotes
        games = "\n".join(games["games"]).replace("’", "").split("\n")
        return onlinefix_cache["onlinefix_cache"], games
