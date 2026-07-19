"""Scraping and content-monitoring configuration."""

############################# Game3rb ############################
SITE_URL_GAME3RB = "https://game3rb.com/category/games-online/"
GAME3RB_TO_REMOVE = (
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
    "™",
    ")",
)
ICON_GAME3RB = "https://files.catbox.moe/oj3jso.png"

############################# Online-Fix ############################
ONLINEFIX_MAX_RESULTS = 10
SITE_URL_ONLINEFIX = "https://online-fix.me/chat.php"
ICON_ONLINEFIX = "https://files.catbox.moe/o361yb.png"

############################# AlienwareArena ############################
ALIENWAREARENA_MAX_RESULTS = 3
SITE_URL_ALIENWAREARENA = (
    "https://eu.alienwarearena.com/esi/featured-tile-data/Giveaway"
)
ALIENWAREARENA_TO_REMOVE = ("Key", "Giveaway", "Steam Game")

############################# Joke APIs ############################
API_JOKEAPI = "https://v2.jokeapi.dev/joke/Miscellaneous,Dark?amount=10"
API_HUMORAPI = "https://api.humorapi.com/jokes/search?number=10&include-tags="
API_DAD_JOKE = "https://icanhazdadjoke.com/search?limit=10"

############################# Lavalink ############################
API_LAVALIST = "https://lavalink-list.ajieblogs.eu.org/All"
