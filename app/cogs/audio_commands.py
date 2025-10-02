from typing import Optional

import discord
import wavelink
from discord import option
from discord.commands import slash_command, guild_only
from discord.ext import commands
from pycord.multicog import subcommand

from app.decorators import is_joined
from app.response_handler import send_response
from app.utils import get_guild_data


class Audio(commands.Cog):
    """Class for audio commands.

    Parameters
    ----------
    bot: class:`discord.Bot`
        The _bot instance.
    """

    def __init__(self, bot: commands.Bot):
        self._bot = bot

    @subcommand("music")
    @slash_command(name="volume", description="Sets audio volume.")
    @guild_only()
    @option(
        "volume",
        type=int,
        required=False,
        description="Max is 200.",
        min_value=1,
        max_value=200,
    )
    @is_joined()
    async def change_volume(
        self, ctx: discord.ApplicationContext, volume: Optional[int] = None
    ) -> None:
        """Sets the volume of the player.

        Parameters
        ----------
        ctx: class:`discord.ApplicationContext`
            The context of the command.
        volume: Optional[int]
            The volume to set. If not provided, it will return the current volume.
        """
        player: wavelink.Player = ctx.voice_client

        if volume is None:
            await send_response(ctx, "CURRENT_VOLUME", volume=player.volume)
            return

        guild_data, _ = await get_guild_data(self._bot, ctx.guild_id)
        guild_data["music"]["volume"] = volume
        await self._bot.guild_data_db.update_one(
            {"_id": ctx.guild_id}, {"$set": guild_data}
        )
        self._bot.guild_data[ctx.guild_id] = guild_data
        await player.set_volume(volume)
        await send_response(ctx, "VOLUME_CHANGED", ephemeral=False, volume=volume)

    @subcommand("music")
    @slash_command(name="speed", description="Speeds up music.")
    @guild_only()
    @option(
        "multiplier",
        type=int,
        required=False,
        description="It might take 3-5 seconds to start speeding up,"
        " no value sets it to normal speed",
        min_value=1,
        max_value=8,
    )
    @is_joined()
    async def speed(
        self, ctx: discord.ApplicationContext, multiplier: Optional[int] = 2
    ) -> None:
        """Sets the speed of the player.

        Parameters
        ----------
        ctx: class:`discord.ApplicationContext`
            The context of the command.
        multiplier: Optional[int]
            The multiplier to set. If not provided, it will set it to normal speed.
        """
        player: wavelink.Player = ctx.voice_client
        filters: wavelink.Filters = player.filters
        filters.timescale.set(speed=multiplier)

        await player.set_filters(filters)
        await send_response(
            ctx, "SPEED_CHANGED", ephemeral=False, multiplier=multiplier
        )

    @subcommand("music")
    @slash_command(name="clear-effects", description="Clears all effects on player.")
    @guild_only()
    @is_joined()
    async def clear_effects(self, ctx: discord.ApplicationContext) -> None:
        """Clears all effects on the player.

        Parameters
        ----------
        ctx: class:`discord.ApplicationContext`
            The context of the command.
        """
        player: wavelink.Player = ctx.voice_client
        filters: wavelink.Filters = player.filters

        filters.reset()
        await player.set_filters(filters)
        await send_response(ctx, "EFFECTS_CLEARED", ephemeral=False)


def setup(bot: commands.Bot):
    """Sets up the Audio cog."""
    bot.add_cog(Audio(bot))
