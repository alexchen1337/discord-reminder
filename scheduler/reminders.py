import discord
from discord.ext import commands
from datetime import datetime, timedelta, date
from sqlalchemy import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database import (
    User, GoogleAccount, SentReminder, async_session
)
from integrations import GoogleCalendarClient
from utils import CalendarRenderer
import config


class ReminderScheduler:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.google_client = GoogleCalendarClient()
        self.renderer = CalendarRenderer()
    
    def start(self):
        """Start the scheduler with all jobs"""
        # daily summary at 8 AM
        self.scheduler.add_job(
            self.send_daily_summaries,
            CronTrigger(hour=config.DAILY_REMINDER_HOUR, minute=0),
            id="daily_summary",
            replace_existing=True
        )
        
        # check for hour-before reminders every 5 minutes
        self.scheduler.add_job(
            self.check_hour_before_reminders,
            IntervalTrigger(minutes=config.HOUR_BEFORE_CHECK_INTERVAL),
            id="hour_before_check",
            replace_existing=True
        )
        
        self.scheduler.start()
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
    
    async def send_daily_summaries(self):
        """Send daily summary to all users with linked accounts"""
        async with async_session() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()
            
            for user in users:
                await self._send_user_daily_summary(user.discord_user_id, session)
    
    async def _send_user_daily_summary(self, user_id: str, session):
        """Send daily summary to a specific user"""
        today = date.today().isoformat()
        
        # check if already sent today
        result = await session.execute(
            select(SentReminder).where(
                SentReminder.discord_user_id == user_id,
                SentReminder.reminder_type == "daily_summary",
                SentReminder.event_id == today
            )
        )
        if result.scalar_one_or_none():
            return
        
        google_events = []
        
        # fetch Google Calendar events
        result = await session.execute(
            select(GoogleAccount).where(GoogleAccount.discord_user_id == user_id)
        )
        google_accounts = result.scalars().all()
        
        for account in google_accounts:
            try:
                events, new_token, new_expiry = await self.google_client.get_upcoming_events(
                    account.access_token,
                    account.refresh_token,
                    account.token_expires_at,
                    days=config.REMINDER_DAYS_AHEAD
                )
                google_events.extend(events)
                
                if new_token:
                    account.access_token = new_token
                    account.token_expires_at = new_expiry
            except Exception:
                pass
        
        # only send if there's something to report
        if not google_events:
            return
        
        # get Discord user and send DM
        try:
            discord_user = await self.bot.fetch_user(int(user_id))
            if discord_user:
                embed = self.renderer.render_daily_summary_embed(
                    google_events,
                    days=config.REMINDER_DAYS_AHEAD
                )
                await discord_user.send(embed=embed)
                
                # mark as sent
                reminder = SentReminder(
                    discord_user_id=user_id,
                    reminder_type="daily_summary",
                    event_id=today,
                    scheduled_time=datetime.utcnow(),
                )
                session.add(reminder)
                await session.commit()
        except discord.Forbidden:
            pass
        except Exception:
            pass
    
    async def check_hour_before_reminders(self):
        """Check for events starting in the next hour and send reminders"""
        async with async_session() as session:
            result = await session.execute(select(GoogleAccount))
            google_accounts = result.scalars().all()
            
            for account in google_accounts:
                try:
                    events, new_token, new_expiry = await self.google_client.get_events_starting_soon(
                        account.access_token,
                        account.refresh_token,
                        account.token_expires_at,
                        hours=1
                    )
                    
                    if new_token:
                        account.access_token = new_token
                        account.token_expires_at = new_expiry
                    
                    for event in events:
                        await self._send_hour_before_reminder(
                            account.discord_user_id,
                            event,
                            session
                        )
                    
                    await session.commit()
                except Exception:
                    pass
    
    async def _send_hour_before_reminder(self, user_id: str, event: dict, session):
        """Send hour-before reminder for a specific event"""
        event_id = event.get("id")
        
        # check if already sent
        result = await session.execute(
            select(SentReminder).where(
                SentReminder.discord_user_id == user_id,
                SentReminder.reminder_type == "hour_before",
                SentReminder.event_id == str(event_id)
            )
        )
        if result.scalar_one_or_none():
            return
        
        try:
            discord_user = await self.bot.fetch_user(int(user_id))
            if discord_user:
                event_date = event.get("date")
                if isinstance(event_date, str):
                    event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                
                time_str = event_date.strftime("%H:%M") if event_date else "Soon"
                
                embed = discord.Embed(
                    title="⏰ Event Starting Soon!",
                    description=f"**{event.get('title', 'Untitled')}** starts in about 1 hour",
                    color=discord.Color.red()
                )
                embed.add_field(name="Time", value=time_str, inline=True)
                if event.get("location"):
                    embed.add_field(name="Location", value=event["location"], inline=True)
                
                await discord_user.send(embed=embed)
                
                # mark as sent
                reminder = SentReminder(
                    discord_user_id=user_id,
                    reminder_type="hour_before",
                    event_id=str(event_id),
                    scheduled_time=event_date if isinstance(event_date, datetime) else None,
                )
                session.add(reminder)
        except discord.Forbidden:
            pass
        except Exception:
            pass
    
