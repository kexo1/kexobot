import re
import unidecode
import discord
import pymongo
import logging

from datetime import datetime
from bson.objectid import ObjectId
from bs4 import BeautifulSoup
from constants import GAME3RB_MUST_BE_ONLINE, GAME3RB_STRIP


class Game3rb:
    def __init__(self, session, database, bot):
        self.session = session
        self.database = database
        self.bot = bot

    async def run(self):
        try:
            games_doc = self.database.find_one(
                {'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                {'game3rb_cache': 1, 'games': 1}
            )
        except pymongo.errors.ServerSelectionTimeoutError as e:
            logging.error(f'Game3rb: Database error: {e}')
            return

        game3rb_cache = games_doc['game3rb_cache']
        games = '\n'.join(games_doc['games'])

        source = await self.session.get('https://www.game3rb.com/')
        game_info = []
        to_upload = []

        if 'Bad gateway' in source.text:
            logging.info('Game3rb: Bad gateway')
            return

        soup = BeautifulSoup(source.content, 'html.parser')
        article = soup.find('article')

        if not article:
            return

        for sticky in article.select('article.sticky.hentry'):
            sticky.decompose()

        for _ in range(16):
            line = article.find('a', {'title': True})

            if not line:
                break

            game_title = line.get('title')
            full_title = game_title
            has_online = 'online' in game_title.lower()

            for part in GAME3RB_STRIP:
                game_title = game_title.replace(part, '')

            game_title = game_title.split()
            version = ''
            regex = re.compile(r'v\d+(\.\d+)+')

            if regex.match(game_title[-1]):
                version = f' got updated to {game_title[-1]}'
                game_title.pop()
            else:
                pattern = r"Build [\d.]+"
                match = re.search(pattern, full_title)
                if match:
                    version = f' got updated to {match.group().lower()}'
                    to_remove = version.split()[-1]
                    try:
                        game_title.pop(game_title.index(to_remove))
                    except ValueError:
                        if full_title not in game3rb_cache not in to_upload:
                            self.database.update_one(
                                {'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                {'$set': {'game3rb_cache': to_upload}}
                            )
                            await self.user_kexo.send(f'Game3rb: Broken name - {full_title}')
                            to_upload.append(full_title)
                        continue

            game_title = ' '.join(game_title)
            carts = []

            for cart in article.find_all(id='cart'):
                if cart:
                    carts.append(cart.text)
                else:
                    break

            if game_title.lower() in games.lower():
                if any(game in game_title.lower() for game in GAME3RB_MUST_BE_ONLINE):
                    if has_online is False:
                        article = article.find_next('article')
                        continue
            else:
                article = article.find_next('article')
                continue

            game_info.append({
                'title': game_title,
                'full_title': full_title,
                'version': version,
                'link': line.get('href'),
                'image': article.find('img', {'class': 'entry-image'})['src'],
                'timestamp': article.find('time')['datetime'],
                'carts': carts
            })
            article = article.find_next('article')

        if not game_info:
            return

        for game in game_info:
            to_upload.append(game['full_title'])
            if game['full_title'] in game3rb_cache:
                continue

            description = []
            source = await self.session.get(game['link'])
            soup = BeautifulSoup(source.content, 'html.parser')

            torrent_link = soup.find('a', {'class': 'torrent'})
            if torrent_link:
                description.append(f'[Torrent link]({torrent_link["href"]})')
            direct_link = soup.find('a', {'class': 'direct'})
            if direct_link:
                description.append(f'[Direct link]({direct_link["href"]})')

            if 'Fix already included' in str(soup) or 'Crack online already added' in str(soup):
                description.append('_Fix already included_')
            else:
                crack_url = soup.find('a', {'class': 'online'})
                if crack_url:
                    description.append(f'[Crack link]({crack_url["href"]})')
                else:
                    crack_url = soup.find('a', {'class': 'crack'})
                    if crack_url:
                        description.append(f'[Crack link]({crack_url["href"]})')

            game_update_link, game_update_name = [], []
            update_pattern = r'>Update (.*?)</strong>.*?<a\s+id="download-link"\s+class="update"\s+href="(.*?)"'
            for match in re.finditer(update_pattern, source.text, re.DOTALL):
                update_name = re.sub(r'<.*?>', '', match.group(1)).strip()
                game_update_name.append(unidecode.unidecode(update_name))
                game_update_link.append(unidecode.unidecode(match.group(2).strip()))

            embed = discord.Embed(title=game['title'] + game['version'], url=game['link'])
            embed.timestamp = datetime.fromisoformat(game['timestamp'])
            embed.add_field(name='Download links:', value='\n'.join(description))
            if game_update_name:
                game_update = '\n'.join(
                    f'{i + 1}. [{game_update_name[i]}]({game_update_link[i]})'
                    for i in range(len(game_update_link))
                )
                embed.add_field(name='Update links:', value=game_update, inline=False)
            embed.set_footer(text=', '.join(game['carts']),
                             icon_url='https://media.discordapp.net/attachments/796453724713123870'
                                      '/1162443171209433088/d95X3.png?ex=653bf491&is=65297f91&hm'
                                      '=c36058433d50580eeec7cd89ddfe60965ec297d6fc8054994fee5ae976bedfd3&=')
            embed.set_image(url=game['image'])
            game_updates = self.bot.get_channel(882185054174994462)
            await game_updates.send(embed=embed)

        if to_upload:
            self.database.update_one(
                {'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                {'$set': {'game3rb_cache': to_upload}}
            )
