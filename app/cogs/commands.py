from __future__ import annotations

import datetime
import logging
import os
import random
import sys
import time
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands

from app.__init__ import __version__
from app.config.colors import COLOR_BLUE
from app.config.discord import CHANNEL_ID_KEXO_SERVER
from app.config.mongo import DB_CHOICES, DB_LISTS
from app.response_handler import make_embed, send

if TYPE_CHECKING:
    from app.client import KexoBotClient

logger = logging.getLogger(__name__)


def get_memory_usage() -> float:
    """Get the current memory usage of the process in MB."""
    import psutil

    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)


async def is_owner(interaction: discord.Interaction) -> bool:
    return await cast("KexoBotClient", interaction.client).is_owner(interaction.user)


class CommandCog(commands.Cog):
    """Cog for general, admin, bot configuration, and Reddit commands.

    This includes commands for:
    - Bot configuration and Reddit management
    - Bot info
    - Random number generator
    - Pick a random word from a list
    - Clear messages

    Parameters
    ----------
    bot: :class:`KexoBotClient`
        The bot instance.
    """

    def __init__(self, bot: KexoBotClient) -> None:
        self._bot: KexoBotClient = bot

        self._run_time = time.time()

    slash_bot_config = app_commands.Group(
        name="bot_config",
        description="Update Bot Configuration",
        guild_ids=[CHANNEL_ID_KEXO_SERVER],
    )

    # -------------------- Discord functions -------------------- #
    @app_commands.command(name="info", description="Shows bot info.")
    async def info(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about the bot.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        embed = discord.Embed(title="KexoBOT Info", color=COLOR_BLUE)
        embed.add_field(
            name="Run time:ㅤㅤ",
            value=f"{datetime.timedelta(seconds=round(int(time.time()) - self._run_time))!s}",
        )
        embed.add_field(name="Ping:ㅤㅤ", value=f"{round(self._bot.latency * 1000)} ms")
        embed.add_field(name="Memory usage:ㅤㅤ", value=f"{get_memory_usage():.2f} MB")
        embed.add_field(name="Online nodes:ㅤ", value=self._bot.state.get_online_nodes())
        embed.add_field(
            name="Available nodes:ㅤ", value=self._bot.state.get_available_nodes()
        )
        embed.add_field(name="Joined servers:ㅤ", value=len(self._bot.guilds))
        embed.add_field(name="Bot version:", value=__version__)
        embed.add_field(name="Discord.py version:ㅤㅤ", value=discord.__version__)
        embed.add_field(
            name="Python version:",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        embed.set_footer(text="Bot owner: _kexo")
        await send(ctx, embed=embed)

    @app_commands.command(
        name="random_number", description="Choose number between intervals."
    )
    @app_commands.describe(
        integer1="First number in range.",
        integer2="Second number in range.",
    )
    async def random_number(
        self, ctx: discord.Interaction, integer1: int, integer2: int
    ) -> None:
        """Method to generate a random number between two integers.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        integer1: int
            The first integer of the range.
        integer2: int
            The second integer of the range.
        """
        if integer1 > integer2:
            integer2, integer1 = integer1, integer2
        await send(ctx, f"I chose `{random.randint(integer1, integer2)}`")

    @app_commands.command(
        name="pick",
        description="Selects one word, words needs to be separated by space.",
    )
    @app_commands.describe(words="Space-separated words to choose from.")
    async def pick(self, ctx: discord.Interaction, words: str) -> None:
        """Method to pick a random word from a list of words.
        Parameter is a string of words separated by spaces,
        but it is split into a list.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        words: str
            The list of words separated by spaces.
        """
        word_list = words.split()
        await send(ctx, "I chose " + "`" + str(random.choice(word_list)) + "`")

    @app_commands.command(
        name="clear-messages", description="Clears messages, max 50 (Admin)"
    )
    @app_commands.describe(integer="How many messages to delete (1-50).")
    @app_commands.default_permissions(administrator=True)
    async def clear(
        self,
        ctx: discord.Interaction,
        integer: app_commands.Range[int, 1, 50],
    ) -> None:
        """Method to clear messages in a channel.
        This method is only available to administrators.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        integer: int
            The number of messages to clear (max 50).
        """
        await send(
            ctx, f"`{integer}` messages cleared ✅", delete_after=20, ephemeral=True
        )
        await cast(discord.TextChannel, ctx.channel).purge(limit=integer)

    @app_commands.command(
        name="spam", description="Spams a word (bot owner only, max 50)."
    )
    @app_commands.describe(
        word="Word to spam.",
        integer="How many times to send it (1-50).",
        channel="Optional text channel.",
    )
    @app_commands.check(is_owner)
    async def spam(
        self,
        ctx: discord.Interaction,
        word: str,
        integer: app_commands.Range[int, 1, 50],
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Spam a word in the current channel or a selected text channel."""
        target_channel: discord.abc.Messageable = channel or cast(
            discord.abc.Messageable, ctx.channel
        )

        if channel is not None:
            await send(
                ctx,
                f"Spamming `{word}` in {channel.mention}",
                ephemeral=True,
            )
            repeat_count = integer
        else:
            await send(ctx, word)
            repeat_count = integer - 1

        for _ in range(repeat_count):
            await target_channel.send(word)

    # -------------------- Database Managment -------------------- #
    @slash_bot_config.command(
        name="add",
        description="Adds string to selected list.",
    )
    @app_commands.describe(
        collection="Target bot config list.",
        to_upload="Value to add to selected list.",
    )
    @app_commands.choices(
        collection=[app_commands.Choice(name=name, value=name) for name in DB_CHOICES]
    )
    @app_commands.check(is_owner)
    async def bot_config_add(
        self,
        ctx: discord.Interaction,
        collection: str,
        to_upload: str,
    ) -> None:
        """Method to add a string to a selected database collection.
        This method is only available to the bot owner.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        collection: str
            The name of the database collection to add the string to.
        to_upload: str
            The string to upload to the database.
        """
        await self._add_to_bot_config(ctx, collection, to_upload)

    @slash_bot_config.command(
        name="remove",
        description="Removes string from selected list.",
    )
    @app_commands.describe(
        collection="Target bot config list.",
        to_remove="Value to remove from selected list.",
    )
    @app_commands.choices(
        collection=[app_commands.Choice(name=name, value=name) for name in DB_CHOICES]
    )
    @app_commands.check(is_owner)
    async def bot_config_remove(
        self,
        ctx: discord.Interaction,
        collection: str,
        to_remove: str,
    ) -> None:
        """Method to remove a string from a selected database collection.
        This method is only available to the bot owner.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        collection: str
            The name of the database collection to remove the string from.
        to_remove: str
            The string to remove from the database.
        """
        await self._remove_from_bot_config(ctx, collection, to_remove)

    @slash_bot_config.command(
        name="show",
        description="Shows data from selected lists.",
    )
    @app_commands.describe(collection="Target bot config list.")
    @app_commands.choices(
        collection=[app_commands.Choice(name=name, value=name) for name in DB_CHOICES]
    )
    @app_commands.check(is_owner)
    async def bot_config_show(
        self,
        ctx: discord.Interaction,
        collection: str,
    ) -> None:
        """Method to show data from a selected database collection.
        This method is only available to the bot owner.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        collection: str
            The name of the database collection to show data from.
        """
        await self._show_bot_config(ctx, collection)

    async def _show_bot_config(self, ctx: discord.Interaction, collection: str) -> None:
        collection_db_name = DB_CHOICES[collection]
        collection_list = await self._bot.config_manager.get(
            collection_db_name, DB_LISTS
        )

        embed = discord.Embed(title=collection, color=COLOR_BLUE)
        embed.add_field(
            name=f"_{len(collection_list)} items_",
            value="\n".join(
                f"{i + 1}. {collection_list[i]}" for i in range(len(collection_list))
            ),
        )
        await send(ctx, embed=embed)

    async def _add_to_bot_config(
        self,
        ctx: discord.Interaction,
        collection: str,
        to_upload: str,
    ) -> None:
        collection_db_name = DB_CHOICES[collection]
        collection_list = await self._bot.config_manager.get(
            collection_db_name, DB_LISTS
        )

        if to_upload in collection_list:
            await send(
                ctx,
                embed=make_embed(f":x: `{to_upload}` is already in the list."),
            )
            return

        collection_list.append(to_upload)
        await self._bot.config_manager.save(collection_db_name, DB_LISTS)
        await send(
            ctx,
            embed=make_embed(
                f":white_check_mark: Added `{to_upload}` to {collection} list."
            ),
        )

    async def _remove_from_bot_config(
        self,
        ctx: discord.Interaction,
        collection: str,
        to_remove: str,
    ) -> None:
        collection_db_name = DB_CHOICES[collection]
        collection_list = await self._bot.config_manager.get(
            collection_db_name, DB_LISTS
        )

        if to_remove not in collection_list:
            await send(
                ctx,
                embed=make_embed(f":x: `{to_remove}` is not in the list."),
            )
            return

        collection_list.pop(collection_list.index(to_remove))
        await self._bot.config_manager.save(collection_db_name, DB_LISTS)
        await send(
            ctx,
            embed=make_embed(
                f":white_check_mark: Removed `{to_remove}` from {collection} list."
            ),
        )


async def setup(bot: KexoBotClient) -> None:
    """Register general, admin, and bot configuration commands."""
    await bot.add_cog(CommandCog(bot))
