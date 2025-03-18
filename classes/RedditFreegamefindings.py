import asyncio
import re
import asyncprawcore
import pymongo
import logging
import discord

from bson.objectid import ObjectId
from urllib.parse import urlparse
from datetime import datetime, timedelta
from constants import REDDIT_FREEGAME_EMBEDS, REDDIT_FREEGAME_POSTS
from asyncprawcore.exceptions import AsyncPrawcoreException, ResponseException, RequestException


class RedditFreegamefindings:
    def __init__(self, database, reddit):
        self.database = database
        self.reddit = reddit

    async def run(self) -> None:
        try:
            freegame_url_cache = self.database.find_one({'_id': ObjectId('617958fae4043ee4a3f073f2')})
        except pymongo.errors.ServerSelectionTimeoutError as e:
            logging.error(f'RedditFreegamefindings: Error while connecting to database: {e}')
            return

        _freegame_url_cache = freegame_url_cache['free_game_link']
        freegame_url_cache = _freegame_url_cache
        ignore_list = self.database.find_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')})
        ignore_list = ignore_list['freegame_exceptions']
        pending_link_list = []
        subreddit = await self.reddit.subreddit("FreeGameFindings")

        try:
            async for submission in subreddit.new(limit=REDDIT_FREEGAME_POSTS):
                # If it was already posted in disord
                if submission.url in freegame_url_cache:
                    continue
                # If it's free game
                if '(game)' not in submission.title.lower():
                    continue
                # Some simple filters
                if ('https' not in submission.url
                        or 'virtual' in submission.title.lower()
                        or 'trivia' in submission.title.lower()):
                    continue
                number = [k for k in ignore_list if k in submission.url]
                # Check if is not in blacklisted sites and database
                if number:
                    continue
                # Move url positions, new url on first position, last one is removed
                _freegame_url_cache = [_freegame_url_cache[-1]] + _freegame_url_cache[:-1]
                _freegame_url_cache[0] = submission.url
                pending_link_list.append(submission.url)
        except (AsyncPrawcoreException, RequestException, ResponseException):
            pass

        # If nothing found, return
        if not pending_link_list:
            return

        tasks = []
        self.database.update_one({'_id': ObjectId('617958fae4043ee4a3f073f2')},
                                 {'$set': {'free_game_link': _freegame_url_cache}})
        # alienwarearena
        task_funcs = {
            'key-hub': key_hub,
            'fanatical': fanatical
        }
        for url in pending_link_list:
            # If url is valid, send link to dedicated fucntions, else make default embed
            appended = False
            for key, func in task_funcs.items():
                if key in url:
                    tasks.append(func(url, self.session))
                    appended = True
                    break
            # If not found in first dictionary
            if appended is True:
                continue
            for key, value in REDDIT_FREEGAME_EMBEDS:
                if key in url:
                    tasks.append(send_freegame_embed((value[0], value[1], url, value[2], None)))
                    appended = True
                    break
            if appended is True:
                continue
            else:
                tasks.append(send_freegame_embed(('Free game - unknown site',
                                                  'Keys from this site __disappear really fast__ so you should go and '
                                                  'get it fast!',
                                                  url, None, None)))
        await asyncio.gather(*tasks)


async def key_hub(url, session) -> None:
    source = session.get(url).text
    if 'nsfw' in source.lower():
        return

    pattern = re.compile(r'og:title" content="(.*?)-', re.DOTALL)
    match = pattern.search(source)

    if match:
        title = match.group(1)
    else:
        title = 'Free game'
        logging.error(f'KeyHub: Title not found in {url}')

    pattern = re.compile(r'og:image" content="(.*?)"', re.DOTALL)
    match = pattern.search(source)

    if not match:
        logging.error(f'KeyHub: Title not found in {url}')
        return

    await send_freegame_embed((title,
                               '**KeyHub** - keys from this site __disappear really fast__ so you should go and get '
                               'it fast!',
                               url,
                               'https://cdn.discordapp.com/attachments/823205909353857085/890997523173494794/favicon'
                               '-32x32.png',
                               match.group(1)))


async def fanatical(url, session) -> None:
    source = session.get(url).text
    pattern = re.compile(r'product-name">(.*?)<', re.DOTALL)
    match = pattern.search(source)

    if match:
        title = match.group(1)
    else:
        title = 'Free game'

    match = re.search(r"https://fanatical\.imgix\.net/[^\s\"]+", source)
    await send_freegame_embed((title,
                               f'**Fanatical** - sale ends <t:{datetime.now() +
                                                               timedelta(days=5).timestamp().split(".")[0]}>', url,
                               'https://media.discordapp.net/attachments/'
                               '796453724713123870/1053672867591634965/output-onlinepngtools_1.png',
                               match.group()))


async def send_freegame_embed(info) -> None:
    embed = discord.Embed(title=info[0], description=info[1], color=discord.Color.dark_theme())
    url_obj = urlparse(info[2])
    domain = url_obj.netloc

    embed.add_field(name='\u200b', value='**[{}]({})**'.format(domain, info[2]))

    if info[3]:
        embed.set_thumbnail(url=info[3])

    if info[4]:
        if 'youtube' not in info[4]:
            embed.set_image(url=info[4])

    embed.set_footer(text='I took it from - r/FreeGameFindings',
                     icon_url='https://cdn.discordapp.com/attachments/796453724713123870/881868163137032212'
                              '/communityIcon_xnoh6m7g9qh71.png')
    # For this file, sending of the embed is assumed to be handled externally
    # You can adjust the message sending code as needed.
    print("Embed sent:", embed.to_dict())
