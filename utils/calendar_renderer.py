import calendar
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import discord


class CalendarRenderer:
    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    @staticmethod
    def render_year_embed(year: int, events: List[Dict[str, Any]]) -> List[discord.Embed]:
        """Render a full year calendar with events summary"""
        embeds = []
        
        # group events by month
        events_by_month: Dict[int, List[Dict]] = {m: [] for m in range(1, 13)}
        for event in events:
            event_date = event.get("date")
            if isinstance(event_date, str):
                event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00")).date()
            elif isinstance(event_date, datetime):
                event_date = event_date.date()
            
            if event_date.year == year:
                events_by_month[event_date.month].append(event)
        
        # create embeds for each quarter (3 months per embed to stay within limits)
        for quarter in range(4):
            embed = discord.Embed(
                title=f"📅 {year} - Q{quarter + 1}",
                color=discord.Color.blue()
            )
            
            for month_offset in range(3):
                month = quarter * 3 + month_offset + 1
                month_name = calendar.month_name[month]
                month_events = events_by_month[month]
                
                if month_events:
                    event_lines = []
                    for event in sorted(month_events, key=lambda e: e.get("date", "")):
                        event_date = event.get("date")
                        if isinstance(event_date, str):
                            event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                        elif isinstance(event_date, date) and not isinstance(event_date, datetime):
                            event_date = datetime.combine(event_date, datetime.min.time())
                        
                        day = event_date.day if event_date else "?"
                        title = event.get("title", "Untitled")[:30]
                        source = event.get("source", "")
                        source_icon = "📆" if source == "google" else "📚"
                        event_lines.append(f"`{day:2d}` {source_icon} {title}")
                    
                    value = "\n".join(event_lines[:10])
                    if len(event_lines) > 10:
                        value += f"\n*...and {len(event_lines) - 10} more*"
                else:
                    value = "*No events*"
                
                embed.add_field(name=f"**{month_name}**", value=value, inline=True)
            
            embeds.append(embed)
        
        return embeds
    
    @staticmethod
    def render_month_embed(year: int, month: int, events: List[Dict[str, Any]]) -> discord.Embed:
        """Render a single month calendar with events"""
        month_name = calendar.month_name[month]
        cal = calendar.Calendar(firstweekday=0)
        
        embed = discord.Embed(
            title=f"📅 {month_name} {year}",
            color=discord.Color.green()
        )
        
        # build calendar grid header
        header = " ".join(f"{d:^3}" for d in CalendarRenderer.WEEKDAYS)
        
        # build calendar grid
        grid_lines = [f"`{header}`"]
        for week in cal.monthdayscalendar(year, month):
            week_str = " ".join(f"{d:^3}" if d != 0 else "   " for d in week)
            grid_lines.append(f"`{week_str}`")
        
        embed.description = "\n".join(grid_lines)
        
        # group events by day
        events_by_day: Dict[int, List[Dict]] = {}
        for event in events:
            event_date = event.get("date")
            if isinstance(event_date, str):
                event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
            elif isinstance(event_date, date) and not isinstance(event_date, datetime):
                event_date = datetime.combine(event_date, datetime.min.time())
            
            if event_date and event_date.year == year and event_date.month == month:
                day = event_date.day
                if day not in events_by_day:
                    events_by_day[day] = []
                events_by_day[day].append(event)
        
        # add events section
        if events_by_day:
            event_text = []
            for day in sorted(events_by_day.keys()):
                day_events = events_by_day[day]
                for event in day_events:
                    title = event.get("title", "Untitled")[:40]
                    time_str = ""
                    event_date = event.get("date")
                    if isinstance(event_date, str):
                        event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                    if isinstance(event_date, datetime) and event_date.hour != 0:
                        time_str = f" @ {event_date.strftime('%H:%M')}"
                    
                    source = event.get("source", "")
                    source_icon = "📆" if source == "google" else "📚"
                    event_text.append(f"**{day}** {source_icon} {title}{time_str}")
            
            # split into chunks if too long
            chunk = "\n".join(event_text[:15])
            if len(event_text) > 15:
                chunk += f"\n*...and {len(event_text) - 15} more events*"
            
            embed.add_field(name="Events", value=chunk, inline=False)
        else:
            embed.add_field(name="Events", value="*No events this month*", inline=False)
        
        return embed
    
    @staticmethod
    def render_week_embed(start_date: date, events: List[Dict[str, Any]]) -> discord.Embed:
        """Render a week view with events"""
        end_date = start_date + timedelta(days=6)
        
        embed = discord.Embed(
            title=f"📅 Week of {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}",
            color=discord.Color.purple()
        )
        
        # group events by day
        events_by_day: Dict[date, List[Dict]] = {start_date + timedelta(days=i): [] for i in range(7)}
        
        for event in events:
            event_date = event.get("date")
            if isinstance(event_date, str):
                event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00")).date()
            elif isinstance(event_date, datetime):
                event_date = event_date.date()
            
            if event_date in events_by_day:
                events_by_day[event_date].append(event)
        
        # add each day as a field
        for day_date in sorted(events_by_day.keys()):
            day_name = day_date.strftime("%A, %b %d")
            day_events = events_by_day[day_date]
            
            if day_events:
                event_lines = []
                for event in sorted(day_events, key=lambda e: e.get("date", "")):
                    title = event.get("title", "Untitled")[:35]
                    time_str = ""
                    evt_date = event.get("date")
                    if isinstance(evt_date, str):
                        evt_date = datetime.fromisoformat(evt_date.replace("Z", "+00:00"))
                    if isinstance(evt_date, datetime) and evt_date.hour != 0:
                        time_str = f"`{evt_date.strftime('%H:%M')}` "
                    
                    source = event.get("source", "")
                    source_icon = "📆" if source == "google" else "📚"
                    event_lines.append(f"{time_str}{source_icon} {title}")
                
                value = "\n".join(event_lines[:5])
                if len(event_lines) > 5:
                    value += f"\n*+{len(event_lines) - 5} more*"
            else:
                value = "*No events*"
            
            embed.add_field(name=day_name, value=value, inline=False)
        
        return embed
    
        
        for ann in announcements[:10]:
            course = ann.get("course", "Unknown Course")
            title = ann.get("title", "Untitled")[:50]
            posted = ann.get("posted_at")
            
            if posted:
                if isinstance(posted, str):
                    posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                posted_str = posted.strftime("%b %d, %H:%M")
            else:
                posted_str = "Unknown"
            
            # truncate message
            message = ann.get("message", "")[:200]
            if len(ann.get("message", "")) > 200:
                message += "..."
            
            value = f"**{course}**\n{message}\n*Posted: {posted_str}*"
            embed.add_field(name=title, value=value, inline=False)
        
        if len(announcements) > 10:
            embed.set_footer(text=f"...and {len(announcements) - 10} more announcements")
        
        return embed
    
    @staticmethod
    def render_daily_summary_embed(
        google_events: List[Dict[str, Any]],
        days: int = 7
    ) -> discord.Embed:
        """Render daily summary for reminders"""
        embed = discord.Embed(
            title=f"📋 Your Next {days} Days",
            description=f"Here's what's coming up!",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Google Calendar events
        if google_events:
            event_lines = []
            for event in sorted(google_events, key=lambda e: e.get("date", ""))[:10]:
                event_date = event.get("date")
                if isinstance(event_date, str):
                    event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                
                date_str = event_date.strftime("%b %d") if event_date else "?"
                time_str = event_date.strftime("%H:%M") if event_date and event_date.hour != 0 else ""
                title = event.get("title", "Untitled")[:30]
                
                line = f"`{date_str}` {title}"
                if time_str:
                    line += f" @ {time_str}"
                event_lines.append(line)
            
            value = "\n".join(event_lines)
            if len(google_events) > 10:
                value += f"\n*...and {len(google_events) - 10} more*"
            embed.add_field(name="📆 Google Calendar", value=value, inline=False)
        else:
            embed.add_field(name="📆 Google Calendar", value="*No upcoming events*", inline=False)
        
        return embed

