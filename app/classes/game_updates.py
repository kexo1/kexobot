import datetime
import re
from typing import List, Dict, Any, Tuple, Optional

import discord
import httpx
import unidecode
from bs4 import BeautifulSoup, Tag
from deep_translator import GoogleTranslator
from motor.motor_asyncio import AsyncIOMotorClient

from app.constants import (
    DB_CACHE,
    DB_LISTS,
    ALIENWAREARENA_MAX_POSTS,
    ALIENWAREARENA_STRIP,
    ALIENWAREARENA_URL,
    GAME3RB_STRIP,
    GAME3RB_URL,
    GAME3RB_ICON,
    FANATICAL_MAX_POSTS,
    FANATICAL_URL,
    FANATICAL_IMG_URL,
    ONLINEFIX_MAX_GAMES,
    ONLINEFIX_URL,
    ONLINEFIX_ICON,
)
from app.utils import (
    make_http_request,
    strip_text,
    iso_to_timestamp,
)


class GameUpdates:
    """Class for monitoring and reporting game updates from multiple sources."""

    def __init__(
        self,
        bot_config: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        channel: discord.TextChannel,
        user_kexo: Optional[discord.User] = None,
    ) -> None:
        self.bot_config = bot_config
        self.session = session
        self.channel = channel
        self.user_kexo = user_kexo

    # AlienwareArena methods
    async def alienware_arena(self) -> None:
        """Check for updates from Alienware Arena."""
        alienwarearena_cache, to_filter = await self._load_alienware_config()
        json_data = await make_http_request(
            self.session, ALIENWAREARENA_URL, get_json=True
        )
        if not json_data:
            return
        await self._send_alienware_embed(json_data, alienwarearena_cache, to_filter)

    async def _send_alienware_embed(
        self, json_data: dict, alienwarearena_cache: list, to_filter: list
    ) -> None:
        for giveaway in json_data["data"][:ALIENWAREARENA_MAX_POSTS]:
            url = "https://eu.alienwarearena.com" + giveaway["url"]

            if url in alienwarearena_cache:
                break

            title = giveaway["title"]

            is_filtered = [k for k in to_filter if k in title.lower()]
            if is_filtered:
                continue

            for part in ALIENWAREARENA_STRIP:
                title = title.replace(part, "")

            del alienwarearena_cache[0]
            alienwarearena_cache.append(url)

            soup = BeautifulSoup(giveaway["description"], "html.parser")

            about_section = soup.find("p", string=lambda text: text and "About" in text)
            if about_section:
                result = []
                current = about_section
                while current:
                    result.append(current.get_text(strip=True))
                    current = current.find_next_sibling("p")
                description = "\n".join(result)
            else:
                strong_element = soup.find("strong")
                strong_text = strong_element.text if strong_element else ""
                description = strong_text + f"\n\n**[eu.alienwarearena.com]({url})**"

            embed = discord.Embed(
                title=title, description=description, colour=discord.Colour.dark_theme()
            )
            embed.set_image(url=giveaway["image"])
            await self.channel.send(embed=embed)

        await self.bot_config.update_one(
            DB_CACHE, {"$set": {"alienwarearena_cache": alienwarearena_cache}}
        )

    async def _load_alienware_config(self) -> Tuple[List[str], List[str]]:
        alienwarearena_cache = await self.bot_config.find_one(DB_CACHE)
        to_filter = await self.bot_config.find_one(DB_LISTS)
        return (
            alienwarearena_cache["alienwarearena_cache"],
            to_filter["alienwarearena_exceptions"],
        )

    # Game3rb methods
    async def game3rb(self) -> None:
        """Check for updates from Game3rb."""
        if not self.user_kexo:
            return

        game3rb_cache = await self.bot_config.find_one(DB_CACHE)
        game3rb_cache = game3rb_cache["game3rb_cache"]

        game_list = await self.bot_config.find_one(DB_LISTS)
        game_list = "\n".join(game_list["games"])
        source = await make_http_request(self.session, GAME3RB_URL)

        game_info = []
        to_upload = []

        if "Bad gateway" in source.text:
            print("Game3rb: Bad gateway")
            return

        soup = BeautifulSoup(source.text, "html.parser")
        article = soup.find("article")

        if not article:
            return

        for sticky in article.select("article.sticky.hentry"):
            sticky.decompose()

        for _ in range(16):
            line = article.find("a", {"title": True})

            if not line:
                break

            game_title = line.get("title")
            full_title = game_title

            game_title: list = strip_text(game_title, GAME3RB_STRIP).split()
            version = ""
            regex = re.compile(r"v\d+(\.\d+)+")

            if regex.match(game_title[-1]):
                version = f" got updated to {game_title[-1]}"
                game_title.pop()
            else:
                pattern = r"Build [\d.]+"
                match = re.search(pattern, full_title)
                if match:
                    version = f" got updated to {match.group().lower()}"
                    to_remove = version.split()[-1]
                    try:
                        game_title.pop(game_title.index(to_remove))
                    except ValueError:
                        if full_title not in game3rb_cache not in to_upload:
                            await self.bot_config.update_one(
                                DB_CACHE, {"$set": {"game3rb_cache": to_upload}}
                            )
                            await self.user_kexo.send(
                                f"Game3rb: Broken name - {full_title}"
                            )
                            to_upload.append(full_title)
                        continue

            game_title = " ".join(game_title)
            carts = []

            if game_title.lower() not in game_list.lower():
                article = article.find_next("article")
                continue

            for cart in article.find_all(id="cart"):
                if not cart:
                    break
                carts.append(cart.text)

            game_info.append(
                {
                    "title": game_title,
                    "full_title": full_title,
                    "version": version,
                    "url": line.get("href"),
                    "image": article.find("img", {"class": "entry-image"})["src"],
                    "timestamp": article.find("time")["datetime"],
                    "carts": carts,
                }
            )
            article = article.find_next("article")

        if not game_info:
            return

        for game in game_info:
            to_upload.append(game["full_title"])
            if game["full_title"] in game3rb_cache:
                continue

            description = []
            source = await make_http_request(
                self.session,
                game["url"],
            )
            if not source:
                print("Broken link - ", game["url"])
                continue
            soup = BeautifulSoup(source.text, "html.parser")

            torrent_url = soup.find("a", {"class": "torrent"})
            if torrent_url:
                description.append(f"[Torrent link]({torrent_url['href']})")
            direct_url = soup.find("a", {"class": "direct"})
            if direct_url:
                description.append(f"[Direct link]({direct_url['href']})")

            if "Fix already included" in str(
                soup
            ) or "Crack online already added" in str(soup):
                description.append("_Fix already included_")
            else:
                crack_url = soup.find("a", {"class": "online"})
                if crack_url:
                    description.append(f"[Crack link]({crack_url['href']})")
                else:
                    crack_url = soup.find("a", {"class": "crack"})
                    if crack_url:
                        description.append(f"[Crack link]({crack_url['href']})")

            game_update_url, game_update_name = [], []
            update_pattern = r'>Update (.*?)</strong>.*?<a\s+id="download-link"\s+class="update"\s+href="(.*?)"'
            for match in re.finditer(update_pattern, source.text, re.DOTALL):
                update_name = re.sub(r"<.*?>", "", match.group(1)).strip()
                game_update_name.append(unidecode.unidecode(update_name))
                game_update_url.append(unidecode.unidecode(match.group(2).strip()))

            embed = discord.Embed(
                title=game["title"] + game["version"],
                url=game["url"],
                timestamp=datetime.datetime.fromisoformat(game["timestamp"]),
            )
            embed.add_field(name="Download links:", value="\n".join(description))
            if game_update_name:
                game_update = "\n".join(
                    f"{i + 1}. [{game_update_name[i]}]({game_update_url[i]})"
                    for i in range(len(game_update_url))
                )
                embed.add_field(name="Update links:", value=game_update, inline=False)
            embed.set_footer(
                text=", ".join(game["carts"]),
                icon_url=GAME3RB_ICON,
            )
            embed.set_image(url=game["image"])
            await self.channel.send(embed=embed)

        if to_upload:
            await self.bot_config.update_one(
                DB_CACHE, {"$set": {"game3rb_cache": to_upload}}
            )

    # Fanatical methods
    async def fanatical(self) -> None:
        """Check for updates from Fanatical."""
        fanatical_cache = await self._load_fanatical_config()
        json_data = await make_http_request(self.session, FANATICAL_URL, get_json=True)
        if not json_data:
            return
        await self._send_fanatical_embed(json_data, fanatical_cache)

    async def _send_fanatical_embed(
        self, json_data: dict, fanatical_cache: list
    ) -> None:
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

    async def _load_fanatical_config(self) -> List[str]:
        fanatical_cache = await self.bot_config.find_one(DB_CACHE)
        return fanatical_cache["fanatical_cache"]

    # OnlineFix methods
    async def online_fix(self) -> None:
        """Check for updates from Online-Fix."""
        onlinefix_cache, games = await self._load_onlinefix_config()
        chat_log = await make_http_request(self.session, ONLINEFIX_URL)
        if not chat_log:
            return
        chat_messages = await self._get_onlinefix_messages(chat_log.text)
        await self._process_onlinefix_messages(chat_messages, onlinefix_cache, games)

    async def _send_onlinefix_embed(self, url: str, game_title: str) -> None:
        onlinefix_article = await make_http_request(self.session, url)
        soup = BeautifulSoup(onlinefix_article.text, "html.parser")
        head_tag = soup.find("head")

        meta_tag = head_tag.find("meta", attrs={"property": "og:image"})
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
        version: str = f" v{version_pattern[0][0]}" if version_pattern else ""

        embed = discord.Embed(
            title=game_title + version,
            url=url,
            description=description,
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(
            text="online-fix.me",
            icon_url=ONLINEFIX_ICON,
        )
        embed.set_thumbnail(url=img_url)
        await self.channel.send(embed=embed)

    async def _process_onlinefix_messages(
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
                continue

            game_title = message.find_all("a")[1].text.replace(" по сети", "")
            if game_title not in games:
                continue

            await self._send_onlinefix_embed(url, game_title)
            to_upload.append(message_id)

            limit -= 1
            if limit == 0:
                break

        if to_upload:
            await self.bot_config.update_one(
                DB_CACHE, {"$set": {"onlinefix_cache": to_upload}}
            )

    @staticmethod
    async def _get_onlinefix_messages(chat_log: str) -> list:
        soup = BeautifulSoup(chat_log, "html.parser")
        chat_element = soup.find("ul", id="lc_chat")
        if not isinstance(chat_element, Tag):
            print("OnlineFix: Chat element not found")
            return []
        return chat_element.find_all("li", class_="lc_chat_li lc_chat_li_foto")

    async def _load_onlinefix_config(self) -> Tuple[List[str], List[str]]:
        onlinefix_cache = await self.bot_config.find_one(DB_CACHE)
        games = await self.bot_config.find_one(DB_LISTS)
        # Remove quotes due to online-fix.me not using quotes
        games = "\n".join(games["games"]).replace("'", "").split("\n")
        return onlinefix_cache["onlinefix_cache"], games
