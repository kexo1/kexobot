from constants import DB_LISTS
from motor.motor_asyncio import AsyncIOMotorClient


class DatabaseManager:
    class DataTypes:
        GAMES = "Games"
        FREEGAMEFINDINGS_EXCEPTIONS = "r/FreeGameFindings Exceptions"
        CRACKWATCH_EXCEPTIONS = "r/CrackWatch Exceptions"
        ESUTAZE_EXCEPTIONS = "Esutaze Exceptions"
        ALIENWAREARENA_EXCEPTIONS = "AlienwareArena Exceptions"

    def __init__(self, database: AsyncIOMotorClient) -> None:
        self.database = database

    async def get_database(self, collection: str) -> list:
        db_list = await self.database.find_one(DB_LISTS)
        if collection == self.DataTypes.GAMES:
            return db_list["games"]

        if collection == self.DataTypes.FREEGAMEFINDINGS_EXCEPTIONS:
            return db_list["freegamefindings_exceptions"]

        if collection == self.DataTypes.CRACKWATCH_EXCEPTIONS:
            return db_list["crackwatch_exceptions"]

        if collection == self.DataTypes.ESUTAZE_EXCEPTIONS:
            return db_list["esutaze_exceptions"]

        if collection == self.DataTypes.ALIENWAREARENA_EXCEPTIONS:
            return db_list["alienwarearena_exceptions"]
        return []

    async def update_database(self, collection: str, updated_db: list) -> None:
        if collection == self.DataTypes.GAMES:
            await self.database.update_one(DB_LISTS, {"$set": {"games": updated_db}})

        elif collection == self.DataTypes.FREEGAMEFINDINGS_EXCEPTIONS:
            await self.database.update_one(
                DB_LISTS, {"$set": {"freegamefindings_exceptions": updated_db}}
            )

        elif collection == self.DataTypes.CRACKWATCH_EXCEPTIONS:
            await self.database.update_one(
                DB_LISTS, {"$set": {"crackwatch_exceptions": updated_db}}
            )

        elif collection == self.DataTypes.ESUTAZE_EXCEPTIONS:
            await self.database.update_one(
                DB_LISTS, {"$set": {"esutaze_exceptions": updated_db}}
            )

        elif collection == self.DataTypes.ALIENWAREARENA_EXCEPTIONS:
            await self.database.update_one(
                DB_LISTS, {"$set": {"alienwarearena_exceptions": updated_db}}
            )
