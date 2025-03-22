import discord

from discord.ext import commands
from discord.commands import slash_command
from discord.commands import option
from constants import DB_LISTS, KEXO_SERVER


class DatabaseManager(commands.Cog):
    class DataTypes:
        GAMES = "Games"
        FREEGAMEFINDINGS_EXCEPTIONS = "r/FreeGameFindings Exceptions"
        CRACKWATCH_EXCEPTIONS = "r/CrackWatch Exceptions"
        ESUTAZE_EXCEPTIONS = "Esutaze Exceptions"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.database = self.bot.database

    async def _get_database(self, collection: DataTypes) -> list:
        db_list = await self.database.find_one(DB_LISTS)
        if collection == self.DataTypes.GAMES:
            return db_list["games"]

        elif collection == self.DataTypes.FREEGAMEFINDINGS_EXCEPTIONS:
            return db_list["freegamefindings_exceptions"]

        elif collection == self.DataTypes.CRACKWATCH_EXCEPTIONS:
            return db_list["crackwatch_exceptions"]

        elif collection == self.DataTypes.ESUTAZE_EXCEPTIONS:
            return db_list["esutaze_exceptions"]

    async def _update_database(self, collection: DataTypes, updated_db: str) -> None:
        if collection == self.DataTypes.GAMES:
            await self.database.update_one(DB_LISTS, {"$set": {"games": updated_db}})

        elif collection == self.DataTypes.FREEGAMEFINDINGS_EXCEPTIONS:
            await self.database.update_one(DB_LISTS, {"$set": {"freegamefindings_exceptions": updated_db}})

        elif collection == self.DataTypes.CRACKWATCH_EXCEPTIONS:
            await self.database.update_one(DB_LISTS, {"$set": {"crackwatch_exceptions": updated_db}})

        elif collection == self.DataTypes.ESUTAZE_EXCEPTIONS:
            await self.database.update_one(DB_LISTS, {"$set": {"esutaze_exceptions": updated_db}})

    @slash_command(name="add_to", description="Adds string to selected list.", guild_ids=[KEXO_SERVER])
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database",
            choices=["Games", "r/FreeGameFindings Exceptions", "r/CrackWatch Exceptions", "Esutaze Exceptions"])
    async def add_to(self, ctx, collection: str, to_upload: str) -> None:
        db_list = await self._get_database(collection)

        if to_upload in db_list:
            return await ctx.respond(
                str(ctx.author.mention) + ", string `" + to_upload + "` is already in the database, use `/show_data`")

        db_list.append(to_upload)
        await self._update_database(collection, db_list)
        await ctx.respond(f"String `" + to_upload + f"` was added to `{collection}` :white_check_mark:")

    @slash_command(name="remove_from", description="Removes string from selected list.",
                   guild_ids=[KEXO_SERVER])
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database",
            choices=["Games", "r/FreeGameFindings Exceptions", "r/CrackWatch Exceptions", "Esutaze Exceptions"])
    async def remove(self, ctx, collection: str, to_remove: str) -> None:
        db_list = await self._get_database(collection)

        if to_remove not in db_list:
            return await ctx.respond(
                str(ctx.author.mention) + ", string `" + to_remove + "` is not in the database, use `/show_data`")
        db_list.pop(db_list.index(to_remove))

        await self._update_database(collection, db_list)
        await ctx.respond(f"String `" + to_remove + "` was removed from `{collection}` :white_check_mark:")

    @slash_command(name="show_data", description="Shows data from selected lists.", guild_ids=[KEXO_SERVER])
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database",
            choices=["Games", "r/FreeGameFindings Exceptions", "r/CrackWatch Exceptions", "Esutaze Exceptions"])
    async def show_data(self, ctx, collection: str) -> None:
        listing = await self._get_database(collection)

        embed = discord.Embed(title=collection, color=discord.Color.blue())
        embed.add_field(name=f"_{len(listing)} items_",
                        value="\n".join(f"{i + 1}. {listing[i]}" for i in range(len(listing))))
        await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(DatabaseManager(bot))
