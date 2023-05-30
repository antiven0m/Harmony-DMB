import os
import sys
import asyncio

import discord
from discord.ext import commands

from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Set up logging
def setup_logger():
    """Configures the logging settings."""
    logger.add(
        sys.stderr,
        colorize=True,
        format="<green>{time:MM-DD-YYYY %I:%M %p}</green> | <yellow><level>{level: <2}</level></yellow> | <level>{message}</level>",
        level="INFO",
        enqueue=True
    )

# Get environment variables
BOT_VERSION = os.getenv("VERSION")
BOT_PREFIX = os.getenv("PREFIX")
DISCORD_TOKEN = os.getenv("TOKEN")
BOT_OWNER = os.getenv("OWNER")

# Set up bot status
BOT_STATUS = discord.Activity(
    type=discord.ActivityType.watching,
    name=f"{BOT_PREFIX}help | v{BOT_VERSION}"
)

class ID4(commands.Bot): 
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(BOT_PREFIX),
            owner_id=BOT_OWNER,
            activity=BOT_STATUS,
            case_insensitive=True,
            description="ID4 is an asynchronous Discord bot written in Python using the discord.py library.",
            status=discord.Status.online,
            intents=discord.Intents.all(),
        )

    async def on_ready(self) -> None:
        logger.info(
            f"Discord.py API version: {discord.__version__}, Python version: {sys.version}"
        )
        self.bot_info = await self.application_info()
        for guild in self.guilds:
            logger.info(f"Connected to {guild.name} (ID: {guild.id})")
        logger.info(f"Serving {len(self.users)} users in {len(self.guilds)} servers.")
        await self.load_cogs()

    async def load_cogs(self) -> None:
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                cog_name = filename[:-3]
                try:
                    await self.load_extension(f"cogs.{cog_name}")
                    logger.info(f"Loaded {cog_name}")
                except Exception as e:
                    logger.error(f"Failed to load {cog_name}")
                    logger.error(e)

if __name__ == "__main__":
    setup_logger()
    logger.info("Starting up...")
    bot = ID4()
    logger.info("Logging in...")
    bot.run(DISCORD_TOKEN)
