from datetime import datetime

import re
import httpx
import unidecode
import discord

from motor.motor_asyncio import AsyncIOMotorClient
from bs4 import BeautifulSoup
from constants import GAME3RB_STRIP, GAME3RB_URL, GAME3RB_ICON, DB_CACHE, DB_LISTS


class Game3rb:
    def __init__(
        self,
        database: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        channel: discord.TextChannel,
        user_kexo: discord.User,
    ) -> None:
        self.session = session
        self.database = database
        self.channel = channel
        self.user_kexo = user_kexo

    async def run(self) -> None:
        game3rb_cache = await self.database.find_one(DB_CACHE)
        game3rb_cache = game3rb_cache["game3rb_cache"]

        game_list = await self.database.find_one(DB_LISTS)
        game_list = "\n".join(game_list["games"])
        try:
            source = await self.session.get(GAME3RB_URL)
        except httpx.ReadTimeout:
            print("Game3rb: Timeout")
            return

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

            for part in GAME3RB_STRIP:
                game_title = game_title.replace(part, "")

            game_title = game_title.split()
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
                            await self.database.update_one(
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
            source = await self.session.get(game["url"])
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
                timestamp=datetime.fromisoformat(game["timestamp"]),
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
            await self.database.update_one(
                DB_CACHE, {"$set": {"game3rb_cache": to_upload}}
            )
