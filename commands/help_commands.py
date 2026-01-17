import discord
from discord import app_commands
from discord.ext import commands


class HelpCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="help", description="Show all available commands and what they do")
    async def help_command(self, interaction: discord.Interaction):
        """Display help information about all commands"""
        embed = discord.Embed(
            title="📖 Calendar Reminder Bot - Help",
            description="Here's everything I can do for you!",
            color=discord.Color.blue()
        )
        
        # Account Management
        embed.add_field(
            name="🔗 Account Management",
            value=(
                "`/link_google` - Link your Google Calendar account\n"
                "└ *Starts the OAuth flow to authorize access*\n\n"
                "`/google_callback <code>` - Complete Google authorization\n"
                "└ *Paste the authorization code from the redirect URL*\n\n"
                "`/unlink_google <email>` - Unlink a Google account\n"
                "└ *Remove a linked Google Calendar account*\n\n"
                "`/accounts` - View all your linked accounts\n"
                "└ *See which Google accounts are connected*"
            ),
            inline=False
        )
        
        # Calendar Views
        embed.add_field(
            name="📅 Calendar Views",
            value=(
                "`/year` - View the current year's calendar\n"
                "└ *Shows all events for the year, use ◀▶ to navigate*\n\n"
                "`/month` - View the current month's calendar\n"
                "└ *Shows all events this month, use ◀▶ to navigate*\n\n"
                "`/week` - View the current week (today + 6 days)\n"
                "└ *Shows events for the next 7 days, use ◀▶ to navigate*"
            ),
            inline=False
        )
        
        # Automatic Reminders
        embed.add_field(
            name="🔔 Automatic Reminders",
            value=(
                "**Daily Summary** - Every day at 8 AM\n"
                "└ *Get a summary of events in the next 7 days*\n\n"
                "**Hour Before** - 1 hour before each event\n"
                "└ *Reminder sent 60 minutes before event starts*"
            ),
            inline=False
        )
        
        # Tips
        embed.add_field(
            name="💡 Tips",
            value=(
                "• You can link multiple Google accounts\n"
                "• All reminders are sent via DM\n"
                "• Make sure your DMs are enabled!\n"
                "• Calendar views update in real-time"
            ),
            inline=False
        )
        
        embed.set_footer(text="Need more help? Contact your server admin!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCommands(bot))

