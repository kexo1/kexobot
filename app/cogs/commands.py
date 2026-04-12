from __future__ import annotations

import datetime
import logging
import os
import random
import sys
import time
from typing import Optional
from urllib.parse import urlparse

import asyncpraw.models
import discord
import httpx
import sonolink
from discord import app_commands
from discord.ext import commands
from pymongo import AsyncMongoClient

from app.__init__ import __version__
from app.classes.sfd_servers import SFDServers
from app.constants import (
    CHANNEL_ID_KEXO_SERVER,
    DB_CHOICES,
    DB_LISTS,
    MUSIC_SUPPORTED_PLATFORMS,
    SFD_TIMEZONE_CHOICE,
    SHITPOST_SUBREDDITS_ALL,
)
from app.response_handler import defer_interaction, send_interaction, send_response
from app.utils import (
    QueuePaginator,
    check_node_status,
    get_file_age,
    get_memory_usage,
    get_user_data,
    iso_to_timestamp,
    switch_node,
)

host_authors = []


async def is_owner(interaction: discord.Interaction) -> bool:
    return await interaction.client.is_owner(interaction.user)


class CommandCog(commands.Cog):
    """Cog that contains all main commands.

    This includes commands for:
    - Bot configuration
    - Node management
    - SFD servers
    - Reddit management
    - Bot info
    - Random number generator
    - Pick a random word from a list
    - Clear messages
    - Database management

    Parameters
    ----------
    bot: :class:`commands.Bot`
        The bot instance.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot
        self._session: httpx.AsyncClient = self._bot.session
        self._bot_config: AsyncMongoClient = self._bot.bot_config
        self._user_data_db: AsyncMongoClient = self._bot.user_data_db
        self._user_data: dict = self._bot.user_data
        self._temp_user_data: dict = self._bot.temp_user_data

        self._run_time = time.time()
        self._graphs_dir = os.path.join(os.getcwd(), "graphs")
        self._sfd_servers = SFDServers(self._bot_config, self._bot.session)

    slash_bot_config = app_commands.Group(
        name="bot_config",
        description="Update Bot Configuration",
        guild_ids=[CHANNEL_ID_KEXO_SERVER],
    )
    slash_node = app_commands.Group(
        name="node", description="Commands for managing nodes"
    )
    slash_reddit = app_commands.Group(
        name="reddit", description="Commands for reddit posts"
    )
    slash_sfd = app_commands.Group(
        name="sfd", description="Show Superfighters Deluxe stats and servers"
    )

    # -------------------- Node Managment -------------------- #
    @slash_node.command(
        name="manual_connect", description="Manually input Lavalink address"
    )
    @app_commands.describe(
        uri="Node hostname or IP address.",
        port="Lavalink port (1-65535).",
        password="Lavalink password.",
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def manual_connect(
        self,
        ctx: discord.Interaction,
        uri: str,
        port: app_commands.Range[int, 1, 65535],
        password: str,
    ) -> None:
        """Method to manually connect to a Lavalink server.

        This method is used to connect to a Lavalink server by providing the
        server's URI, port, and password. It checks if the server is reachable
        and if the connection is successful, it sets the node for the bot.
        If the connection fails, it sends an error message to the user.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        uri: str
            The URI of the Lavalink server.
        port: int
            The port of the Lavalink server.
        password: str
            The password for the Lavalink server.
        """
        await defer_interaction(ctx)
        node: sonolink.Node = await check_node_status(
            self._bot, f"{uri}:{str(port)}", password
        )

        if not node:
            await send_response(ctx, "NODE_CONNECT_FAILURE", uri=uri)
            return

        self._bot.node = node
        await send_response(ctx, "NODE_CONNECT_SUCCESS", ephemeral=False, uri=node.uri)

    @slash_node.command(
        name="reconnect",
        description="Automatically reconnect to available node",
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def reconnect_node(self, ctx: discord.Interaction) -> None:
        """Method to reconnect to an available Lavalink node.

        This method checks if the bot is connected to a voice channel and if so,
        it attempts to reconnect to the node. If the bot is not connected to a
        voice channel, it connects to the node and sets it as the current node.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        await defer_interaction(ctx)
        player: sonolink.Player = ctx.guild.voice_client

        if player:
            node: sonolink.Node | None = await switch_node(
                self._bot, player=player, play_after=False, send_success_message=False
            )
            if not node:
                await send_response(ctx, "NODE_CONNECT_FAILURE", uri="best available")
                return

            self._bot.node = node
            await send_response(
                ctx,
                "NODE_RECONNECT_TO_PLAYER_SUCCESS",
                ephemeral=False,
                uri=self._bot.node.uri,
            )
            return

        node: sonolink.Node | None = await self._bot.connect_node(guild_id=ctx.guild.id)
        if not node:
            await send_response(ctx, "NODE_CONNECT_FAILURE", uri="best available")
            return

        self._bot.node = node
        await send_response(
            ctx,
            "NODE_RECONNECT_SUCCESS",
            ephemeral=False,
            uri=self._bot.node.uri,
        )

    @slash_node.command(name="info", description="Information about connected node")
    async def node_info(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about the connected Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        node: sonolink.Node = self._bot.node
        try:
            node_info: sonolink.InfoResponsePayload = await node.fetch_info()
        except Exception:
            await send_response(ctx, "NO_NODE_INFO")
            return

        embed = discord.Embed(
            title=urlparse(node.uri).netloc,
            color=discord.Color.blue(),
        )
        plugins: sonolink.PluginResponsePayload = node_info.plugins
        unix_timestamp = int(iso_to_timestamp(str(node_info.build_time)).timestamp())

        embed.add_field(
            name="Plugins:",
            value=", ".join(f"{plugin.name}: {plugin.version}" for plugin in plugins),
            inline=False,
        )
        embed.add_field(name="Lavaplayer version:", value=node_info.lavaplayer)
        embed.add_field(name="Java version:", value=node_info.jvm)
        embed.add_field(name="Build time:", value=f"<t:{unix_timestamp}:D>")
        embed.add_field(name="Filters:", value=", ".join(node_info.filters))

        await send_interaction(ctx, embed=embed)

    @slash_node.command(
        name="supported_platforms",
        description="Supported music platforms in the current node",
    )
    async def node_supported_platforms(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display supported platforms of the connected Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        node: sonolink.Node = self._bot.node

        try:
            node_info: sonolink.InfoResponsePayload = await node.fetch_info()
        except Exception:
            await send_response(ctx, "NO_NODE_INFO")
            return

        plugins: sonolink.PluginResponsePayload = node_info.plugins
        youtube_plugin, lavasrc_plugin, lavasearch_plugin = False, False, False
        for plugin in plugins:
            if "lavasrc" in plugin.name:
                lavasrc_plugin = True
            if "youtube" in plugin.name or "yt-" in plugin.name:
                youtube_plugin = True
            if "lavasearch-plugin" in plugin.name:
                lavasearch_plugin = True

        embed = discord.Embed(
            title=urlparse(node.uri).netloc,
            color=discord.Color.blue(),
        )

        if lavasrc_plugin:
            supported_platforms_count = len(MUSIC_SUPPORTED_PLATFORMS)
        elif youtube_plugin:
            supported_platforms_count = 3
        else:
            embed.description = "No platforms supported"
            supported_platforms_count = 0

        if not lavasearch_plugin:
            no_search_warning = "(no search plugin, only direct links)"
        else:
            no_search_warning = ""

        if supported_platforms_count != 0:
            embed.add_field(
                name=f"_{supported_platforms_count} platforms supported {no_search_warning}_",
                value="\n".join(
                    f"{i + 1}. {MUSIC_SUPPORTED_PLATFORMS[i]}"
                    for i in range(supported_platforms_count)
                ),
            )

        if lavasrc_plugin:
            embed.set_footer(
                text=(
                    "unlikely - depends if node owner added API key for each platform"
                )
            )

        await send_interaction(ctx, embed=embed)

    @slash_node.command(name="players", description="Information about node players.")
    async def node_players(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about players connected to the Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        nodes: list[sonolink.Node] = list(self._bot.sonolink_client.nodes)

        if not nodes:
            await send_response(ctx, "NO_NODES_CONNECTED")
            return
        # Would change to dict
        server_name = []
        playing = []
        node_uri = []

        for node in nodes:
            try:
                players: sonolink.PlayerResponsePayload = await node.fetch_players()
            except Exception:
                continue

            if not players:
                continue

            embed = discord.Embed(
                title="Node Players",
                color=discord.Color.blue(),
            )

            for player in players:
                guild: discord.Guild = await self._bot.fetch_guild(player.guild_id)
                server_name.append(guild.name)
                playing.append(player.track.title if player.track else "Nothing")
                node_uri.append(node.uri)

        if not server_name:
            await send_response(ctx, "NO_PLAYERS_CONNECTED")
            return

        embed.add_field(name="Server:ㅤㅤㅤㅤ", value="\n".join(server_name))
        embed.add_field(name="Playing:ㅤㅤ", value="\n".join(playing))
        embed.add_field(name="Node:", value="\n".join(node_uri))

        embed.set_footer(text=f"Total players: {len(players)}")
        await send_interaction(ctx, embed=embed)

    # -------------------- SFD Servers -------------------- #
    @slash_sfd.command(
        name="servers", description="Fetches Superfighters Deluxe servers."
    )
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def get_sfd_servers(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about available SFD servers.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        servers_dict, all_players = await self._sfd_servers.get_servers_info()
        if not servers_dict:
            await send_response(ctx, "SFD_SERVERS_NOT_FOUND")
            return

        # Cleaning up the server names and maps
        servers_dict["server_name"] = [s.strip() for s in servers_dict["server_name"]]
        servers_dict["maps"] = [m.strip() for m in servers_dict["maps"]]

        server_name_char, map_char, stopped_at = 0, 0, 0
        pages = []

        for i in range(len(servers_dict["server_name"])):
            server_name_char += len(servers_dict["server_name"][i])
            map_char += len(servers_dict["maps"][i])

            embed = discord.Embed(
                title="Available Servers",
                color=discord.Color.blue(),
            )
            embed.set_footer(text=f"Total players: {all_players}")
            additional_char = i - stopped_at
            if (
                server_name_char + additional_char > 1024
                or map_char + additional_char > 1024
            ) or (i == len(servers_dict["server_name"]) - 1 and not pages):
                embed.add_field(
                    name="Servers:",
                    value="\n".join(servers_dict["server_name"][stopped_at : i - 1]),
                )
                embed.add_field(
                    name="Current Map:",
                    value="\n".join(servers_dict["maps"][stopped_at : i - 1]),
                )
                embed.add_field(
                    name="Players:",
                    value="\n".join(servers_dict["players"][stopped_at : i - 1]),
                )
                stopped_at = i
                server_name_char, map_char = 0, 0
                pages.append(embed)

        if len(pages) == 1:
            await send_interaction(ctx, embed=embed)
        else:
            view = QueuePaginator(pages)
            await send_interaction(ctx, embed=pages[0], view=view)

    @slash_sfd.command(name="server_info", description="Find searched server.")
    @app_commands.describe(search="Server name to search for.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def get_sfd_server_info(
        self,
        ctx: discord.Interaction,
        search: app_commands.Range[str, 1, 80],
    ) -> None:
        """Method to fetch and display information about a specific SFD server.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        search: str
            The name of the server to search for.
        """
        server = await self._sfd_servers.get_server(search)
        if not server:
            await send_response(ctx, "SFD_SERVER_NOT_FOUND")
            return

        embed = discord.Embed(
            title=server.server_name,
            description=server.description,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Version: {server.version}")
        embed.add_field(name="Players:ㅤㅤ", value=server.players)
        embed.add_field(name="Max Players:ㅤㅤ", value=server.max_players)
        embed.add_field(name="Bots:ㅤㅤ", value=server.bots)
        embed.add_field(name="Map Name:ㅤㅤ", value=server.map_name)
        embed.add_field(name="Has Password:ㅤㅤ", value=server.has_password)
        embed.add_field(name="Game Mode:ㅤㅤ", value=server.game_mode)
        await send_interaction(ctx, embed=embed)

    @slash_sfd.command(
        name="activity",
        description="Shows graph of SFD servers activity.",
    )
    @app_commands.describe(
        graph_range="Time span for the graph.",
        timezone="Timezone used for graph labels.",
    )
    @app_commands.choices(
        graph_range=[
            app_commands.Choice(name="Day", value="Day"),
            app_commands.Choice(name="Week", value="Week"),
        ],
        timezone=[
            app_commands.Choice(name=timezone, value=timezone)
            for timezone in SFD_TIMEZONE_CHOICE
        ],
    )
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def get_sfd_graph(
        self,
        ctx: discord.Interaction,
        graph_range: str,
        timezone: str = "New_York",
    ) -> None:
        """Method to fetch and display a graph of SFD server activity.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        graph_range: str
            The range of the graph (Day or Week).
        timezone: str
            The timezone to adjust time-based data on the graph.
        """
        await defer_interaction(ctx)

        if graph_range == "Day":
            filename = f"sfd_activity_day_{timezone}.png"
            generator = self._sfd_servers.generate_graph_day
        else:
            filename = f"sfd_activity_week_{timezone}.png"
            generator = self._sfd_servers.generate_graph_week

        image_location = os.path.join(self._graphs_dir, filename)

        if not os.path.exists(image_location) or get_file_age(image_location) >= 3600:
            await generator(timezone)

        file = discord.File(image_location, filename=filename)
        await send_interaction(ctx, files=[file], embed=None)

    # -------------------- SFD Hosting -------------------- #
    @slash_sfd.command(
        name="host",
        description="Creates hosting embed, you can also choose some optional info.",
    )
    @app_commands.describe(
        server_name="Hosting title shown in the embed.",
        duration="How long the session should run.",
        ping_role="Role to ping for the hosting announcement.",
        branch="Game branch/version stream.",
        version="Version suffix (optional).",
        password="Server password (optional).",
        region="Server region (optional).",
        scripts="Enabled scripts/mods (optional).",
        slots="Player slot count.",
        image="Optional thumbnail image URL.",
    )
    @app_commands.choices(
        duration=[
            app_commands.Choice(name="As long as I want", value="As long as I want"),
            app_commands.Choice(name="15 minutes", value="15 minutes"),
            app_commands.Choice(name="30 minutes", value="30 minutes"),
            app_commands.Choice(name="1 hour", value="1 hour"),
            app_commands.Choice(name="1-2 hours", value="1-2 hours"),
            app_commands.Choice(name="2-4 hours", value="2-4 hours"),
            app_commands.Choice(name="4+ hours", value="4+ hours"),
            app_commands.Choice(name="24/7", value="24/7"),
        ],
        branch=[
            app_commands.Choice(name="Stable", value="Stable"),
            app_commands.Choice(name="Beta", value="Beta"),
            app_commands.Choice(name="Redux", value="Redux"),
        ],
    )
    @app_commands.checks.cooldown(1, 300, key=lambda i: i.user.id)
    async def host(
        self,
        ctx: discord.Interaction,
        server_name: str,
        duration: str,
        ping_role: discord.Role,
        branch: Optional[str] = None,
        version: Optional[str] = None,
        password: Optional[str] = None,
        region: Optional[str] = None,
        scripts: Optional[str] = None,
        slots: app_commands.Range[int, 1, 16] = 8,
        image: Optional[str] = None,
    ) -> None:
        """Method to create a hosting embed for SFD servers.

        This method creates an embed with information about the server being hosted.
        It also uses class `HostView` to create a button for the user to stop hosting.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        server_name: str
            The name of the server being hosted.
        duration: str
            The duration for which the server will be hosted.
        branch: str
            The branch of the server (Stable, Beta, Redux).
        version: str
            The version of the server being hosted.
        password: str
            The password for the server.
        region: str
            The region of the server.
        scripts: str
            The scripts enabled on the server.
        slots: int
            The number of slots on the server (default is 8).
        ping_role: bool
            Whether to ping role or not (default is None).
        image: str
            The URL of the image to be used in the embed.
        """
        author = ctx.user

        if author in host_authors:
            await send_response(ctx, "ALREADY_HOSTING")
            return None

        host_authors.append(author.name)

        embed = discord.Embed(
            title=server_name,
            color=discord.Color.from_rgb(r=0, g=200, b=0),
        )

        embed.set_author(
            icon_url=author.avatar.url, name=f"{author.name} is now hosting!"
        )

        if not branch:
            branch = "Stable"
        version = f"{branch} {version}" if version else branch or ""

        timestamp = int(time.time())  # Current time in seconds
        timestamp = f"<t:{timestamp}:R>"

        embed.add_field(
            name="Status:ㅤㅤ", value="**ONLINE** <a:online:1355562936919392557>"
        )
        embed.add_field(name="Duration:ㅤㅤ", value=duration)
        embed.add_field(name="Uptime:ㅤㅤㅤㅤ", value=timestamp)
        embed.add_field(name="Version:ㅤㅤ", value=version)
        embed.add_field(name="Slots:ㅤㅤ", value=slots)
        embed.add_field(name="Region:ㅤㅤ", value=region if region else "Not specified")

        if password:
            embed.add_field(
                name="Password:",
                value=password if password else "Not specified",
            )

        if scripts:
            embed.add_field(
                name="Scripts:", value=scripts if scripts else "Not specified"
            )

        if image:
            if image.endswith((".jpg", ".jpeg", ".png", ".gif")):
                embed.set_thumbnail(url=image)
            else:
                await send_response(ctx, "INCORRECT_IMAGE_URL")
                return None

        if ping_role:
            try:
                await send_interaction(ctx, ping_role.mention)
            except AttributeError:
                await send_response(ctx, "CANT_PING_ROLE")
                return None

        view = HostView(author=author)
        response = await send_interaction(ctx, embed=embed, view=view)
        if response is None:
            response = await ctx.original_response()
        view.message = response
        return None

    # -------------------- Discord functions -------------------- #
    @app_commands.command(name="info", description="Shows bot info.")
    async def info(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about the bot.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        embed = discord.Embed(title="KexoBOT Info", color=discord.Color.blue())
        embed.add_field(
            name="Run time:ㅤㅤ",
            value=f"{str(datetime.timedelta(seconds=round(int(time.time()) - self._run_time)))}",
        )
        embed.add_field(name="Ping:ㅤㅤ", value=f"{round(self._bot.latency * 1000)} ms")
        embed.add_field(name="Memory usage:ㅤㅤ", value=f"{get_memory_usage():.2f} MB")
        embed.add_field(name="Online nodes:ㅤ", value=self._bot.get_online_nodes())
        embed.add_field(name="Available nodes:ㅤ", value=self._bot.get_available_nodes())
        embed.add_field(name="Joined servers:ㅤ", value=len(self._bot.guilds))
        embed.add_field(name="Bot version:", value=__version__)
        embed.add_field(name="Discord.py version:ㅤㅤ", value=discord.__version__)
        embed.add_field(
            name="Python version:",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        embed.set_footer(text="Bot owner: _kexo")
        await send_interaction(ctx, embed=embed)

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
        await send_interaction(ctx, f"I chose `{random.randint(integer1, integer2)}`")

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
        words = words.split()
        await send_interaction(ctx, "I chose " + "`" + str(random.choice(words)) + "`")

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
        await send_interaction(
            ctx, f"`{integer}` messages cleared ✅", delete_after=20, ephemeral=True
        )
        await ctx.channel.purge(limit=integer)

    @app_commands.command(
        name="spam", description="Spams a word (bot owner only, max 50)."
    )
    @app_commands.describe(
        word="Word to spam.",
        integer="How many times to send it (1-50).",
        channel="Optional text channel.",
    )
    @app_commands.checks.check(is_owner)
    async def spam(
        self,
        ctx: discord.Interaction,
        word: str,
        integer: app_commands.Range[int, 1, 50],
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Spam a word in the current channel or a selected text channel."""
        target_channel: discord.abc.Messageable = channel or ctx.channel

        if channel is not None:
            await send_interaction(
                ctx,
                f"Spamming `{word}` in {channel.mention}",
                ephemeral=True,
            )
            repeat_count = integer
        else:
            await send_interaction(ctx, word)
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
    @app_commands.checks.check(is_owner)
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
    @app_commands.checks.check(is_owner)
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
    @app_commands.checks.check(is_owner)
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

    @slash_reddit.command(
        name="settings",
        description="Change your list of subreddits.",
    )
    async def edit_subreddit(self, ctx: discord.Interaction) -> None:
        """Method to edit the list of subreddits for the user.

        This method creates a view with a select menu for the user to choose
        subreddits. The currently selected subreddits are pre-checked.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        user_id = ctx.user.id
        user_data, _ = await get_user_data(self._bot, ctx)
        current_subreddits = user_data["reddit"]["subreddits"]
        # Create a view with select menu for all available subreddits
        view = SubredditSelectorView(current_subreddits, self._bot, user_id)

        embed = discord.Embed(
            title="Select Subreddits",
            description="Select the subreddits you want to see in shitpost command."
            " Currently selected subreddits are pre-checked.",
            color=discord.Color.blue(),
        )

        await send_interaction(ctx, embed=embed, view=view, ephemeral=True)

    async def _show_bot_config(self, ctx, collection: str) -> None:
        bot_config: dict = await self._bot_config.find_one(DB_LISTS)
        collection_name = collection
        collection: list = bot_config[DB_CHOICES[collection]]

        embed = discord.Embed(title=collection_name, color=discord.Color.blue())
        embed.add_field(
            name=f"_{len(collection)} items_",
            value="\n".join(
                f"{i + 1}. {collection[i]}" for i in range(len(collection))
            ),
        )
        await send_interaction(ctx, embed=embed)

    async def _add_to_bot_config(self, ctx, collection: str, to_upload: str) -> None:
        bot_config: dict = await self._bot_config.find_one(DB_LISTS)
        collection_name = collection
        collection_db_name = DB_CHOICES[collection]
        collection: list = bot_config[collection_db_name]

        if to_upload in collection:
            await send_response(ctx, "DB_ALREADY_IN_LIST", to_upload=to_upload)
            return

        collection.append(to_upload)
        await self._bot_config.update_one(
            DB_LISTS, {"$set": {collection_db_name: collection}}
        )
        await send_response(
            ctx,
            "DB_ADDED",
            to_upload=to_upload,
            collection_name=collection_name,
        )

    async def _remove_from_bot_config(
        self, ctx, collection: str, to_remove: str
    ) -> None:
        bot_config: dict = await self._bot_config.find_one(DB_LISTS)
        collection_name = collection
        collection_db_name = DB_CHOICES[collection]
        collection: list = bot_config[collection_db_name]

        if to_remove not in collection:
            await send_response(ctx, "DB_NOT_IN_LIST", to_remove=to_remove)
            return

        collection.pop(collection.index(to_remove))
        await self._bot_config.update_one(
            DB_LISTS, {"$set": {collection_db_name: collection}}
        )
        await send_response(
            ctx,
            "DB_REMOVED",
            to_remove=to_remove,
            collection_name=collection_name,
        )


class HostView(discord.ui.View):
    """View for the hosting embed.

    This view contains a button that allows the user to stop hosting.
    When the button is clicked, it disables the embed and removes the
    user from the list of host authors. If the button is not clicked
    within 12 hours, the embed is disabled and a message is sent to the user.

    Parameters
    ----------
    author: :class:`discord.Member`
        The author of the hosting embed.
    """

    def __init__(self, author: discord.Member):
        super().__init__(timeout=43200)
        self._author = author

    # noinspection PyUnusedLocal
    @discord.ui.button(
        style=discord.ButtonStyle.gray, label="I stopped hosting.", emoji="📣"
    )
    async def button_callback(
        self, interaction: discord.Interaction, button: discord.Button
    ) -> None:
        """Callback for the button in the hosting embed.

        This method is called when the button is clicked.
        It checks if the user who clicked the button is the same as the author of the embed.
        If so, it disables the embed and removes the author from the list of host authors.
        If not, it sends a response indicating that the user is not the author of the embed.

        Parameters
        ----------
        button: :class:`discord.Button`
            The button that was clicked.
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        if interaction.user.name in host_authors:
            embed = await self._disable_embed()
            await interaction.response.edit_message(embed=embed, view=None)
            host_authors.pop(host_authors.index(self._author.name))
            return

        await send_response(interaction, "NOT_EMBED_AUTHOR")

    async def on_timeout(self) -> None:
        """Method called when the view times out.

        This method disables the embed and sends a message to the
        author indicating that they forgot to click the button.
        It also removes the author from the list of host authors.
        """
        embed = await self._disable_embed()
        await self.message.edit(embed=embed, view=None)
        await self._author.send(
            f"You forgot to click button in {self.message.jump_url} you {
                random.choice(('dumbass', 'retard', 'prick', 'cunt', 'shitling'))
            }."
            "\nhttps://tenor.com/view/zombie-screaming-gif-12431778992096703656"
        )
        host_authors.pop(host_authors.index(self._author.name))

    async def _disable_embed(self) -> discord.Embed:
        self.stop()

        embed = self.message.embeds[0]
        embed.set_author(
            icon_url=self._author.avatar.url,
            name=f"{self._author.name} is no longer hosting.",
        )
        embed.color = discord.Color.from_rgb(r=200, g=0, b=0)
        embed.set_field_at(
            0,
            name="Status:ㅤㅤ",
            value="**OFFLINE** <:offline:1355571345613787296>",
        )

        timestamp = embed.fields[2].value.replace("R", "t")
        embed.set_field_at(2, name="Hosted at:ㅤ", value=timestamp)
        return embed


class SubredditSelectorView(discord.ui.View):
    """Class which manages selector

    Parameters
    ----------
    current_subreddits: set
        A set of currently selected subreddits.
    bot: :class:`discord.Bot`
        The bot instance.
    user_id: int
        The ID of the user who is editing the subreddits.
    """

    def __init__(
        self, current_subreddits: set, bot: commands.Bot, user_id: int
    ) -> None:
        super().__init__(timeout=600)
        self._current_subreddits = current_subreddits
        self.selected_subreddits = set()
        self._bot = bot
        self._user_id = user_id

        self._user_data = self._bot.user_data
        self._user_data_db = self._bot.user_data_db
        self._temp_user_data = self._bot.temp_user_data

        self._select = SubredditSelect(current_subreddits)
        self._save_button = discord.ui.Button(
            label="Save Changes",
            style=discord.ButtonStyle.green,
            custom_id="save_changes",
        )
        self._save_button.callback = self.save_changes

        nsfw_status = self._user_data[user_id]["reddit"]["nsfw_posts"]
        self._nsfw_button = discord.ui.Button(
            label="NSFW ON" if nsfw_status else "NSFW OFF",
            style=(
                discord.ButtonStyle.green
                if not nsfw_status
                else discord.ButtonStyle.red
            ),
            custom_id="nsfw_posts",
        )
        self._nsfw_button.callback = self.nsfw_posts

        self.add_item(self._select)
        self.add_item(self._save_button)
        self.add_item(self._nsfw_button)

    async def nsfw_posts(self, interaction: discord.Interaction) -> None:
        """Callback for the NSFW button.

        This method toggles the NSFW status of the user and updates the database.
        It also updates the button label and style to reflect the new status.

        Parameters
        ----------
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        nsfw_status = not self._user_data[self._user_id]["reddit"]["nsfw_posts"]

        self._user_data[self._user_id]["reddit"]["nsfw_posts"] = nsfw_status
        await self._user_data_db.update_one(
            {"_id": self._user_id}, {"$set": self._user_data[self._user_id]}
        )

        self._nsfw_button.label = "NSFW ON" if nsfw_status else "NSFW OFF"
        self._nsfw_button.style = (
            discord.ButtonStyle.green if not nsfw_status else discord.ButtonStyle.red
        )

        await interaction.response.edit_message(view=self)

    async def save_changes(self, interaction: discord.Interaction) -> None:
        """Callback for the save changes button.

        This method saves the selected subreddits to the database and updates the multireddit
        if the user has one. It also sends a response to the user indicating that the changes
        were saved successfully.

        Parameters
        ----------
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        if self.selected_subreddits:
            self._user_data[self._user_id]["reddit"]["subreddits"] = list(
                self.selected_subreddits
            )

            await self._user_data_db.update_one(
                {"_id": self._user_id},
                {"$set": self._user_data[self._user_id]},
            )

            if self._user_id in self._temp_user_data:
                await self._update_multireddit()

        embed = discord.Embed(
            title="Changes Saved",
            description="Successfully updated your subreddit list"
            f" to `{len(self.selected_subreddits)}` subreddits.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await interaction.response.edit_message(embed=embed, view=None, delete_after=20)

    async def on_timeout(self) -> None:
        self.disable_all_items()
        self.stop()

    async def _update_multireddit(self) -> None:
        multireddit: asyncpraw.models.Multireddit = self._temp_user_data[self._user_id][
            "reddit"
        ]["multireddit"]
        await multireddit.load()
        added_subreddits = set()

        for subreddit in multireddit.subreddits:
            if subreddit.display_name not in self.selected_subreddits:
                await multireddit.remove(subreddit)
                continue
            added_subreddits.add(subreddit.display_name)

        for subreddit in self.selected_subreddits:
            if subreddit in added_subreddits:
                continue

            try:
                await multireddit.add(await self._bot.reddit_agent.subreddit(subreddit))
            except asyncpraw.exceptions.RedditAPIException:
                logging.warning(f"[Reddit] Failed to add subreddit `{subreddit}`")


class SubredditSelect(discord.ui.Select):
    """Class to create a select menu for subreddit selection.

    This class inherits from discord.ui.Select and is used to create a select menu
    for the user to choose subreddits. The currently selected subreddits are pre-checked.

    Parameters
    ----------
    current_subreddits: set
        A set of currently selected subreddits.
    """

    def __init__(self, current_subreddits: set):
        options = [
            discord.SelectOption(
                label=f"r/{subreddit}",
                value=subreddit,
                default=subreddit in current_subreddits,
                description=f"Select to {'remove' if subreddit in current_subreddits else 'add'}"
                " this subreddit",
            )
            for subreddit in SHITPOST_SUBREDDITS_ALL
        ]

        super().__init__(
            placeholder="Select subreddits to toggle",
            max_values=len(SHITPOST_SUBREDDITS_ALL),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Callback for the subreddit select menu.

        This method is called when the user selects or deselects a subreddit.
        It updates the selected subreddits based on the user's choices.

        Parameters
        ----------
        interaction: :class:`discord.Interaction`
            The interaction that triggered the select menu callback.
        """
        self.view.selected_subreddits = set()
        for subreddit in self.values:
            self.view.selected_subreddits.add(subreddit)
        await interaction.response.defer()


async def setup(bot: commands.Bot):
    """Setup function to add the CommandCog to the bot."""
    await bot.add_cog(CommandCog(bot))
