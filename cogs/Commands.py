import asyncio
import discord
import random
import aiohttp
import wavelink
import time
import sys

from datetime import datetime, timedelta
from discord.ext import commands
from discord.commands import slash_command
from discord.commands import option

host_authors = []


class Commands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.run_time = time.time()

    @slash_command(name='manual_reconnect_node', description='Manually input server info')
    @option('uri', description='Lavalink server URL (without http:// at start)', required=True)
    @option('port', description='Lavalink server port.', required=True)
    @option('password', description='Lavalink server password.', required=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def manual_recconect_node(self, ctx: discord.ApplicationContext, uri: str, port: int, password: str) -> None:
        embed = discord.Embed(title="",
                              description=f'**🔄 Connecting to `{uri}`**',
                              color=discord.Color.blue())
        message = await ctx.respond(embed=embed)

        node = [wavelink.Node(uri=f"http://{uri}:{str(port)}", password=password, retries=1, resume_timeout=0)]
        await wavelink.Pool.connect(nodes=node, client=self.bot)
        self.bot.node = node

        await ctx.trigger_typing()
        await asyncio.sleep(2)

        try:
            await node[0].fetch_info()

            embed = discord.Embed(title="",
                                  description=f'**✅ Connected to node `{uri}`**',
                                  color=discord.Color.blue())
            await message.edit(embed=embed)

        except (aiohttp.client_exceptions.ClientConnectorError, aiohttp.ConnectionTimeoutError):
            embed = discord.Embed(title="",
                                  description=f":x: Failed to connect to `{uri}`",
                                  color=discord.Color.from_rgb(r=255, g=0, b=0))
            await message.edit(embed=embed)

    @slash_command(name='reconnect_node', description='Automatically reconnect to avaiable node')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def recconect_node(self, ctx: discord.ApplicationContext) -> None:
        await ctx.trigger_typing()
        embed = discord.Embed(title="",
                              description=f'**🔄 Getting Lavalink server.**',
                              color=discord.Color.blue())
        await ctx.respond(embed=embed)

        try:
            await self.bot.connect_node()
            await self.bot.node[0].fetch_info()
        except (aiohttp.client_exceptions.ClientConnectorError, aiohttp.ConnectionTimeoutError,
                wavelink.exceptions.NodeException):
            embed = discord.Embed(title="",
                                  description=f":x: Failed to connect to `{self.bot.node[0].uri}`, "
                                              f"rolling back to previous node.",
                                  color=discord.Color.from_rgb(r=255, g=0, b=0))
            return await ctx.send(embed=embed)

        embed = discord.Embed(title="",
                              description=f'**✅ Connected to node `{self.bot.node[0].uri}`**',
                              color=discord.Color.blue())
        await ctx.send(embed=embed)

    @slash_command(name='host', description='Creates hosting embed, you can also choose some optional info.',
                   guild_ids=[723197287861583885, 692810367851692032])
    @option('server_name', description='Your server name.')
    @option('duration', description='How long are you going to be hositng.',
            choices=['As long as I want/Before any crash.', '15 minutes', '30 minutes',
                     '45 minutes', '1 hour', '1+ hours',
                     '2+ hours', '3+ hours'])
    @option('ping', description='Should this embed ping @Exotic or not, default is True', required=False)
    @option('password', description='Server password.', required=False)
    @option('region', description='Server region.', required=False)
    @option('category_maps', description='What kind of server, which maps, etc...', required=False)
    @option('scripts', description='Which scripts are enabled.', required=False)
    @option('slots', description='How many server slots, default is 8', required=False)
    @option('image', description='Add custom image url for embed, needs to end with .png, .gif and etc.',
            required=False)
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def host(self, ctx, server_name: str, duration, password: str, region: str, category_maps: str, scripts: str,
            slots: int = 8, ping: bool = True, image: str = None) -> None:
        author = ctx.author

        if author in host_authors:
            return await ctx.respond(
                "You have already created host embed! Click on button embed to stop it from beign active.",
                delete_after=10,
                ephemeral=True)

        host_authors.append(author.name)

        embed = discord.Embed(
            title=server_name,
            description='**Online**  :green_circle: ',
            color=discord.Color.green())

        embed.set_author(icon_url=author.avatar.url, name=f'{author.name} is now hosting!')
        embed.timestamp = datetime.utcnow()

        embed.add_field(name='Uptime:ㅤㅤ', value=duration)
        embed.set_footer(text=f'Slots: {slots}')

        if password:
            embed.add_field(name='Password:ㅤㅤ', value=password)

        if region:
            embed.add_field(name='Region:ㅤㅤ', value=region)

        if category_maps:
            embed.add_field(name='Category/Maps:ㅤㅤ', value=category_maps)

        if scripts:
            embed.add_field(name='Scripts:ㅤㅤ', value=scripts)

        if image:
            if image.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                embed.set_thumbnail(url=image)
            else:
                await ctx.respond('Image url needs to end with .jpg, .png, .gif and etc.',
                                  ephemeral=True,
                                  delete_after=10)
        if ping:
            role = discord.utils.get(ctx.guild.roles, name='Exotic')
            await ctx.send(role.mention)

        view = HostView(author=author)
        await ctx.respond(embed=embed, view=view)

        # Timeout 15 minutes, convert to normal message
        interaction = await ctx.interaction.original_response()
        view.message = await ctx.channel.fetch_message(interaction.id)

    @slash_command(name='info')
    async def info(self, ctx: discord.ApplicationContext) -> None:
        embed = discord.Embed(title="INFO", color=discord.Color.blue())
        embed.add_field(name="Run time:ㅤㅤ" + '\u200b',
                        value=f"{str(timedelta(seconds=round(int(time.time()) - self.run_time)))}")
        embed.add_field(name="Ping:ㅤㅤㅤㅤ", value=f"{round(self.bot.latency * 1000)} ms")
        embed.add_field(name="Version:", value="2.0")
        embed.add_field(name="Py-cord version:ㅤ", value=discord.__version__)
        embed.add_field(name="Python version:",
                        value=f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
        embed.set_footer(text="Bot owner: _kexo")
        await ctx.respond(embed=embed)

    @slash_command(name='random_number', description='Choose number between intervals.')
    async def random_number(self, ctx: discord.ApplicationContext, ineteger1: int, ineteger2: int) -> None:
        if ineteger1 > ineteger2:
            ineteger2, ineteger1 = ineteger1, ineteger2
        await ctx.respond(f"I chose `{random.randint(ineteger1, ineteger2)}`")

    @slash_command(name='pick', description='Selects one word, words needs to be separated by space.')
    @option('words', description='Seperate words by space.')
    async def pick(self, ctx, words: str) -> None:
        words = words.split()
        await ctx.respond("I chose " + "`" + str(random.choice(words)) + "`")

    @slash_command(name='c', description='Clears messages, max 50 (Admin)')
    @discord.default_permissions(administrator=True)
    @option(
        'integer',
        description='Max is 50.',
        min_value=1,
        max_value=50
    )
    async def clear(self, ctx: discord.ApplicationContext, integer: int) -> None:
        await ctx.respond(f'`{integer}` messages cleared ✅', delete_after=20, ephemeral=True)
        await ctx.channel.purge(limit=integer)


class HostView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=43200, disable_on_timeout=True)
        self.author = author

    # noinspection PyUnusedLocal
    @discord.ui.button(style=discord.ButtonStyle.gray, label="I stopped hosting.", emoji='📣')
    async def button_callback(self, button: discord.Button, interaction: discord.Interaction) -> None:
        if interaction.user.name in host_authors:
            embed = await self.disable_embed()
            await interaction.response.edit_message(embed=embed, view=None)
            pos = host_authors.index(self.author.name)
            host_authors.pop(pos)
        else:
            await interaction.response.send_message(
                interaction.user.mention + ', you are not author of this embed.', delete_after=5, ephemeral=True)

    async def on_timeout(self) -> None:
        embed = await self.disable_embed()
        await self.message.edit(embed=embed, view=None)
        await self.author.send(
            f'You forgot to click button in {self.message.jump_url} you {random.choice(
                ("dumbass", "retard", "nitwit", "cockwomble", "prick",
                 "cunt", "pillock", "twat"))}.')
        pos = host_authors.index(self.author.name)
        host_authors.pop(pos)

    async def disable_embed(self) -> discord.Embed:
        self.stop()

        embed = self.message.embeds[0]
        embed.set_author(icon_url=self.author.avatar.url,
                         name=f'{self.author.name} is no longer hosting.')
        embed.description = 'Status: **Offline**  :red_circle: '
        embed.color = discord.Color.from_rgb(r=255, g=0, b=0)
        return embed


def setup(bot: commands.Bot):
    bot.add_cog(Commands(bot))
