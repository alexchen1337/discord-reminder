import asyncio
import discord
from discord.ext import commands
import logging

import config
from database import init_db
from scheduler import ReminderScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CalendarBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Calendar reminder bot with Google Calendar and Canvas"
        )
        
        self.reminder_scheduler: ReminderScheduler = None
    
    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Initializing database...")
        await init_db()
        
        logger.info("Loading command cogs...")
        await self.load_extension("commands.calendar_commands")
        await self.load_extension("commands.canvas_commands")
        await self.load_extension("commands.link_commands")
        
        logger.info("Syncing slash commands...")
        await self.tree.sync()
        
        logger.info("Starting reminder scheduler...")
        self.reminder_scheduler = ReminderScheduler(self)
        self.reminder_scheduler.start()
    
    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")
        
        # set status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="your calendar 📅"
            )
        )
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        
        logger.error(f"Command error: {error}", exc_info=error)
        
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid argument: {error}")
        else:
            await ctx.send("An error occurred while processing your command.")
    
    async def close(self):
        """Cleanup when bot is shutting down"""
        if self.reminder_scheduler:
            logger.info("Stopping reminder scheduler...")
            self.reminder_scheduler.stop()
        
        await super().close()


async def main():
    if not config.DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set in environment")
        return
    
    bot = CalendarBot()
    
    try:
        await bot.start(config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())

