import copy
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

from app.config.mongo import DB_CACHE, DB_LISTS
from app.config.reddit import (
    CRACKWATCH_HIGHLIGHT_KEYWORDS,
    ICON_REDDIT_CRACKWATCH,
    ICON_REDDIT_FREEGAMEFINDINGS,
    REDDIT_CRACKWATCH_MAX_RESULTS,
    REDDIT_FREEGAMEFINDINGS_EMBEDS,
    REDDIT_FREEGAMEFINDINGS_MAX_RESULTS,
    REDDIT_TO_REMOVE,
)
from app.data.bot_data import BotConfigManager
from app.utils import strip_text


def get_image_from_line(line: str) -> Optional[str]:
    match = re.search(r"\((https?://[^)\s]+?\.(?:png|jpe?g))\)", line, re.I)
    if not match:
        return None
    return match.group(1)


def create_embed_crackwatch(
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
        config_manager: BotConfigManager,
        session: httpx.AsyncClient,
        reddit_agent: asyncpraw.Reddit,
        free_stuff: discord.TextChannel,
        game_cracks: discord.TextChannel,
    ) -> None:
        self._config_manager = config_manager
        self._session = session
        self._reddit_agent = reddit_agent
        self._free_stuff = free_stuff
        self._game_cracks = game_cracks

    async def crackwatch(self) -> None:
        """Method to fetch game repacks from r/CrackWatch subreddit."""
        crackwatch_cache = await self._config_manager.get("crackwatch_cache", DB_CACHE)
        crackwatch_cache_copy = crackwatch_cache.copy()
        to_filter = await self._config_manager.get("crackwatch_exceptions", DB_LISTS)

        subreddit: asyncpraw.models.Subreddit = await self._reddit_agent.subreddit(
            "CrackWatch"
        )
        try:
            async for submission in subreddit.new(limit=REDDIT_CRACKWATCH_MAX_RESULTS):
                if not self._is_valid_crackwatch_submission(
                    submission,
                    crackwatch_cache_copy,
                    to_filter,
                ):
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

                    if img_candidate := get_image_from_line(line):
                        img_url = img_candidate
                        continue

                    description_list.append(f"• {line}\n")

                crackwatch_cache.pop(0)
                crackwatch_cache.append(submission.permalink)

                description = "".join(description_list)[:4096]
                title_lower = submission.title.lower()
                description_lower = description.lower()

                if any(
                    keyword in title_lower or keyword in description_lower
                    for keyword in CRACKWATCH_HIGHLIGHT_KEYWORDS
                ):
                    embed = create_embed_crackwatch(
                        submission, description, discord.Color.gold()
                    )
                else:
                    embed = create_embed_crackwatch(
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
        finally:
            await self._config_manager.save("crackwatch_cache", DB_CACHE)

    def _is_valid_crackwatch_submission(
        self,
        submission: asyncpraw.models.Submission,
        cache: list[str],
        to_filter: list[str],
    ) -> bool:
        if (
            submission.locked
            or submission.stickied
            or submission.over_18
            or hasattr(submission, "poll_data")
        ):
            return False

        if submission.permalink in cache:
            return False

        title_lower = submission.title.lower()
        if any(token.lower() in title_lower for token in to_filter):
            return False

        return True

    async def freegamefindings(self) -> None:
        """Method to fetch free games from r/FreeGameFindings subreddit."""
        freegamefindings_cache = await self._config_manager.get(
            "freegamefindings_cache", DB_CACHE
        )
        freegamefindings_cache_copy = freegamefindings_cache.copy()
        to_filter = await self._config_manager.get(
            "freegamefindings_exceptions", DB_LISTS
        )

        subreddit: asyncpraw.models.Subreddit = await self._reddit_agent.subreddit(
            "FreeGameFindings"
        )
        try:
            async for submission in subreddit.new(
                limit=REDDIT_FREEGAMEFINDINGS_MAX_RESULTS
            ):
                if not self._is_valid_freegame_submission(
                    submission,
                    freegamefindings_cache_copy,
                    to_filter,
                ):
                    continue

                freegamefindings_cache.pop(0)
                freegamefindings_cache.append(submission.url)
                await self._process_submission(submission)

        except discord.errors.HTTPException as e:
            logging.warning(
                f"[FreeGameFindings] - Error when sending message ({submission.permalink}):\n{e}"
            )
        except (
            AsyncPrawcoreException,
            RequestException,
            ResponseException,
        ) as e:
            logging.warning(
                f"[FreeGameFindings] - Error while fetching subreddit:\n{e}"
            )
        finally:
            await self._config_manager.save("freegamefindings_cache", DB_CACHE)

    def _is_valid_freegame_submission(
        self,
        submission: asyncpraw.models.Submission,
        cache: list[str],
        to_filter: list[str],
    ) -> bool:
        if (
            submission.locked
            or submission.stickied
            or submission.over_18
            or hasattr(submission, "poll_data")
        ):
            return False

        if submission.url in cache:
            return False

        submission_title_lower = submission.title.lower()

        if "(game)" not in submission_title_lower:
            return False

        url_obj = urlparse(submission.url)
        if url_obj.scheme not in {"http", "https"}:
            return False

        if any(token in submission.url for token in to_filter):
            return False

        # Allow Epic Games giveaways, but only mobile games
        if (
            "epic games" in submission_title_lower
            and "mobile" not in submission_title_lower
        ):
            return False

        return True

    async def _process_submission(
        self, submission: asyncpraw.models.Submission
    ) -> None:
        freegame_embeds: dict = REDDIT_FREEGAMEFINDINGS_EMBEDS

        if "gleam" in submission.url:
            await self._create_embed(freegame_embeds["Gleam"], submission.url)
        elif "fanatical" in submission.url:
            await self._create_embed(freegame_embeds["Fanatical"], submission.url)
        elif "alienwarearena" in submission.url:
            await self._alienwarearena(submission.url)
        else:
            default_freegame_embed = copy.deepcopy(freegame_embeds["Default"])
            title_stripped = re.sub(r"\[.*?]|\(.*?\)", "", submission.title).strip()
            default_freegame_embed["title"] = title_stripped
            await self._create_embed(default_freegame_embed, submission.url)

    async def _alienwarearena(self, url) -> None:
        # There might be an occurence where giveaway is not showing in alienwarearena.com
        alienwarearena_cache = await self._config_manager.get(
            "alienwarearena_cache", DB_CACHE
        )
        reddit_path = url[29:]
        for cached_url in alienwarearena_cache:
            if reddit_path in cached_url:
                return

        await self._create_embed(REDDIT_FREEGAMEFINDINGS_EMBEDS["AlienwareArena"], url)

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
