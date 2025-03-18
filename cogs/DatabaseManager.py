import discord

from discord.ext import commands
from discord.commands import slash_command
from discord.commands import option
from bson.objectid import ObjectId


class DatabaseManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def manage_list(self, collection, manage):
        # If manage is False (showing database), else editing database
        if manage is False:
            listing = self.bot.database.find_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')})

        if collection == 'Games':
            if manage is False:
                listing = listing['games']
            else:
                self.bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                             {'$set': {'games': manage}})
        elif collection == 'r/Free Game Findings exceptions':
            if manage is False:
                listing = listing['freegame_exceptions']
            else:
                self.bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                             {'$set': {'freegame_exceptions': manage}})
        elif collection == 'r/Crackwatch exceptions':
            if manage is False:
                listing = listing['crackwatch_exceptions']
            else:
                self.bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                             {'$set': {'crackwatch_exceptions': manage}})
        elif collection == 'eSutaze exceptions':
            if manage is False:
                listing = listing['esutaze_exceptions']
            else:
                self.bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                             {'$set': {'esutaze_exceptions': manage}})

        if manage is False:
            return listing

    @slash_command(name='add_to', description='Adds string to selected list.', guild_ids=[692810367851692032])
    @discord.ext.commands.is_owner()
    @option('collection', description='Choose database',
            choices=['Games', 'r/Free Game Findings exceptions', 'r/Crackwatch exceptions', 'eSutaze exceptions'])
    async def add_to(self, ctx, collection: str, string: str):
        listing = await self.manage_list(collection, False)

        if string in listing:
            return await ctx.respond(
                str(ctx.author.mention) + ", string `" + string + "` is already in the database, use `/show_data`")

        listing.append(string)
        await self.manage_list(collection, listing)
        await ctx.respond(
            "String `" + string + "` was added :white_check_mark:")

    @slash_command(name='remove_from', description='Removes string from selected list.',
                   guild_ids=[692810367851692032])
    @discord.ext.commands.is_owner()
    @option('collection', description='Choose database',
            choices=['Games', 'r/Free Game Findings exceptions', 'r/Crackwatch exceptions', 'eSutaze exceptions'])
    async def remove(self, ctx, collection: str, string: str):
        listing = await self.manage_list(collection, False)

        if string not in listing:
            return await ctx.respond(str(ctx.author.mention) + ", string `" + string + "` is not in the database, use "
                                                                                       "`/show_data`")

        listing.pop(listing.index(string))

        await self.manage_list(collection, listing)
        await ctx.respond(
            "String `" + string + "` was removed :white_check_mark:")

    @slash_command(name='show_data', description='Shows data from selected lists.', guild_ids=[692810367851692032])
    @discord.ext.commands.is_owner()
    @option('collection', description='Choose database',
            choices=['Games', 'Site exceptions', 'Crackwatch exceptions', 'Esutaze exceptions'])
    async def show_data(self, ctx, collection: str):
        listing = await self.manage_list(collection, False)

        embed = discord.Embed(title=collection, color=discord.Color.blue())
        embed.add_field(name=f'_{len(listing)} words_',
                        value='\n'.join(f'{i + 1}. {listing[i]}' for i in range(len(listing))))
        await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(DatabaseManager(bot))
