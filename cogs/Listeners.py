import discord
import wavelink

from discord.ext import commands
from cogs.Disconnect import Disconnect
from wavelink import NodeDisconnectedEventPayload, NodeReadyEventPayload


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: NodeReadyEventPayload) -> None:
        print(f"Node {payload.node.uri} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: NodeDisconnectedEventPayload) -> None:
        print(f"Node {payload.node.uri} is disconnected!")
        await self.bot.get_lavalink_server()
        await self.bot.connect_node(switch_node=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
            self,
            member: discord.member.Member,
            before: discord.VoiceState,
            after: discord.VoiceState) -> None:

        voice_state = member.guild.voice_client
        if voice_state is None:
            return

        if len(voice_state.channel.members) == 1:
            await Disconnect.disconnect_player(member.guild)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Listeners(bot))
