import datetime
import re
from io import BytesIO
from typing import List, Tuple

import discord
import httpx
import unidecode
from bs4 import BeautifulSoup, Tag
from deep_translator import GoogleTranslator
from pymongo import AsyncMongoClient

from app.constants import (
    DB_CACHE,
    DB_LISTS,
    ALIENWAREARENA_MAX_POSTS,
    ALIENWAREARENA_STRIP,
    ALIENWAREARENA_URL,
    ALIENWAREARENA_NEWS_URL,
    ALIENWAREARENA_ICON,
    GAME3RB_STRIP,
    GAME3RB_URL,
    GAME3RB_ICON,
    FANATICAL_MAX_POSTS,
    FANATICAL_API_URL,
    FANATICAL_API_MEGAMENU_URL,
    FANATICAL_IMG_URL,
    FANATICAL_STRIP,
    ONLINEFIX_MAX_GAMES,
    ONLINEFIX_URL,
    ONLINEFIX_ICON,
    POWER_OUTAGES_URL,
    POWER_OUTAGES_MAX_ARTICLES,
    POWER_OUTAGES_ICON,
    ESUTAZE_URL,
    ESUTAZE_ICON,
)
from app.utils import (
    make_http_request,
    strip_text,
    iso_to_timestamp,
)


class ContentMonitor:
    """Class for monitoring and reporting various
    content updates including games, contests, and power outages.

    Parameters
    ----------
    bot_config: :class:`AsyncMongoClient`
        MongoDB client for database operations.
    session: :class:`httpx.AsyncClient`
        HTTP client for making requests.
    game_updates_channel: :class:`discord.TextChannel`
        Discord channel for game updates.
    esutaze_channel: :class:`discord.TextChannel`
        Discord channel for contests.
    alienware_arena_news_channel: :class:`discord.TextChannel`
        Discord channel for Alienware Arena news.
    user_kexo: :class:`discord.User`
        Discord user for sending messages.
    """

    def __init__(
        self,
        bot_config: AsyncMongoClient,
        session: httpx.AsyncClient,
        game_updates_channel: discord.TextChannel,
        free_stuff_channel: discord.TextChannel,
        esutaze_channel: discord.TextChannel,
        alienware_arena_news_channel: discord.TextChannel,
        user_kexo: discord.User = None,
    ) -> None:
        self._bot_config = bot_config
        self._session = session
        self._game_updates_channel = game_updates_channel
        self._free_stuff_channel = free_stuff_channel
        self._esutaze_channel = esutaze_channel
        self._alienware_arena_news_channel = alienware_arena_news_channel
        self._user_kexo = user_kexo

    async def alienware_arena(self) -> None:
        """Checks for free games from Alienware Arena."""
        alienwarearena_cache, to_filter = await self._load_alienware_cache()
        json_data = await make_http_request(
            self._session, ALIENWAREARENA_URL, get_json=True
        )
        if not json_data:
            return
        await self._send_alienware_arena_embed(
            json_data, alienwarearena_cache, to_filter
        )

    async def alienware_arena_news(self) -> None:
        """Checks for news from Alienware Arena."""
        alienwarearena_news_cache = await self._load_alienware_news_cache()
        response = await make_http_request(
            self._session,
            ALIENWAREARENA_NEWS_URL,
        )
        if not response:
            return
        await self._send_alienware_arena_news_embed(
            response, alienwarearena_news_cache
        )

    async def game3rb(self) -> None:
        """Check for selected games from Game3rb."""
        game3rb_cache = await self._bot_config.find_one(DB_CACHE)
        game3rb_cache = game3rb_cache["game3rb_cache"]

        game_list = await self._bot_config.find_one(DB_LISTS)
        game_list = "\n".join(game_list["games"])
        source = await make_http_request(self._session, GAME3RB_URL)
        if not source:
            return

        game_info = []
        to_upload = []

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
            regex = re.compile(r"v\d+(\.\d+)*")

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
                            await self._bot_config.update_one(
                                DB_CACHE,
                                {"$set": {"game3rb_cache": to_upload}},
                            )
                            await self._user_kexo.send(
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
                    "image": article.find("img", {"class": "entry-image"})[
                        "src"
                    ],
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
                self._session,
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
                        description.append(
                            f"[Crack link]({crack_url['href']})"
                        )

            game_update_url, game_update_name = [], []
            update_pattern = (
                r">Update (.*?)</strong>.*?<a\s+"
                r'id="download-link"\s+class="update"\s+href="(.*?)"'
            )
            for match in re.finditer(update_pattern, source.text, re.DOTALL):
                update_name = re.sub(r"<.*?>", "", match.group(1)).strip()
                game_update_name.append(unidecode.unidecode(update_name))
                game_update_url.append(
                    unidecode.unidecode(match.group(2).strip())
                )

            embed = discord.Embed(
                title=game["title"] + game["version"],
                url=game["url"],
                timestamp=datetime.datetime.fromisoformat(game["timestamp"]),
            )
            embed.add_field(
                name="Download links:", value="\n".join(description)
            )
            if game_update_name:
                game_update = "\n".join(
                    f"{i + 1}. [{game_update_name[i]}]({game_update_url[i]})"
                    for i in range(len(game_update_url))
                )
                embed.add_field(
                    name="Update links:", value=game_update, inline=False
                )
            embed.set_footer(
                text=", ".join(game["carts"]),
                icon_url=GAME3RB_ICON,
            )
            embed.set_image(url=game["image"])
            await self._game_updates_channel.send(embed=embed)

        if to_upload:
            await self._bot_config.update_one(
                DB_CACHE, {"$set": {"game3rb_cache": to_upload}}
            )

    async def fanatical(self) -> None:
        """Checks for free games from Fanatical."""
        fanatical_cache = await self._load_fanatical_cache()
        json_data = await make_http_request(
            self._session, FANATICAL_API_URL, get_json=True
        )
        if not json_data:
            return
        await self._send_fanatical_embed(json_data, fanatical_cache)

    async def online_fix(self) -> None:
        """Checks for selected games from Online-Fix."""
        onlinefix_cache, games = await self._load_onlinefix_cache()
        chat_log = await make_http_request(self._session, ONLINEFIX_URL)
        if not chat_log:
            return
        chat_messages = await self._get_onlinefix_messages(chat_log.text)
        await self._process_onlinefix_messages(
            chat_messages, onlinefix_cache, games
        )

    async def power_outages(self) -> None:
        """Checks for power outages."""
        elektrinavypadky_cache = await self._load_power_outages_cache()
        html_content = await make_http_request(
            self._session, POWER_OUTAGES_URL
        )
        if not html_content:
            return

        articles = self._get_power_outage_articles(html_content.text)
        await self._process_power_outage_articles(
            articles, elektrinavypadky_cache
        )

    async def contests(self) -> None:
        """Checks for contests."""
        to_filter, esutaze_cache = await self._load_contests_cache()
        esutaze_cache_copy = esutaze_cache.copy()
        articles = await self._get_contest_articles()

        if not articles:
            return

        for article in articles:
            url = article.find("link").text

            if url in esutaze_cache_copy:
                break

            title = article.find("title").text
            is_filtered = [k for k in to_filter if k.lower() in title]
            if is_filtered:
                continue

            del esutaze_cache[0]
            esutaze_cache.append(url)

            await self._send_contest_article(article)

        if esutaze_cache != esutaze_cache_copy:
            await self._bot_config.update_one(
                DB_CACHE, {"$set": {"esutaze_cache": esutaze_cache}}
            )

    async def _send_alienware_arena_embed(
        self, json_data: dict, alienwarearena_cache: list, to_filter: list
    ) -> None:
        alienwarearena_cache_copy = alienwarearena_cache.copy()
        for giveaway in json_data["data"][:ALIENWAREARENA_MAX_POSTS]:
            url = "https://eu.alienwarearena.com" + giveaway["url"]

            if url in alienwarearena_cache_copy:
                break

            title = giveaway["title"]

            is_filtered = [k for k in to_filter if k.lower() in title.lower()]
            if is_filtered:
                continue

            title = strip_text(title, ALIENWAREARENA_STRIP)

            del alienwarearena_cache[0]
            alienwarearena_cache.append(url)

            soup = BeautifulSoup(giveaway["description"], "html.parser")
            description = ""
            if soup:
                paragraphs = soup.find_all("p")
                description = paragraphs[1].get_text(strip=True)

            embed = discord.Embed(
                title=title,
                description=description,
                colour=discord.Colour.dark_theme(),
                url=url,
            )
            embed.set_image(url=giveaway["image"])
            await self._free_stuff_channel.send(embed=embed)

        if alienwarearena_cache != alienwarearena_cache_copy:
            await self._bot_config.update_one(
                DB_CACHE,
                {"$set": {"alienwarearena_cache": alienwarearena_cache}},
            )

    async def _send_alienware_arena_news_embed(
        self, response: httpx.Response, alienware_arena_news_cache: list
    ) -> None:
        soup = BeautifulSoup(response.text, "html.parser")
        news_widget = soup.find(
            "div", class_="widget-table announcements-table"
        )
        if not news_widget:
            print("Alienware Arena: News widget not found")
            return

        alienware_arena_news_cache_copy = alienware_arena_news_cache.copy()
        for post in news_widget.find_all("div", class_="widget-table-row"):
            post_info = post.find("a", class_="link relay-announcement-wrap")
            url = post_info["href"]
            if url in alienware_arena_news_cache_copy:
                break

            del alienware_arena_news_cache[0]
            alienware_arena_news_cache.append(url)

            title = post_info.text
            post_date = post.find("span", class_="timeago").get("title")
            post_date = datetime.datetime.strptime(
                post_date, "%Y-%m-%d %H:%M:%S"
            )

            embed = discord.Embed(
                title=title,
                description=f"**[eu.alienwarearena.com](https://eu.alienwarearena.com{url})**",
                colour=discord.Colour.dark_theme(),
                timestamp=post_date,
                thumbnail=ALIENWAREARENA_ICON,
            )
            await self._alienware_arena_news_channel.send(embed=embed)

        if alienware_arena_news_cache != alienware_arena_news_cache_copy:
            await self._bot_config.update_one(
                DB_CACHE,
                {
                    "$set": {
                        "alienwarearena_news_cache": alienware_arena_news_cache
                    }
                },
            )

    async def _send_fanatical_embed(
        self, json_data: dict, fanatical_cache: list
    ) -> None:
        fanatical_cache_copy = fanatical_cache.copy()
        for giveaway in json_data["freeProducts"][:FANATICAL_MAX_POSTS]:
            if giveaway["min_spend"]["EUR"] != 0:
                continue  # Skip if not free

            product_info = giveaway["required_products"][0]
            url = "https://www.fanatical.com/en/game/" + product_info["slug"]

            # Check if product is preorder
            product_data: dict = await make_http_request(
                self._session,
                FANATICAL_API_MEGAMENU_URL,
                headers={"referer": url},
                get_json=True,
            )

            if not product_data:
                print("Fanatical: Product data not found")
                continue

            title = product_info["name"]
            title_strip = strip_text(title, FANATICAL_STRIP)

            is_preorder = False
            for unreleased_game in product_data["comingSoon"]:
                if title_strip in unreleased_game["name"]:
                    is_preorder = True
                    break

            if url in fanatical_cache_copy:
                break

            del fanatical_cache[0]
            fanatical_cache.append(url)

            if is_preorder:
                continue

            img_url = FANATICAL_IMG_URL + product_info["cover"]
            timestamp = f"<t:{int(iso_to_timestamp(giveaway['valid_until']).timestamp())}:F>"

            embed = discord.Embed(
                title=title,
                description=f"Get the key before {timestamp}\n\n**[www.fanatical.com]({url})**",
                colour=discord.Colour.dark_theme(),
                timestamp=iso_to_timestamp(giveaway["valid_from"]),
            )
            embed.set_image(url=img_url)
            await self._game_updates_channel.send(embed=embed)

        if fanatical_cache != fanatical_cache_copy:
            await self._bot_config.update_one(
                DB_CACHE, {"$set": {"fanatical_cache": fanatical_cache}}
            )

    async def _send_onlinefix_embed(self, url: str, game_title: str) -> None:
        onlinefix_article = await make_http_request(self._session, url)
        if not onlinefix_article:
            return
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
        description: str = (
            description_element.text if description_element else ""
        )
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
        await self._game_updates_channel.send(embed=embed)

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

            game_title = message.find_all("a")[1].text.replace(" по сети", "")
            if game_title not in games:
                continue

            to_upload.append(message_id)
            if message_id in onlinefix_cache:
                break

            await self._send_onlinefix_embed(url, game_title)

            limit -= 1
            if limit == 0:
                break

        if to_upload:
            await self._bot_config.update_one(
                DB_CACHE, {"$set": {"onlinefix_cache": to_upload}}
            )

    async def _process_power_outage_articles(
        self, articles: list, elektrinavypadky_cache: list
    ) -> None:
        elektrinavypadky_cache_copy = elektrinavypadky_cache.copy()
        above_limit = False

        for article in articles:
            description = article.find("content").text
            url = article.find("link")["href"]
            if url in elektrinavypadky_cache_copy:
                break

            title = article.find("title").text

            if not (
                "elektri" in description.lower()
                or "elektri" in title.lower()
                or "odstávka vody" in title.lower()
            ):
                continue

            del elektrinavypadky_cache[0]
            elektrinavypadky_cache.append(url)

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
                    title=title,
                    url=url,
                    description=description,
                    timestamp=timestamp,
                )

            embed.set_footer(
                text="",
                icon_url=POWER_OUTAGES_ICON,
            )
            await self._user_kexo.send(embed=embed)

            if above_limit:
                await self._user_kexo.send(description)

        if elektrinavypadky_cache != elektrinavypadky_cache_copy:
            await self._bot_config.update_one(
                DB_CACHE,
                {"$set": {"elektrinavypadky_cache": elektrinavypadky_cache}},
            )

    async def _send_contest_article(self, article) -> None:
        title = article.find("title").text
        url = article.find("link").text
        contest_description = article.find("description")
        contest_description = (
            BeautifulSoup(contest_description.text, "html.parser")
            .find("p")
            .text
        )
        unix_time = article.find("pubDate").text
        timestamp = datetime.datetime.strptime(
            unix_time, "%a, %d %b %Y %H:%M:%S %z"
        )

        article_content = article.find("content:encoded").text
        soup = BeautifulSoup(article_content, "html.parser")
        contest_ending_time = soup.find("h4").text.strip()

        img_tag = soup.find("img")
        if not isinstance(img_tag, Tag):
            print("Esutaze: Image tag not found")
            return

        img_url = img_tag.get("src")
        image_response = await make_http_request(
            self._session, img_url, binary=True
        )
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
        await self._esutaze_channel.send(
            embed=embed, file=discord.File(image, "image.png")
        )

    async def _get_contest_articles(self) -> list:
        html_content = await make_http_request(self._session, ESUTAZE_URL)
        if not html_content:
            return []

        soup = BeautifulSoup(html_content.content, "xml")
        return soup.find_all("item")

    @staticmethod
    async def _get_onlinefix_messages(chat_log: str) -> list:
        soup = BeautifulSoup(chat_log, "html.parser")
        chat_element = soup.find("ul", id="lc_chat")
        if not isinstance(chat_element, Tag):
            print("OnlineFix: Chat element not found")
            return []
        return chat_element.find_all("li", class_="lc_chat_li lc_chat_li_foto")

    @staticmethod
    def _get_power_outage_articles(html_content: str) -> list:
        soup = BeautifulSoup(html_content, "xml")
        articles = soup.find_all("entry")
        return articles[:POWER_OUTAGES_MAX_ARTICLES]

    async def _load_alienware_cache(self) -> Tuple[List[str], List[str]]:
        alienwarearena_cache = await self._bot_config.find_one(DB_CACHE)
        to_filter = await self._bot_config.find_one(DB_LISTS)
        return (
            alienwarearena_cache["alienwarearena_cache"],
            to_filter["alienwarearena_exceptions"],
        )

    async def _load_fanatical_cache(self) -> List[str]:
        fanatical_cache = await self._bot_config.find_one(DB_CACHE)
        return fanatical_cache["fanatical_cache"]

    async def _load_alienware_news_cache(self) -> List[str]:
        alienwarearena_news_cache = await self._bot_config.find_one(DB_CACHE)
        return alienwarearena_news_cache["alienwarearena_news_cache"]

    async def _load_onlinefix_cache(self) -> Tuple[List[str], List[str]]:
        onlinefix_cache = await self._bot_config.find_one(DB_CACHE)
        games = await self._bot_config.find_one(DB_LISTS)
        # Remove quotes due to online-fix.me not using quotes
        games = "\n".join(games["games"]).replace("'", "").split("\n")
        return onlinefix_cache["onlinefix_cache"], games

    async def _load_power_outages_cache(self) -> list:
        elektrinavypadky_cache = await self._bot_config.find_one(DB_CACHE)
        return elektrinavypadky_cache["elektrinavypadky_cache"]

    async def _load_contests_cache(self) -> tuple:
        to_filter = await self._bot_config.find_one(DB_LISTS)
        esutaze_cache = await self._bot_config.find_one(DB_CACHE)
        return to_filter["esutaze_exceptions"], esutaze_cache["esutaze_cache"]
