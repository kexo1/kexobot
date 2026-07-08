"""Environment variables, logging setup, and OS-level configuration."""

import logging
import os
import socket

from dotenv import load_dotenv
from fake_useragent import UserAgent

############################ Switching between DEV and PROD ############################
LOCAL_MACHINE_NAME = "mato"
if LOCAL_MACHINE_NAME in socket.gethostname():
    load_dotenv(os.getenv("SECRET_PATH"))
    ENV_DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_DEV")
else:
    ENV_DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

############################ Logging Configuration ############################
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%d/%m/%y %H:%M:%S"
)
console_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(console_handler)

logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
logging.getLogger("aiohttp.client").setLevel(logging.CRITICAL)
logging.getLogger("sonolink").setLevel(logging.DEBUG)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

############################ MongoDB Configuration ############################
ENV_API_DB = (
    f"mongodb+srv://{os.getenv('MONGO_KEY')}"
    f"@cluster0.exygx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)

############################# User Agent Configuration ############################
try:
    USER_AGENT = UserAgent(min_version=120.0).random
except Exception:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

############################## Joke APIs Configuration ############################
_humor_api_tokens = os.getenv("HUMOR_API_TOKENS", "")
ENV_HUMOR_KEY = [token for token in _humor_api_tokens.split(":") if token]

############################# Wordnik API Configuration ############################
API_WORDNIK = f"https://api.wordnik.com/v4/words.json/wordOfTheDay?api_key={os.getenv('WORDNIK_API_KEY')}"
