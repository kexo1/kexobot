import re
import discord
import html
import pymongo
import logging

from datetime import datetime
from bs4 import BeautifulSoup
from bson.objectid import ObjectId
from constants import ESUTAZE_MAX_ARTICLES


class Esutaze:
    def __init__(self, session, database, bot):
        self.session = session
        self.database = database
        self.bot = bot

    async def run(self) -> None:
        try:
            title_exceptions = self.database.find_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')})
        except pymongo.errors.ServerSelectionTimeoutError as e:
            logging.error(f'Esutaze: Database error when loading: \n{e}')
            return

        title_exceptions = title_exceptions['esutaze_exceptions']
        post_title = self.database.find_one({'_id': ObjectId('618945c8221f18d804636965')})
        post_title = post_title['esutaze_link_cache']
        source = await self.session.get("https://www.esutaze.sk/feed/")
        soup = BeautifulSoup(source.content, 'xml')
        article = soup.find('channel')

        if not article:
            return

        for _ in range(ESUTAZE_MAX_ARTICLES):
            article = article.find_next('item')
            title = article.find('title').text

            if title in post_title:
                return

            category = article.find('category').text
            if not (category == 'Internetové súťaže' or 'TOP SÚŤAŽ' in category):
                continue

            number = [k for k in title_exceptions if k.lower() in title]
            if number:
                continue

            post_title = [post_title[-1]] + post_title[:-1]
            post_title[0] = title
            esutaze_link = article.find('link').text

            description = html.unescape(article.find('description').text)
            pattern = re.compile(r'<p>(.*?)</p>', re.DOTALL)
            match = pattern.search(description)
            description = match.group(1)
            description = description.replace('\xa0', '\n').replace('ilustračné foto:', '')
            pos = description.find('Koniec súťaže')
            description = description[:pos] + '\n**' + description[pos:] + '**'

            source_unescaped = html.unescape(article.text)
            pattern = re.compile(r'" src="(.*?)"', re.DOTALL)
            match = pattern.search(source_unescaped)
            image_link = match.group(1)
            pattern = re.compile(r'</h4>\n<a href="(.*?)"', re.DOTALL)
            match = pattern.search(source_unescaped)
            giveaway_link = match.group(1)

            embed = discord.Embed(title=title, url=giveaway_link, description=description,
                                  colour=discord.Colour.brand_red())
            embed.set_image(url=image_link)
            embed.timestamp = datetime.utcnow()
            embed.set_footer(text=esutaze_link,
                             icon_url='https://www.esutaze.sk/wp-content/uploads/2014/07/esutaze-logo2.jpg')
            esutaze_channel = self.bot.get_channel(1302271245919981638)
            await esutaze_channel.send(embed=embed)
            self.database.update_one({'_id': ObjectId('618945c8221f18d804636965')},
                                     {'$set': {'esutaze_link_cache': post_title}})
