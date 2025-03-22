import discord
from discord.ext import commands
from functools import wraps
import wavelink


def is_joined():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # args[0] is self and args[1] is ctx.
            ctx = args[1]
            if not ctx.author.voice or not ctx.author.voice.channel:
                embed = discord.Embed(
                    title="",
                    description=f"{ctx.author.mention}, you're not in a voice channel. Type `/p` to join.",
                    color=discord.Color.blue()
                )
                return await ctx.respond(embed=embed, ephemeral=True)

            vc = ctx.voice_client

            if not vc or not getattr(vc, "_connected", False):
                embed = discord.Embed(
                    title="",
                    description=f"{ctx.author.mention}, I'm not joined in a voice channel.",
                    color=discord.Color.blue()
                )
                return await ctx.respond(embed=embed, ephemeral=True)

            if not vc.connected:
                try:
                    await ctx.author.voice.channel.connect(cls=wavelink.Player)
                except wavelink.InvalidChannelStateException:
                    embed = discord.Embed(
                        title="",
                        description=f":x: I don't have permissions to join your channel.",
                        color=discord.Color.from_rgb(r=255, g=0, b=0)
                    )
                    return await ctx.respond(embed=embed)

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
                embed = discord.Embed(title="",
                                      description=ctx.author.mention + ", bot is not playing anything. "
                                                                       "Type `/p` from vc.",
                                      color=discord.Color.blue())
                await ctx.respond(embed=embed, ephemeral=True)
                return

            if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
                embed = discord.Embed(title="", description=str(
                    ctx.author.mention) + ", bot is playing in a different voice channel.", color=discord.Color.blue())
                await ctx.respond(embed=embed)

            return await func(*args, **kwargs)

        return wrapper

    return decorator
