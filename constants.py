import os
from bson.objectid import ObjectId

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ESUTAZE_CHANNEL = 1302271245919981638
GAME_UPDATES_CHANNEL = 882185054174994462
FREE_STUFF_CHANNEL = 1081883673902714953

# MongoDB
MONGO_DB_URL = (f"mongodb+srv://{os.getenv("MONGO_KEY")}@cluster0.exygx.mongodb.net/myFirstDatabase?retryWrites=true&w"
                f"=majority")
DB_CACHE = {"_id": ObjectId("617958fae4043ee4a3f073f2")}
DB_LISTS = {"_id": ObjectId("6178211ec5f5c08c699b8fd3")}
DB_REDDIT_CACHE = {"_id": ObjectId("61795a8950149bebf7666e55")}

# Reddit
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_STRIP = (" *", "* ", "*", "---")

# Game3rb
GAME3RB_STRIP = (
    "Download ", " + OnLine", "-P2P", " Build", " + Update Only", " + Update", " + Online",
    " + 5 DLCs-FitGirl Repack",
    " Hotfix 1", ")-FitGirl Repack", " + Bonus Content DLC",
    " Hotfix 2" " Hotfix", " rc", "\u200b", "-GOG", "-Repack", " VR", "/Denuvoless", " (Build",
    "-FitGirl Repack", "[Frankenpack]", ")")
GAME3RB_MUST_BE_ONLINE = (
    "barotrauma", "green hell", "ready or not", "generation zero", "evil west",
    "devour", "minecraft legends", "the long drive", "stronghold definitive edition", "valheim", "no mans sky",
    "warhammer 40,000: space marine 2", "abiotic factor", "core keeper")

# OnlineFix
ONLINEFIX_MAX_GAMES = 10

# RedditFreegamefindings
REDDIT_FREEGAME_EMBEDS = {
    "gleam": (
        "Gleam",
        "**Gleam** - keys from this site __disappear really fast__ so you should go and get it fast!",
        "https://media.discordapp.net/attachments/796453724713123870/1038118297914318878/favicon.png"),
    "alienwarearena": (
        "Alienwarearena",
        "**Alienwarearena** - keys from this site __disappear really fast__ so you should go and get it fast!",
        "https://media.discordapp.net/attachments/796453724713123870/1009896932929441874/unknown.png")}
REDDIT_FREEGAME_POSTS = 5

# Crackwatch
REDDIT_CRACKWATCH_POSTS = 5

# ElektrinaVypadky
ELEKTRINA_MAX_ARTICLES = 3

# FunStuff
ROAST_COMMANDS_MSG = """Wassup, can a loc come up in your crib?
Man fuck you, I"ll see you at work
Ah, nigga don"t hate me cause I"m beautiful nigga
Maybe if you got rid of that yee yee ass hair cut you get some bitches on your dick.
Oh, better yet, Maybe Tanisha"ll call your dog-ass if she ever stop fucking with that brain 
surgeon or lawyer she fucking with,
Niggaaa...
What?!
https://www.youtube.com/watch?v=6gJ6VEG8Y4I"""
IMGFLIP_USERNAME = os.getenv("IMGFLIP_USERNAME")
IMGFLIP_PASSWORD = os.getenv("IMGFLIP_PASSWORD")
HUMOR_SECRET = os.getenv("HUMOR_SECRET")
KYS_MESSAGES = ("Kys", "Skap", "Zdechni", "Zahraj sa na luster",
                "Choď pobozkať kolajnice keď príde vlak", "Zec mi kar")
SHITPOST_SUBREDDITS = ("discordVideos", "okbuddyretard", "MemeVideos",
                       "doodoofard", "dankvideos", "whenthe")
REDDIT_VIDEO_STRIP = ("DASH_360", "DASH_480", "DASH_720", "DASH_1080")
CLEAR_CACHE_HOUR = 0
