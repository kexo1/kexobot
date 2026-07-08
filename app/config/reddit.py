"""Reddit API credentials and subreddit configuration."""

import os

############################# Reddit Configuration ############################
ENV_REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
ENV_REDDIT_SECRET = os.getenv("REDDIT_SECRET")
ENV_REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
ENV_REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
ENV_REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")

############################# Icons ############################
ICON_REDDIT = "https://www.pngkit.com/png/full/207-2074270_reddit-icon-png.png"

############################# Subreddits ############################
SHITPOST_SUBREDDITS_DEFAULT = (
    "discordVideos",
    "okbuddyretard",
    "shitposting",
    "MemeVideos",
    "doodoofard",
)

SHITPOST_SUBREDDITS_ALL = (
    "discordVideos",
    "okbuddyretard",
    "MemeVideos",
    "doodoofard",
    "dankvideos",
    "whenthe",
    "ihaveihaveihavereddit",
    "memes",
    "simpsonsshitposting",
    "shitposting",
    "clamworks",
)

############################# Scraping ############################
REDDIT_TO_REMOVE = (" *", "* ", "*", "---")
REDDIT_FREEGAMEFINDINGS_MAX_RESULTS = 5
REDDIT_CRACKWATCH_MAX_RESULTS = 5
CRACKWATCH_HIGHLIGHT_KEYWORDS = ["denuvo removed", "voices38"]

############################# Default Embeds ############################
REDDIT_FREEGAMEFINDINGS_EMBEDS = {
    "Default": {
        "title": "",
        "description": "",
        "icon": "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png",
    },
    "Gleam": {
        "title": "Gleam",
        "description": "**Gleam** - keys from this site __disappear really fast__"
        " so you should get it fast!",
        "icon": "https://files.catbox.moe/or8beg.png",
    },
    "AlienwareArena": {
        "title": "AlienwareArena",
        "description": "**AlienwareArena** - "
        "keys from this site __disappear really fast__ so you should get it fast!",
        "icon": "https://play-lh.googleusercontent.com"
        "/X3K4HfYdxmascX5mRFikhuv8w8BYvg1Ny_R4ndNhF1C7GgjPeIKfROvbcOcjhafFmLdl",
    },
    "Fanatical": {
        "title": "Fanatical",
        "description": "**Fanatical** - keys from this site __disappear really fast__ so you should get it fast!",
        "icon": "https://files.catbox.moe/6hns7j.png",
    },
}

############################# Icons ############################
ICON_REDDIT_FREEGAMEFINDINGS = (
    "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png"
)
ICON_REDDIT_CRACKWATCH = (
    "https://b.thumbs.redditmedia.com/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png"
)
