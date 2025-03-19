import re
import discord

from datetime import datetime
from asyncprawcore.exceptions import AsyncPrawcoreException, ResponseException, RequestException
from constants import REDDIT_CRACKWATCH_POSTS, REDDIT_STRIP, DB_CACHE, DB_LISTS


class RedditCrackwatch:
    def __init__(self, database, reddit, bot):
        self.database = database
        self.reddit = reddit
        self.bot = bot

    async def run(self) -> None:
        crackwatch_cache = await self.database.find_one(DB_CACHE)
        crackwatch_cache = crackwatch_cache["crackwatch_cache"]
        crackwatch_cache_upload = crackwatch_cache

        crackwatch_exceptions = await self.database.find_one(DB_LISTS)
        crackwatch_exceptions = crackwatch_exceptions["crackwatch_exceptions"]

        subreddit = await self.reddit.subreddit("CrackWatch")

        try:
            async for submission in subreddit.new(limit=REDDIT_CRACKWATCH_POSTS):
                # If already checked
                if submission.permalink in crackwatch_cache:
                    continue

                number = [k for k in crackwatch_exceptions if k.lower() in submission.title.lower()]
                # If in exceptions
                if number:
                    continue

                try:
                    image_url = None
                    # If an image is in post description
                    if submission.url.endswith((".jpg", ".jpeg", ".png")):
                        image_url = submission.url

                    description = []
                    post_description = submission.selftext

                    if post_description:
                        for part in REDDIT_STRIP:
                            post_description = post_description.replace(part, "")
                        post_description = post_description.split("\n")
                        for string in post_description:
                            string = string.strip()
                            string_low = string.lower()
                            if not string:
                                continue
                            if ".png" in string_low or ".jpeg" in string_low or ".jpg" in string_low:
                                pattern = r"\((.*?)\)"
                                match = re.findall(pattern, string)
                                if not match:
                                    continue
                                if len(match) > 1:
                                    image_url = match[1]
                                else:
                                    image_url = match[0]
                            else:
                                description.append(f"• {string}\n")

                    crackwatch_cache_upload = [crackwatch_cache_upload[-1]] + crackwatch_cache_upload[:-1]
                    crackwatch_cache_upload[0] = submission.permalink

                    embed = discord.Embed(title=submission.title[:256],
                                          url=f"https://www.reddit.com{submission.permalink}",
                                          description="".join(description)[:4096])
                    if "denuvo removed" in submission.title.lower() or "denuvo removed" in "".join(description).lower():
                        embed.color = discord.Color.gold()
                    else:
                        embed.color = discord.Color.orange()
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text="I took it from - r/CrackWatch",
                                     icon_url="https://b.thumbs.redditmedia.com"
                                              "/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png")
                    embed.timestamp = datetime.fromtimestamp(submission.created_utc)
                    await self.game_updates_channel.send(embed=embed)
                except Exception as e:
                    await self.bot.fetch_user(402221830930432000).send(f"Incorrect embed: `{submission.permalink}`"
                                                                       f"\n```css\n[{e}]```"
                                                                       f"\nImage url: {image_url}"
                                                                       f"\nDescription: {post_description}")
            if crackwatch_cache != crackwatch_cache_upload:
                await self.database.update_one(DB_CACHE, {"$set": {"crackwatch_cache": crackwatch_cache_upload}})
        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print("Error when accessing crackwatch:", e)
