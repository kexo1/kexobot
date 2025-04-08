import os
from bson.objectid import ObjectId

# -------------------- Discord -------------------- #
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ESUTAZE_CHANNEL = 1302271245919981638
GAME_UPDATES_CHANNEL = 882185054174994462
FREE_STUFF_CHANNEL = 1081883673902714953
KEXO_SERVER = 692810367851692032
SISKA_GANG_SERVER = 765262686908186654
XTC_SERVER = 723197287861583885

# -------------------- Lavalink -------------------- #
LAVAINFO_API_URLS = [
    "https://lavainfo.netlify.app/api/non-ssl",
    "https://lavainfo.netlify.app/api/ssl",
]
LAVALIST_URL = "https://lavalink-list.ajieblogs.eu.org/All"
# -------------------- SFD Servers -------------------- #
SFD_SERVER_URL = "https://mythologicinteractive.com/SFDGameServices.asmx"
SFD_REQUEST = """<?xml version='1.0' encoding='utf-8'?>
    <soap12:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'
     xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap12='http://www.w3.org/2003/05/soap-envelope'>
        <soap12:Body>
            <GetGameServers xmlns='https://mythologicinteractive.com/Games/SFD/'>
                <validationToken></validationToken>
            </GetGameServers>
        </soap12:Body>
    </soap12:Envelope>"""
SFD_HEADERS = {
    "Content-Type": "application/soap+xml; charset=utf-8",
    "SOAPAction": "https://mythologicinteractive.com/Games/SFD/GetGameServers",
}
TIMEZONES = {
    "New_York": "America/New_York",
    "London": "Europe/London",
    "Tokyo": "Asia/Tokyo",
    "Shanghai": "Asia/Shanghai",
    "Slovakia": "Europe/Bratislava",
    "Russia": "Europe/Moscow",
    "Spain": "Europe/Madrid",
    "Italy": "Europe/Rome",
}
SFD_TIMEZONE_CHOICE = list(TIMEZONES.keys())

# -------------------- MongoDB -------------------- #
MONGO_DB_URL = (
    f"mongodb+srv://{os.getenv('MONGO_KEY')}"
    f"@cluster0.exygx.mongodb.net/myFirstDatabase?retryWrites=true&w"
    f"=majority"
)
DB_CACHE = {"_id": ObjectId("617958fae4043ee4a3f073f2")}
DB_LISTS = {"_id": ObjectId("6178211ec5f5c08c699b8fd3")}
DB_REDDIT_CACHE = {"_id": ObjectId("61795a8950149bebf7666e55")}
DB_SFD_ACTIVITY = {"_id": ObjectId("67eaab02440fd08b31d39a89")}
DB_CHOICES = (
    "Games",
    "r/FreeGameFindings Exceptions",
    "r/CrackWatch Exceptions",
    "Esutaze Exceptions",
    "AlienwareArena Exceptions",
)

# -------------------- Reddit -------------------- #
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_STRIP = (" *", "* ", "*", "---")
REDDIT_FREEGAME_EMBEDS = {
    "Default": {
        "title": "Free Game - unknown site",
        "description": None,
        "icon": "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png",
    },
    "Gleam": {
        "title": "Gleam",
        "description": "**Gleam** - keys from this site __disappear really fast__"
        " so you should get it fast!",
        "icon": "https://static-00.iconduck.com/assets.00/gleam-icon-512x512-vxvvbmg8.png",
    },
    "AlienwareArena": {
        "title": "AlienwareArena",
        "description": "**AlienwareArena** - "
        "keys from this site __disappear really fast__ so you should get it fast!",
        "icon": "https://play-lh.googleusercontent.com"
        "/X3K4HfYdxmascX5mRFikhuv8w8BYvg1Ny_R4ndNhF1C7GgjPeIKfROvbcOcjhafFmLdl",
    },
}
REDDIT_FREEGAME_MAX_POSTS = 5
REDDIT_FREEGAME_ICON = (
    "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png"
)
REDDIT_CRACKWATCH_POSTS = 5
REDDIT_CRACKWATCH_ICON = (
    "https://b.thumbs.redditmedia.com/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png"
)

