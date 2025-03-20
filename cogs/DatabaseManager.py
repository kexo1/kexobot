import discord

from discord.ext import commands
from discord.commands import slash_command
from discord.commands import option
from constants import DB_LISTS


class DatabaseManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.database = self.bot.database

    async def manage_list(self, collection: str, manage: bool) -> list:
        # If manage is False (showing database), else editing database
        if manage is False:
            listing = await self.database.find_one(DB_LISTS)

        if collection == "Games":
            if manage is False:
                listing = listing["games"]
            else:
                await self.database.update_one(DB_LISTS, {"$set": {"games": manage}})
        elif collection == "r/FreeGameFindings Exceptions":
            if manage is False:
                listing = listing["freegamefindings_exceptions"]
            else:
                await self.database.update_one(DB_LISTS, {"$set": {"freegamefindings_exceptions": manage}})
        elif collection == "r/CrackWatch Exceptions":
            if manage is False:
                listing = listing["crackwatch_exceptions"]
            else:
                await self.database.update_one(DB_LISTS, {"$set": {"crackwatch_exceptions": manage}})
        elif collection == "Esutaze Exceptions":
            if manage is False:
                listing = listing["esutaze_exceptions"]
            else:
                await self.database.update_one(DB_LISTS, {"$set": {"esutaze_exceptions": manage}})

        if manage is False:
            return listing

    @slash_command(name="add_to", description="Adds string to selected list.", guild_ids=[692810367851692032])
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database",
            choices=["Games", "r/FreeGameFindings Exceptions", "r/CrackWatch Exceptions", "Esutaze Exceptions"])
    async def add_to(self, ctx, collection: str, string: str) -> None:
        listing = await self.manage_list(collection, False)

        if string in listing:
            return await ctx.respond(
                str(ctx.author.mention) + ", string `" + string + "` is already in the database, use `/show_data`")

        listing.append(string)
        await self.manage_list(collection, listing)
        await ctx.respond(f"String `" + string + f"` was added to `{collection}` :white_check_mark:")

    @slash_command(name="remove_from", description="Removes string from selected list.",
                   guild_ids=[692810367851692032])
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database",
            choices=["Games", "r/FreeGameFindings Exceptions", "r/CrackWatch Exceptions", "Esutaze Exceptions"])
    async def remove(self, ctx, collection: str, string: str) -> None:
        listing = await self.manage_list(collection, False)

        if string not in listing:
            return await ctx.respond(str(ctx.author.mention) + ", string `" + string + "` is not in the database, use "
                                                                                       "`/show_data`")
        listing.pop(listing.index(string))

        await self.manage_list(collection, listing)
        await ctx.respond(f"String `" + string + "` was removed from `{collection}` :white_check_mark:")

    @slash_command(name="show_data", description="Shows data from selected lists.", guild_ids=[692810367851692032])
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database",
            choices=["Games", "r/FreeGameFindings Exceptions", "r/CrackWatch Exceptions", "Esutaze Exceptions"])
    async def show_data(self, ctx, collection: str) -> None:
        listing = await self.manage_list(collection, False)

        embed = discord.Embed(title=collection, color=discord.Color.blue())
        embed.add_field(name=f"_{len(listing)} words_",
                        value="\n".join(f"{i + 1}. {listing[i]}" for i in range(len(listing))))
        await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(DatabaseManager(bot))
