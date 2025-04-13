from functools import wraps

import discord
import wavelink

from utils import find_track


def is_joined():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # args[0] is self and args[1] is ctx.
            ctx = args[1]
            if not ctx.author.voice or not ctx.author.voice.channel:
                embed = discord.Embed(
                    title="",
                    description=f"{ctx.author.mention},"
                    f" you're not in a voice channel. Type `/p` to join.",
                    color=discord.Color.blue(),
                )
                return await ctx.respond(embed=embed, ephemeral=True)

            vc = ctx.voice_client

            if not vc or not getattr(vc, "_connected", False):
                embed = discord.Embed(
                    title="",
                    description=f"{ctx.author.mention}, I'm not joined in a voice channel.",
                    color=discord.Color.blue(),
                )
                return await ctx.respond(embed=embed, ephemeral=True)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_playing():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = args[1]
            vc = ctx.voice_client
            if not vc or not vc.playing or not vc.current:
                embed = discord.Embed(
                    title="",
                    description=ctx.author.mention + ", bot is not playing anything. "
                    "Type `/p` from vc.",
                    color=discord.Color.blue(),
                )
                await ctx.respond(embed=embed, ephemeral=True)
                return

            if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
                embed = discord.Embed(
                    title="",
                    description=str(ctx.author.mention)
                    + ", bot is playing in a different voice channel.",
                    color=discord.Color.blue(),
                )
                await ctx.respond(embed=embed)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_queue_empty():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = args[1]
            vc = ctx.voice_client
            if not vc or not vc.queue:
                embed = discord.Embed(
                    title="",
                    description=ctx.author.mention + ", queue is empty.",
                    color=discord.Color.blue(),
                )
                await ctx.respond(embed=embed, ephemeral=True)
                return

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_song_in_queue():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = args[1]
            to_find = kwargs["to_find"]
            player = ctx.voice_client

            if not find_track(player, to_find):
                embed = discord.Embed(
                    title="",
                    description=ctx.author.mention + ", track not found in queue.",
                    color=discord.Color.blue(),
                )
                await ctx.respond(embed=embed, ephemeral=True)
                return

            return await func(*args, **kwargs)

        return wrapper

    return decorator
