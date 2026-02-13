import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import asyncpraw
import asyncpraw.models
import discord
import httpx
from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    RequestException,
    ResponseException,
)
from pymongo import AsyncMongoClient

from app.constants import (
    DB_CACHE,
    DB_LISTS,
    ICON_REDDIT_CRACKWATCH,
    ICON_REDDIT_FREEGAMEFINDINGS,
    REDDIT_CRACKWATCH_MAX_RESULTS,
    REDDIT_FREEGAMEFINDINGS_EMBEDS,
    REDDIT_FREEGAMEFINDINGS_MAX_RESULTS,
    REDDIT_TO_REMOVE,
)
from app.utils import strip_text


def get_image_from_line(line: str) -> Optional[str]:
    image_url = re.findall(r"\((.*?)\)", line)
    if not image_url:
        return None

    if len(image_url) > 1:
        return image_url[1]
    return image_url[0]


async def create_embed_crackwatch(
    submission: asyncpraw.reddit.Submission,
    description: str,
    color: discord.Color,
) -> discord.Embed:
    embed = discord.Embed(
        title=submission.title[:256],
        url=f"https://www.reddit.com{submission.permalink}",
        description=description,
        color=color,
    )
    return embed


class RedditFetcher:
    """Fetch game info from subreddits and send it to Discord channels.

    It fetches data from the following subreddits:
    - r/CrackWatch
    - r/FreeGameFindings

    Parameters
    ----------
    bot_config: :class:`motor.motor_asyncio.AsyncMongoClient`
        MongoDB client for accessing the database.
    session: :class:`httpx.AsyncClient`
        HTTP client for making requests.
    reddit_agent: :class:`asyncpraw.Reddit`
        Reddit client for accessing the Reddit API.
    free_stuff: :class:`discord.TextChannel`
        Discord channel for sending free game info.
    game_updates: :class:`discord.TextChannel`
        Discord channel for sending game updates.
    """

    def __init__(
        self,
        bot_config: AsyncMongoClient,
        session: httpx.AsyncClient,
        reddit_agent: asyncpraw.Reddit,
        free_stuff: discord.TextChannel,
        game_cracks: discord.TextChannel,
    ) -> None:
        self._bot_config = bot_config
        self._session = session
        self._reddit_agent = reddit_agent
        self._free_stuff = free_stuff
        self._game_cracks = game_cracks

    async def crackwatch(self) -> None:
        """Method to fetch game repacks from r/CrackWatch subreddit."""
        crackwatch_cache, to_filter = await self._load_bot_config(
            "crackwatch_cache", "crackwatch_exceptions"
        )
        crackwatch_cache_upload = crackwatch_cache.copy()
        subreddit: asyncpraw.models.Subreddit = await self._reddit_agent.subreddit(
            "CrackWatch"
        )
        try:
            async for submission in subreddit.new(limit=REDDIT_CRACKWATCH_MAX_RESULTS):
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

                submission_text = strip_text(submission_text, REDDIT_TO_REMOVE).split(
                    "\n"
                )
                for line in submission_text:
                    line = line.strip()

                    if not line:
                        continue

                    if ".png" in line or ".jpeg" in line or ".jpg" in line:
                        img_url = get_image_from_line(line)
                        continue
                    description_list.append(f"• {line}\n")

                crackwatch_cache_upload.pop(0)
                crackwatch_cache_upload.append(submission.permalink)

                description = "".join(description_list)[:4096]
                if (
                    "denuvo removed" in submission.title.lower()
                    or "denuvo removed" in description.lower()
                ):
                    embed = await create_embed_crackwatch(
                        submission, description, discord.Color.gold()
                    )
                else:
                    embed = await create_embed_crackwatch(
                        submission, description, discord.Color.orange()
                    )

                if img_url:
                    embed.set_image(url=img_url)

                embed.set_footer(
                    text="I took it from - r/CrackWatch",
                    icon_url=ICON_REDDIT_CRACKWATCH,
                )
                embed.timestamp = datetime.fromtimestamp(submission.created_utc)
                await self._game_cracks.send(embed=embed)

            if crackwatch_cache != crackwatch_cache_upload:
                await self._bot_config.update_one(
                    DB_CACHE,
                    {"$set": {"crackwatch_cache": crackwatch_cache_upload}},
                )
        except discord.errors.HTTPException as e:
            logging.warning(
                f"[CrackWatch] - Error when sending message ({submission.permalink}):\n{e}"
            )
        except (
            AsyncPrawcoreException,
            RequestException,
            ResponseException,
        ) as e:
            logging.warning(f"[CrackWatch] - Error when accessing crackwatch:\n{e}")

    async def freegamefindings(self) -> None:
        """Method to fetch free games from r/FreeGameFindings subreddit."""
        freegamefindings_cache, to_filter = await self._load_bot_config(
            "freegamefindings_cache", "freegamefindings_exceptions"
        )
        freegamefindings_cache_upload = freegamefindings_cache.copy()
        subreddit: asyncpraw.models.Subreddit = await self._reddit_agent.subreddit(
            "FreeGameFindings"
        )

        try:
            async for submission in subreddit.new(
                limit=REDDIT_FREEGAMEFINDINGS_MAX_RESULTS
            ):
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

                freegamefindings_cache_upload.pop(0)
                freegamefindings_cache_upload.append(submission.url)
                await self._process_submission(submission)

        except discord.errors.HTTPException as e:
            logging.warning(
                f"[CrackWatch] - Error when sending message ({submission.permalink}):\n{e}"
            )
        except (
            AsyncPrawcoreException,
            RequestException,
            ResponseException,
        ) as e:
            logging.warning(
                f"[FreeGameFindings] - Error while fetching subreddit:\n{e}"
            )

        if freegamefindings_cache_upload != freegamefindings_cache:
            await self._bot_config.update_one(
                DB_CACHE,
                {"$set": {"freegamefindings_cache": freegamefindings_cache_upload}},
            )

    async def _process_submission(
        self, submission: asyncpraw.models.Submission
    ) -> None:
        freegame_embeds: dict = REDDIT_FREEGAMEFINDINGS_EMBEDS

        if "gleam" in submission.url:
            await self._create_embed(freegame_embeds["Gleam"], submission.url)
        elif "alienwarearena" in submission.url:
            await self._alienwarearena(submission.url)
        else:
            title_stripped = re.sub(r"\[.*?]|\(.*?\)", "", submission.title).strip()
            freegame_embeds["Default"]["title"] = title_stripped
            await self._create_embed(freegame_embeds["Default"], submission.url)

    async def _alienwarearena(self, url) -> None:
        # There might be an occurence where giveaway is not showing in alienwarearena.com
        alienwarearena_cache = await self._bot_config.find_one(DB_CACHE)
        reddit_path = url[29:]
        for cached_url in alienwarearena_cache["alienwarearena_cache"]:
            if reddit_path in cached_url:
                return

        freegame_embeds: dict = REDDIT_FREEGAMEFINDINGS_EMBEDS
        await self._create_embed(freegame_embeds["AlienwareArena"], url)

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
            icon_url=ICON_REDDIT_FREEGAMEFINDINGS,
        )
        await self._free_stuff.send(embed=embed)

    async def _load_bot_config(
        self, cache: str, exceptions: str
    ) -> tuple[list[str], list[str]]:
        crackwatch_cache = await self._bot_config.find_one(DB_CACHE)
        to_filter = await self._bot_config.find_one(DB_LISTS)
        return crackwatch_cache[cache], to_filter[exceptions]