# -------------------- Game3rb -------------------- #
GAME3RB_URL = "https://game3rb.com/category/games-online/"
GAME3RB_ICON = (
    "https://media.discordapp.net/attachments/796453724713123870"
    "/1162443171209433088/d95X3.png?ex=653bf491&is=65297f91&hm"
    "=c36058433d50580eeec7cd89ddfe60965ec297d6fc8054994fee5ae976bedfd3&="
)
GAME3RB_STRIP = (
    "Download ",
    " + OnLine",
    "-P2P",
    " Build",
    " + Update Only",
    " + Update",
    " + Online",
    " + 5 DLCs-FitGirl Repack",
    " Hotfix 1",
    ")-FitGirl Repack",
    " + Bonus Content DLC",
    " Hotfix 2 Hotfix",
    " rc",
    "\u200b",
    "-GOG",
    "-Repack",
    " VR",
    "/Denuvoless",
    " (Build",
    "-FitGirl Repack",
    "[Frankenpack]",
    ")",
)

# -------------------- Online-Fix -------------------- #
ONLINEFIX_MAX_GAMES = 10
ONLINEFIX_URL = "https://online-fix.me/chat.php"
ONLINEFIX_ICON = (
    "https://media.discordapp.net/attachments/"
    "796453724713123870/1035951759505506364/favicon-1.png"
)

# -------------------- Alienwarearena -------------------- #
ALIENWAREARENA_MAX_POSTS = 3
ALIENWAREARENA_URL = "https://eu.alienwarearena.com/esi/featured-tile-data/Giveaway"
ALIENWAREARENA_STRIP = ("Key", "Giveaway", "Steam Game")

# -------------------- Fanatical -------------------- #
FANATICAL_MAX_POSTS = 3
FANATICAL_URL = "https://www.fanatical.com/api/all-promotions/en"
FANATICAL_IMG_URL = "https://cdn-ext.fanatical.com/production/product/1280x720/"

# -------------------- Elektrina vypadky -------------------- #
ELEKTRINA_MAX_ARTICLES = 5
ELEKTRINA_URL = "https://www.hliniknadhronom.sk/get_rss.php?id=1_atom_1947"
ELEKTRINA_ICON = (
    "https://www.hliniknadhronom.sk/portals_pictures/i_006868/i_6868718.png"
)

# -------------------- Esutaze -------------------- #
ESUTAZE_URL = "https://www.esutaze.sk/category/internetove-sutaze/feed/"
ESUTAZE_ICON = "https://www.esutaze.sk/wp-content/uploads/2014/07/esutaze-logo2.jpg"

# -------------------- Fun Stuff -------------------- #
ROAST_COMMANDS_MSG = """Wassup, can a loc come up in your crib?
Man fuck you, I'll see you at work
Ah, nigga don't hate me cause I"m beautiful nigga
Maybe if you got rid of that yee yee ass hair cut you get some bitches on your dick.
Oh, better yet, Maybe Tanisha'll call your dog-ass if she ever stop fucking with that brain 
surgeon or lawyer she fucking with,
Niggaaa...
What?!
https://www.youtube.com/watch?v=6gJ6VEG8Y4I"""
IMGFLIP_USERNAME = os.getenv("IMGFLIP_USERNAME")
IMGFLIP_PASSWORD = os.getenv("IMGFLIP_PASSWORD")
HUMOR_SECRET = os.getenv("HUMOR_SECRET")
KYS_MESSAGES = (
    "Kys",
    "Skap",
    "Zdechni",
    "Zahraj sa na luster",
    "Choď pobozkať kolajnice keď príde vlak",
    "Zec mi kar",
)
SHITPOST_SUBREDDITS = (
    "discordVideos",
    "okbuddyretard",
    "MemeVideos",
    "doodoofard",
    "dankvideos",
    "whenthe",
)
REDDIT_VIDEO_STRIP = ("DASH_360", "DASH_480", "DASH_720", "DASH_1080")
CLEAR_CACHE_HOUR = 0
