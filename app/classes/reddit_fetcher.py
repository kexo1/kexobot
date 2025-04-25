from typing import Optional
from datetime import datetime

import re
import asyncpraw
import asyncpraw.models
import httpx
import discord

from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlparse
from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    ResponseException,
    RequestException,
)
from app.constants import (
    REDDIT_CRACKWATCH_POSTS,
    REDDIT_STRIP,
    REDDIT_CRACKWATCH_ICON,
    REDDIT_FREEGAME_EMBEDS,
    REDDIT_FREEGAME_MAX_POSTS,
    REDDIT_FREEGAME_ICON,
    DB_CACHE,
    DB_LISTS,
)
from app.utils import strip_text


class RedditFetcher:
    def __init__(
        self,
        bot_config: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        reddit_agent: asyncpraw.Reddit,
        free_stuff: discord.TextChannel,
        game_updates: discord.TextChannel,
    ) -> None:
        self.bot_config = bot_config
        self.session = session
        self.reddit_agent = reddit_agent
        self.free_stuff = free_stuff
        self.game_updates = game_updates

    async def crackwatch(self) -> None:
        crackwatch_cache, to_filter = await self._load_bot_config(
            "crackwatch_cache", "crackwatch_exceptions"
        )
        crackwatch_cache_upload = crackwatch_cache.copy()
        subreddit: asyncpraw.models.Subreddit = await self.reddit_agent.subreddit(
            "CrackWatch"
        )
        try:
            async for submission in subreddit.new(limit=REDDIT_CRACKWATCH_POSTS):
                if (
                    submission.locked
                    or submission.stickied
                    or submission.over_18
                    or hasattr(submission, "poll_data")
                ):
                    continue

                if submission.permalink in crackwatch_cache:
                    continue

                is_filtered = [
                    k for k in to_filter if k.lower() in submission.title.lower()
                ]
                if is_filtered:
                    continue

                img_url = None
                if submission.url.endswith((".jpg", ".jpeg", ".png")):
                    img_url = submission.url

                submission_text = submission.selftext
                if not submission_text:
                    continue

                description_list = []

                submission_text = strip_text(submission_text, REDDIT_STRIP).split("\n")
                for line in submission_text:
                    line = line.strip()

                    if not line:
                        continue

                    if ".png" in line or ".jpeg" in line or ".jpg" in line:
                        img_url = self._get_image(line)
                        continue
                    description_list.append(f"• {line}\n")

                del crackwatch_cache_upload[0]
                crackwatch_cache_upload.append(submission.permalink)

                description = "".join(description_list)[:4096]
                if (
                    "denuvo removed" in submission.title.lower()
                    or "denuvo removed" in description.lower()
                ):
                    embed = await self._create_embed_crackwatch(
                        submission, description, discord.Color.gold()
                    )
                else:
                    embed = await self._create_embed_crackwatch(
                        submission, description, discord.Color.orange()
                    )

                if img_url:
                    embed.set_image(url=img_url)

                embed.set_footer(
                    text="I took it from - r/CrackWatch",
                    icon_url=REDDIT_CRACKWATCH_ICON,
                )
                embed.timestamp = datetime.fromtimestamp(submission.created_utc)
                await self.game_updates.send(embed=embed)

            if crackwatch_cache != crackwatch_cache_upload:
                await self.bot_config.update_one(
                    DB_CACHE, {"$set": {"crackwatch_cache": crackwatch_cache_upload}}
                )
        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print(f"Error when accessing crackwatch:\n{e}")

    async def freegamefindings(self) -> None:
        freegamefindings_cache, to_filter = await self._load_bot_config(
            "freegamefindings_cache", "freegamefindings_exceptions"
        )
        freegamefindings_cache_upload = freegamefindings_cache.copy()
        subreddit: asyncpraw.models.Subreddit = await self.reddit_agent.subreddit(
            "FreeGameFindings"
        )

        try:
            async for submission in subreddit.new(limit=REDDIT_FREEGAME_MAX_POSTS):
                # If post is locked, or is stickied, nsfw, or it's a poll, skip it
                if (
                    submission.locked
                    or submission.stickied
                    or submission.over_18
                    or hasattr(submission, "poll_data")
                ):
                    continue

                if submission.url in freegamefindings_cache:
                    continue

                if "[PSA]" in submission.title and "Amazon" not in submission.title:
                    continue

                if "(Game)" not in submission.title:
                    continue

                if "https" not in submission.url:
                    continue

                is_filtered = [k for k in to_filter if k in submission.url]
                if is_filtered:
                    continue

                del freegamefindings_cache_upload[0]
                freegamefindings_cache_upload.append(submission.url)
                await self._process_submission(submission)
        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print(f"[FreeGameFindings] - Error while fetching subreddit:\n{e}")

        if freegamefindings_cache_upload != freegamefindings_cache:
            await self.bot_config.update_one(
                DB_CACHE,
                {"$set": {"freegamefindings_cache": freegamefindings_cache_upload}},
            )

    async def _process_submission(
        self, submission: asyncpraw.models.Submission
    ) -> None:
        feeegame_embeds: dict = REDDIT_FREEGAME_EMBEDS

        if "gleam" in submission.url:
            await self._create_embed(feeegame_embeds["Gleam"], submission.url)
        elif "alienwarearena" in submission.url:
            await self._alienwarearena(submission.url)
        else:
            title_stripped = re.sub(r"\[.*?]|\(.*?\)", "", submission.title).strip()
            feeegame_embeds["Default"]["title"] = title_stripped
            await self._create_embed(feeegame_embeds["Default"], submission.url)

    async def _alienwarearena(self, url) -> None:
        # There might be an occurence where giveaway is not showing in alienwarearena.com
        alienwarearena_cache = await self.bot_config.find_one(DB_CACHE)
        reddit_path = url[29:]
        for cached_url in alienwarearena_cache["alienwarearena_cache"]:
            if reddit_path in cached_url:
                return

        feeegame_embeds: dict = REDDIT_FREEGAME_EMBEDS
        await self._create_embed(feeegame_embeds["AlienwareArena"], url)

    async def _create_embed(self, embed_dict: dict, url: str) -> None:
        url_obj = urlparse(url)
        embed = discord.Embed(
            title=embed_dict["title"],
            description=f"{embed_dict['description']}\n\n**[{url_obj.netloc}]({url})**",
            color=discord.Color.dark_theme(),
        )
        embed.set_thumbnail(url=embed_dict["icon"])
        embed.set_footer(
            text="I took it from - r/FreeGameFindings",
            icon_url=REDDIT_FREEGAME_ICON,
        )
        await self.free_stuff.send(embed=embed)

    @staticmethod
    async def _create_embed_crackwatch(
        submission: asyncpraw.Reddit.submission, description: str, color: discord.Color
    ) -> discord.Embed:
        embed = discord.Embed(
            title=submission.title[:256],
            url=f"https://www.reddit.com{submission.permalink}",
            description=description,
            color=color,
        )
        return embed

    @staticmethod
    def _get_image(line: str) -> Optional[str]:
        image_url = re.findall(r"\((.*?)\)", line)
        if not image_url:
            return None

        if len(image_url) > 1:
            return image_url[1]
        return image_url[0]

    async def _load_bot_config(self, cache: str, exceptions: str) -> tuple:
        crackwatch_cache = await self.bot_config.find_one(DB_CACHE)
        to_filter = await self.bot_config.find_one(DB_LISTS)
        return crackwatch_cache[cache], to_filter[exceptions]
