import re
import discord

from datetime import datetime
from asyncprawcore.exceptions import AsyncPrawcoreException, ResponseException, RequestException
from constants import REDDIT_CRACKWATCH_POSTS, REDDIT_STRIP, DB_CACHE, DB_LISTS


class RedditCrackWatch:
    def __init__(self, database, reddit, channel, user_kexo):
        self.database = database
        self.reddit = reddit
        self.channel = channel
        self.user_kexo = user_kexo

    async def run(self) -> None:
        crackwatch_cache, to_filter = await self._load_database()
        crackwatch_cache_upload = crackwatch_cache
        subreddit = await self.reddit.subreddit("CrackWatch")
        try:
            async for submission in subreddit.new(limit=REDDIT_CRACKWATCH_POSTS):
                if submission.permalink in crackwatch_cache:
                    continue

                is_filtered = [k for k in to_filter if k.lower() in submission.title.lower()]
                if is_filtered:
                    continue

                img_url = None
                if submission.url.endswith((".jpg", ".jpeg", ".png")):
                    img_url = submission.url

                submission_text = submission.selftext
                if not submission_text:
                    continue
                    
                description = []
                
                for part in REDDIT_STRIP:
                    submission_text = submission_text.replace(part, "")
                    
                submission_text = submission_text.split("\n")
                for line in submission_text:
                    line = line.strip()

                    if not line:
                        continue

                    if ".png" in line or ".jpeg" in line or ".jpg" in line:
                        img_url = await self._get_image(line)
                        continue
                    description.append(f"• {line}\n")

                crackwatch_cache_upload = [crackwatch_cache_upload[-1]] + crackwatch_cache_upload[:-1]
                crackwatch_cache_upload[0] = submission.permalink

                description = "".join(description)[:4096]
                embed = discord.Embed(title=submission.title[:256],
                                      url=f"https://www.reddit.com{submission.permalink}",
                                      description=description)

                embed.color = discord.Color.orange()
                if "denuvo removed" in submission.title.lower() or "denuvo removed" in description.lower():
                    embed.color = discord.Color.gold()

                if img_url:
                    embed.set_image(url=img_url)

                embed.set_footer(text="I took it from - r/CrackWatch",
                                 icon_url="https://b.thumbs.redditmedia.com"
                                          "/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png")
                embed.timestamp = datetime.fromtimestamp(submission.created_utc)
                await self.channel.send(embed=embed)

            if crackwatch_cache != crackwatch_cache_upload:
                await self.database.update_one(DB_CACHE, {"$set": {"crackwatch_cache": crackwatch_cache_upload}})
        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print(f"Error when accessing crackwatch:\n{e}")

    @staticmethod
    async def _get_image(line: str) -> str:
        print(line)
        image_url = re.findall(r"\((.*?)\)", line)
        if not image_url:
            return None

        if len(image_url) > 1:
            image_url = image_url[1]
        else:
            image_url = image_url[0]
        return image_url

    async def _load_database(self) -> list:
        crackwatch_cache = await self.database.find_one(DB_CACHE)
        to_filter = await self.database.find_one(DB_LISTS)
        return crackwatch_cache["crackwatch_cache"], to_filter["crackwatch_exceptions"]
