from typing import Optional
from datetime import datetime

import re
import asyncpraw
import asyncpraw.models
import discord

from motor.motor_asyncio import AsyncIOMotorClient
from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    ResponseException,
    RequestException,
)
from constants import (
    REDDIT_CRACKWATCH_POSTS,
    REDDIT_STRIP,
    REDDIT_CRACKWATCH_ICON,
    DB_CACHE,
    DB_LISTS,
)


class RedditCrackWatch:
    def __init__(
        self,
        bot_config: AsyncIOMotorClient,
        reddit: asyncpraw.Reddit,
        channel: discord.TextChannel,
        user_kexo: discord.User,
    ) -> None:
        self.bot_config = bot_config
        self.reddit = reddit
        self.channel = channel
        self.user_kexo = user_kexo

    async def run(self) -> None:
        crackwatch_cache, to_filter = await self._load_bot_config()
        crackwatch_cache_upload = crackwatch_cache.copy()
        subreddit: asyncpraw.models.Subreddit = await self.reddit.subreddit(
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

                for part in REDDIT_STRIP:
                    submission_text = submission_text.replace(part, "")

                submission_text = submission_text.split("\n")
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
                    embed = await self._create_embed(
                        submission, description, discord.Color.gold()
                    )
                else:
                    embed = await self._create_embed(
                        submission, description, discord.Color.orange()
                    )

                if img_url:
                    embed.set_image(url=img_url)

                embed.set_footer(
                    text="I took it from - r/CrackWatch",
                    icon_url=REDDIT_CRACKWATCH_ICON,
                )
                embed.timestamp = datetime.fromtimestamp(submission.created_utc)
                await self.channel.send(embed=embed)

            if crackwatch_cache != crackwatch_cache_upload:
                await self.bot_config.update_one(
                    DB_CACHE, {"$set": {"crackwatch_cache": crackwatch_cache_upload}}
                )
        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print(f"Error when accessing crackwatch:\n{e}")

    @staticmethod
    async def _create_embed(
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

    async def _load_bot_config(self) -> tuple:
        crackwatch_cache = await self.bot_config.find_one(DB_CACHE)
        to_filter = await self.bot_config.find_one(DB_LISTS)
        return crackwatch_cache["crackwatch_cache"], to_filter["crackwatch_exceptions"]
