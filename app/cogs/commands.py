import datetime
import os
import random
import sys
import time
from urllib.parse import urlparse

import aiohttp
import asyncpraw.models
import discord
import httpx
import wavelink
from discord.commands import slash_command, guild_only, option
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

from app.__init__ import __version__
from app.classes.sfd_servers import SFDServers
from app.constants import (
    DB_LISTS,
    XTC_SERVER,
    KEXO_SERVER,
    DB_CHOICES,
    SFD_TIMEZONE_CHOICE,
    SHITPOST_SUBREDDITS_ALL,
    SUPPORTED_PLATFORMS,
)
from app.response_handler import send_response
from app.utils import (
    get_memory_usage,
    iso_to_timestamp,
    get_file_age,
    check_node_status,
    get_user_data,
    switch_node,
)

host_authors = []


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
        self._bot_config: AsyncIOMotorClient = self._bot.bot_config
        self._user_data_db: AsyncIOMotorClient = self._bot.user_data_db
        self._user_data: dict = self._bot.user_data
        self._temp_user_data: dict = self._bot.temp_user_data

        self._run_time = time.time()
        self._graphs_dir = os.path.join(os.getcwd(), "graphs")
        self._sfd_servers = SFDServers(self._bot_config, self._bot.session)

    slash_bot_config = discord.SlashCommandGroup(
        "bot_config", "Update Bot Configuration"
    )
    slash_node = discord.SlashCommandGroup("node", "Commands for managing nodes")
    slash_reddit = discord.SlashCommandGroup("reddit", "Commands for reddit posts")
    slash_sfd = discord.SlashCommandGroup(
        "sfd", "Show Superfighters Deluxe stats and servers"
    )

    # -------------------- Node Managment -------------------- #
    @slash_node.command(
        name="manual_connect", description="Manually input Lavalink adress"
    )
    @guild_only()
    @option(
        "uri",
        description="Lavalink server full URL",
        required=True,
    )
    @option("port", description="Lavalink server port.", required=True)
    @option("password", description="Lavalink server password.", required=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def manual_connect(
        self, ctx: discord.ApplicationContext, uri: str, port: int, password: str
    ) -> None:
        """Method to manually connect to a Lavalink server.

        This method is used to connect to a Lavalink server by providing the
        server's URI, port, and password. It checks if the server is reachable
        and if the connection is successful, it sets the node for the bot.
        If the connection fails, it sends an error message to the user.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        uri: str
            The URI of the Lavalink server.
        port: int
            The port of the Lavalink server.
        password: str
            The password for the Lavalink server.
        """
        await ctx.defer()
        node: wavelink.Node = await check_node_status(
            self._bot, f"{uri}:{str(port)}", password
        )

        if not node:
            await send_response(ctx, "NODE_CONNECT_FAILURE", uri=uri)
            return

        self._bot.node = node
        await send_response(
            ctx, "NODE_CONNECT_SUCCESS", ephemeral=False, uri=node[0].uri
        )

    @slash_node.command(
        name="reconnect", description="Automatically reconnect to avaiable node"
    )
    @guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def recconect_node(self, ctx: discord.ApplicationContext) -> None:
        """Method to reconnect to an available Lavalink node.

        This method checks if the bot is connected to a voice channel and if so,
        it attempts to reconnect to the node. If the bot is not connected to a
        voice channel, it connects to the node and sets it as the current node.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        await ctx.defer()
        player: wavelink.Player = ctx.voice_client

        if player:
            node: wavelink.Node = await switch_node(
                self._bot.connect_node, player=player, play_after=False
            )
            self._bot.node = node
            await send_response(
                ctx,
                "NODE_RECONNECT_TO_PLAYER_SUCCESS",
                ephemeral=False,
                uri=self._bot.node.uri,
            )
        else:
            node: wavelink.Node = await self._bot.connect_node(guild_id=ctx.guild_id)
            self._bot.node = node
            await send_response(
                ctx, "NODE_RECONNECT_SUCCESS", ephemeral=False, uri=self._bot.node.uri
            )

    @slash_node.command(name="info", description="Information about connected node")
    async def node_info(self, ctx: discord.ApplicationContext) -> None:
        """Method to fetch and display information about the connected Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        node: wavelink.Node = self._bot.node
        node_info: wavelink.InfoResponsePayload = await node.fetch_info()
        embed = discord.Embed(
            title=urlparse(node.uri).netloc,
            color=discord.Color.blue(),
        )
        plugins: wavelink.PluginResponsePayload = node_info.plugins
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

        await ctx.respond(embed=embed)

    @slash_node.command(
        name="supported_platforms",
        description="Supported music platforms in the current node",
    )
    async def node_supported_platforms(self, ctx: discord.ApplicationContext) -> None:
        """Method to fetch and display supported platforms of the connected Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        node: wavelink.Node = self._bot.node
        node_info: wavelink.InfoResponsePayload = await node.fetch_info()

        plugins: wavelink.PluginResponsePayload = node_info.plugins
        youtube_plugin, lavasrc_plugin = False, False
        for plugin in plugins:
            if "lavasrc" in plugin.name:
                lavasrc_plugin = True
            if "youtube" in plugin.name or "yt-" in plugin.name:
                youtube_plugin = True

        embed = discord.Embed(
            title=urlparse(node.uri).netloc,
            color=discord.Color.blue(),
        )
        if youtube_plugin and lavasrc_plugin:
            embed.add_field(
                name=f"_{len(SUPPORTED_PLATFORMS)} platforms supported_",
                value="\n".join(
                    f"{i + 1}. {SUPPORTED_PLATFORMS[i]}"
                    for i in range(len(SUPPORTED_PLATFORMS))
                ),
            )

        elif youtube_plugin:
            embed.add_field(
                name="_3 platforms supported_",
                value="\n".join(f"{i + 1}. {SUPPORTED_PLATFORMS[i]}" for i in range(3)),
            )
        else:
            embed.description = "No platforms supported"

        embed.set_footer(
            text="unlikely - depends if node owner added API key for each platform"
            if lavasrc_plugin
            else ""
        )
        await ctx.respond(embed=embed)

    @slash_node.command(name="players", description="Information about node players.")
    async def node_players(self, ctx: discord.ApplicationContext) -> None:
        """Method to fetch and display information about players connected to the Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        nodes: dict[str, wavelink.Node] = wavelink.Pool.nodes.values()

        if not nodes:
            await send_response(ctx, "NO_NODES_CONNECTED")
            return
        # Would change to dict
        server_name = []
        playing = []
        node_uri = []

        for node in nodes:
            try:
                players: wavelink.PlayerResponsePayload = await node.fetch_players()
            except (
                wavelink.exceptions.LavalinkException,
                wavelink.exceptions.NodeException,
                aiohttp.client_exceptions.ServerDisconnectedError,
                aiohttp.client_exceptions.ClientConnectorError,
            ):
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
        await ctx.respond(embed=embed)

    # -------------------- SFD Servers -------------------- #
    @slash_sfd.command(
        name="servers", description="Fetches Superfighters Deluxe servers."
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def get_sfd_servers(self, ctx: discord.ApplicationContext) -> None:
        """Method to fetch and display information about available SFD servers.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        servers_dict, all_players = await self._sfd_servers.get_servers_info()
        if not servers_dict:
            await send_response(ctx, "SFD_SERVERS_NOT_FOUND")
            return

        embed = discord.Embed(
            title="Available Servers",
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Total players: {all_players}")
        embed.add_field(name="Servers:", value="\n".join(servers_dict["server_name"]))
        embed.add_field(name="Current Map:", value="\n".join(servers_dict["maps"]))
        embed.add_field(name="Players:", value="\n".join(servers_dict["players"]))
        await ctx.respond(embed=embed)

    @slash_sfd.command(name="server_info", description="Find searched server.")
    @option("server", description="Server name.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def get_sfd_server_info(
        self, ctx: discord.ApplicationContext, search: str
    ) -> None:
        """Method to fetch and display information about a specific SFD server.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        search: str
            The name of the server to search for.
        """
        server = await self._sfd_servers.get_server(search)
        if not server:
            await send_response(ctx, "SFD_SERVER_NOT_FOUND")
            return

        print(server)

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
        await ctx.respond(embed=embed)

    @slash_sfd.command(
        name="activity",
        description="Shows graph of SFD servers activity.",
    )
    @option(
        "graph_range",
        description="Range of Graph.",
        required=True,
        choices=["Day", "Week"],
    )
    @option(
        "timezone",
        description="Timezone to properly adjust time-based data on graph, default is New York",
        required=False,
        choices=SFD_TIMEZONE_CHOICE,
    )
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def get_sfd_graph(
        self,
        ctx: discord.ApplicationContext,
        graph_range: str,
        timezone: str = "New_York",
    ) -> None:
        """Method to fetch and display a graph of SFD server activity.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        graph_range: str
            The range of the graph (Day or Week).
        timezone: str
            The timezone to adjust time-based data on the graph.
        """
        await ctx.defer()

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
        await ctx.respond(files=[file], embed=None)

    # -------------------- SFD Hosting -------------------- #
    @slash_sfd.command(
        name="host",
        description="Creates hosting embed, you can also choose some optional info.",
        guild_ids=[XTC_SERVER, KEXO_SERVER],
    )
    @option("server_name", description="Your server name.")
    @option(
        "duration",
        description="How long are you going to be hositng.",
        choices=[
            "As long as I want",
            "15 minutes",
            "30 minutes",
            "1 hour",
            "1–2 hours",
            "2–4 hours",
            "4+ hours",
            "24/7",
        ],
    )
    @option(
        "branch",
        description="If you're hosting on stable, beta, redux, default is stable.",
        choices=[
            "Stable",
            "Beta",
            "Redux",
        ],
        required=False,
    )
    @option(
        "version",
        description="Which version are you hosting on.",
        required=False,
    )
    @option(
        "ping",
        description="Should this embed ping @Exotic or not, default is True",
        required=False,
    )
    @option("password", description="Server password.", required=False)
    @option("region", description="Server region.", required=False)
    @option("scripts", description="Which scripts are enabled.", required=False)
    @option("slots", description="How many server slots, default is 8", required=False)
    @option(
        "image",
        description="Add custom image url for embed, needs to end with .png, .gif and etc.",
        required=False,
    )
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def host(
        self,
        ctx: discord.ApplicationContext,
        server_name: str,
        duration: str,
        branch: str,
        version: str,
        password: str,
        region: str,
        scripts: str,
        slots: int = 8,
        ping: bool = True,
        image: str = None,
    ) -> None:
        """Method to create a hosting embed for SFD servers.

        This method creates an embed with information about the server being hosted.
        It also uses class `HostView` to create a button for the user to stop hosting.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
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
        ping: bool
            Whether to ping the @Exotic role or not (default is True).
        image: str
            The URL of the image to be used in the embed.
        """
        author = ctx.author

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
                name="Password:", value=password if password else "Not specified"
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

        if ping:
            try:
                role = discord.utils.get(ctx.guild.roles, name="Exotic")
                await ctx.send(role.mention)
            except AttributeError:
                await send_response(ctx, "CANT_PING_ROLE")
                return None

        view = HostView(author=author)
        await ctx.respond(embed=embed, view=view)

        interaction = await ctx.interaction.original_response()
        view.message = await ctx.channel.fetch_message(interaction.id)
        return None

    # -------------------- Discord functions -------------------- #
    @slash_command(name="info", description="Shows bot info.")
    async def info(self, ctx: discord.ApplicationContext) -> None:
        """Method to fetch and display information about the bot.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
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
        embed.add_field(name="Available nodes:ㅤ", value=self._bot.get_avaiable_nodes())
        embed.add_field(name="Joined servers:ㅤ", value=len(self._bot.guilds))
        embed.add_field(name="Bot version:", value=__version__)
        embed.add_field(name="Py-cord version:ㅤㅤ", value=discord.__version__)
        embed.add_field(
            name="Python version:",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        embed.set_footer(text="Bot owner: _kexo")
        await ctx.respond(embed=embed)

    @slash_command(name="random_number", description="Choose number between intervals.")
    async def random_number(
        self, ctx: discord.ApplicationContext, ineteger1: int, ineteger2: int
    ) -> None:
        """Method to generate a random number between two integers.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        ineteger1: int
            The first integer of the range.
        ineteger2: int
            The second integer of the range.
        """
        if ineteger1 > ineteger2:
            ineteger2, ineteger1 = ineteger1, ineteger2
        await ctx.respond(f"I chose `{random.randint(ineteger1, ineteger2)}`")

    @slash_command(
        name="pick",
        description="Selects one word, words needs to be separated by space.",
    )
    @option("words", description="Seperate words by space.")
    async def pick(self, ctx, words: str) -> None:
        """Method to pick a random word from a list of words.
        Parameter is a string of words separated by spaces,
        but it is split into a list.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        words: str
            The list of words separated by spaces.
        """
        words = words.split()
        await ctx.respond("I chose " + "`" + str(random.choice(words)) + "`")

    @slash_command(name="clear-messages", description="Clears messages, max 50 (Admin)")
    @discord.default_permissions(administrator=True)
    @option("integer", description="Max is 50.", min_value=1, max_value=50)
    async def clear(self, ctx: discord.ApplicationContext, integer: int) -> None:
        """Method to clear messages in a channel.
        This method is only available to administrators.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        integer: int
            The number of messages to clear (max 50).
        """
        await ctx.respond(
            f"`{integer}` messages cleared ✅", delete_after=20, ephemeral=True
        )
        await ctx.channel.purge(limit=integer)

    # -------------------- Database Managment -------------------- #
    @slash_bot_config.command(
        name="add",
        description="Adds string to selected list.",
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES.keys())
    @option("to_upload", description="String to upload.")
    async def bot_config_add(self, ctx, collection: str, to_upload: str) -> None:
        """Method to add a string to a selected database collection.
        This method is only available to the bot owner.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
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
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES.keys())
    @option("to_remove", description="String to remove.")
    async def bot_config_remove(self, ctx, collection: str, to_remove: str) -> None:
        """Method to remove a string from a selected database collection.
        This method is only available to the bot owner.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
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
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES.keys())
    async def bot_config_show(self, ctx, collection: str) -> None:
        """Method to show data from a selected database collection.
        This method is only available to the bot owner.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        collection: str
            The name of the database collection to show data from.
        """
        await self._show_bot_config(ctx, collection)

    @slash_reddit.command(
        name="settings",
        description="Change your list of subreddits.",
    )
    async def edit_subreddit(self, ctx: discord.ApplicationContext) -> None:
        """Method to edit the list of subreddits for the user.

        This method creates a view with a select menu for the user to choose
        subreddits. The currently selected subreddits are pre-checked.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command invocation.
        """
        user_id = ctx.author.id
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

        await ctx.respond(embed=embed, view=view, ephemeral=True)

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
        await ctx.respond(embed=embed)

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
            ctx, "DB_ADDED", to_upload=to_upload, collection_name=collection_name
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

        del collection[collection.index(to_remove)]
        await self._bot_config.update_one(
            DB_LISTS, {"$set": {collection_db_name: collection}}
        )
        await send_response(
            ctx, "DB_REMOVED", to_remove=to_remove, collection_name=collection_name
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
        super().__init__(timeout=43200, disable_on_timeout=True)
        self._author = author

    # noinspection PyUnusedLocal
    @discord.ui.button(
        style=discord.ButtonStyle.gray, label="I stopped hosting.", emoji="📣"
    )
    async def button_callback(
        self, button: discord.Button, interaction: discord.Interaction
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
            f"**You forgot to click button in {self.message.jump_url} you {
                random.choice(
                    (
                        'dumbass',
                        'retard',
                        'nitwit',
                        'prick',
                        'cunt',
                        'pillock',
                        'twat',
                    )
                )
            }.**"
        )
        del host_authors[host_authors.index(self._author.name)]

    async def _disable_embed(self) -> discord.Embed:
        self.stop()

        embed = self.message.embeds[0]
        embed.set_author(
            icon_url=self._author.avatar.url,
            name=f"{self._author.name} is no longer hosting.",
        )
        embed.color = discord.Color.from_rgb(r=200, g=0, b=0)
        embed.set_field_at(
            0, name="Status:ㅤㅤ", value="**OFFLINE** <:offline:1355571345613787296>"
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

    def __init__(self, current_subreddits: set, bot: discord.Bot, user_id: int) -> None:
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
                {"_id": self._user_id}, {"$set": self._user_data[self._user_id]}
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
                print(f"Failed to add subreddit `{subreddit}`")


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


def setup(bot: commands.Bot):
    """Setup function to add the CommandCog to the bot."""
    bot.add_cog(CommandCog(bot))
