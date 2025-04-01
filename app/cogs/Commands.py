import asyncio
import discord
import datetime
import random
import aiohttp
import wavelink
import time
import sys
import os

from discord.ext import commands
from discord.commands import slash_command
from discord.commands import option

from constants import XTC_SERVER, KEXO_SERVER, DB_LISTS, DB_CHOICES, SFD_TIMEZONE_CHOICE
from classes.DatabaseManager import DatabaseManager
from classes.SFDServers import SFDServers
from utils import get_memory_usage
from __init__ import __version__

host_authors = []


class Commands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.database = bot.database
        self.run_time = time.time()
        self.graphs_dir = os.path.join(os.getcwd(), "graphs")
        self.sfd_servers = SFDServers(bot.session, self.database)
        self.database_manager = DatabaseManager(self.database)

    async def init_sfd_servers(self) -> None:
        self.sfd_servers = self.bot.sfd_servers

    # -------------------- Node Managment -------------------- #
    @slash_command(
        name="manual_reconnect_node", description="Manually input server info"
    )
    @option(
        "uri",
        description="Lavalink server URL (without http:// at start)",
        required=True,
    )
    @option("port", description="Lavalink server port.", required=True)
    @option("password", description="Lavalink server password.", required=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def manual_recconect_node(
        self, ctx: discord.ApplicationContext, uri: str, port: int, password: str
    ) -> None:
        embed = discord.Embed(
            title="",
            description=f"**🔄 Connecting to `{uri}`**",
            color=discord.Color.blue(),
        )
        message = await ctx.respond(embed=embed)

        node = [
            wavelink.Node(
                uri=f"http://{uri}:{str(port)}",
                password=password,
                retries=1,
                resume_timeout=0,
            )
        ]
        await wavelink.Pool.connect(nodes=node, client=self.bot)
        self.bot.node = node

        await ctx.trigger_typing()
        await asyncio.sleep(2)

        try:
            await node[0].fetch_info()

            embed = discord.Embed(
                title="",
                description=f"**✅ Connected to node `{uri}`**",
                color=discord.Color.blue(),
            )
            await message.edit(embed=embed)

        except (
            aiohttp.client_exceptions.ClientConnectorError,
            aiohttp.ConnectionTimeoutError,
            wavelink.exceptions.NodeException,
            AssertionError,
        ):
            embed = discord.Embed(
                title="",
                description=f":x: Failed to connect to `{uri}`",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await message.edit(embed=embed)

    @slash_command(
        name="reconnect_node", description="Automatically reconnect to avaiable node"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def recconect_node(self, ctx: discord.ApplicationContext) -> None:
        await ctx.trigger_typing()
        embed = discord.Embed(
            title="",
            description=f"**🔄 Getting Lavalink server.**",
            color=discord.Color.blue(),
        )
        await ctx.respond(embed=embed)

        try:
            await self.bot.connect_node()
        except (
            aiohttp.client_exceptions.ClientConnectorError,
            aiohttp.ConnectionTimeoutError,
            wavelink.exceptions.NodeException,
            AssertionError,
        ):
            embed = discord.Embed(
                title="",
                description=f":x: Failed to connect to `{self.bot.node[0].uri}`, rolling back to previous node.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="",
            description=f"**✅ Connected to node `{self.bot.node[0].uri}`**",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    # -------------------- SFD Servers -------------------- #
    @slash_command(
        name="sfd_servers", description="Fetches Superfighters Deluxe servers."
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

    @slash_command(name="sfd_server_info", description="Find searched server.")
    @option("server", description="Server name.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def get_sfd_server_info(
        self, ctx: discord.ApplicationContext, search: str
    ) -> None:
        server = await self.sfd_servers.get_server(search)
        if not server:
            embed = discord.Embed(
                title="",
                description=":x: Server you searched for is not in the list,\n"
                "make sure you parsed correct server name.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
            await ctx.respond(
                embed=embed,
                ephemeral=True,
                delete_after=10,
            )
            return

        server = await server.get_full_server_info()

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

    @slash_command(
        name="sfd_activity",
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
        description="Timezone, default is New York",
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
        await ctx.trigger_typing()
        embed = discord.Embed(
            title="",
            description="**🔄 Fetching SFD servers activity.**",
            color=discord.Color.blue(),
        )
        message = await ctx.respond(embed=embed)

        if graph_range == "Day":
            if timezone != "New_York":
                await self.sfd_servers.generate_graph_day(timezone)
            image_location = os.path.join(self.graphs_dir, "sfd_activity_day.png")
        else:
            if timezone != "New_York":
                await self.sfd_servers.generate_graph_week(timezone)
            image_location = os.path.join(self.graphs_dir, "sfd_activity_week.png")

        filename = os.path.basename(image_location)
        file = discord.File(image_location, filename=filename)
        await message.edit(files=[file], embed=None)

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
                "You have already created host embed! Click on button embed to stop it from beign active.",
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
                return

        if ping:
            try:
                role = discord.utils.get(ctx.guild.roles, name="Exotic")
                await ctx.send(role.mention)
            except AttributeError:
                await ctx.respond(
                    "I can't ping Exotic role, please check if role exists or if I have permission to ping it.",
                    delete_after=10,
                    ephemeral=True,
                )
                return

        view = HostView(author=author)
        await ctx.respond(embed=embed, view=view)

        interaction = await ctx.interaction.original_response()
        view.message = await ctx.channel.fetch_message(interaction.id)

    # -------------------- Discord functions -------------------- #
    @slash_command(name="info")
    async def info(self, ctx: discord.ApplicationContext) -> None:
        embed = discord.Embed(title="INFO", color=discord.Color.blue())
        embed.add_field(
            name="Run time:ㅤㅤ",
            value=f"{str(datetime.timedelta(seconds=round(int(time.time()) - self.run_time)))}",
        )
        embed.add_field(name="Ping:ㅤㅤ", value=f"{round(self.bot.latency * 1000)} ms")
        embed.add_field(name="Memory usage:ㅤㅤ", value=f"{get_memory_usage():.2f} MB")
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

    @slash_command(name="clear", description="Clears messages, max 50 (Admin)")
    @discord.default_permissions(administrator=True)
    @option("integer", description="Max is 50.", min_value=1, max_value=50)
    async def clear(self, ctx: discord.ApplicationContext, integer: int) -> None:
        await ctx.respond(
            f"`{integer}` messages cleared ✅", delete_after=20, ephemeral=True
        )
        await ctx.channel.purge(limit=integer)

    # -------------------- Database Managment -------------------- #
    @slash_command(
        name="add_to",
        description="Adds string to selected list.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES)
    async def add_to(self, ctx, collection: str, to_upload: str) -> None:
        db_list = await self.database_manager.get_database(collection)

        if to_upload in db_list:
            return await ctx.respond(
                f"{ctx.author.mention} string `{to_upload}` "
                f"is already in the database, use `/show_data`"
            )

        db_list.append(to_upload)
        await self.database_manager.update_database(collection, db_list)
        await ctx.respond(
            f"String `{to_upload}` was added to `{collection}` :white_check_mark:"
        )

    @slash_command(
        name="remove_from",
        description="Removes string from selected list.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES)
    async def remove(self, ctx, collection: str, to_remove: str) -> None:
        db_list = await self.database_manager.get_database(collection)

        if to_remove not in db_list:
            await ctx.respond(
                f"{ctx.author.mention}, string `{to_remove}` is not in the database, use `/show_data`"
            )
            return
        db_list.pop(db_list.index(to_remove))

        await self.database_manager.update_database(collection, db_list)
        await ctx.respond(
            f"String `{to_remove}` was removed from `{collection}` :white_check_mark:"
        )

    @slash_command(
        name="show_data",
        description="Shows data from selected lists.",
        guild_ids=[KEXO_SERVER],
    )
    @discord.ext.commands.is_owner()
    @option("collection", description="Choose database", choices=DB_CHOICES)
    async def show_data(self, ctx, collection: str) -> None:
        listing = await self.database_manager.get_database(collection)

        embed = discord.Embed(title=collection, color=discord.Color.blue())
        embed.add_field(
            name=f"_{len(listing)} items_",
            value="\n".join(f"{i + 1}. {listing[i]}" for i in range(len(listing))),
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

        embed = discord.Embed(
            title="",
            description=f"{interaction.user.mention}, you are not author of this embed.",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(
            embed=embed,
            delete_after=10,
            ephemeral=True,
        )

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


def setup(bot: commands.Bot):
    bot.add_cog(Commands(bot))
