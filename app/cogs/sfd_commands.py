from __future__ import annotations

import datetime
import os
import random
import time
from typing import TYPE_CHECKING, Any, cast

import discord
from discord import app_commands
from discord.ext import commands
from pymongo.asynchronous.collection import AsyncCollection

from app.classes.sfd_servers import SFDServers
from app.config.colors import COLOR_BLUE, COLOR_GREEN_SUCCESS, COLOR_RED, COLOR_RED_DARK
from app.player_types import member_of
from app.response_handler import defer_interaction, make_embed, send
from app.utils import EmbedPaginator

if TYPE_CHECKING:
    from app.client import KexoBotClient


host_authors: set[str] = set()


def get_file_age(file_path: str) -> float:
    if os.path.exists(file_path):
        file_time = os.path.getmtime(file_path)
        current_time = datetime.datetime.now().timestamp()
        return current_time - file_time
    return 0.0


class SFDCommands(commands.Cog):
    slash_sfd = app_commands.Group(
        name="sfd", description="Show Superfighters Deluxe stats and servers"
    )

    def __init__(self, bot: KexoBotClient) -> None:
        self._bot = bot
        self._bot_config: AsyncCollection[Any] = bot.bot_config
        self._sfd_servers = SFDServers(self._bot_config, bot.session)
        self._graphs_dir = os.path.join(os.getcwd(), "graphs")

    async def get_sfd_servers(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about available SFD servers.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        servers_dict, all_players = await self._sfd_servers.get_servers_info()
        if servers_dict is None or all_players is None:
            await send(ctx, embed=make_embed(":x: No servers found."))
            return

        # Cleaning up the server names and maps
        servers_dict["server_name"] = [s.strip() for s in servers_dict["server_name"]]
        servers_dict["maps"] = [m.strip() for m in servers_dict["maps"]]

        server_name_char, map_char, stopped_at = 0, 0, 0
        pages: list[discord.Embed] = []
        embed = discord.Embed(title="Available Servers", color=COLOR_BLUE)

        for i in range(len(servers_dict["server_name"])):
            server_name_char += len(servers_dict["server_name"][i])
            map_char += len(servers_dict["maps"][i])

            embed = discord.Embed(
                title="Available Servers",
                color=COLOR_BLUE,
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
            await send(ctx, embed=embed)
        else:
            view = EmbedPaginator(pages)
            await send(ctx, embed=pages[0], view=view)

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
            await send(ctx, embed=make_embed(":x: No server found."))
            return

        embed = discord.Embed(
            title=server.server_name,
            description=server.description,
            color=COLOR_BLUE,
        )
        embed.set_footer(text=f"Version: {server.version}")
        embed.add_field(name="Players:ㅤㅤ", value=server.players)
        embed.add_field(name="Max Players:ㅤㅤ", value=server.max_players)
        embed.add_field(name="Bots:ㅤㅤ", value=server.bots)
        embed.add_field(name="Map Name:ㅤㅤ", value=server.map_name)
        embed.add_field(name="Has Password:ㅤㅤ", value=server.has_password)
        embed.add_field(name="Game Mode:ㅤㅤ", value=server.game_mode)
        await send(ctx, embed=embed)

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
        await send(ctx, files=[file], embed=None)

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
        branch: str | None = None,
        version: str | None = None,
        password: str | None = None,
        region: str | None = None,
        scripts: str | None = None,
        slots: app_commands.Range[int, 2, 16] = 8,
        image: str | None = None,
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
        ping_role: discord.Role
            The role to ping for the hosting announcement
        image: str
            The URL of the image to be used in the embed.
        """
        author = member_of(ctx)

        if author in host_authors:
            await send(
                ctx,
                embed=make_embed(
                    ":x: You are already hosting a server, stop hosting first."
                ),
            )
            return

        host_authors.add(author.name)

        embed = discord.Embed(
            title=server_name,
            color=COLOR_GREEN_SUCCESS,
        )

        embed.set_author(
            icon_url=author.display_avatar.url, name=f"{author.name} is now hosting!"
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
                await send(
                    ctx,
                    embed=make_embed(
                        ":x: Incorrect image URL, use .jpg, .jpeg, .png or .gif"
                    ),
                )
                return

        try:
            await send(ctx, ping_role.mention)
        except discord.Forbidden:
            await send(
                ctx,
                embed=make_embed(
                    ":x: Can't ping role, I don't have permission to do so.",
                    color=COLOR_RED,
                ),
                ephemeral=False,
            )
            return

        view = HostView(author=author)
        response = await send(ctx, embed=embed, view=view)
        view.message = cast(discord.Message, response)
        return


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

    message: discord.Message

    def __init__(self, author: discord.Member):
        super().__init__(timeout=43200)
        self._author = author

    # noinspection PyUnusedLocal
    @discord.ui.button(
        style=discord.ButtonStyle.gray, label="I stopped hosting.", emoji="📣"
    )
    async def button_callback(
        self, interaction: discord.Interaction, _button: discord.ui.Button[HostView]
    ) -> None:
        """Callback for the button in the hosting embed.

        This method is called when the button is clicked.
        It checks if the user who clicked the button is the same as the author of the embed.
        If so, it disables the embed and removes the author from the list of host authors.
        If not, it sends a response indicating that the user is not the author of the embed.

        Parameters
        ----------
        button: :class:`discord.ui.Button`
            The button that was clicked.
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        if interaction.user.name in host_authors:
            embed = await self._disable_embed()
            await interaction.response.edit_message(embed=embed, view=None)
            host_authors.discard(self._author.name)
            return

        await send(
            interaction,
            embed=make_embed(":x: You are not the author of this embed."),
        )

    async def on_timeout(self) -> None:
        """Method called when the view times out.

        This method disables the embed and sends a message to the
        author indicating that they forgot to click the button.
        It also removes the author from the list of host authors.
        """
        embed = await self._disable_embed()
        await self.message.edit(embed=embed, view=None)
        await self._author.send(
            f"You forgot to click button in {self.message.jump_url} you {random.choice(('dumbass', 'retard', 'prick', 'cunt', 'shitling'))}."
            "\nhttps://tenor.com/view/zombie-screaming-gif-12431778992096703656"
        )
        host_authors.discard(self._author.name)

    async def _disable_embed(self) -> discord.Embed:
        self.stop()

        embed = self.message.embeds[0]
        embed.set_author(
            icon_url=self._author.display_avatar.url,
            name=f"{self._author.name} is no longer hosting.",
        )
        embed.color = COLOR_RED_DARK
        embed.set_field_at(
            0,
            name="Status:ㅤㅤ",
            value="**OFFLINE** <:offline:1355571345613787296>",
        )

        timestamp = (embed.fields[2].value or "").replace("R", "t")
        embed.set_field_at(2, name="Hosted at:ㅤ", value=timestamp)
        return embed


async def setup(bot: KexoBotClient) -> None:
    await bot.add_cog(SFDCommands(bot))
