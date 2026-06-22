"""MongoDB database configuration (collection _id filters, choices)."""

from bson.objectid import ObjectId

DB_CACHE = {"_id": ObjectId("617958fae4043ee4a3f073f2")}
DB_LISTS = {"_id": ObjectId("6178211ec5f5c08c699b8fd3")}
DB_SFD_ACTIVITY = {"_id": ObjectId("67eaab02440fd08b31d39a89")}
DB_CHOICES = {
    "Games": "games",
    "r/FreeGameFindings Exceptions": "freegamefindings_exceptions",
    "r/CrackWatch Exceptions": "crackwatch_exceptions",
    "AlienwareArena Exceptions": "alienwarearena_exceptions",
}
