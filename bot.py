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


class WelcomeView(discord.ui.View):
    """Persistent view for the welcome message button"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Get Started! 🚀", style=discord.ButtonStyle.primary, custom_id="welcome_button")
    async def welcome_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Send introduction DM when user clicks the button"""
        try:
            embed = discord.Embed(
                title="👋 Welcome to Calendar Reminder Bot!",
                description="I'm here to help you stay on top of your schedule by sending you reminders from your Google Calendar.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="🔗 Getting Started",
                value="First, link your Google Calendar account using `/link_google`. I'll guide you through the authorization process!",
                inline=False
            )
            
            embed.add_field(
                name="📅 What I Can Do",
                value=(
                    "• Send daily summaries of upcoming events (8 AM)\n"
                    "• Remind you 1 hour before events\n"
                    "• Show calendar views (year, month, week)\n"
                    "• Keep track of multiple Google accounts"
                ),
                inline=False
            )
            
            embed.add_field(
                name="❓ Need Help?",
                value="Use `/help` to see all available commands and what they do!",
                inline=False
            )
            
            embed.set_footer(text="Let's get you organized! 📆")
            
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Check your DMs for setup instructions!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I couldn't send you a DM. Please enable DMs from server members in your privacy settings!",
                ephemeral=True
            )


class CalendarBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Calendar reminder bot with Google Calendar"
        )
        
        self.reminder_scheduler: ReminderScheduler = None
    
    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Initializing database...")
        await init_db()
        
        logger.info("Loading command cogs...")
        await self.load_extension("commands.calendar_commands")
        await self.load_extension("commands.link_commands")
        await self.load_extension("commands.help_commands")
        
        # Add persistent view for welcome button
        self.add_view(WelcomeView())
        
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
    
    async def on_guild_join(self, guild: discord.Guild):
        """Send welcome message when bot joins a server"""
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
        
        # Find the first text channel we can send to
        channel = None
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break
        
        if channel:
            embed = discord.Embed(
                title="👋 Hi! I'm Calendar Reminder Bot",
                description=(
                    "I'm here to remind you of things in case you don't check your calendar or you're gaming! 🎮\n\n"
                    "I'll send you reminders for your Google Calendar events so you never miss anything important."
                ),
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🚀 Ready to get started?",
                value="Click the button below to receive a DM with setup instructions!",
                inline=False
            )
            
            embed.set_footer(text="Use /help to see all available commands")
            
            view = WelcomeView()
            await channel.send(embed=embed, view=view)
    
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

