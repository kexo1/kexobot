import datetime

import discord
import wavelink
from discord.commands import slash_command, option, guild_only
from discord.ext import commands
from pycord.multicog import subcommand

from app.decorators import is_playing, is_joined, is_queue_empty
from app.response_handler import send_response
from app.utils import find_track, fix_audio_title


# noinspection PyUnusedLocal
class QueuePaginator(discord.ui.View):
    def __init__(self, embeds: list, timeout: int = 600) -> None:
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0

    async def update_message(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if self.current_page > 0:
            self.current_page -= 1
        else:
            self.current_page = len(self.embeds) - 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
        else:
            self.current_page = 0
        await self.update_message(interaction)


class Queue(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @subcommand("music")
    @slash_command(name="queue", description="Shows the current queue")
    @guild_only()
    @is_joined()
    @is_queue_empty()
    async def queue(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client
        pages = await self._get_queue_embeds(ctx, player)

        if len(pages) == 1:
            await ctx.respond(embed=pages[0])
        else:
            view = QueuePaginator(pages)
            await ctx.respond(embed=pages[0], view=view)

    @subcommand("music")
    @slash_command(name="playing", description="What track is currently playing")
    @guild_only()
    @is_playing()
    async def playing_command(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond(embed=await self._get_playing_embed(ctx))

    @subcommand("music")
    @slash_command(name="remove", description="Removes a song from the queue")
    @guild_only()
    @option(
        "to_find",
        description="Both position in the queue and name of the song are accepted.",
    )
    @is_joined()
    @is_queue_empty()
    async def remove(self, ctx: discord.ApplicationContext, to_find: str):
        player: wavelink.Player = ctx.voice_client
        track_pos = find_track(player, to_find)
        if track_pos is None:
            await send_response(ctx, "NO_TRACK_FOUND_IN_QUEUE", to_find=to_find)
            return

        track = player.queue[track_pos - 1]
        del player.queue[track_pos - 1]
        await send_response(
            ctx,
            "QUEUE_TRACK_REMOVED",
            ephemeral=False,
            title=track.title,
            uri=track.uri,
        )

    @subcommand("music")
    @slash_command(
        name="shuffle",
        description="Shuffles the queue",
    )
    @guild_only()
    @is_joined()
    @is_queue_empty()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player: wavelink.Player = ctx.voice_client

        if len(player.queue) < 2:
            await send_response(ctx, "CANT_SHUFFLE")
            return

        player.queue.shuffle()
        await send_response(ctx, "QUEUE_SHUFFLED", ephemeral=False)

    @subcommand("music")
    @slash_command(
        name="loop-queue",
        description="Loops queue, run command again to disable queue loop",
    )
    @guild_only()
    @is_joined()
    @is_queue_empty()
    async def loop_queue(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.queue.mode == wavelink.QueueMode.loop_all:
            player.queue.mode = wavelink.QueueMode.loop_all
            await send_response(ctx, "QUEUE_LOOP_DISABLED")
            return

        player.queue.mode = wavelink.QueueMode.loop_all
        await send_response(
            ctx, "QUEUE_LOOP_ENABLED", ephemeral=False, count=player.queue.count
        )

    @subcommand("music")
    @slash_command(
        name="loop",
        description="Loops currently playing song, run command again to disable loop.",
    )
    @guild_only()
    @is_playing()
    async def loop(self, ctx: discord.ApplicationContext) -> None:
        player: wavelink.Player = ctx.voice_client

        if player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.normal
            await send_response(ctx, "TRACK_LOOP_DISABLED")
            return

        player.queue.mode = wavelink.QueueMode.loop
        await send_response(
            ctx,
            "TRACK_LOOP_ENABLED",
            ephemeral=False,
            title=player.current.title,
            uri=player.current.uri,
        )

    @subcommand("music")
    @slash_command(name="clear", description="Clears queue")
    @guild_only()
    @is_joined()
    async def clear_queue(self, ctx: discord.ApplicationContext):
        player: wavelink.Player = ctx.voice_client
        player.queue.clear()

        await send_response(ctx, "QUEUE_CLEARED", ephemeral=False)

    async def _get_queue_embeds(
        self, ctx: discord.ApplicationContext, player: wavelink.Player
    ) -> list:
        queue_status, footer = await self._get_queue_status(player.queue.mode)

        header = (
            f"\n***__{queue_status}:__***\n **[{fix_audio_title(player.current)}]({player.current.uri})**\n"
            f" `{int(divmod(player.current.length, 60000)[0])}:{round(divmod(player.current.length, 60000)[1] / 1000):02} | "
            f"Requested by: {player.current.requester.name}`\n\n ***__Next:__***\n"
        )

        pages = []
        current_description = header

        for pos, track in enumerate(player.queue):
            song_line = (
                f"`{pos + 1}.` **[{fix_audio_title(track)}]({track.uri})**\n"
                f" `{int(divmod(track.length, 60000)[0])}:{round(divmod(track.length, 60000)[1] / 1000):02} | "
                f"Requested by: {track.requester.name}`\n"
            )
            if len(current_description) + len(song_line) > 4000:
                embed = discord.Embed(
                    title=f"Queue for {ctx.guild.name}",
                    description=current_description,
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"\n{footer}{player.queue.count} songs in queue")
                pages.append(embed)
                current_description = header + song_line
            else:
                current_description += song_line

        embed = discord.Embed(
            title=f"Queue for {ctx.guild.name}",
            description=current_description,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"\n{footer}{player.queue.count} songs in queue")
        pages.append(embed)
        return pages

    @staticmethod
    async def _get_queue_status(queue_mode: wavelink.QueueMode) -> tuple:
        if queue_mode == wavelink.QueueMode.loop_all:
            return "Looping queue", "🔁 "

        if queue_mode == wavelink.QueueMode.loop:
            return "Looping currently playing song", "🔁 "

        return "Now Playing", ""

    @staticmethod
    async def _get_playing_embed(ctx: discord.ApplicationContext) -> discord.Embed:
        player: wavelink.Player = ctx.voice_client

        embed = discord.Embed(
            title="Now playing",
            colour=discord.Colour.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_author(name="Playback Information")
        embed.set_footer(
            text=f"Requested by {player.current.requester.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        embed.add_field(
            name="Track title",
            value=f"**[{player.current.title}]({player.current.uri})**",
            inline=False,
        )
        embed.add_field(
            name="Artist",
            value=f"_{player.current.author if player.current.author else 'None'}_",
            inline=False,
        )
        embed.set_image(url=player.current.artwork)
        position = divmod(player.position, 60000)
        length = divmod(player.current.length, 60000)
        embed.add_field(
            name="Position",
            value=f"`{int(position[0])}:{round(position[1] / 1000):02}"
            f"/{int(length[0])}:{round(length[1] / 1000):02}`",
            inline=False,
        )
        return embed


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Queue(bot))
