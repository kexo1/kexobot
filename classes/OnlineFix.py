import re
import html
import logging
import pymongo
import discord

from deep_translator import GoogleTranslator
from datetime import datetime
from bson.objectid import ObjectId
from constants import ONLINEFIX_MAX_GAMES


class OnlineFix:
    def __init__(self, session, database, bot):
        self.session = session
        self.database = database
        self.bot = bot

    async def run(self) -> None:
        try:
            games_doc = self.database.find_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                               {'onlinefix_cache': 1, 'games': 1})
        except pymongo.errors.ServerSelectionTimeoutError as e:
            logging.error(f'OnlineFix: Database error: \n{e}')
            return

        onlinefix_cache = games_doc['onlinefix_cache']
        games = games_doc['games']

        source = await self.session.get('https://online-fix.me/chat.php')
        source = source.text.replace(' по сети', '')

        game_info = []
        for _ in range(ONLINEFIX_MAX_GAMES):
            pattern = re.compile(r'@0xdeadc0de</b> обновил:.*?">(.*?)<', re.DOTALL)
            match = pattern.search(source)

            if not match:
                break

            if match.group(1) in games:
                title = html.unescape(match.group(1))
                pattern = re.compile(r'@0xdeadc0de</b> обновил:.*?href="(.*?)"', re.DOTALL)
                match = pattern.search(source)
                link = match.group(1)
                game_info.append({'title': title, 'link': link})
            source = source[match.end():]

        if not game_info:
            return

        to_upload = []
        for game in game_info:
            to_upload.append(game['title'])
            if game['title'] in onlinefix_cache:
                continue

            game_source = await self.session.get(game['link']).text

            pattern = re.compile(r'<meta property="og:image" content="(.*?)"')
            match = pattern.search(game_source)
            image_link = match.group(1)

            pattern = re.compile(r'Причина: (.*?)\n')
            match = pattern.search(game_source)
            description = GoogleTranslator(source='ru').translate(text=match.group(1))

            pattern = re.compile(r'version\s*(\d+(\.\d+)*)')
            version = pattern.findall(description)
            version = f' v{version[0][0]}' if version else ''

            embed = discord.Embed(title=game['title'] + version,
                                  url=game['link'],
                                  description=description, color=discord.Color.blue())
            embed.timestamp = datetime.utcnow()
            embed.set_footer(text='https://online-fix.me',
                             icon_url='https://media.discordapp.net/attachments/796453724713123870'
                                      '/1035951759505506364/favicon-1.png')
            embed.set_thumbnail(url=image_link)
            game_updates = self.bot.get_channel(882185054174994462)
            await game_updates.send(embed=embed)

        self.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                 {'$set': {'onlinefix_cache': to_upload}})
