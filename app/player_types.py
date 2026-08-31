"""Typing helpers for the customised Lavalink player.

The bot attaches a handful of attributes to sonolink :class:`~sonolink.Player`
instances at runtime (see ``app.cogs.music_commands`` and ``app.cogs.listeners``).
:class:`KexoPlayer` documents those attributes for the type checker; it is never
instantiated directly - players are still created by sonolink.
"""

from __future__ import annotations

from typing import cast

import discord
import sonolink
from sonolink import models as sl_models


class KexoPlayer(sonolink.Player):
    """``sonolink.Player`` plus the attributes the bot assigns at runtime."""

    temp_current: sl_models.Playable | None
    _now_playing_sent: bool
    should_respond: bool
    text_channel: discord.abc.MessageableChannel


def get_player(ctx: discord.Interaction) -> KexoPlayer:
    """Return the guild's active player, typed as :class:`KexoPlayer`.

    Every call site is guarded by the ``is_joined`` / ``is_playing`` decorators or
    an explicit ``voice_client`` check, so the guild and the player are always
    present at runtime; the casts only narrow types.
    """
    guild = cast(discord.Guild, ctx.guild)
    return cast(KexoPlayer, guild.voice_client)


def guild_of(ctx: discord.Interaction) -> discord.Guild:
    """Return ``ctx.guild`` narrowed to :class:`discord.Guild`.

    Commands that use this are guild-only, so ``ctx.guild`` is never ``None`` at
    runtime; mirrors the pre-existing bare ``ctx.guild.*`` access.
    """
    return cast(discord.Guild, ctx.guild)


def member_of(ctx: discord.Interaction) -> discord.Member:
    """Return the invoking user as a :class:`discord.Member`.

    All music/voice commands are guild-only, so ``ctx.user`` is always a member at
    runtime; this only narrows the ``User | Member`` static type.
    """
    return cast(discord.Member, ctx.user)


def caller_voice_channel(ctx: discord.Interaction) -> discord.VoiceChannel:
    """Voice channel the invoking member is connected to.

    Mirrors the pre-existing ``ctx.user.voice.channel`` access (raises the same
    ``AttributeError`` if the member is not in a voice channel); call sites are
    guarded by ``is_joined`` / an explicit ``ctx.user.voice`` check.
    """
    voice = cast(discord.VoiceState, member_of(ctx).voice)
    return cast(discord.VoiceChannel, voice.channel)


def caller_voice_channel_id(ctx: discord.Interaction) -> int:
    """Id of the voice channel the invoking member is connected to."""
    return caller_voice_channel(ctx).id
