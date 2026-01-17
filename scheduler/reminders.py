import discord
from discord.ext import commands
from datetime import datetime, timedelta, date
from sqlalchemy import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database import (
    User, GoogleAccount, CanvasAccount, SentReminder, async_session
)
from integrations import GoogleCalendarClient, CanvasClient
from utils import CalendarRenderer
import config


class ReminderScheduler:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.google_client = GoogleCalendarClient()
        self.canvas_client = CanvasClient()
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
        
        # check for new Canvas announcements every 30 minutes
        self.scheduler.add_job(
            self.check_canvas_announcements,
            IntervalTrigger(minutes=config.ANNOUNCEMENT_CHECK_INTERVAL),
            id="announcement_check",
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
        canvas_assignments = []
        
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
        
        # fetch Canvas assignments
        result = await session.execute(
            select(CanvasAccount).where(CanvasAccount.discord_user_id == user_id)
        )
        canvas_accounts = result.scalars().all()
        
        for account in canvas_accounts:
            try:
                assignments = await self.canvas_client.get_assignments(
                    account.canvas_url,
                    account.api_token,
                    days_ahead=config.REMINDER_DAYS_AHEAD
                )
                canvas_assignments.extend(assignments)
            except Exception:
                pass
        
        # only send if there's something to report
        if not google_events and not canvas_assignments:
            return
        
        # get Discord user and send DM
        try:
            discord_user = await self.bot.fetch_user(int(user_id))
            if discord_user:
                embed = self.renderer.render_daily_summary_embed(
                    google_events,
                    canvas_assignments,
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
    
    async def check_canvas_announcements(self):
        """Check for new Canvas announcements and send notifications"""
        async with async_session() as session:
            result = await session.execute(select(CanvasAccount))
            canvas_accounts = result.scalars().all()
            
            for account in canvas_accounts:
                try:
                    # check for announcements in the last hour
                    since = datetime.utcnow() - timedelta(minutes=config.ANNOUNCEMENT_CHECK_INTERVAL + 5)
                    announcements = await self.canvas_client.get_announcements(
                        account.canvas_url,
                        account.api_token,
                        since=since
                    )
                    
                    for ann in announcements:
                        await self._send_announcement_notification(
                            account.discord_user_id,
                            ann,
                            session
                        )
                    
                    await session.commit()
                except Exception:
                    pass
    
    async def _send_announcement_notification(self, user_id: str, announcement: dict, session):
        """Send notification for a new Canvas announcement"""
        ann_id = f"canvas_ann_{announcement.get('id')}"
        
        # check if already sent
        result = await session.execute(
            select(SentReminder).where(
                SentReminder.discord_user_id == user_id,
                SentReminder.reminder_type == "announcement",
                SentReminder.event_id == ann_id
            )
        )
        if result.scalar_one_or_none():
            return
        
        try:
            discord_user = await self.bot.fetch_user(int(user_id))
            if discord_user:
                course = announcement.get("course", "Unknown Course")
                title = announcement.get("title", "Untitled")
                message = announcement.get("message", "")[:500]
                if len(announcement.get("message", "")) > 500:
                    message += "..."
                author = announcement.get("author", "Instructor")
                url = announcement.get("url")
                
                embed = discord.Embed(
                    title=f"📢 New Announcement: {title}",
                    description=message,
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="Course", value=course, inline=True)
                if author:
                    embed.add_field(name="Posted by", value=author, inline=True)
                if url:
                    embed.add_field(name="Link", value=f"[View in Canvas]({url})", inline=False)
                
                await discord_user.send(embed=embed)
                
                # mark as sent
                reminder = SentReminder(
                    discord_user_id=user_id,
                    reminder_type="announcement",
                    event_id=ann_id,
                )
                session.add(reminder)
        except discord.Forbidden:
            pass
        except Exception:
            pass
