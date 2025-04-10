from urllib.parse import urlparse

import asyncpraw
import asyncpraw.models
import discord
import httpx
import re

from motor.motor_asyncio import AsyncIOMotorClient
from asyncprawcore.exceptions import (  # type: ignore
    AsyncPrawcoreException,
    ResponseException,
    RequestException,
)

from constants import (
    REDDIT_FREEGAME_EMBEDS,
    REDDIT_FREEGAME_MAX_POSTS,
    REDDIT_FREEGAME_ICON,
    DB_CACHE,
    DB_LISTS,
)


class RedditFreeGameFindings:
    def __init__(
        self,
        database: AsyncIOMotorClient,
        session: httpx.AsyncClient,
        reddit: asyncpraw.Reddit,
        channel: discord.TextChannel,
    ) -> None:
        self.database = database
        self.reddit = reddit
        self.session = session
        self.channel = channel

    async def run(self) -> None:
        freegamefindings_cache, to_filter = await self._load_database()
        freegamefindings_cache_upload = freegamefindings_cache.copy()
        subreddit: asyncpraw.models.Subreddit = await self.reddit.subreddit(
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
            await self.database.update_one(
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
            title_stripped = re.sub(r"\[.*?]|\(.*?\)", "", text).strip()
            feeegame_embeds["Default"]["title"] = title_stripped
            await self._create_embed(feeegame_embeds["Default"], submission.url)

    async def _alienwarearena(self, url) -> None:
        # There might be an occurence where giveaway is not showing in alienwarearena.com
        alienwarearena_cache = await self.database.find_one(DB_CACHE)
        reddit_path = url[29:]
        for cached_url in alienwarearena_cache["alienwarearena_cache"]:
            if reddit_path in cached_url:
                return

        feeegame_embeds: dict = REDDIT_FREEGAME_EMBEDS
        await self._create_embed(feeegame_embeds["AlienwareArena"], url)

    async def _create_embed(self, embed_dict: dict, url: str) -> None:
        url_obj = urlparse(url)
        domain = url_obj.netloc
        embed = discord.Embed(
            title=embed_dict["title"],
            description=f"{embed_dict['description']}\n\n**[{domain}]({url})**",
            color=discord.Color.dark_theme(),
        )
        embed.set_thumbnail(url=embed_dict["icon"])
        embed.set_footer(
            text="I took it from - r/FreeGameFindings",
            icon_url=REDDIT_FREEGAME_ICON,
        )
        await self.channel.send(embed=embed)

    async def _load_database(self) -> tuple:
        freegamefindings_cache = await self.database.find_one(DB_CACHE)
        to_filter = await self.database.find_one(DB_LISTS)
        return (
            freegamefindings_cache["freegamefindings_cache"],
            to_filter["freegamefindings_exceptions"],
        )
