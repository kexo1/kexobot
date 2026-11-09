from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import discord
import sonolink
from discord import app_commands
from discord.ext import commands
from sonolink.rest.schemas.info import PluginObject

from app.config.colors import COLOR_BLUE
from app.config.music import (
    PLATFORM_EMOJIS,
    PLUGIN_PLATFORM_REGISTRY,
    AudioSourceSupport,
)
from app.player_types import get_player
from app.response_handler import defer_interaction, make_embed, send

if TYPE_CHECKING:
    from app.client import KexoBotClient

logger = logging.getLogger(__name__)


def iso_to_timestamp(iso_time: str) -> datetime:
    return datetime.fromisoformat(iso_time)


class NodeCommands(commands.Cog):
    slash_node = app_commands.Group(
        name="node", description="Commands for managing nodes"
    )

    def __init__(self, bot: KexoBotClient) -> None:
        self._bot = bot

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

        node_uri = f"{uri}:{port!s}"
        node = self._bot.state.build_node(node_uri, password)
        is_connected: bool = await self._bot.state.node_attempt_connection(node)

        if not is_connected:
            await send(ctx, code="NODE_CONNECT_FAILURE", uri=uri)
            return

        self._bot.node = node
        await send(
            ctx,
            embed=make_embed(f":white_check_mark: Connected to node {node.uri}"),
            ephemeral=False,
        )

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
        player = get_player(ctx)

        if player:
            node: sonolink.Node | None = await self._bot.state.switch_node(
                player=player,
                send_success_message=False,
            )
            if not node:
                await send(ctx, code="NODE_CONNECT_FAILURE")
                return

            self._bot.node = node
            await send(ctx, code="RECONNECTED_NODE", node=node.uri)
            return

        node = await self._bot.connect_node(
            exclude_nodes=[self._bot.node.uri] if self._bot.node else None
        )
        if not node:
            await send(ctx, code="NODE_CONNECT_FAILURE")
            return

        self._bot.node = node
        await send(ctx, code="RECONNECTED_NODE", node=node.uri)

    @slash_node.command(name="info", description="Information about connected node")
    async def node_info(self, ctx: discord.Interaction) -> None:
        """Method to fetch and display information about the connected Lavalink node.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command invocation.
        """
        node = self._bot.node
        if node is None:
            await send(ctx, code="NO_NODE_INFO")
            return

        try:
            node_info = await node.fetch_info()
        except Exception as exc:  # noqa: BLE001 - node API failures use the same response
            logger.warning("[Sonolink] Failed to fetch node info: %s", exc)
            await send(ctx, code="NO_NODE_INFO")
            return

        embed = discord.Embed(
            title=urlparse(node.uri).netloc,
            color=COLOR_BLUE,
        )
        plugins = node_info.plugins
        unix_timestamp = int(iso_to_timestamp(str(node_info.build_time)).timestamp())
        embed.add_field(
            name="Score:",
            value=self._bot.state.get_node_score(node.uri) or 0,
        )

        embed.add_field(
            name="Ping:", value=f"{self._bot.state.get_node_ping(node.uri) or 0} ms"
        )
        embed.add_field(
            name="Plugins:",
            value=", ".join(f"{plugin.name}: {plugin.version}" for plugin in plugins),
            inline=False,
        )
        embed.add_field(name="Lavaplayer version:", value=node_info.lavaplayer)
        embed.add_field(name="Java version:", value=node_info.jvm)
        embed.add_field(name="Build time:", value=f"<t:{unix_timestamp}:D>")
        embed.add_field(name="Filters:", value=", ".join(node_info.filters))

        await send(ctx, embed=embed)

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

        def resolve_platform_support(
            plugins: list[PluginObject],
        ) -> dict[str, AudioSourceSupport]:
            """Merge all plugin platform support, preferring LIKELY over UNLIKELY."""
            merged: dict[str, AudioSourceSupport] = {}

            for plugin in plugins:
                name = plugin.name.lower()
                for fragment, platforms in PLUGIN_PLATFORM_REGISTRY.items():
                    if fragment.lower() in name:
                        for platform, support in platforms.items():
                            if (
                                platform not in merged
                                or support == AudioSourceSupport.LIKELY
                            ):
                                merged[platform] = support

            return merged

        node = self._bot.node
        if node is None:
            await send(ctx, code="NO_NODE_INFO")
            return

        try:
            node_info = await node.fetch_info()
        except Exception as exc:  # noqa: BLE001 - node API failures use the same response
            logger.warning("[Sonolink] Failed to fetch node info: %s", exc)
            await send(ctx, code="NO_NODE_INFO")
            return

        platform_support = resolve_platform_support(node_info.plugins)
        SEARCH_PLUGINS = {"lavasearch", "youtube"}

        has_search = any(
            any(fragment in p.name.lower() for fragment in SEARCH_PLUGINS)
            for p in node_info.plugins
        )

        embed = discord.Embed(
            title=urlparse(node.uri).netloc,
            color=COLOR_BLUE,
        )

        if not platform_support:
            embed.description = "No platforms supported"
            await send(ctx, embed=embed)
            return

        likely = [
            p for p, s in platform_support.items() if s == AudioSourceSupport.LIKELY
        ]
        unlikely = [
            p for p, s in platform_support.items() if s == AudioSourceSupport.UNLIKELY
        ]

        no_search_warning = (
            "" if has_search else " _(no search plugin, only direct links)_"
        )

        if likely:
            embed.add_field(
                name=f"{len(likely)} likely supported{no_search_warning}",
                value="\n".join(f"{PLATFORM_EMOJIS.get(p, '🎵')} {p}" for p in likely),
                inline=False,
            )

        if unlikely:
            embed.add_field(
                name=f"{len(unlikely)} unlikely (depends on node configuration)",
                value="\n".join(
                    f"{PLATFORM_EMOJIS.get(p, '🎵')} {p}" for p in unlikely
                ),
                inline=False,
            )

        await send(ctx, embed=embed)

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
            await send(ctx, embed=make_embed(":x: No nodes connected."))
            return

        await defer_interaction(ctx)
        entries: list[list[str]] = []
        total_players = 0

        for node in nodes:
            try:
                players = await node.fetch_players()
            except Exception as exc:  # noqa: BLE001 - skip an unavailable node
                logger.warning(
                    "[Sonolink] Failed to fetch players from %s: %s",
                    node.uri,
                    exc,
                )
                continue

            if not players:
                continue

            total_players += len(players)
            guilds: dict[int, discord.Guild] = {g.id: g for g in self._bot.guilds}

            for player in players:
                guild = guilds.get(player.guild_id)
                server_name = guild.name if guild else f"Unknown ({player.guild_id})"
                track_title = player.track.title if player.track else "Nothing"
                entries.append([server_name, track_title, node.uri])

        if not entries:
            await send(ctx, embed=make_embed(":x: No players connected."))
            return

        embed = discord.Embed(title="Node Players", color=COLOR_BLUE)
        embed.add_field(
            name="Server:ㅤㅤㅤㅤ",
            value="\n".join(e[0] for e in entries),
        )
        embed.add_field(
            name="Playing:ㅤㅤ",
            value="\n".join(e[1] for e in entries),
        )
        embed.add_field(
            name="Node:",
            value="\n".join(e[2] for e in entries),
        )
        embed.set_footer(text=f"Total players: {total_players}")
        await send(ctx, embed=embed)


async def setup(bot: KexoBotClient) -> None:
    await bot.add_cog(NodeCommands(bot))
