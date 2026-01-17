import discord
from discord import app_commands
from discord.ext import commands
import secrets
from typing import Optional
from sqlalchemy import select

from database import User, GoogleAccount, CanvasAccount, async_session
from integrations import GoogleCalendarClient, CanvasClient
from utils.encryption import encrypt_token


# store pending OAuth states (in production, use Redis or database)
pending_oauth_states: dict[str, str] = {}


class LinkCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.google_client = GoogleCalendarClient()
        self.canvas_client = CanvasClient()
    
    @app_commands.command(name="link_google", description="Link a Google Calendar account")
    async def link_google(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # generate state token for OAuth
        state = secrets.token_urlsafe(32)
        pending_oauth_states[state] = user_id
        
        auth_url = self.google_client.get_auth_url(state)
        
        embed = discord.Embed(
            title="🔗 Link Google Calendar",
            description="Click the link below to authorize access to your Google Calendar.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Authorization Link",
            value=f"[Click here to authorize]({auth_url})",
            inline=False
        )
        embed.add_field(
            name="Next Steps",
            value="After authorizing, you'll be redirected. Copy the authorization code and use `/google_callback` to complete the setup.",
            inline=False
        )
        embed.set_footer(text="This link expires in 10 minutes")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="google_callback", description="Complete Google Calendar linking")
    @app_commands.describe(code="The authorization code from Google")
    async def google_callback(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        
        try:
            token_data = await self.google_client.exchange_code(code)
            
            async with async_session() as session:
                # ensure user exists
                result = await session.execute(
                    select(User).where(User.discord_user_id == user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    user = User(discord_user_id=user_id)
                    session.add(user)
                
                # check if account already linked
                email = token_data.get("email")
                result = await session.execute(
                    select(GoogleAccount).where(
                        GoogleAccount.discord_user_id == user_id,
                        GoogleAccount.account_email == email
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # update tokens
                    existing.access_token = token_data["access_token"]
                    if token_data.get("refresh_token"):
                        existing.refresh_token = token_data["refresh_token"]
                    existing.token_expires_at = token_data.get("token_expires_at")
                else:
                    # create new account link
                    google_account = GoogleAccount(
                        discord_user_id=user_id,
                        account_email=email,
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token", ""),
                        token_expires_at=token_data.get("token_expires_at"),
                    )
                    session.add(google_account)
                
                await session.commit()
            
            embed = discord.Embed(
                title="✅ Google Calendar Linked",
                description=f"Successfully linked **{email}**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="What's Next?",
                value="Use `/month`, `/week`, or `/year` to view your calendar!",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to link Google Calendar: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="link_canvas", description="Link a Canvas LMS account")
    @app_commands.describe(
        canvas_url="Your Canvas instance URL (e.g., https://canvas.instructure.com)",
        api_token="Your Canvas API token (get from Account > Settings > New Access Token)"
    )
    async def link_canvas(
        self,
        interaction: discord.Interaction,
        canvas_url: str,
        api_token: str
    ):
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        canvas_url = canvas_url.rstrip("/")
        
        # validate token
        user_info = await self.canvas_client.validate_token(canvas_url, api_token)
        
        if not user_info:
            await interaction.followup.send(
                "❌ Invalid Canvas URL or API token. Please check your credentials.",
                ephemeral=True
            )
            return
        
        async with async_session() as session:
            # ensure user exists
            result = await session.execute(
                select(User).where(User.discord_user_id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                user = User(discord_user_id=user_id)
                session.add(user)
            
            # check if already linked
            result = await session.execute(
                select(CanvasAccount).where(
                    CanvasAccount.discord_user_id == user_id,
                    CanvasAccount.canvas_url == canvas_url
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # update token
                existing.api_token = encrypt_token(api_token)
            else:
                # create new
                canvas_account = CanvasAccount(
                    discord_user_id=user_id,
                    canvas_url=canvas_url,
                    api_token=encrypt_token(api_token),
                )
                session.add(canvas_account)
            
            await session.commit()
        
        canvas_name = user_info.get("name", "Unknown")
        
        embed = discord.Embed(
            title="✅ Canvas Account Linked",
            description=f"Successfully linked Canvas account for **{canvas_name}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Canvas URL", value=canvas_url, inline=False)
        embed.add_field(
            name="What's Next?",
            value="Use `/assignments` to view your upcoming assignments!",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="unlink_google", description="Unlink a Google Calendar account")
    @app_commands.describe(email="Email of the Google account to unlink")
    async def unlink_google(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        
        async with async_session() as session:
            result = await session.execute(
                select(GoogleAccount).where(
                    GoogleAccount.discord_user_id == user_id,
                    GoogleAccount.account_email == email
                )
            )
            account = result.scalar_one_or_none()
            
            if not account:
                await interaction.followup.send(
                    f"No Google account found with email {email}",
                    ephemeral=True
                )
                return
            
            await session.delete(account)
            await session.commit()
        
        await interaction.followup.send(
            f"✅ Unlinked Google account **{email}**",
            ephemeral=True
        )
    
    @app_commands.command(name="unlink_canvas", description="Unlink a Canvas account")
    @app_commands.describe(canvas_url="URL of the Canvas instance to unlink")
    async def unlink_canvas(self, interaction: discord.Interaction, canvas_url: str):
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        canvas_url = canvas_url.rstrip("/")
        
        async with async_session() as session:
            result = await session.execute(
                select(CanvasAccount).where(
                    CanvasAccount.discord_user_id == user_id,
                    CanvasAccount.canvas_url == canvas_url
                )
            )
            account = result.scalar_one_or_none()
            
            if not account:
                await interaction.followup.send(
                    f"No Canvas account found for {canvas_url}",
                    ephemeral=True
                )
                return
            
            await session.delete(account)
            await session.commit()
        
        await interaction.followup.send(
            f"✅ Unlinked Canvas account for **{canvas_url}**",
            ephemeral=True
        )
    
    @app_commands.command(name="accounts", description="View all linked accounts")
    async def view_accounts(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        
        embed = discord.Embed(
            title="🔗 Linked Accounts",
            color=discord.Color.blue()
        )
        
        async with async_session() as session:
            # Google accounts
            result = await session.execute(
                select(GoogleAccount).where(GoogleAccount.discord_user_id == user_id)
            )
            google_accounts = result.scalars().all()
            
            if google_accounts:
                google_list = "\n".join([f"• {acc.account_email}" for acc in google_accounts])
            else:
                google_list = "*No accounts linked*"
            embed.add_field(name="📆 Google Calendar", value=google_list, inline=False)
            
            # Canvas accounts
            result = await session.execute(
                select(CanvasAccount).where(CanvasAccount.discord_user_id == user_id)
            )
            canvas_accounts = result.scalars().all()
            
            if canvas_accounts:
                canvas_list = "\n".join([f"• {acc.canvas_url}" for acc in canvas_accounts])
            else:
                canvas_list = "*No accounts linked*"
            embed.add_field(name="📚 Canvas LMS", value=canvas_list, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LinkCommands(bot))

