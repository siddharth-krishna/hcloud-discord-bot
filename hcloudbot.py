import asyncio
import hcloud as h
from hcloud import Client
from hcloud.server_types import ServerType
from hcloud.servers import ServerCreatePublicNetwork
import discord
from discord.ext import commands
import yaml
from os import path
from tabulate import tabulate
import datetime as dt
from humanize import naturaltime

# TODO
# auto shutdown
# start is blocking status until completed!
# ctr-c handler for bot shutdown?
# stop, kill
# logging
# help descriptions for category, args


def _relative_time(t: dt.datetime | None):
    if t:
        return naturaltime(dt.datetime.now(dt.timezone.utc) - t)
    return t


class CloudAdmin(commands.Cog):
    def __init__(self, hcloud_token, auth_user, *args, **kwargs):
        # super().__init__(*args, **kwargs)

        self.hClient = Client(token=hcloud_token)
        self.auth_user = auth_user  # TODO get bot owner from discord instead?
        return

    @commands.command(name="status")
    async def cloud_status(self, ctx):
        await ctx.send("Fetching status..")
        res = "```\n"
        servers = self.hClient.servers.get_all()
        res += tabulate(
            (
                (server.id, server.name, server.status, _relative_time(server.created))
                for server in servers
            ),
            headers=["Server ID", "Name", "Status", "Created"],
        )
        res += "\n\n"
        images = self.hClient.images.get_all(type="snapshot")
        res += tabulate(
            (
                (img.id, img.description, img.image_size, _relative_time(img.created))
                for img in images
            ),
            headers=["Image ID", "Description", "Size", "Created"],
        )
        res += "\n```\n"
        await ctx.send(res)

    @commands.command(name="start")
    async def start_server(self, ctx, server: str):
        images = self.hClient.images.get_all(type="snapshot")
        name_to_img = {img.description.split("-")[0]: img for img in images}
        if server not in name_to_img:
            await ctx.send(
                f"Error: could not find snapshot image for server `{server}`"
            )
            return
        name_to_ip = {"nub": 48363362}  # TODO save as labels on ip?
        try:
            response = self.hClient.servers.create(
                name=server,
                location=self.hClient.locations.get_by_name("hel1"),
                image=name_to_img[server],
                public_net=ServerCreatePublicNetwork(
                    ipv4=self.hClient.primary_ips.get_by_id(name_to_ip[server])
                ),
                server_type=ServerType(name="ccx33"),  # TODO default size in config?
                ssh_keys=self.hClient.ssh_keys.get_all(),
            )
        except h.APIException as e:
            await ctx.send(f"Error creating server: {e.message}")
            return
        await ctx.send(
            f"Creating server with: {response.action.command}"
        )  # TODO instead show params
        # TODO this is blocking, and also doesn't wait long enough
        try:
            response.action.wait_until_finished()
        except h.actions.ActionFailedException:
            await ctx.send(
                f"Error: server creation failed with: {response.action.error}"
            )
        except h.actions.ActionTimeoutException:
            await ctx.send(
                "Warning: got bored waiting for server creation, over to you"
            )
        else:
            await ctx.send("Server created successfully")

    @commands.command(name="start")
    async def stop_server(self, ctx, server_name: str):
        # hcloud server shutdown nub && sleep 30 && hcloud server create-image --type snapshot nub --description nub-02-16 && hcloud server delete nub && hcloud image delete 149793636; echo -e '\a'
        await ctx.send(f"Stopping server: {server_name}")
        server = self.hClient.servers.get_by_name(server_name)
        if server is None:
            await ctx.send(f"Error: could not find server `{server}`")
            return
        # 1. Shutdown:
        try:
            response = self.hClient.servers.shutdown(server)
        except h.APIException as e:
            await ctx.send(
                f"Error shutting down server: {e.message}\nSnapshotting and killing server.."
            )
        else:
            # TODO check response
            await ctx.send("Server shutdown. Now snapshotting..")
        await asyncio.sleep(30)
        # 2. Snapshot:
        try:
            response = self.hClient.servers.create_image(
                name=server,
                description=f"{server_name}-",  # TODO add date
                type="snapshot",
            )
        except h.APIException as e:
            await ctx.send(f"Error snapshotting server: {e.message}\nAborting shutdown")
            return
        else:
            # TODO check response
            await ctx.send("Server snapshotted. Now killing..")
        # 3. Kill:
        try:
            response = self.hClient.servers.delete(server)
        except h.APIException as e:
            await ctx.send(f"Error killing server: {e.message}\nPlease kill again")
        else:
            # TODO check response
            await ctx.send("Server killed. Now cleaning up image..")
        # 4. Delete old snapshot image:
        try:
            response = self.hClient.servers.delete(server)
        except h.APIException as e:
            await ctx.send(f"Error killing server: {e.message}\nPlease kill again")
        else:
            # TODO check response
            await ctx.send("Server killed. Now cleaning up image..")

    # TODO Only reply to authorized user
    # await message.channel.send("I don't talk to strangers")


config_path = path.join(path.dirname(__file__), "config.yaml")
config = yaml.safe_load(open(config_path))

intents = discord.Intents.default()
intents.message_content = True
description = "A bot to manage Hetzner Cloud"

bot = commands.Bot(command_prefix="", description=description, intents=intents)
cog = CloudAdmin(auth_user=config["auth-user"], hcloud_token=config["hcloud-token"])


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")


async def main():
    async with bot:
        await bot.add_cog(cog)
        await bot.start(config["discord-token"])


asyncio.run(main())
