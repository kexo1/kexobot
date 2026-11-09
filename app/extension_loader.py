from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
import httpx

from app.config.discord import CHANNEL_ID_KEXO_SERVER
from app.config.env import USER_AGENT

logger = logging.getLogger(__name__)

COG_EXTENSIONS = (
    "fun_commands",
    "commands",
    "reddit_commands",
    "node_commands",
    "sfd_commands",
    "music_commands",
    "radio_commands",
    "listeners",
)


class ExtensionBot(Protocol):
    session: httpx.AsyncClient

    @property
    def tree(self) -> object: ...

    async def load_extension(self, name: str) -> None: ...


async def setup_extensions(bot: ExtensionBot) -> None:
    """Create the cog HTTP session, load extensions, and sync app commands."""
    bot.session = httpx.AsyncClient()
    bot.session.headers = httpx.Headers({"User-Agent": USER_AGENT})

    for extension in COG_EXTENSIONS:
        await bot.load_extension(f"app.cogs.{extension}")

    tree = cast(discord.app_commands.CommandTree, bot.tree)
    await tree.sync()
    await tree.sync(guild=discord.Object(id=CHANNEL_ID_KEXO_SERVER))
    logger.info("[Starter] Cogs loaded.")
