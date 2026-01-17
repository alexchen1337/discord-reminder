import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from sqlalchemy import select

from database import CanvasAccount, async_session
from integrations import CanvasClient
from utils import CalendarRenderer


class AssignmentsPaginatorView(discord.ui.View):
    def __init__(self, cog, user_id: str, current_start: datetime, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.current_start = current_start
        self.days = 14  # 2 weeks
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("This isn't your view!", ephemeral=True)
            return
        
        await interaction.response.defer()
        self.current_start -= timedelta(days=self.days)
        await self._update(interaction)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("This isn't your view!", ephemeral=True)
            return
        
        await interaction.response.defer()
        self.current_start += timedelta(days=self.days)
        await self._update(interaction)
    
    async def _update(self, interaction: discord.Interaction):
        assignments = await self.cog._get_assignments(
            self.user_id,
            self.current_start,
            self.current_start + timedelta(days=self.days)
        )
        
        embed = self.cog.renderer.render_assignments_embed(
            assignments,
            self.days,
            self.current_start
        )
        await interaction.edit_original_response(embed=embed, view=self)


class CanvasCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.canvas_client = CanvasClient()
        self.renderer = CalendarRenderer()
    
    async def _get_assignments(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> list:
        """Fetch assignments from all linked Canvas accounts"""
        all_assignments = []
        
        async with async_session() as session:
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
                    all_assignments.extend(assignments)
                except Exception:
                    pass
        
        return sorted(all_assignments, key=lambda x: x.get("due_at", ""))
    
    @app_commands.command(name="assignments", description="View Canvas assignments due in next 2 weeks")
    async def view_assignments(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_id = str(interaction.user.id)
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=14)
        
        async with async_session() as session:
            result = await session.execute(
                select(CanvasAccount).where(CanvasAccount.discord_user_id == user_id)
            )
            canvas_accounts = result.scalars().all()
            
            if not canvas_accounts:
                embed = discord.Embed(
                    title="📚 Canvas Assignments",
                    description="No Canvas accounts linked. Use `/link_canvas` to connect your Canvas account.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return
        
        assignments = await self._get_assignments(user_id, start_date, end_date)
        
        embed = self.renderer.render_assignments_embed(assignments, 14, start_date)
        view = AssignmentsPaginatorView(self, user_id, start_date)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(CanvasCommands(bot))
