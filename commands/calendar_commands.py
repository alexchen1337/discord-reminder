import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, date, timedelta
from sqlalchemy import select

from database import GoogleAccount, async_session
from integrations import GoogleCalendarClient
from utils import CalendarRenderer


class CalendarPaginatorView(discord.ui.View):
    def __init__(self, cog, user_id: str, view_type: str, current_value, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.view_type = view_type  # 'year', 'month', 'week'
        self.current_value = current_value  # year int, (year, month) tuple, or date
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("This isn't your calendar!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        if self.view_type == "year":
            self.current_value -= 1
            await self._update_year(interaction)
        elif self.view_type == "month":
            year, month = self.current_value
            if month == 1:
                self.current_value = (year - 1, 12)
            else:
                self.current_value = (year, month - 1)
            await self._update_month(interaction)
        elif self.view_type == "week":
            self.current_value -= timedelta(days=7)
            await self._update_week(interaction)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("This isn't your calendar!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        if self.view_type == "year":
            self.current_value += 1
            await self._update_year(interaction)
        elif self.view_type == "month":
            year, month = self.current_value
            if month == 12:
                self.current_value = (year + 1, 1)
            else:
                self.current_value = (year, month + 1)
            await self._update_month(interaction)
        elif self.view_type == "week":
            self.current_value += timedelta(days=7)
            await self._update_week(interaction)
    
    async def _update_year(self, interaction: discord.Interaction):
        year = self.current_value
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
        
        events = await self.cog._get_all_events(self.user_id, start_date, end_date)
        embeds = self.cog.renderer.render_year_embed(year, events)
        await interaction.edit_original_response(embeds=embeds, view=self)
    
    async def _update_month(self, interaction: discord.Interaction):
        year, month = self.current_value
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)
        
        events = await self.cog._get_all_events(self.user_id, start_date, end_date)
        embed = self.cog.renderer.render_month_embed(year, month, events)
        await interaction.edit_original_response(embed=embed, view=self)
    
    async def _update_week(self, interaction: discord.Interaction):
        start_date = self.current_value
        end_date = start_date + timedelta(days=6)
        
        events = await self.cog._get_all_events(
            self.user_id,
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.max.time())
        )
        embed = self.cog.renderer.render_week_embed(start_date, events)
        await interaction.edit_original_response(embed=embed, view=self)


class CalendarCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.google_client = GoogleCalendarClient()
        self.canvas_client = CanvasClient()
        self.renderer = CalendarRenderer()
    
    async def _get_all_events(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> list:
        """Fetch events from all linked accounts"""
        all_events = []
        
        async with async_session() as session:
            result = await session.execute(
                select(GoogleAccount).where(GoogleAccount.discord_user_id == user_id)
            )
            google_accounts = result.scalars().all()
            
            for account in google_accounts:
                try:
                    events, new_token, new_expiry = await self.google_client.get_events(
                        account.access_token,
                        account.refresh_token,
                        account.token_expires_at,
                        start_date,
                        end_date
                    )
                    all_events.extend(events)
                    
                    if new_token:
                        account.access_token = new_token
                        account.token_expires_at = new_expiry
                        await session.commit()
                except Exception:
                    pass
            
            result = await session.execute(
                select(CanvasAccount).where(CanvasAccount.discord_user_id == user_id)
            )
            canvas_accounts = result.scalars().all()
            
            for account in canvas_accounts:
                try:
                    assignments = await self.canvas_client.get_all_assignments(
                        account.canvas_url,
                        account.api_token,
                        start_date,
                        end_date
                    )
                    all_events.extend(assignments)
                except Exception:
                    pass
        
        return sorted(all_events, key=lambda x: x.get("date", ""))
    
    @app_commands.command(name="year", description="View this year's calendar")
    async def view_year(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        year = datetime.now().year
        user_id = str(interaction.user.id)
        
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
        
        events = await self._get_all_events(user_id, start_date, end_date)
        
        if not events:
            embed = discord.Embed(
                title=f"📅 {year}",
                description="No events found. Link your accounts with `/link_google` or `/link_canvas`",
                color=discord.Color.gray()
            )
            await interaction.followup.send(embed=embed)
            return
        
        embeds = self.renderer.render_year_embed(year, events)
        view = CalendarPaginatorView(self, user_id, "year", year)
        await interaction.followup.send(embeds=embeds, view=view)
    
    @app_commands.command(name="month", description="View this month's calendar")
    async def view_month(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        now = datetime.now()
        year, month = now.year, now.month
        user_id = str(interaction.user.id)
        
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)
        
        events = await self._get_all_events(user_id, start_date, end_date)
        
        embed = self.renderer.render_month_embed(year, month, events)
        view = CalendarPaginatorView(self, user_id, "month", (year, month))
        await interaction.followup.send(embed=embed, view=view)
    
    @app_commands.command(name="week", description="View this week's calendar")
    async def view_week(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        start_date = date.today()
        end_date = start_date + timedelta(days=6)
        user_id = str(interaction.user.id)
        
        events = await self._get_all_events(
            user_id,
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.max.time())
        )
        
        embed = self.renderer.render_week_embed(start_date, events)
        view = CalendarPaginatorView(self, user_id, "week", start_date)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(CalendarCommands(bot))
