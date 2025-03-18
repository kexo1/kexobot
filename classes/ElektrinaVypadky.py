import discord
import pymongo
import logging

from bson.objectid import ObjectId
from datetime import datetime
from bs4 import BeautifulSoup
from constants import ELEKTRINA_MAX_ARTICLES


class ElektrinaVypadky:
    def __init__(self, session, database, user_kexo):
        self.session = session
        self.database = database
        self.user_kexo = user_kexo

    async def run(self) -> None:

        try:
            post_link_doc = self.database.find_one({'_id': ObjectId('618945c8221f18d804636965')})
        except pymongo.errors.ServerSelectionTimeoutError as e:
            logging.error(f"ElektrinaVypadky: Database error when loading: \n{e}")
            return

        post_link = post_link_doc['hlinik_post_link_cache']
        source = await self.session.get("https://www.hliniknadhronom.sk/mid/492460/ma0/all/.html")
        soup = BeautifulSoup(source.content, 'html.parser')
        article = soup.find(class_='oznamy-new-columns-all-list-default oznamy-new-columns-all-list')
        # If site is unreachable
        if not article:
            logging.error('ElektrinaVypadky: Site is unreachable')
            return

        to_upload = []

        for i in range(ELEKTRINA_MAX_ARTICLES):

            article = article.find_next('div', {'class': 'short-text-envelope-default short-text-envelope'})
            full_article = article.find('div').text.lower()
            article_head = article.find('a')['aria-label'].lower()

            if 'elektriny' in full_article or 'elektriny' in article_head or 'odstávka vody' in article_head:
                pass
            else:
                continue

            if "link" in post_link:
                continue

            link = f"https://www.hliniknadhronom.sk{article.find('a')['href']}"
            to_upload.append(link)

            title = article.find('a')['aria-label']
            source = await self.session.get(link)
            soup = BeautifulSoup(source.content, 'html.parser')
            post = soup.find(class_='ci-full').text

            if len(post) > 2048:
                embed = discord.Embed(title=title, url=link,
                                      description='Under embed (amount of text in embed is restricted')
                above_limit = True
            else:
                embed = discord.Embed(title=title, url=link, description=post)
                above_limit = False

            embed.timestamp = datetime.utcnow()
            embed.set_footer(text='',
                             icon_url='https://www.hliniknadhronom.sk/portals_pictures/i_006868/i_6868718.png')
            await self.user_kexo.send(embed=embed)

            if above_limit:
                await self.user_kexo.send(post)
            self.database.update_one({'_id': ObjectId('618945c8221f18d804636965')},
                                     {'$set': {'hlinik_post_link_cache': to_upload}})
