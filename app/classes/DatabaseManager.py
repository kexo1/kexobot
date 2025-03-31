from constants import DB_LISTS


class DatabaseManager:
    class DataTypes:
        GAMES = "Games"
        FREEGAMEFINDINGS_EXCEPTIONS = "r/FreeGameFindings Exceptions"
        CRACKWATCH_EXCEPTIONS = "r/CrackWatch Exceptions"
        ESUTAZE_EXCEPTIONS = "Esutaze Exceptions"

    def __init__(self, database) -> None:
        self.database = database

    async def get_database(self, collection: str) -> list:
        db_list = await self.database.find_one(DB_LISTS)
        if collection == self.DataTypes.GAMES:
            return db_list["games"]

        elif collection == self.DataTypes.FREEGAMEFINDINGS_EXCEPTIONS:
            return db_list["freegamefindings_exceptions"]

        elif collection == self.DataTypes.CRACKWATCH_EXCEPTIONS:
            return db_list["crackwatch_exceptions"]

        elif collection == self.DataTypes.ESUTAZE_EXCEPTIONS:
            return db_list["esutaze_exceptions"]
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
