import datetime
import random
import time
import sys
import os

import asyncpraw.models
import discord
import wavelink

from discord.ext import commands
from discord.commands import slash_command, guild_only, option
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlparse

from app.constants import (
    DB_LISTS,
    XTC_SERVER,
    KEXO_SERVER,
    DB_CHOICES,
    SFD_TIMEZONE_CHOICE,
    SHITPOST_SUBREDDITS_ALL,
)
from app.classes.sfd_servers import SFDServers
from app.utils import (
    get_memory_usage,
    iso_to_timestamp,
    get_file_age,
    check_node_status,
    generate_user_data,
)
from app.errors import send_error
from app.__init__ import __version__

host_authors = []


class Commands(commands.Cog):
    """Cog that contains all main commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot_config: AsyncIOMotorClient = self.bot.bot_config
        self.user_data_db: AsyncIOMotorClient = self.bot.user_data_db
        self.user_data: dict = self.bot.user_data
        self.temp_user_data: dict = self.bot.temp_user_data
        self.guild_temp_data: dict = self.bot.guild_temp_data

        self.run_time = time.time()
        self.graphs_dir = os.path.join(os.getcwd(), "graphs")
        self.sfd_servers = SFDServers(self.bot_config, self.bot.session)

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
        await ctx.defer()
        node: wavelink.Node = await check_node_status(
            self.bot, f"{uri}:{str(port)}", password
        )

        if not node:
            embed = discord.Embed(
                title="",
                description=f":x: Failed to connect to `{uri}`",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(embed=embed)
            return

        self.bot.node = node
        embed = discord.Embed(
            title="",
            description=f"**✅ Connected to node `{node[0].uri}`**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    @slash_node.command(
        name="reconnect", description="Automatically reconnect to avaiable node"
    )
    @guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def recconect_node(self, ctx: discord.ApplicationContext) -> None:
        await ctx.defer()
        node: wavelink.Node = await self.bot.connect_node(ctx.guild_id)
        player: wavelink.Player = ctx.voice_client

        if player:
            await player.switch_node(node)
            embed = discord.Embed(
                title="",
                description=f"**✅ Connected your player to node `{self.bot.node.uri}`**",
                color=discord.Color.blue(),
            )
        else:
            embed = discord.Embed(
                title="",
                description=f"**✅ Connected to node `{self.bot.node.uri}`**",
                color=discord.Color.blue(),
            )

        await ctx.respond(embed=embed)

    @slash_node.command(name="info", description="Information about connected node.")
    async def node_info(self, ctx: discord.ApplicationContext) -> None:
        node: wavelink.Node = self.bot.node
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

    @slash_node.command(name="players", description="Information about node players.")
    async def node_players(self, ctx: discord.ApplicationContext) -> None:
        nodes: dict[str, wavelink.Node] = wavelink.Pool.nodes.values()

        if not nodes:
            embed = discord.Embed(
                title="",
                description=":x: There are no nodes connected.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
            return
        # Would change to dict
        server_name = []
        playing = []
        node_uri = []

        for node in nodes:
            players: wavelink.PlayerResponsePayload = await node.fetch_players()

            if not players:
                continue

            embed = discord.Embed(
                title="Node Players",
                color=discord.Color.blue(),
            )

            for player in players:
                guild: discord.Guild = await self.bot.fetch_guild(player.guild_id)
                server_name.append(guild.name)
                playing.append(player.track.title if player.track else "Nothing")
                node_uri.append(node.uri)

        if not server_name:
            embed = discord.Embed(
                title="",
                description=":x: There are no players connected.",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed)
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
        servers = await self.sfd_servers.get_servers()
        if not servers:
            embed = discord.Embed(
                title="",
                description=":x: There are no servers available right now.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(
                embed=embed,
                ephemeral=True,
                delete_after=10,
            )
            return

        servers_dict, all_players = await self.sfd_servers.get_servers_info()
        embed = discord.Embed(
            title="Available Servers",
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Total players: {all_players}")
        embed.add_field(name="Servers", value="\n".join(servers_dict["server_name"]))
        embed.add_field(name="Current Map", value="\n".join(servers_dict["maps"]))
        embed.add_field(name="Players", value="\n".join(servers_dict["players"]))
        await ctx.respond(embed=embed)

    @slash_sfd.command(name="server_info", description="Find searched server.")
    @option("server", description="Server name.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def get_sfd_server_info(
        self, ctx: discord.ApplicationContext, search: str
    ) -> None:
        server = self.sfd_servers.get_server(search)
        if not server:
            await send_error(ctx, "SFD_SERVER_NOT_FOUND")
            return

        server = server.get_full_server_info()

        embed = discord.Embed(
            title=server.server_name,
            description=server.description,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Version: {server.version}")
        embed.add_field(name="Playersㅤㅤ", value=server.players)
        embed.add_field(name="Max Playersㅤㅤ", value=server.max_players)
        embed.add_field(name="Botsㅤㅤ", value=server.bots)
        embed.add_field(name="Map Nameㅤㅤ", value=server.map_name)
        embed.add_field(name="Has Passwordㅤㅤ", value=server.has_password)
        embed.add_field(name="Game Modeㅤㅤ", value=await server.get_game_mode())
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
        await ctx.defer()

        if graph_range == "Day":
            filename = f"sfd_activity_day_{timezone}.png"
            generator = self.sfd_servers.generate_graph_day
        else:
            filename = f"sfd_activity_week_{timezone}.png"
            generator = self.sfd_servers.generate_graph_week

        image_location = os.path.join(self.graphs_dir, filename)

        if not os.path.exists(image_location) or get_file_age(image_location) >= 3600:
            await generator(timezone)

        file = discord.File(image_location, filename=filename)
        await ctx.respond(files=[file], embed=None)

    # -------------------- SFD Hosting -------------------- #
    @slash_command(
        name="host",
        description="Creates hosting embed, you can also choose some optional info.",
        guild_ids=[XTC_SERVER, KEXO_SERVER],
    )
    @option("server_name", description="Your server name.")
    @option(
        "duration",
        description="How long are you going to be hositng.",
        choices=[
            "As long as I want.",
            "15 minutes",
            "15-60 minutes",
            "1 hour",
            "1+ hours",
            "2+ hours",
            "3+ hours",
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
        author = ctx.author

        if author in host_authors:
            return await ctx.respond(
                "You have already created host embed!"
                " Click on button embed to stop it from beign active.",
                delete_after=10,
                ephemeral=True,
            )

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
                await ctx.respond(
                    "Image url needs to end with .png, .gif and etc.",
                    ephemeral=True,
                    delete_after=10,
                )
                return None

        if ping:
            try:
                role = discord.utils.get(ctx.guild.roles, name="Exotic")
                await ctx.send(role.mention)
            except AttributeError:
                await send_error(ctx, "CANT_PING_ROLE")
                return None

        view = HostView(author=author)
        await ctx.respond(embed=embed, view=view)

        interaction = await ctx.interaction.original_response()
        view.message = await ctx.channel.fetch_message(interaction.id)
        return None

    # -------------------- Discord functions -------------------- #
    @slash_command(name="info", description="Shows bot info.")
    async def info(self, ctx: discord.ApplicationContext) -> None:
        embed = discord.Embed(title="KexoBOT Info", color=discord.Color.blue())
        embed.add_field(
            name="Run time:ㅤㅤ",
            value=f"{str(datetime.timedelta(seconds=round(int(time.time()) - self.run_time)))}",
        )
        embed.add_field(name="Ping:ㅤㅤ", value=f"{round(self.bot.latency * 1000)} ms")
        embed.add_field(name="Memory usage:ㅤㅤ", value=f"{get_memory_usage():.2f} MB")
        embed.add_field(name="Online nodes:ㅤ", value=self.bot.get_online_nodes())
        embed.add_field(name="Joined servers:ㅤ", value=len(self.bot.guilds))
        embed.add_field(name="Version:", value=__version__)
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
        if ineteger1 > ineteger2:
            ineteger2, ineteger1 = ineteger1, ineteger2
        await ctx.respond(f"I chose `{random.randint(ineteger1, ineteger2)}`")

    @slash_command(
        name="pick",
        description="Selects one word, words needs to be separated by space.",
    )
    @option("words", description="Seperate words by space.")
    async def pick(self, ctx, words: str) -> None:
        words = words.split()
        await ctx.respond("I chose " + "`" + str(random.choice(words)) + "`")

    @slash_command(name="clear-messages", description="Clears messages, max 50 (Admin)")
    @discord.default_permissions(administrator=True)
    @option("integer", description="Max is 50.", min_value=1, max_value=50)
    async def clear(self, ctx: discord.ApplicationContext, integer: int) -> None:
        await ctx.respond(
            f"`{integer}` messages cleared ✅", delete_after=20, ephemeral=True
        )
        await ctx.channel.purge(limit=integer)

    # -------------------- Database Managment -------------------- #
    @slash_bot_config.command(
        name="add",
        description="Adds string to selected list.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES.keys())
    @option("to_upload", description="String to upload.")
    async def bot_config_add(self, ctx, collection: str, to_upload: str) -> None:
        await self._add_to_bot_config(ctx, collection, to_upload)

    @slash_bot_config.command(
        name="remove",
        description="Removes string from selected list.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES.keys())
    @option("to_remove", description="String to remove.")
    async def bot_config_remove(self, ctx, collection: str, to_remove: str) -> None:
        await self._remove_from_bot_config(ctx, collection, to_remove)

    @slash_bot_config.command(
        name="show",
        description="Shows data from selected lists.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES.keys())
    async def bot_config_show(self, ctx, collection: str) -> None:
        await self._show_bot_config(ctx, collection)

    @slash_reddit.command(
        name="settings",
        description="Change your list of subreddits.",
    )
    async def edit_subreddit(self, ctx: discord.ApplicationContext) -> None:
        user_id = ctx.author.id
        user_data = await self.user_data_db.find_one({"_id": user_id})

        if not user_data:
            user_data = generate_user_data()
            await self.user_data_db.insert_one(
                {"_id": user_id, "reddit": user_data["reddit"]}
            )

            embed = discord.Embed(
                title="",
                description="**✅ Generated user data.**",
                color=discord.Color.blue(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            self.user_data[user_id] = user_data
        else:
            self.user_data.setdefault(user_id, {})["reddit"] = user_data["reddit"]

        current_subreddits = user_data["reddit"]["subreddits"]
        # Create a view with select menu for all available subreddits
        view = SubredditSelectorView(current_subreddits, self.bot, user_id)

        embed = discord.Embed(
            title="Select Subreddits",
            description="Select the subreddits you want to see in shitpost command."
            " Currently selected subreddits are pre-checked.",
            color=discord.Color.blue(),
        )

        await ctx.respond(embed=embed, view=view, ephemeral=True)

    async def _show_bot_config(self, ctx, collection: str) -> None:
        bot_config: dict = await self.bot_config.find_one(DB_LISTS)
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
        bot_config: dict = await self.bot_config.find_one(DB_LISTS)
        collection_name = collection
        collection_db_name = DB_CHOICES[collection]
        collection: list = bot_config[collection_db_name]

        if to_upload in collection:
            await send_error(ctx, "DB_ALREADY_IN_LIST", to_upload=to_upload)
            return

        collection.append(to_upload)
        await self.bot_config.update_one(
            DB_LISTS, {"$set": {collection_db_name: collection}}
        )
        embed = discord.Embed(
            title="",
            description=f":white_check_mark: String `{to_upload}` was added to `{collection_name}`",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

    async def _remove_from_bot_config(
        self, ctx, collection: str, to_remove: str
    ) -> None:
        bot_config: dict = await self.bot_config.find_one(DB_LISTS)
        collection_name = collection
        collection_db_name = DB_CHOICES[collection]
        collection: list = bot_config[collection_db_name]

        if to_remove not in collection:
            await send_error(ctx, "DB_NOT_IN_LIST", to_remove=to_remove)
            return

        del collection[collection.index(to_remove)]

        await self.bot_config.update_one(
            DB_LISTS, {"$set": {collection_db_name: collection}}
        )
        embed = discord.Embed(
            title="",
            description=f":white_check_mark: String `{to_remove}` was removed from `{collection_name}`",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)


class HostView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=43200, disable_on_timeout=True)
        self.author = author

    # noinspection PyUnusedLocal
    @discord.ui.button(
        style=discord.ButtonStyle.gray, label="I stopped hosting.", emoji="📣"
    )
    async def button_callback(
        self, button: discord.Button, interaction: discord.Interaction
    ) -> None:
        if interaction.user.name in host_authors:
            embed = await self.disable_embed()
            await interaction.response.edit_message(embed=embed, view=None)
            host_authors.pop(host_authors.index(self.author.name))
            return

        await send_error(interaction, "NOT_EMBED_AUTHOR")

    async def on_timeout(self) -> None:
        embed = await self.disable_embed()
        await self.message.edit(embed=embed, view=None)
        await self.author.send(
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
        host_authors.pop(host_authors.index(self.author.name))

    async def disable_embed(self) -> discord.Embed:
        self.stop()

        embed = self.message.embeds[0]
        embed.set_author(
            icon_url=self.author.avatar.url,
            name=f"{self.author.name} is no longer hosting.",
        )
        embed.color = discord.Color.from_rgb(r=200, g=0, b=0)
        embed.set_field_at(
            0, name="Status:ㅤㅤ", value="**OFFLINE** <:offline:1355571345613787296>"
        )

        timestamp = embed.fields[2].value.replace("R", "t")
        embed.set_field_at(2, name="Hosted atㅤ", value=timestamp)
        return embed


class SubredditSelectorView(discord.ui.View):
    def __init__(self, current_subreddits: set, bot: discord.Bot, user_id: int) -> None:
        super().__init__(timeout=600)
        self.current_subreddits = current_subreddits
        self.selected_subreddits = set()
        self.bot = bot
        self.user_id = user_id

        self._user_data = self.bot.user_data
        self._user_data_db = self.bot.user_data_db
        self._temp_user_data = self.bot.temp_user_data

        self.select = SubredditSelect(current_subreddits)
        self.save_button = discord.ui.Button(
            label="Save Changes",
            style=discord.ButtonStyle.green,
            custom_id="save_changes",
        )
        self.save_button.callback = self.save_changes

        nsfw_status = self._user_data[user_id]["reddit"]["nsfw_posts"]
        self.nsfw_button = discord.ui.Button(
            label="NSFW ON" if nsfw_status else "NSFW OFF",
            style=(
                discord.ButtonStyle.green
                if not nsfw_status
                else discord.ButtonStyle.red
            ),
            custom_id="nsfw_posts",
        )
        self.nsfw_button.callback = self.nsfw_posts

        self.add_item(self.select)
        self.add_item(self.save_button)
        self.add_item(self.nsfw_button)

    async def nsfw_posts(self, interaction: discord.Interaction) -> None:
        nsfw_status = not self._user_data[self.user_id]["reddit"]["nsfw_posts"]

        self._user_data[self.user_id]["reddit"]["nsfw_posts"] = nsfw_status
        await self._user_data_db.update_one(
            {"_id": self.user_id}, {"$set": self._user_data[self.user_id]}
        )

        self.nsfw_button.label = "NSFW ON" if nsfw_status else "NSFW OFF"
        self.nsfw_button.style = (
            discord.ButtonStyle.green if not nsfw_status else discord.ButtonStyle.red
        )

        await interaction.response.edit_message(view=self)

    async def save_changes(self, interaction: discord.Interaction) -> None:
        if self.selected_subreddits:
            self._user_data[self.user_id]["reddit"]["subreddits"] = list(
                self.selected_subreddits
            )

            await self._user_data_db.update_one(
                {"_id": self.user_id}, {"$set": self._user_data[self.user_id]}
            )

            if self.user_id in self._temp_user_data:
                await self._update_multireddit()

        embed = discord.Embed(
            title="Changes Saved",
            description=f"Successfully updated your subreddit list to `{len(self.selected_subreddits)}` subreddits.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await interaction.response.edit_message(embed=embed, view=None, delete_after=20)

    async def on_timeout(self) -> None:
        self.disable_all_items()
        self.stop()

    async def _update_multireddit(self) -> None:
        multireddit: asyncpraw.models.Multireddit = self._temp_user_data[self.user_id][
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
                await multireddit.add(await self.bot.reddit_agent.subreddit(subreddit))
            except asyncpraw.exceptions.RedditAPIException:
                print(f"Failed to add subreddit `{subreddit}`")

        self._temp_user_data[self.user_id]["reddit"]["multireddit"] = multireddit


class SubredditSelect(discord.ui.Select):
    def __init__(self, current_subreddits: set):
        options = [
            discord.SelectOption(
                label=f"r/{subreddit}",
                value=subreddit,
                default=subreddit in current_subreddits,
                description=f"Select to {'remove' if subreddit in current_subreddits else 'add'} this subreddit",
            )
            for subreddit in SHITPOST_SUBREDDITS_ALL
        ]

        super().__init__(
            placeholder="Select subreddits to toggle",
            max_values=len(SHITPOST_SUBREDDITS_ALL),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_subreddits = set()
        for subreddit in self.values:
            self.view.selected_subreddits.add(subreddit)
        await interaction.response.defer()


def setup(bot: commands.Bot):
    bot.add_cog(Commands(bot))
