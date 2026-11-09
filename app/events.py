from __future__ import annotations

import logging
from typing import Protocol

import discord
from discord import app_commands
from discord.ext import commands

from app.client import KexoBotClient
from app.config.colors import COLOR_ORANGE_LIGHT, COLOR_RED
from app.response_handler import make_embed, send

logger = logging.getLogger(__name__)


class _Runtime(Protocol):
    async def wordnik_presence(self) -> None: ...


def register_events(bot: KexoBotClient, runtime: _Runtime) -> None:
    """Register application-level Discord event and error handlers."""

    @bot.event
    async def on_ready() -> None:
        """Set the bot presence when Discord reports it ready."""
        await runtime.wordnik_presence()
        logger.info("[Starter] Bot is ready.")

    async def on_application_command_error(
        ctx: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(
            error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)
        ):
            embed = make_embed(
                f"🚫 You're sending too much!, try again in `{round(error.retry_after, 1)}s`.",
                color=COLOR_RED,
                footer="Message will be deleted in 20 seconds.",
            )
            await send(ctx, embed=embed, ephemeral=True, delete_after=20)
            return

        if isinstance(error, commands.MissingPermissions):
            embed = make_embed(
                f"🚫 You don't have the required permissions to use this command.\nRequired permissions: `{', '.join(error.missing_permissions)}`",
                color=COLOR_RED,
            )
            await send(ctx, embed=embed, ephemeral=True)
            return

        if isinstance(error, commands.BotMissingPermissions):
            embed = make_embed(
                f"🚫 I don't have the required permissions to use this command.\nRequired permissions: `{', '.join(error.missing_permissions)}`",
                color=COLOR_RED,
            )
            await send(ctx, embed=embed)
            return

        if isinstance(error, commands.BotMissingRole):
            embed = make_embed(
                f"🚫 I don't have the required role to use this command.\nRequired role: `{error.missing_role}`",
                color=COLOR_RED,
            )
            await send(ctx, embed=embed, ephemeral=True)
            return

        if isinstance(error, discord.errors.NotFound) and "Unknown interaction" in str(
            error
        ):
            embed = make_embed(
                "⚠️ Discord API is not responding. Please try again in a minute.",
                color=COLOR_ORANGE_LIGHT,
            )
            if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                try:
                    await ctx.channel.send(embed=embed, delete_after=20)
                except discord.Forbidden:
                    pass
            return

        if isinstance(error, commands.NotOwner):
            embed = make_embed(
                "🚫 This command is available only to owner of this bot.",
                color=COLOR_RED,
            )
            await send(ctx, embed=embed, ephemeral=True)
            return

        if isinstance(error, commands.CommandInvokeError):
            logger.error("[Command Error] %s", error.original)
            return

        raise error

    async def on_tree_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await on_application_command_error(interaction, error)

    async def on_guild_join(guild: discord.Guild) -> None:
        logger.info("Joined new guild: %s", guild.name)

    bot.tree.error(on_tree_error)
    bot.event(on_application_command_error)
    bot.event(on_guild_join)
