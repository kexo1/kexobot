import re
import discord
import asyncprawcore
import pymongo
import logging

from datetime import datetime
from bson.objectid import ObjectId
from constants import REDDIT_CRACKWATCH_POSTS, REDDIT_STRIP


class RedditCrackwatch:
    def __init__(self, database, reddit, bot):
        self.database = database
        self.reddit = reddit
        self.bot = bot

    async def run(self) -> None:
        try:
            crack_cache = self.database.find_one({'_id': ObjectId('617958fae4043ee4a3f073f2')})
        except pymongo.errors.ServerSelectionTimeoutError as e:
            logging.error(f'RedditCrackwatch: Database error when loading: \n{e}')
            return

        crack_cache_link = crack_cache['crack_game_link']
        crack_cache = crack_cache_link

        ignore_list = self.database.find_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')})
        ignore_list = ignore_list['crackwatch_exceptions']

        subreddit = await self.reddit.subreddit('CrackWatch')

        try:
            async for submission in subreddit.new(limit=REDDIT_CRACKWATCH_POSTS):
                # If already checked
                if submission.permalink in crack_cache:
                    continue

                number = [k for k in ignore_list if k.lower() in submission.title.lower()]
                # If in exceptions
                if number:
                    continue

                try:
                    image_url = None
                    # If an image is in post description
                    if submission.url.endswith(('.jpg', '.jpeg', '.png')):
                        image_url = submission.url

                    description = []
                    post_description = submission.selftext

                    if post_description:
                        for part in REDDIT_STRIP:
                            post_description = post_description.replace(part, '')
                        post_description = post_description.split('\n')
                        for string in post_description:
                            string = string.strip()
                            string_low = string.lower()
                            if not string:
                                continue
                            if '.png' in string_low or '.jpeg' in string_low or '.jpg' in string_low:
                                pattern = r"\((.*?)\)"
                                match = re.findall(pattern, string)
                                if not match:
                                    continue
                                if len(match) > 1:
                                    image_url = match[1]
                                else:
                                    image_url = match[0]
                            else:
                                description.append(f'• {string}\n')

                    crack_cache_link = [crack_cache_link[-1]] + crack_cache_link[:-1]
                    crack_cache_link[0] = submission.permalink

                    embed = discord.Embed(title=submission.title[:256],
                                          url=f'https://www.reddit.com{submission.permalink}',
                                          description=''.join(description)[:4096])
                    if 'denuvo removed' in submission.title.lower() or 'denuvo removed' in ''.join(description).lower():
                        embed.color = discord.Color.gold()
                    else:
                        embed.color = discord.Color.orange()
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text='I took it from - r/CrackWatch',
                                     icon_url='https://b.thumbs.redditmedia.com'
                                              '/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png')
                    embed.timestamp = datetime.fromtimestamp(submission.created_utc)
                    game_updates = self.bot.get_channel(882185054174994462)
                    await game_updates.send(embed=embed)
                except Exception as e:
                    await self.bot.fetch_user(402221830930432000).send(f"Incorrect embed: `{submission.permalink}`"
                                                                       f"\n```css\n[{e}]```"
                                                                       f"\nImage url: {image_url}"
                                                                       f"\nDescription: {post_description}")
            if crack_cache != crack_cache_link:
                self.database.update_one({'_id': ObjectId('617958fae4043ee4a3f073f2')},
                                         {'$set': {'crack_game_link': crack_cache_link}})
        except (asyncprawcore.exceptions.AsyncPrawcoreException, asyncprawcore.exceptions.RequestException,
                asyncprawcore.exceptions.ResponseException, AssertionError):
            pass
